"""FastAPI application: recorded sessions, laps and lap comparisons, plus the dashboard."""

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from raceengineer.analysis.car import CarSummary, summarize_car
from raceengineer.analysis.compare import Channels, compare_laps, lap_trace, summarize
from raceengineer.analysis.diagnosis import diagnose, lap_data
from raceengineer.analysis.laps import best_clean_lap, segment_laps
from raceengineer.api.schemas import (
    CarOut,
    ChannelsOut,
    ComparisonOut,
    LapOut,
    LapRef,
    NoteOut,
    SegmentOut,
    SessionLapsOut,
    SessionOut,
    TyreOut,
)
from raceengineer.domain.models import Lap, SessionRecord, TelemetrySample
from raceengineer.storage.sqlite import SqliteSessionRepository

STATIC_DIR = Path(__file__).parent / "static"


@dataclass(frozen=True, slots=True)
class _Session:
    record: SessionRecord
    samples: list[TelemetrySample]
    laps: list[Lap]


def create_app(db_path: Path, static_dir: Path | None = STATIC_DIR) -> FastAPI:
    app = FastAPI(title="RaceEngineerAI", version="0.1")

    def load(session_id: int) -> _Session:
        if not db_path.exists():
            raise HTTPException(404, f"No existe la sesión {session_id}")
        with SqliteSessionRepository(db_path) as repository:
            record = repository.get_session(session_id)
            if record is None:
                raise HTTPException(404, f"No existe la sesión {session_id}")
            samples = repository.load_samples(session_id)
        return _Session(record=record, samples=samples, laps=segment_laps(samples))

    @app.get("/api/sessions")
    def list_sessions() -> list[SessionOut]:
        if not db_path.exists():
            return []
        with SqliteSessionRepository(db_path) as repository:
            records = repository.list_sessions()
        return [_session_out(r) for r in reversed(records)]

    @app.get("/api/sessions/{session_id}/laps")
    def session_laps(session_id: int) -> SessionLapsOut:
        session = load(session_id)
        best = best_clean_lap(session.laps)
        return SessionLapsOut(
            session=_session_out(session.record),
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
        target_trace = lap_trace(target.samples, target_lap, target.record.info.track_length_m)
        reference_trace = lap_trace(
            reference.samples, reference_lap, reference.record.info.track_length_m
        )
        try:
            comparison = compare_laps(target_trace, reference_trace, step_m=step_m)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        segments = summarize(comparison)
        target_car = summarize_car(target.samples, target_lap)
        reference_car = summarize_car(reference.samples, reference_lap)
        notes = diagnose(
            lap_data(target.samples, target_lap, target_trace.length_m),
            lap_data(reference.samples, reference_lap, reference_trace.length_m),
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


def _finished_lap(session: _Session, number: int) -> Lap:
    lap = next((lap for lap in session.laps if lap.number == number), None)
    if lap is None or lap.time_ms is None:
        raise HTTPException(
            404,
            f"La vuelta {number} no existe o no está terminada en la sesión {session.record.id}",
        )
    return lap


def _session_out(record: SessionRecord) -> SessionOut:
    info = record.info
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
