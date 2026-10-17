from collections.abc import Iterator
from datetime import UTC, datetime
from threading import Event

import pytest

from raceengineer.adapters.fake import FakeSource
from raceengineer.capture.recorder import Recorder
from raceengineer.domain.models import SessionInfo, TelemetrySample
from raceengineer.storage.sqlite import SqliteSessionRepository

FIXED_TIME = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class FailingSource:
    """Yields some samples from a FakeSource, then raises like a crashed simulator."""

    def __init__(self, fail_after: int) -> None:
        self._inner = FakeSource(laps=1)
        self._fail_after = fail_after

    def session_info(self) -> SessionInfo:
        return self._inner.session_info()

    def samples(self) -> Iterator[TelemetrySample]:
        for i, sample in enumerate(self._inner.samples()):
            if i == self._fail_after:
                raise ConnectionError("simulator closed")
            yield sample


def test_records_every_sample_and_finishes_session() -> None:
    source = FakeSource(laps=1)
    expected = list(source.samples())
    with SqliteSessionRepository(":memory:") as repo:
        result = Recorder(source, repo, batch_size=50, clock=lambda: FIXED_TIME).record()

        assert result.sample_count == len(expected)
        assert repo.load_samples(result.session_id) == expected
        [record] = repo.list_sessions()
        assert record.info == source.session_info()
        assert record.ended_at == FIXED_TIME


def test_keeps_samples_received_before_a_source_failure() -> None:
    with SqliteSessionRepository(":memory:") as repo:
        with pytest.raises(ConnectionError):
            Recorder(FailingSource(fail_after=125), repo, batch_size=50).record()

        [record] = repo.list_sessions()
        assert record.sample_count == 125
        assert record.ended_at is not None


def test_stop_event_ends_recording_early() -> None:
    stop = Event()
    stop.set()
    with SqliteSessionRepository(":memory:") as repo:
        result = Recorder(FakeSource(laps=1), repo).record(stop=stop)

        assert result.sample_count == 1
        assert len(repo.load_samples(result.session_id)) == 1


def test_rejects_invalid_batch_size() -> None:
    with SqliteSessionRepository(":memory:") as repo, pytest.raises(ValueError):
        Recorder(FakeSource(), repo, batch_size=0)
