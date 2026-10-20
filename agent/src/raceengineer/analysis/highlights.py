"""The key moments of one lap: fastest point, hardest braking, slowest corners, incidents."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from raceengineer.analysis.car import WHEEL_NAMES, WHEELS
from raceengineer.analysis.compare import lap_distances
from raceengineer.analysis.diagnosis import LOCK_RATIO, MIN_EVENT_S, SPIN_RATIO
from raceengineer.analysis.laps import OFF_TRACK_TYRES
from raceengineer.domain.models import TelemetrySample

G = 9.81
DECEL_WINDOW_S = 0.25
"""Speed change is measured over this window, which smooths out sample noise."""
CORNER_SPACING_M = 150.0
"""Two slow points closer than this belong to the same corner."""
CORNERS = 3
MAP_POINTS = 300


@dataclass(frozen=True, slots=True)
class Moment:
    kind: str
    """top_speed, braking, corner, off_track, lockup, wheelspin."""
    title: str
    value: str
    detail: str
    distance_m: float
    pos_x: float
    pos_z: float
    warn: bool = False


@dataclass(frozen=True, slots=True)
class LapStats:
    full_throttle_pct: float
    braking_pct: float
    coasting_pct: float
    avg_speed_kmh: float
    max_rpm: float
    gear_changes: int


@dataclass(frozen=True, slots=True)
class LapHighlights:
    moments: list[Moment]
    stats: LapStats
    path_x: list[float]
    path_z: list[float]


def lap_highlights(samples: Sequence[TelemetrySample], length_m: float) -> LapHighlights:
    """``samples`` is one lap, in order."""
    if len(samples) < 3:
        raise ValueError("La vuelta tiene muy pocas muestras")
    distance = lap_distances(samples, length_m)
    moments: list[Moment] = []

    def at(i: int, kind: str, title: str, value: str, detail: str, warn: bool = False) -> Moment:
        s = samples[i]
        return Moment(kind, title, value, detail, round(distance[i]), s.pos_x, s.pos_z, warn)

    top = max(range(len(samples)), key=lambda i: samples[i].speed_kmh)
    moments.append(
        at(
            top,
            "top_speed",
            "Velocidad máxima",
            f"{samples[top].speed_kmh:.0f} km/h",
            f"en {samples[top].gear}ª, a {distance[top]:.0f} m",
        )
    )

    braking = _hardest_braking(samples)
    if braking is not None:
        start, g, entry, exit_ = braking
        moments.append(
            at(
                start,
                "braking",
                "Frenada más fuerte",
                f"{g:.1f} G",
                f"de {entry:.0f} a {exit_:.0f} km/h, empieza a {distance[start]:.0f} m",
            )
        )

    for i in _slowest_corners(samples, distance):
        moments.append(
            at(
                i,
                "corner",
                "Curva lenta",
                f"{samples[i].speed_kmh:.0f} km/h",
                f"en {samples[i].gear}ª, a {distance[i]:.0f} m",
            )
        )

    for start, end in _runs(samples, lambda s: s.tyres_out >= OFF_TRACK_TYRES):
        wheels = max(s.tyres_out for s in samples[start:end])
        moments.append(
            at(
                start,
                "off_track",
                "Fuera de pista",
                f"{wheels} ruedas",
                f"{_duration(samples, start, end):.1f} s, a {distance[start]:.0f} m",
                warn=True,
            )
        )
    for wheel in WHEELS:

        def locked(s: TelemetrySample, w: str = wheel) -> bool:
            return s.brake > 0.2 and float(getattr(s, f"slip_ratio_{w}")) < LOCK_RATIO

        for start, end in _runs(samples, locked, MIN_EVENT_S):
            moments.append(
                at(
                    start,
                    "lockup",
                    "Bloqueo",
                    WHEEL_NAMES[wheel],
                    f"{_duration(samples, start, end):.1f} s, a {distance[start]:.0f} m",
                    warn=True,
                )
            )

    def spinning(s: TelemetrySample) -> bool:
        return s.throttle > 0.5 and any(
            float(getattr(s, f"slip_ratio_{w}")) > SPIN_RATIO for w in WHEELS
        )

    for start, end in _runs(samples, spinning, 1.5 * MIN_EVENT_S):
        moments.append(
            at(
                start,
                "wheelspin",
                "Patinada al acelerar",
                f"{_duration(samples, start, end):.1f} s",
                f"a {distance[start]:.0f} m",
                warn=True,
            )
        )

    step = max(1, len(samples) // MAP_POINTS)
    return LapHighlights(
        moments=moments,
        stats=_stats(samples),
        path_x=[round(s.pos_x, 1) for s in samples[::step]],
        path_z=[round(s.pos_z, 1) for s in samples[::step]],
    )


def _hardest_braking(
    samples: Sequence[TelemetrySample],
) -> tuple[int, float, float, float] | None:
    """(start index, peak G, entry km/h, minimum km/h) of the hardest stop."""
    best: tuple[int, float, float, float] | None = None
    for start, end in _runs(samples, lambda s: s.brake > 0.3):
        peak_g = 0.0
        j = start
        for i in range(start, end):
            while j < i and samples[i].t - samples[j].t > DECEL_WINDOW_S:
                j += 1
            dt = samples[i].t - samples[j].t
            if dt <= 0:
                continue
            g = (samples[j].speed_kmh - samples[i].speed_kmh) / 3.6 / dt / G
            peak_g = max(peak_g, g)
        if peak_g > 0 and (best is None or peak_g > best[1]):
            low = min(s.speed_kmh for s in samples[start : min(end + 1, len(samples))])
            best = (start, peak_g, samples[start].speed_kmh, low)
    return best


def _slowest_corners(samples: Sequence[TelemetrySample], distance: list[float]) -> list[int]:
    """Indexes of the slowest local speed minima, at least CORNER_SPACING_M apart."""
    minima = [
        i
        for i in range(1, len(samples) - 1)
        if samples[i].speed_kmh <= samples[i - 1].speed_kmh
        and samples[i].speed_kmh <= samples[i + 1].speed_kmh
        and not samples[i].in_pit
        and samples[i].speed_kmh > 20
    ]
    chosen: list[int] = []
    for i in sorted(minima, key=lambda k: samples[k].speed_kmh):
        if all(abs(distance[i] - distance[c]) >= CORNER_SPACING_M for c in chosen):
            chosen.append(i)
        if len(chosen) == CORNERS:
            break
    return sorted(chosen, key=lambda k: distance[k])


def _runs(
    samples: Sequence[TelemetrySample],
    condition: Callable[[TelemetrySample], bool],
    min_s: float = 0.0,
) -> list[tuple[int, int]]:
    """[start, end) index ranges where the condition holds for at least ``min_s``."""
    runs = []
    start: int | None = None
    for i, s in enumerate([*samples, None]):
        if s is not None and condition(s):
            if start is None:
                start = i
        elif start is not None:
            if _duration(samples, start, i) >= min_s:
                runs.append((start, i))
            start = None
    return runs


def _duration(samples: Sequence[TelemetrySample], start: int, end: int) -> float:
    """Seconds covered by samples[start:end], counting one sample interval."""
    last = samples[end - 1]
    step = samples[min(end, len(samples) - 1)].t - last.t if end < len(samples) else 0.0
    return last.t - samples[start].t + max(step, 0.0)


def _stats(samples: Sequence[TelemetrySample]) -> LapStats:
    total = samples[-1].t - samples[0].t or 1.0

    def share(condition: Callable[[TelemetrySample], bool]) -> float:
        time = sum(b.t - a.t for a, b in pairwise(samples) if condition(a))
        return round(100 * time / total, 1)

    gears = [s.gear for s in samples if s.gear > 0]
    changes = sum(1 for a, b in pairwise(gears) if a != b)
    return LapStats(
        full_throttle_pct=share(lambda s: s.throttle > 0.95),
        braking_pct=share(lambda s: s.brake > 0.1),
        coasting_pct=share(lambda s: s.throttle < 0.1 and s.brake < 0.1 and s.speed_kmh > 40),
        avg_speed_kmh=round(sum(s.speed_kmh for s in samples) / len(samples), 1),
        max_rpm=max(s.rpm for s in samples),
        gear_changes=changes,
    )
