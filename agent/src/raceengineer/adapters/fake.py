"""Deterministic synthetic telemetry for development and tests without a simulator."""

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass

from raceengineer.domain.models import SessionInfo, TelemetrySample


@dataclass(frozen=True, slots=True)
class Corner:
    position: float
    """Apex position along the lap, 0.0 to 1.0."""
    min_speed_kmh: float
    half_width: float
    """Fraction of the lap over which the car slows down into / speeds up out of the apex."""
    direction: int
    """-1 left, 1 right."""


DEFAULT_CORNERS = (
    Corner(position=0.20, min_speed_kmh=90.0, half_width=0.05, direction=1),
    Corner(position=0.45, min_speed_kmh=140.0, half_width=0.04, direction=-1),
    Corner(position=0.70, min_speed_kmh=70.0, half_width=0.06, direction=1),
)

_GEAR_TOP_SPEEDS_KMH = (60.0, 95.0, 130.0, 165.0, 200.0, 250.0)
_IDLE_RPM = 2500.0
_MAX_RPM = 8000.0


class FakeSource:
    """Drives a fixed number of laps around a synthetic circular track.

    Speed follows a target profile shaped by the corners; each lap is scaled by
    a small seeded random factor so laps differ slightly but runs are reproducible.
    """

    def __init__(
        self,
        laps: int = 3,
        rate_hz: float = 60.0,
        track_length_m: float = 2000.0,
        max_speed_kmh: float = 240.0,
        corners: tuple[Corner, ...] = DEFAULT_CORNERS,
        seed: int = 0,
    ) -> None:
        if laps < 1:
            raise ValueError("laps must be >= 1")
        if rate_hz <= 0:
            raise ValueError("rate_hz must be > 0")
        self._laps = laps
        self._dt = 1.0 / rate_hz
        self._track_length_m = track_length_m
        self._max_speed_kmh = max_speed_kmh
        self._corners = corners
        self._seed = seed

    def session_info(self) -> SessionInfo:
        return SessionInfo(sim="fake", track="synthetic_oval", car="fake_gt3")

    def samples(self) -> Iterator[TelemetrySample]:
        rng = random.Random(self._seed)
        lap_factor = 1.0 + rng.uniform(-0.02, 0.02)
        radius = self._track_length_m / (2 * math.pi)
        t = 0.0
        lap = 0
        lap_start_t = 0.0
        pos = 0.0

        while lap < self._laps:
            speed = self._target_speed(pos) * lap_factor
            throttle, brake = self._pedals(pos)
            gear = _gear_for(speed)
            angle = 2 * math.pi * pos
            yield TelemetrySample(
                t=t,
                lap_number=lap,
                lap_time_ms=round((t - lap_start_t) * 1000),
                normalized_position=pos,
                speed_kmh=speed,
                throttle=throttle,
                brake=brake,
                clutch=0.0,
                steering=self._steering(pos),
                gear=gear,
                rpm=_rpm_for(speed, gear),
                pos_x=radius * math.cos(angle),
                pos_y=0.0,
                pos_z=radius * math.sin(angle),
                in_pit=False,
            )

            t += self._dt
            pos += (speed / 3.6) * self._dt / self._track_length_m
            if pos >= 1.0:
                pos -= 1.0
                lap += 1
                lap_start_t = t
                lap_factor = 1.0 + rng.uniform(-0.02, 0.02)

    def _target_speed(self, pos: float) -> float:
        speed = self._max_speed_kmh
        for corner in self._corners:
            closeness = _distance(pos, corner.position) / corner.half_width
            if closeness < 1.0:
                corner_speed = (
                    corner.min_speed_kmh + (self._max_speed_kmh - corner.min_speed_kmh) * closeness
                )
                speed = min(speed, corner_speed)
        return speed

    def _pedals(self, pos: float) -> tuple[float, float]:
        step = 0.001
        delta = self._target_speed((pos + step) % 1.0) - self._target_speed(pos)
        if delta < -0.5:
            return 0.0, min(1.0, -delta / 10.0)
        if delta > 0.5:
            return 1.0, 0.0
        return self._target_speed(pos) / self._max_speed_kmh, 0.0

    def _steering(self, pos: float) -> float:
        for corner in self._corners:
            closeness = _distance(pos, corner.position) / corner.half_width
            if closeness < 1.0:
                return corner.direction * (1.0 - closeness) * 0.6
        return 0.0


def _distance(a: float, b: float) -> float:
    """Shortest distance between two lap positions, wrapping at the start line."""
    d = abs(a - b) % 1.0
    return min(d, 1.0 - d)


def _gear_for(speed_kmh: float) -> int:
    for gear, top in enumerate(_GEAR_TOP_SPEEDS_KMH, start=1):
        if speed_kmh <= top:
            return gear
    return len(_GEAR_TOP_SPEEDS_KMH)


def _rpm_for(speed_kmh: float, gear: int) -> float:
    top = _GEAR_TOP_SPEEDS_KMH[gear - 1]
    bottom = _GEAR_TOP_SPEEDS_KMH[gear - 2] if gear > 1 else 0.0
    fraction = (speed_kmh - bottom) / (top - bottom)
    return _IDLE_RPM + (_MAX_RPM - _IDLE_RPM) * min(1.0, max(0.0, fraction))
