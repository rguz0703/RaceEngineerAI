"""FastAPI application: recorded sessions, laps and lap comparisons, plus the dashboard."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from raceengineer.adapters.ac_shared_memory import GameProbe
from raceengineer.analysis import lap_index
from raceengineer.analysis.car import CarSummary, summarize_car
from raceengineer.analysis.compare import Channels, compare_laps, lap_trace, summarize
from raceengineer.analysis.diagnosis import diagnose, lap_data
from raceengineer.analysis.laps import best_clean_lap
from raceengineer.analysis.overview import overview
from raceengineer.api.schemas import (
    BestLapOut,
    CarOut,
    ChannelsOut,
    ComparisonOut,
    GameOut,
    LapOut,
    LapRef,
    NoteOut,
    OverviewOut,
    ProgressOut,
    RecordingOut,
    SegmentOut,
    SessionLapsOut,
    SessionOut,
    TotalsOut,
    TyreOut,
)
from raceengineer.capture.live import LiveFrame, ReferenceLap
from raceengineer.capture.service import RecordingService, RecordingState, RecordingStatus
from raceengineer.domain.models import Lap, SessionRecord, TelemetrySample
from raceengineer.storage.sqlite import SqliteSessionRepository

STATIC_DIR = Path(__file__).parent / "static"


@dataclass(frozen=True, slots=True)
class _Session:
    record: SessionRecord
    laps: list[Lap]


def create_app(
    db_path: Path,
    static_dir: Path | None = STATIC_DIR,
    recorder: RecordingService | None = None,
    probe: Callable[[], GameProbe] | None = None,
    live_hz: float = 20.0,
) -> FastAPI:
    """``recorder`` enables start/stop from the dashboard; ``probe`` reports the game's state."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if recorder is not None:
            # Closing the server finishes the recording cleanly (data is kept).
            recorder.stop(wait=True)

    app = FastAPI(title="RaceEngineerAI", version="0.1", lifespan=lifespan)

    def recording_out() -> RecordingOut:
        status = recorder.status() if recorder is not None else RecordingStatus()
        if status.state in (RecordingState.RECORDING, RecordingState.STOPPING):
            game = GameOut(state=status.game_status or "live", track="", car="", message="")
        elif probe is not None:
            found = probe()
            game = GameOut(
                state=found.state, track=found.track, car=found.car, message=found.message
            )
        else:
            game = GameOut(state="unavailable", track="", car="", message="")
        return RecordingOut(
            available=recorder is not None,
            state=status.state.value,
            session_id=status.session_id,
            started_at=status.started_at,
            sample_count=status.sample_count,
            lap=status.lap,
            lap_time_ms=status.lap_time_ms,
            last_lap_ms=status.last_lap_ms,
            best_lap_ms=status.best_lap_ms,
            speed_kmh=status.speed_kmh,
            in_pit=status.in_pit,
            message=status.message,
            last_session_id=status.last_session_id,
            game=game,
        )

    @app.websocket("/ws/live")
    async def live(ws: WebSocket) -> None:
        """Pushes the live frame ~20 times a second; the track outline only when it changes."""
        await ws.accept()
        sent_reference: tuple[str, int] | None = None
        try:
            while True:
                frame, reference = recorder.live() if recorder is not None else (None, None)
                status = recorder.status() if recorder is not None else RecordingStatus()
                message: dict[str, object] = {
                    "state": status.state.value,
                    "game": status.game_status,
                    "frame": _frame_out(frame) if frame is not None else None,
                }
                key = (reference.label, reference.time_ms) if reference is not None else None
                if key != sent_reference:
                    message["reference"] = _reference_out(reference)
                    sent_reference = key
                await ws.send_json(message)
                await asyncio.sleep(1 / live_hz)
        except WebSocketDisconnect:
            return

    @app.get("/api/recording")
    def recording_status() -> RecordingOut:
        return recording_out()

    @app.post("/api/recording/start")
    def recording_start() -> RecordingOut:
        if recorder is None:
            raise HTTPException(409, "Este servidor no puede grabar (se abrió sin grabadora)")
        recorder.start()
        return recording_out()

    @app.post("/api/recording/stop")
    def recording_stop() -> RecordingOut:
        if recorder is None:
            raise HTTPException(409, "Este servidor no puede grabar (se abrió sin grabadora)")
        recorder.stop(wait=True)
        return recording_out()

    def load(session_id: int) -> _Session:
        if not db_path.exists():
            raise HTTPException(404, f"No existe la sesión {session_id}")
        with SqliteSessionRepository(db_path) as repository:
            record = repository.get_session(session_id)
            if record is None:
                raise HTTPException(404, f"No existe la sesión {session_id}")
            return _Session(record=record, laps=lap_index.session_laps(repository, session_id))

    def load_lap(session: _Session, lap: Lap) -> tuple[list[TelemetrySample], Lap]:
        with SqliteSessionRepository(db_path) as repository:
            return lap_index.load_lap(repository, session.record.id, lap)

    @app.get("/api/sessions")
    def list_sessions() -> list[SessionOut]:
        return [_session_out(r, laps) for r, laps in reversed(all_sessions())]

    def all_sessions() -> list[tuple[SessionRecord, list[Lap]]]:
        if not db_path.exists():
            return []
        with SqliteSessionRepository(db_path) as repository:
            return [
                (r, lap_index.session_laps(repository, r.id)) for r in repository.list_sessions()
            ]

    @app.get("/api/overview")
    def home() -> OverviewOut:
        sessions = all_sessions()
        summary = overview(sessions)
        return OverviewOut(
            totals=TotalsOut.model_validate(summary.totals, from_attributes=True),
            best_laps=[_validated(BestLapOut, b) for b in summary.best_laps],
            progress=[_validated(ProgressOut, p) for p in summary.progress],
            recent=[_session_out(r, laps) for r, laps in reversed(sessions[-5:])],
        )

    @app.get("/api/sessions/{session_id}/laps")
    def session_laps(session_id: int) -> SessionLapsOut:
        session = load(session_id)
        best = best_clean_lap(session.laps)
        return SessionLapsOut(
            session=_session_out(session.record, session.laps),
            laps=[_lap_out(lap) for lap in session.laps],
            best_clean_lap=best.number if best else None,
        )

    @app.get("/api/compare")
    def compare(
        session: int,
        lap: int,
        ref_session: int | None = None,
        ref_lap: int | None = None,
        step_m: float = 5.0,
    ) -> ComparisonOut:
        if not 0.5 <= step_m <= 100:
            raise HTTPException(422, "step_m debe estar entre 0.5 y 100")
        target = load(session)
        reference = target if ref_session in (None, session) else load(ref_session)
        target_lap = _finished_lap(target, lap)
        if ref_lap is not None:
            reference_lap = _finished_lap(reference, ref_lap)
        else:
            exclude = target_lap if reference is target else None
            best = best_clean_lap(reference.laps, exclude)
            if best is None:
                raise HTTPException(404, "No hay vuelta de referencia terminada; elige una")
            reference_lap = best
        # Only the two laps' samples are read, whatever the session length.
        target_samples, target_lap = load_lap(target, target_lap)
        reference_samples, reference_lap = load_lap(reference, reference_lap)
        target_trace = lap_trace(target_samples, target_lap, target.record.info.track_length_m)
        reference_trace = lap_trace(
            reference_samples, reference_lap, reference.record.info.track_length_m
        )
        try:
            comparison = compare_laps(target_trace, reference_trace, step_m=step_m)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        segments = summarize(comparison)
        target_car = summarize_car(target_samples, target_lap)
        reference_car = summarize_car(reference_samples, reference_lap)
        notes = diagnose(
            lap_data(target_samples, target_lap, target_trace.length_m),
            lap_data(reference_samples, reference_lap, reference_trace.length_m),
            segments,
            target_car,
        )
        return ComparisonOut(
            target=LapRef(session_id=target.record.id, lap=lap, time_ms=target_lap.time_ms),
            reference=LapRef(
                session_id=reference.record.id,
                lap=reference_lap.number,
                time_ms=reference_lap.time_ms,
            ),
            partial=not (target_lap.complete and reference_lap.complete),
            distance_m=comparison.distance_m,
            delta_s=comparison.delta_s,
            target_channels=_channels_out(comparison.target),
            reference_channels=_channels_out(comparison.reference),
            track_x=[round(v, 1) for v in comparison.reference.pos_x],
            track_z=[round(v, 1) for v in comparison.reference.pos_z],
            segments=[SegmentOut.model_validate(s, from_attributes=True) for s in segments],
            target_car=_car_out(target_car, target.record.info.tyre_compound),
            reference_car=_car_out(reference_car, reference.record.info.tyre_compound),
            notes=[NoteOut.model_validate(n, from_attributes=True) for n in notes],
        )

    if static_dir is not None and (static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="dashboard")
    return app


