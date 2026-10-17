"""Interfaces the core depends on; adapters implement them."""

from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Protocol

from raceengineer.domain.models import SessionInfo, SessionRecord, TelemetrySample


class TelemetrySource(Protocol):
    """A stream of normalized samples from a simulator, a replay or a generator.

    Live sources pace themselves (block until new data); offline sources yield
    as fast as they are consumed. The iterator ends when the source has no more
    data; live sources may also be stopped by the consumer.
    """

    def session_info(self) -> SessionInfo: ...

    def samples(self) -> Iterator[TelemetrySample]: ...


class SessionRepository(Protocol):
    """Persistence for recorded sessions."""

    def create_session(self, info: SessionInfo, started_at: datetime) -> int: ...

    def append_samples(self, session_id: int, samples: Sequence[TelemetrySample]) -> None:
        """Durably store samples, in order, after any already stored."""
        ...

    def finish_session(self, session_id: int, ended_at: datetime) -> None: ...

    def list_sessions(self) -> list[SessionRecord]: ...

    def load_samples(self, session_id: int) -> list[TelemetrySample]: ...
