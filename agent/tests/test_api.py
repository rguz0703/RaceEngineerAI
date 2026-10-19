from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from raceengineer.adapters.fake import FakeSource
from raceengineer.api.app import create_app
from raceengineer.capture.recorder import Recorder
from raceengineer.storage.sqlite import SqliteSessionRepository


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "s.sqlite"
    with SqliteSessionRepository(path) as repository:
        for seed in (1, 2):
            Recorder(
                FakeSource(laps=3, seed=seed),
                repository,
                clock=lambda: datetime(2026, 10, 17, tzinfo=UTC),
            ).record()
    return path


def _client(db: Path, static_dir: Path | None = None) -> TestClient:
    return TestClient(create_app(db, static_dir=static_dir))


def test_sessions_newest_first(db: Path) -> None:
    sessions = _client(db).get("/api/sessions").json()
    assert [s["id"] for s in sessions] == [2, 1]
    assert sessions[0]["lap_count"] == 2
    assert sessions[0]["best_lap_ms"] > 0
    assert sessions[0]["track"] == "synthetic_oval"
    assert sessions[0]["track_length_m"] == 2000.0
    assert sessions[0]["sample_count"] > 0


def test_sessions_without_database(tmp_path: Path) -> None:
    client = _client(tmp_path / "missing.sqlite")
    assert client.get("/api/sessions").json() == []
    assert client.get("/api/sessions/1/laps").status_code == 404


def test_session_laps(db: Path) -> None:
    body = _client(db).get("/api/sessions/1/laps").json()
    assert body["session"]["id"] == 1
    assert [lap["number"] for lap in body["laps"]] == [1, 2, 3]
    assert body["laps"][2]["time_ms"] is None
    assert body["best_clean_lap"] in (1, 2)


def test_compare_defaults_to_best_clean_lap(db: Path) -> None:
    body = _client(db).get("/api/compare", params={"session": 1, "lap": 2}).json()
    assert body["target"] == {"session_id": 1, "lap": 2, "time_ms": body["target"]["time_ms"]}
    assert body["reference"]["lap"] == 1
    assert body["partial"] is False
    n = len(body["distance_m"])
    assert n == len(body["delta_s"]) == len(body["target_channels"]["speed_kmh"])
    assert body["delta_s"][-1] == pytest.approx(
        (body["target"]["time_ms"] - body["reference"]["time_ms"]) / 1000, abs=1e-6
    )
    assert len(body["segments"]) == 10
    # The track map: the reference lap's path on the same grid, split by segment.
    assert len(body["track_x"]) == len(body["track_z"]) == n
    assert body["segments"][0]["start_index"] == 0
    assert body["segments"][-1]["end_index"] == n - 1
    for prev, cur in zip(body["segments"], body["segments"][1:], strict=False):
        assert cur["start_index"] == prev["end_index"]
    # The synthetic source has no tyre data; notes are still computed.
    assert body["target_car"] is None and body["reference_car"] is None
    assert isinstance(body["notes"], list)


def test_compare_across_sessions(db: Path) -> None:
    params = {"session": 1, "lap": 1, "ref_session": 2, "ref_lap": 2, "step_m": 20}
    body = _client(db).get("/api/compare", params=params).json()
    assert body["reference"] == {
        "session_id": 2,
        "lap": 2,
        "time_ms": body["reference"]["time_ms"],
    }
    assert body["distance_m"][1] - body["distance_m"][0] == 20


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"session": 9, "lap": 1}, 404),
        ({"session": 1, "lap": 3}, 404),
        ({"session": 1, "lap": 1, "ref_lap": 7}, 404),
        ({"session": 1, "lap": 1, "step_m": 0}, 422),
    ],
)
def test_compare_errors(db: Path, params: dict[str, int], status: int) -> None:
    response = _client(db).get("/api/compare", params=params)
    assert response.status_code == status
    assert response.json()["detail"]


def test_compare_without_reference_lap(tmp_path: Path) -> None:
    path = tmp_path / "one.sqlite"
    with SqliteSessionRepository(path) as repository:
        Recorder(FakeSource(laps=2), repository).record()
    response = _client(path).get("/api/compare", params={"session": 1, "lap": 1})
    assert response.status_code == 404
    assert "otra sesión" in response.json()["detail"]


def test_compare_laps_without_common_stretch(db: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import raceengineer.api.app as app_module

    def no_overlap(*_: object, **__: object) -> object:
        raise ValueError("Las vueltas no tienen tramo de pista en común")

    monkeypatch.setattr(app_module, "compare_laps", no_overlap)
    response = _client(db).get("/api/compare", params={"session": 1, "lap": 2})
    assert response.status_code == 422


def test_serves_dashboard_when_built(db: Path, tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>dashboard</h1>", encoding="utf-8")

    client = _client(db, static_dir=static)

    assert "dashboard" in client.get("/").text
    assert client.get("/api/sessions").status_code == 200


def test_session_record_times_are_iso(db: Path) -> None:
    started = _client(db).get("/api/sessions").json()[0]["started_at"]
    assert datetime.fromisoformat(started) == datetime(2026, 10, 17, tzinfo=UTC)


def test_overview(db: Path) -> None:
    body = _client(db).get("/api/overview").json()
    assert body["totals"] == {"sessions": 2, "laps": 4, "distance_km": 8.0}
    [best] = body["best_laps"]
    assert best["track"] == "synthetic_oval"
    assert len(body["progress"][0]["points"]) == 2
    assert [s["id"] for s in body["recent"]] == [2, 1]


def test_overview_without_database(tmp_path: Path) -> None:
    body = _client(tmp_path / "none.sqlite").get("/api/overview").json()
    assert body["totals"]["sessions"] == 0


def test_compare_falls_back_to_fastest_lap_without_clean_ones(tmp_path: Path) -> None:
    from dataclasses import replace

    path = tmp_path / "dirty.sqlite"
    samples = [replace(s, tyres_out=4) for s in FakeSource(laps=3).samples()]
    with SqliteSessionRepository(path) as repository:
        sid = repository.create_session(FakeSource().session_info(), datetime.now(UTC))
        repository.append_samples(sid, samples)

    body = _client(path).get("/api/compare", params={"session": sid, "lap": 2}).json()

    assert body["reference"]["lap"] == 1
    assert body["reference_clean"] is False