def _frame_out(frame: LiveFrame) -> dict[str, object]:
    out: dict[str, object] = {}
    for name, value in asdict(frame).items():
        out[name] = round(value, 3) if isinstance(value, float) else value
    return out


def _reference_out(reference: ReferenceLap | None) -> dict[str, object] | None:
    if reference is None:
        return None
    xs, zs = reference.outline()
    return {
        "label": reference.label,
        "time_ms": reference.time_ms,
        "length_m": round(reference.distance_m[-1], 1),
        "x": [round(v, 1) for v in xs],
        "z": [round(v, 1) for v in zs],
    }


def _validated[M: BaseModel](model: type[M], value: object) -> M:
    """Build an API model from a dataclass (nested dataclasses included)."""
    return model.model_validate(value, from_attributes=True)


def _finished_lap(session: _Session, number: int) -> Lap:
    lap = next((lap for lap in session.laps if lap.number == number), None)
    if lap is None or lap.time_ms is None:
        raise HTTPException(
            404,
            f"La vuelta {number} no existe o no está terminada en la sesión {session.record.id}",
        )
    return lap


def _session_out(record: SessionRecord, laps: list[Lap]) -> SessionOut:
    info = record.info
    best = best_clean_lap(laps)
    return SessionOut(
        id=record.id,
        sim=info.sim,
        track=info.track,
        track_config=info.track_config,
        car=info.car,
        track_length_m=info.track_length_m,
        started_at=record.started_at,
        ended_at=record.ended_at,
        sample_count=record.sample_count,
        lap_count=sum(lap.time_ms is not None for lap in laps),
        best_lap_ms=best.time_ms if best else None,
    )


def _lap_out(lap: Lap) -> LapOut:
    return LapOut(
        number=lap.number,
        time_ms=lap.time_ms,
        official=lap.official,
        complete=lap.complete,
        out_lap=lap.out_lap,
        in_lap=lap.in_lap,
        off_track=lap.off_track,
    )


def _car_out(car: CarSummary | None, compound: str) -> CarOut | None:
    if car is None:
        return None
    return CarOut(
        tyre_compound=compound,
        tyres=[TyreOut.model_validate(t, from_attributes=True) for t in car.tyres],
        brake_bias=car.brake_bias,
        tc=car.tc,
        abs=car.abs,
        engine_brake=car.engine_brake,
        fuel_start_l=car.fuel_start_l,
        fuel_end_l=car.fuel_end_l,
    )


def _channels_out(channels: Channels) -> ChannelsOut:
    return ChannelsOut(
        speed_kmh=[round(v, 1) for v in channels.speed_kmh],
        throttle=[round(v, 3) for v in channels.throttle],
        brake=[round(v, 3) for v in channels.brake],
        gear=channels.gear,
    )
