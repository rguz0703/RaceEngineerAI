from datetime import UTC, datetime

import pytest

from raceengineer.adapters.fake import FakeSource
from raceengineer.analysis.lap_index import load_lap, session_laps
from raceengineer.analysis.laps import segment_laps
from raceengineer.domain.models import SessionInfo, TelemetrySample
from raceengineer.storage.sqlite import SqliteSessionRepository

INFO = SessionInfo("fake", "t", "c")
START = datetime(2026, 10, 18, tzinfo=UTC)


@pytest.fixture
def repo() -> SqliteSessionRepository:
    return SqliteSessionRepository(":memory:")


def _session(repo: SqliteSessionRepository, laps: int = 3) -> tuple[int, list[TelemetrySample]]:
    samples = list(FakeSource(laps=laps).samples())
    sid = repo.create_session(INFO, START)
    repo.append_samples(sid, samples)
    return sid, samples


def test_lap_signals_match_full_samples(repo: SqliteSessionRepository) -> None:
    sid, samples = _session(repo)
    signals = repo.load_lap_signals(sid)
    assert len(signals) == len(samples)
    assert segment_laps(signals) == segment_laps(repo.load_samples(sid))


def test_session_laps_builds_index_once(
    repo: SqliteSessionRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid, _ = _session(repo)
    assert repo.load_laps(sid) is None

    laps = session_laps(repo, sid)

    assert repo.load_laps(sid) == laps
    monkeypatch.setattr(repo, "load_lap_signals", lambda _: pytest.fail("index not used"))
    assert session_laps(repo, sid) == laps


def test_index_goes_stale_when_samples_are_added(repo: SqliteSessionRepository) -> None:
    sid, samples = _session(repo, laps=2)
    session_laps(repo, sid)
    repo.append_samples(sid, samples[:5])
    assert repo.load_laps(sid) is None
    assert repo.load_laps(999) is None


def test_load_lap_reads_only_that_lap(repo: SqliteSessionRepository) -> None:
    sid, samples = _session(repo)
    second = session_laps(repo, sid)[1]

    lap_samples, local = load_lap(repo, sid, second)

    assert lap_samples == samples[second.start : second.end]
    assert (local.start, local.end, local.number) == (0, len(lap_samples), 2)


def test_load_samples_range(repo: SqliteSessionRepository) -> None:
    sid, samples = _session(repo, laps=1)
    assert repo.load_samples(sid, 10, 20) == samples[10:20]
    assert repo.load_samples(sid, 10) == samples[10:]


def test_saving_again_replaces_laps(repo: SqliteSessionRepository) -> None:
    sid, _ = _session(repo)
    laps = session_laps(repo, sid)
    repo.save_laps(sid, laps[:1])
    assert repo.load_laps(sid) == laps[:1]
