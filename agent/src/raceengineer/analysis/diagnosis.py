"""Rule-based notes on why a lap lost time against a reference, segment by segment.

Every rule compares measurable things (pedals, speeds, wheel slip, rotation) and
the notes say what was observed and what might explain it. They are suggestions:
with a couple of laps a driving mistake and a setup problem can look alike.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from statistics import median

from raceengineer.analysis.car import WHEEL_NAMES, WHEELS, CarSummary, tyre_hints
from raceengineer.analysis.compare import SegmentSummary, lap_distances
from raceengineer.domain.models import Lap, TelemetrySample

LOSING_S = 0.05
"""Segments losing more than this get the comparative notes."""
LOCK_RATIO = -0.2
SPIN_RATIO = 0.15
MIN_EVENT_S = 0.1
BRAKE_ON = 0.3
FULL_THROTTLE = 0.9
BRAKE_POINT_M = 10.0
MIN_SPEED_KMH = 5.0
THROTTLE_POINT_M = 15.0
COASTING_M = 20.0
BALANCE_CHANGE = 0.15


@dataclass(frozen=True, slots=True)
class Note:
    segment: int | None
    """0-based segment index, or None for the whole lap."""
    topic: str
    """frenada, tracción, velocidad, aceleración, inercia, equilibrio, pista, neumáticos."""
    severity: str
    """"warn" for what likely costs time or risks the car, "info" otherwise."""
    text: str


@dataclass(frozen=True, slots=True)
class LapData:
    samples: list[TelemetrySample]
    distance_m: list[float]

    def window(self, start_m: float, end_m: float) -> list[tuple[float, TelemetrySample]]:
        return [
            (d, s)
            for d, s in zip(self.distance_m, self.samples, strict=True)
            if start_m <= d <= end_m
        ]


def lap_data(samples: Sequence[TelemetrySample], lap: Lap, length_m: float) -> LapData:
    lap_samples = list(samples[lap.start : lap.end])
    return LapData(lap_samples, lap_distances(lap_samples, length_m))


def diagnose(
    target: LapData,
    reference: LapData,
    segments: Sequence[SegmentSummary],
    car: CarSummary | None = None,
) -> list[Note]:
    notes: list[Note] = []
    understeer_segments = 0
    for i, seg in enumerate(segments):
        t = target.window(seg.start_m, seg.end_m)
        r = reference.window(seg.start_m, seg.end_m)
        if not t or not r:
            continue
        notes += _off_track(i, t)
        notes += _lockups(i, t, r)
        notes += _wheelspin(i, t, r)
        if seg.delta_s > LOSING_S:
            notes += _braking_point(i, t, r)
            notes += _min_speed(i, t, r)
            notes += _throttle_point(i, t, r)
            notes += _coasting(i, t, r)
            balance = _balance(i, t, r)
            # Understeer is the balance note flagged as a warning.
            understeer_segments += any(n.severity == "warn" for n in balance)
            notes += balance
    notes += _lap_notes(understeer_segments, car)
    return notes


def _off_track(i: int, t: list[tuple[float, TelemetrySample]]) -> list[Note]:
    worst = max(s.tyres_out for _, s in t)
    if worst < 3:
        return []
    return [Note(i, "pista", "warn", f"Saliste de los límites de pista con {worst} ruedas.")]


def _lockups(
    i: int, t: list[tuple[float, TelemetrySample]], r: list[tuple[float, TelemetrySample]]
) -> list[Note]:
    notes = []
    for wheel in WHEELS:

        def locked(s: TelemetrySample, w: str = wheel) -> bool:
            return s.brake > 0.2 and float(getattr(s, f"slip_ratio_{w}")) < LOCK_RATIO

        duration = _longest_run(t, locked)
        if duration >= MIN_EVENT_S:
            also = "" if _longest_run(r, locked) >= MIN_EVENT_S else " (en la referencia, no)"
            notes.append(
                Note(
                    i,
                    "frenada",
                    "warn",
                    f"Bloqueaste la {WHEEL_NAMES[wheel]} al frenar ({duration:.1f} s){also}.",
                )
            )
    return notes


def _wheelspin(
    i: int, t: list[tuple[float, TelemetrySample]], r: list[tuple[float, TelemetrySample]]
) -> list[Note]:
    notes = []
    for axle, wheels in (("delanteras", ("fl", "fr")), ("traseras", ("rl", "rr"))):

        def spinning(s: TelemetrySample, ws: tuple[str, ...] = wheels) -> bool:
            return s.throttle > 0.5 and any(
                float(getattr(s, f"slip_ratio_{w}")) > SPIN_RATIO for w in ws
            )

        duration = _longest_run(t, spinning)
        if duration >= 1.5 * MIN_EVENT_S:
            also = (
                "" if _longest_run(r, spinning) >= 1.5 * MIN_EVENT_S else " (en la referencia, no)"
            )
            notes.append(
                Note(
                    i,
                    "tracción",
                    "warn",
                    f"Las {axle} patinaron al acelerar ({duration:.1f} s){also}: "
                    "acelera más progresivo o sube el control de tracción.",
                )
            )
    return notes


def _braking_point(
    i: int, t: list[tuple[float, TelemetrySample]], r: list[tuple[float, TelemetrySample]]
) -> list[Note]:
    tb = _first_distance(t, lambda s: s.brake >= BRAKE_ON)
    rb = _first_distance(r, lambda s: s.brake >= BRAKE_ON)
    if tb is None or rb is None or abs(tb - rb) < BRAKE_POINT_M:
        return []
    if tb < rb:
        text = f"Empezaste a frenar {rb - tb:.0f} m antes que en la referencia."
    else:
        text = f"Frenaste {tb - rb:.0f} m más tarde que en la referencia (¿te pasaste de frenada?)."
    return [Note(i, "frenada", "warn", text)]


def _min_speed(
    i: int, t: list[tuple[float, TelemetrySample]], r: list[tuple[float, TelemetrySample]]
) -> list[Note]:
    diff = min(s.speed_kmh for _, s in t) - min(s.speed_kmh for _, s in r)
    if diff > -MIN_SPEED_KMH:
        return []
    return [
        Note(
            i,
            "velocidad",
            "warn",
            f"Tu velocidad mínima fue {-diff:.0f} km/h más baja que en la referencia.",
        )
    ]


def _throttle_point(
    i: int, t: list[tuple[float, TelemetrySample]], r: list[tuple[float, TelemetrySample]]
) -> list[Note]:
    def pickup(window: list[tuple[float, TelemetrySample]]) -> float | None:
        slowest = min(range(len(window)), key=lambda k: window[k][1].speed_kmh)
        return _first_distance(window[slowest:], lambda s: s.throttle >= FULL_THROTTLE)

    tp, rp = pickup(t), pickup(r)
    if tp is None or rp is None or tp - rp < THROTTLE_POINT_M:
        return []
    return [
        Note(
            i,
            "aceleración",
            "warn",
            f"Aceleraste a fondo {tp - rp:.0f} m más tarde que en la referencia "
            "al salir de la curva.",
        )
    ]


def _coasting(
    i: int, t: list[tuple[float, TelemetrySample]], r: list[tuple[float, TelemetrySample]]
) -> list[Note]:
    def meters(window: list[tuple[float, TelemetrySample]]) -> float:
        total = 0.0
        for (d0, s0), (d1, _) in pairwise(window):
            if s0.throttle < 0.1 and s0.brake < 0.1 and s0.speed_kmh > 40:
                total += d1 - d0
        return total

    tm, rm = meters(t), meters(r)
    if tm - rm < COASTING_M:
        return []
    return [
        Note(
            i,
            "inercia",
            "info",
            f"Fuiste {tm:.0f} m sin acelerar ni frenar (en la referencia, {rm:.0f} m).",
        )
    ]


def _balance(
    i: int, t: list[tuple[float, TelemetrySample]], r: list[tuple[float, TelemetrySample]]
) -> list[Note]:
    """Steering needed per unit of rotation: more means the car turned less (understeer)."""

    def effort(window: list[tuple[float, TelemetrySample]]) -> float | None:
        values = [
            abs(s.steering) * s.speed_kmh / abs(s.yaw_rate)
            for _, s in window
            if abs(s.yaw_rate) > 0.15 and s.speed_kmh > 50 and abs(s.steering) > 0.03
        ]
        return median(values) if len(values) >= 5 else None

    te, re = effort(t), effort(r)
    if te is None or re is None:
        return []
    change = te / re - 1
    if change > BALANCE_CHANGE:
        return [
            Note(
                i,
                "equilibrio",
                "warn",
                f"Necesitaste un {change:.0%} más de volante para girar lo mismo: "
                "el coche subviró más que en la referencia.",
            )
        ]
    if change < -BALANCE_CHANGE:
        return [
            Note(
                i,
                "equilibrio",
                "info",
                f"El coche giró con un {-change:.0%} menos de volante que en la referencia: "
                "más rotación o sobreviraje (¿correcciones?).",
            )
        ]
    return []


def _lap_notes(understeer_segments: int, car: CarSummary | None) -> list[Note]:
    notes = []
    if car is not None:
        notes += [Note(None, "neumáticos", "info", h.text) for h in tyre_hints(car)]
    if understeer_segments >= 2:
        causes = "presión o caída de las delanteras"
        if car is not None:
            front = [t for t in car.tyres if t.wheel in ("fl", "fr")]
            pressure = sum(t.pressure_psi for t in front) / 2
            causes = (
                f"la presión delantera ({pressure:.1f} psi), la caída de las delanteras o un "
                f"reparto de frenada muy adelantado ({car.brake_bias:.0%})"
            )
        notes.append(
            Note(
                None,
                "equilibrio",
                "warn",
                f"Subviraje en {understeer_segments} tramos. Si no es por entrar demasiado rápido, "
                f"revisa {causes}.",
            )
        )
    return notes


def _longest_run(
    window: list[tuple[float, TelemetrySample]], condition: Callable[[TelemetrySample], bool]
) -> float:
    """Longest stretch, in seconds, where the condition holds on consecutive samples."""
    if len(window) < 2:
        return 0.0
    step = median(b.t - a.t for (_, a), (_, b) in pairwise(window))
    best = 0.0
    run_start: float | None = None
    last_t = 0.0
    for _, s in window:
        if condition(s):
            if run_start is None:
                run_start = s.t
            last_t = s.t
            best = max(best, last_t - run_start + step)
        else:
            run_start = None
    return best


def _first_distance(
    window: list[tuple[float, TelemetrySample]], condition: Callable[[TelemetrySample], bool]
) -> float | None:
    return next((d for d, s in window if condition(s)), None)
