"""What the car and its tyres were doing over a lap, and what the tyre temperatures suggest."""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from raceengineer.domain.models import Lap, TelemetrySample

WHEELS = ("fl", "fr", "rl", "rr")
WHEEL_NAMES = {
    "fl": "delantera izquierda",
    "fr": "delantera derecha",
    "rl": "trasera izquierda",
    "rr": "trasera derecha",
}

_ON_TRACK_KMH = 30.0

# Rules of thumb for reading tyre temperatures across the tread. They are
# generic (not per car or compound), so the advice is phrased as a suggestion.
PRESSURE_SPREAD_C = 4.0
"""Middle hotter/cooler than the edges' average by more than this hints at pressure."""
CAMBER_MIN_C = 2.0
CAMBER_MAX_C = 12.0
"""Inner edge usually runs a few degrees hotter than the outer with negative camber."""


@dataclass(frozen=True, slots=True)
class TyreState:
    wheel: str
    pressure_psi: float
    temp_inner_c: float
    temp_middle_c: float
    temp_outer_c: float


@dataclass(frozen=True, slots=True)
class CarSummary:
    """Averages over the part of the lap driven on track."""

    tyres: list[TyreState]
    brake_bias: float
    tc: float
    abs: float
    engine_brake: int
    fuel_start_l: float
    fuel_end_l: float


@dataclass(frozen=True, slots=True)
class TyreHint:
    wheel: str
    text: str


def summarize_car(samples: Sequence[TelemetrySample], lap: Lap) -> CarSummary | None:
    """None when the lap has no car data (recorded before it was stored, or never on track)."""
    lap_samples = list(samples[lap.start : lap.end])
    driving = [s for s in lap_samples if s.speed_kmh > _ON_TRACK_KMH and not s.in_pit]
    if not driving or all(s.tyre_pressure_fl == 0 for s in driving):
        return None

    def avg(field: str) -> float:
        return sum(float(getattr(s, field)) for s in driving) / len(driving)

    return CarSummary(
        tyres=[
            TyreState(
                wheel=w,
                pressure_psi=avg(f"tyre_pressure_{w}"),
                temp_inner_c=avg(f"tyre_temp_inner_{w}"),
                temp_middle_c=avg(f"tyre_temp_middle_{w}"),
                temp_outer_c=avg(f"tyre_temp_outer_{w}"),
            )
            for w in WHEELS
        ],
        brake_bias=median(s.brake_bias for s in driving),
        tc=median(s.tc for s in driving),
        abs=median(s.abs for s in driving),
        engine_brake=round(median(s.engine_brake for s in driving)),
        fuel_start_l=lap_samples[0].fuel,
        fuel_end_l=lap_samples[-1].fuel,
    )


def tyre_hints(summary: CarSummary) -> list[TyreHint]:
    """Classic readings of temperatures across the tread (inner, middle, outer)."""
    hints = []
    for tyre in summary.tyres:
        name = WHEEL_NAMES[tyre.wheel]
        edges = (tyre.temp_inner_c + tyre.temp_outer_c) / 2
        spread = tyre.temp_middle_c - edges
        if spread > PRESSURE_SPREAD_C:
            hints.append(
                TyreHint(
                    tyre.wheel,
                    f"{name.capitalize()}: el centro va {spread:.0f} °C más caliente que los "
                    f"bordes; la presión ({tyre.pressure_psi:.1f} psi) podría estar alta.",
                )
            )
        elif spread < -PRESSURE_SPREAD_C:
            hints.append(
                TyreHint(
                    tyre.wheel,
                    f"{name.capitalize()}: el centro va {-spread:.0f} °C más frío que los "
                    f"bordes; la presión ({tyre.pressure_psi:.1f} psi) podría estar baja.",
                )
            )
        camber = tyre.temp_inner_c - tyre.temp_outer_c
        if camber > CAMBER_MAX_C:
            hints.append(
                TyreHint(
                    tyre.wheel,
                    f"{name.capitalize()}: el borde interior va {camber:.0f} °C más caliente "
                    "que el exterior; quizá sobra caída negativa (camber).",
                )
            )
        elif camber < CAMBER_MIN_C:
            reading = (
                f"el borde exterior va {-camber:.0f} °C más caliente que el interior"
                if camber < 0
                else "los bordes interior y exterior van casi igual"
            )
            hints.append(
                TyreHint(
                    tyre.wheel,
                    f"{name.capitalize()}: {reading}; quizá falta caída negativa (camber).",
                )
            )
    return hints
