"""What the race engineer says on the radio: short, rule-based calls built from the data.

Each call has a ``text`` for the screen and a ``speech`` written to be read aloud by
the browser's voice (numbers spelled the way an engineer would say them).
"""

from dataclasses import dataclass

from raceengineer.analysis.car import WHEEL_NAMES
from raceengineer.analysis.compare import LapComparison

LOSS_WINDOW_M = 250.0
"""Length of track over which the biggest loss of the lap is looked for."""
MIN_TIP_LOSS_S = 0.1
"""Smaller losses are noise; the engineer stays quiet."""
LOOK_BACK_M = 150.0
"""The braking for a corner can start this far before the stretch where time was lost."""
BRAKE_ON = 0.3
FULL_THROTTLE = 0.9
BRAKE_EARLY_M = 8.0
SLOWER_KMH = 3.0
THROTTLE_LATE_M = 10.0

SECTOR_WORDS = ("uno", "dos", "tres")


@dataclass(frozen=True, slots=True)
class RadioCall:
    """One radio message."""

    id: int
    """Increasing, so clients speak each call once."""
    kind: str
    """sector, lap, best_lap, tip or incident (clients let the driver mute each kind)."""
    text: str
    speech: str
    lap: int


def gap_words(seconds: float) -> str:
    """0.21 -> "2 décimas", 1.34 -> "1 segundo y 3 décimas"."""
    tenths = round(abs(seconds) * 10)
    whole, rest = divmod(tenths, 10)
    parts = []
    if whole:
        parts.append("1 segundo" if whole == 1 else f"{whole} segundos")
    if rest:
        parts.append("1 décima" if rest == 1 else f"{rest} décimas")
    return " y ".join(parts) or "nada"


def lap_time_words(ms: int) -> str:
    """97_831 -> "1, 37, 8": minutes, seconds, tenths, as engineers read lap times."""
    minutes, rest = divmod(ms, 60_000)
    seconds, millis = divmod(rest, 1000)
    tenth = millis // 100
    return f"{minutes}, {seconds:02d}, {tenth}" if minutes else f"{seconds}, {tenth}"


def lap_time_text(ms: int) -> str:
    minutes, rest = divmod(ms, 60_000)
    return f"{minutes}:{rest / 1000:06.3f}"


def _signed(seconds: float, digits: int = 2) -> str:
    return f"{'+' if seconds > 0 else '\u2212' if seconds < 0 else ''}{abs(seconds):.{digits}f}"


def sector_call(call_id: int, lap: int, sector: int, delta_s: float) -> RadioCall:
    """``sector`` counts from 0; ``delta_s`` is the time lost (+) in that sector only."""
    name = SECTOR_WORDS[sector] if sector < len(SECTOR_WORDS) else str(sector + 1)
    if abs(delta_s) < 0.05:
        verdict = "igual que tu mejor"
    else:
        verdict = f"{gap_words(delta_s)} {'más lento' if delta_s > 0 else 'más rápido'}"
    return RadioCall(
        call_id,
        "sector",
        f"Sector {sector + 1}: {_signed(delta_s)} s",
        f"Sector {name}, {verdict}.",
        lap,
    )


def lap_call(
    call_id: int,
    lap: int,
    time_ms: int,
    reference_ms: int | None,
    new_best: bool,
    off_track: bool,
) -> RadioCall:
    """The call right after the line: lap time and how it compares with your best."""
    spoken = lap_time_words(time_ms)
    shown = lap_time_text(time_ms)
    dirty = " Con salida de pista." if off_track else ""
    gap = (time_ms - reference_ms) / 1000 if reference_ms else None
    if new_best:
        text = f"¡Nueva mejor vuelta! {shown}"
        speech = f"Nueva mejor vuelta. {spoken}."
        if gap is not None and gap < 0:
            text += f" ({_signed(gap, 3)} s)"
            speech += f" {gap_words(gap)} más rápida."
        return RadioCall(call_id, "best_lap", text + dirty, speech + dirty, lap)
    if gap is None:
        return RadioCall(call_id, "lap", f"Vuelta {lap}: {shown}{dirty}", f"{spoken}.{dirty}", lap)
    if abs(gap) < 0.05:
        verdict = "Igual que tu mejor."
    else:
        verdict = f"{gap_words(gap)} {'más lenta' if gap > 0 else 'más rápida'} que tu mejor."
    return RadioCall(
        call_id,
        "lap",
        f"Vuelta {lap}: {shown} ({_signed(gap, 3)} s){dirty}",
        f"{spoken}. {verdict}{dirty}",
        lap,
    )


