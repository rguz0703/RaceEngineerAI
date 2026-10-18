from dataclasses import replace

import pytest

from raceengineer.analysis.car import CarSummary, TyreState, summarize_car, tyre_hints
from raceengineer.analysis.compare import SegmentSummary
from raceengineer.analysis.diagnosis import LapData, Note, diagnose
from raceengineer.domain.models import Lap, TelemetrySample

BASE = TelemetrySample(
    t=0.0,
    lap_number=0,
    lap_time_ms=0,
    normalized_position=0.0,
    speed_kmh=150.0,
    throttle=1.0,
    brake=0.0,
    clutch=0.0,
    steering=0.0,
    gear=4,
    rpm=7000.0,
    pos_x=0.0,
    pos_y=0.0,
    pos_z=0.0,
    in_pit=False,
)
LAP = Lap(1, 0, 0, 60_000, True, True, False, False, False)


def _tyre(wheel: str, inner: float, middle: float, outer: float) -> TyreState:
    return TyreState(wheel, 26.0, inner, middle, outer)


def _car(*tyres: TyreState) -> CarSummary:
    return CarSummary(list(tyres), 0.6, 0.0, 0.0, 0, 30.0, 29.0)


def test_summarize_car_averages_on_track_samples() -> None:
    samples = [
        replace(BASE, speed_kmh=10, in_pit=True, tyre_pressure_fl=99.0, fuel=31.0),
        replace(BASE, tyre_pressure_fl=26.0, tyre_temp_middle_fl=80.0, brake_bias=0.6, fuel=30.0),
        replace(BASE, tyre_pressure_fl=28.0, tyre_temp_middle_fl=90.0, brake_bias=0.6, fuel=29.5),
    ]
    car = summarize_car(samples, replace(LAP, end=3))
    assert car is not None
    fl = car.tyres[0]
    assert (fl.wheel, fl.pressure_psi, fl.temp_middle_c) == ("fl", 27.0, 85.0)
    assert car.brake_bias == pytest.approx(0.6)
    assert (car.fuel_start_l, car.fuel_end_l) == (31.0, 29.5)


def test_summarize_car_without_data() -> None:
    assert summarize_car([BASE, BASE], replace(LAP, end=2)) is None


@pytest.mark.parametrize(
    ("temps", "expected"),
    [
        ((80, 90, 80), "presión"),  # hot middle
        ((80, 70, 80), "baja"),  # cold middle
        ((95, 87, 80), "sobra caída"),  # inner much hotter
        ((70, 75, 80), "falta caída"),  # outer hotter
        ((80, 80, 79), "casi igual"),  # flat
    ],
)
def test_tyre_hints(temps: tuple[float, float, float], expected: str) -> None:
    hints = tyre_hints(_car(_tyre("fr", *temps)))
    assert any(expected in h.text for h in hints)
    assert all(h.wheel == "fr" for h in hints)


def test_healthy_tyre_has_no_hints() -> None:
    assert tyre_hints(_car(_tyre("fl", 86, 83, 80))) == []


def _lap(samples: list[TelemetrySample]) -> LapData:
    return LapData(samples, [s.normalized_position * 1000 for s in samples])


def _corner(
    entry_brake_at: float, min_speed: float, full_throttle_at: float, **changes: float
) -> list[TelemetrySample]:
    """One 1 km lap sampled every 10 m with one braking zone and corner."""
    samples = []
    for k in range(101):
        d = k * 10.0
        braking = entry_brake_at <= d < 500
        corner = 500 <= d < full_throttle_at
        speed = min_speed if 500 <= d < 600 else 150.0
        samples.append(
            replace(
                BASE,
                t=k * 0.1,
                normalized_position=d / 1000,
                speed_kmh=speed,
                brake=1.0 if braking else 0.0,
                throttle=0.0 if braking or corner else 1.0,
                **changes,  # type: ignore[arg-type]
            )
        )
    return samples


SEGMENT = SegmentSummary(0, 100, 0.0, 1000.0, 0.5, 80, 90, 120, 125)


def _texts(notes: list[Note]) -> str:
    return " | ".join(n.text for n in notes)


def test_losing_segment_explains_braking_speed_and_throttle() -> None:
    target = _lap(_corner(entry_brake_at=300, min_speed=80, full_throttle_at=700))
    reference = _lap(_corner(entry_brake_at=400, min_speed=95, full_throttle_at=620))

    notes = diagnose(target, reference, [SEGMENT])

    text = _texts(notes)
    assert "frenar 100 m antes" in text
    assert "15 km/h más baja" in text
    assert "80 m más tarde" in text
    assert all(n.segment == 0 for n in notes)


def test_late_braking_and_coasting() -> None:
    target = _lap(_corner(entry_brake_at=450, min_speed=90, full_throttle_at=800))
    reference = _lap(_corner(entry_brake_at=400, min_speed=90, full_throttle_at=620))
    assert "más tarde que en la referencia (¿te pasaste" in _texts(
        diagnose(target, reference, [SEGMENT])
    )
    assert "sin acelerar ni frenar" in _texts(diagnose(target, reference, [SEGMENT]))


def test_gaining_segment_only_reports_incidents() -> None:
    target = _lap(_corner(300, 80, 700, tyres_out=4))
    reference = _lap(_corner(400, 95, 620))
    gaining = replace(SEGMENT, delta_s=-0.5)

    notes = diagnose(target, reference, [gaining])

    assert [n.topic for n in notes] == ["pista"]


def test_lockup_and_wheelspin() -> None:
    target = _corner(300, 80, 700)
    for k in range(32, 36):  # braking zone
        target[k] = replace(target[k], slip_ratio_fl=-0.6)
    for k in range(75, 80):  # full throttle after the corner
        target[k] = replace(target[k], slip_ratio_rl=0.4)
    reference = _lap(_corner(300, 80, 700))

    text = _texts(diagnose(_lap(target), reference, [replace(SEGMENT, delta_s=-1)]))

    assert "Bloqueaste la delantera izquierda" in text
    assert "(en la referencia, no)" in text
    assert "traseras patinaron" in text


def test_understeer_in_two_segments_suggests_setup_checks() -> None:
    def cornering(steering: float) -> list[TelemetrySample]:
        return [
            replace(s, steering=steering, yaw_rate=0.5, throttle=1.0, brake=0.0)
            for s in _corner(1000, 150, 0)
        ]

    half = [replace(SEGMENT, end_m=500), replace(SEGMENT, start_m=500)]
    car = _car(_tyre("fl", 86, 83, 80), _tyre("fr", 86, 83, 80))

    notes = diagnose(_lap(cornering(0.3)), _lap(cornering(0.2)), half, car)

    assert sum("subviró" in n.text for n in notes) == 2
    lap_notes = [n for n in notes if n.segment is None]
    assert any("26.0 psi" in n.text and "60%" in n.text for n in lap_notes)


def test_more_rotation_is_reported_as_info() -> None:
    def cornering(steering: float) -> list[TelemetrySample]:
        return [replace(s, steering=steering, yaw_rate=-0.5) for s in _corner(1000, 150, 0)]

    notes = diagnose(_lap(cornering(0.1)), _lap(cornering(0.2)), [SEGMENT])

    assert [n.severity for n in notes if n.topic == "equilibrio"] == ["info"]


def test_segments_without_samples_are_skipped() -> None:
    lap = _lap(_corner(300, 80, 700))
    assert diagnose(lap, lap, [replace(SEGMENT, start_m=5000, end_m=6000)]) == []
