"""Records a telemetry source into a session repository."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event

from raceengineer.domain.models import TelemetrySample
from raceengineer.domain.ports import SessionRepository, TelemetrySource


@dataclass(frozen=True, slots=True)
class RecordingResult:
    session_id: int
    sample_count: int


class Recorder:
    """Streams samples from a source into storage in batches.

    Samples are flushed every `batch_size` samples and again when recording
    stops for any reason (end of data, stop event, or an exception), so at most
    one partial batch can be lost if the process is killed outright.
    """

    def __init__(
        self,
        source: TelemetrySource,
        repository: SessionRepository,
        batch_size: int = 60,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self._source = source
        self._repository = repository
        self._batch_size = batch_size
        self._clock = clock

    def record(
        self,
        stop: Event | None = None,
        on_sample: Callable[[TelemetrySample], None] | None = None,
        on_start: Callable[[int], None] | None = None,
    ) -> RecordingResult:
        """Record until the source ends or ``stop`` is set.

        ``on_start`` gets the new session id; ``on_sample`` sees every sample
        (for live status), so it must be quick.
        """
        session_id = self._repository.create_session(self._source.session_info(), self._clock())
        if on_start is not None:
            on_start(session_id)
        batch: list[TelemetrySample] = []
        count = 0
        try:
            for sample in self._source.samples():
                batch.append(sample)
                count += 1
                if on_sample is not None:
                    on_sample(sample)
                if len(batch) >= self._batch_size:
                    self._repository.append_samples(session_id, batch)
                    batch = []
                if stop is not None and stop.is_set():
                    break
        finally:
            self._repository.append_samples(session_id, batch)
            self._repository.finish_session(session_id, self._clock())
        return RecordingResult(session_id=session_id, sample_count=count)