@dataclass(frozen=True, slots=True)
class LossTip:
    """Where the lap lost the most time against the reference, and the likely reason."""

    apex_m: float
    """The slowest point of the reference in that stretch: the corner."""
    loss_s: float
    cause: str
    """Spoken advice, e.g. "Frenaste 12 metros antes." Empty if nothing stands out."""


def biggest_loss(comparison: LapComparison) -> LossTip | None:
    """The 250 m stretch where the most time went, if it is worth mentioning."""
    d = comparison.distance_m
    delta = comparison.delta_s
    if len(d) < 3:
        return None
    step = (d[-1] - d[0]) / (len(d) - 1) or 1.0
    width = max(1, min(len(d) - 1, round(LOSS_WINDOW_M / step)))
    lo = max(range(len(d) - width), key=lambda i: delta[i + width] - delta[i])
    hi = lo + width
    loss = delta[hi] - delta[lo]
    if loss < MIN_TIP_LOSS_S:
        return None

    target, reference = comparison.target, comparison.reference
    apex_ref = min(range(lo, hi + 1), key=lambda i: reference.speed_kmh[i])
    apex_tgt = min(range(lo, hi + 1), key=lambda i: target.speed_kmh[i])
    start = next((i for i in range(lo, -1, -1) if d[lo] - d[i] >= LOOK_BACK_M), 0)

    def first(values: list[float], threshold: float, a: int, b: int) -> int | None:
        return next((i for i in range(a, b + 1) if values[i] > threshold), None)

    reasons: list[tuple[float, str]] = []
    brake_t = first(target.brake, BRAKE_ON, start, hi)
    brake_r = first(reference.brake, BRAKE_ON, start, hi)
    if brake_t is not None and brake_r is not None:
        earlier = d[brake_r] - d[brake_t]
        if earlier >= BRAKE_EARLY_M:
            reasons.append((earlier / BRAKE_EARLY_M, f"Frenaste {earlier:.0f} metros antes."))
    slower = reference.speed_kmh[apex_ref] - target.speed_kmh[apex_tgt]
    if slower >= SLOWER_KMH:
        reasons.append(
            (
                slower / SLOWER_KMH,
                f"Pasaste {slower:.0f} kilómetros por hora más lento por la curva.",
            )
        )
    exit_slower = reference.speed_kmh[hi] - target.speed_kmh[hi]
    if exit_slower >= SLOWER_KMH:
        reasons.append(
            (exit_slower / SLOWER_KMH, f"Saliste {exit_slower:.0f} kilómetros por hora más lento.")
        )
    end = min(len(d) - 1, hi + width)
    throttle_t = first(target.throttle, FULL_THROTTLE, apex_tgt, end)
    throttle_r = first(reference.throttle, FULL_THROTTLE, apex_ref, end)
    if throttle_t is not None and throttle_r is not None:
        later = d[throttle_t] - d[throttle_r]
        if later >= THROTTLE_LATE_M:
            reasons.append(
                (later / THROTTLE_LATE_M, f"Aceleraste a fondo {later:.0f} metros más tarde.")
            )
    cause = max(reasons)[1] if reasons else ""
    return LossTip(apex_m=d[apex_ref], loss_s=loss, cause=cause)


def tip_call(call_id: int, lap: int, tip: LossTip) -> RadioCall:
    where = round(tip.apex_m / 10) * 10
    cause = tip.cause or "Revisa la trazada ahí."
    return RadioCall(
        call_id,
        "tip",
        f"Mayor pérdida: curva de los {where:,} m ({_signed(tip.loss_s)} s). {cause}",
        f"Donde más perdiste fue la curva de los {where} metros, {gap_words(tip.loss_s)}. {cause}",
        lap,
    )


def incident_speech(kind: str, wheel: str = "") -> str:
    if kind == "off_track":
        return "Fuera de pista."
    if kind == "lockup":
        return f"Bloqueo, {WHEEL_NAMES.get(wheel, 'una rueda')}."
    if kind == "wheelspin":
        return "Cuidado con el acelerador, patinaste."
    return ""
