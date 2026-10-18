"""Replays a source at the pace of its own timestamps, as if it were live."""

import time
from collections.abc import Callable, Iterator
from threading import Event

from raceengineer.domain.models import SessionInfo, TelemetrySample
from raceengineer.domain.ports import TelemetrySource


class RealtimeSource:
    """Wraps an offline source (fake data, a dump) so it plays in real time.

    Used for the dashboard's demo mode and to try live features without the game.
    """

    def __init__(
        self,
        source: TelemetrySource,
        stop: Event | None = None,
        speed: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], object] | None = None,
    ) -> None:
        if speed <= 0:
            raise ValueError("speed must be > 0")
        self._source = source
        self._stop = stop if stop is not None else Event()
        self._speed = speed
        self._clock = clock
        # Waiting on the stop event lets a stop interrupt long gaps immediately.
        self._wait = wait if wait is not None else self._stop.wait

    def session_info(self) -> SessionInfo:
        return self._source.session_info()

    def samples(self) -> Iterator[TelemetrySample]:
        start: float | None = None
        for sample in self._source.samples():
            if self._stop.is_set():
                return
            if start is None:
                start = self._clock() - sample.t / self._speed
            delay = start + sample.t / self._speed - self._clock()
            if delay > 0:
                self._wait(delay)
                if self._stop.is_set():
                    return
            yield sample
