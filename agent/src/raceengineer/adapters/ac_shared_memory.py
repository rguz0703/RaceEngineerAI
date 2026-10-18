"""Assetto Corsa (original) telemetry via its shared memory blocks.

AC publishes three named shared memory blocks on Windows while it runs:

- ``Local\\acpmf_physics``: car physics, updated every physics step.
- ``Local\\acpmf_graphics``: session/HUD state (status, laps, timing, position).
- ``Local\\acpmf_static``: data that does not change during a session (car, track).

Layout source: Kunos' "Shared Memory Reference" thread on the official forum
(assettocorsa.net/forum, ``threads/shared-memory-reference.3352``), header
``SharedFileOut.h``, shared memory version 1.7 (AC 1.13+). Cross-checked against
the MIT-licensed C# reader https://github.com/mdjarv/assettocorsasharedmemory
(Physics.cs, Graphics.cs, StaticInfo.cs). Newer AC builds append fields after the
ones declared here; that is harmless because we only map and read this prefix.

Checked against real dumps (AC 1.16.4, SM 1.7, Monza, 2026-10-17; see
tests/fixtures/): strings, status, laps, lap timer, speed (matches |velocity|),
gear (0 = R, 1 = N), rpm, temperatures and brake bias all decode to plausible
values, so the offsets are right. Physics updates at ~333 Hz. steerAngle is the
normalized wheel input: -1 full left, +1 full right (calibration dump). Lap times
from a 3-lap recording matched the game's results screen within 10 ms.
STILL UNVERIFIED: the clutch direction (no dump has the pedal pressed yet) and
whether the brake reaches 1.0 (the calibration dump ended as it was pressed).

Parsing (bytes -> sample) is pure Python and runs on any OS. Only
``WindowsSharedMemoryReader`` touches Windows APIs.
"""

import ctypes
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from enum import IntEnum
from threading import Event
from typing import Protocol

from raceengineer.domain.models import SessionInfo, TelemetrySample

SIM_NAME = "assetto_corsa"

PHYSICS_TAG = "Local\\acpmf_physics"
GRAPHICS_TAG = "Local\\acpmf_graphics"
STATIC_TAG = "Local\\acpmf_static"

# Strings are wchar_t (UTF-16 on Windows). ctypes.c_wchar is 4 bytes on macOS/Linux,
# so we declare them as uint16 arrays to get the Windows layout on every OS.
_F = ctypes.c_float
_I = ctypes.c_int32


def _wstr(chars: int) -> type[ctypes.Array[ctypes.c_uint16]]:
    return ctypes.c_uint16 * chars


class SPageFilePhysics(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("packetId", _I),
        ("gas", _F),
        ("brake", _F),
        ("fuel", _F),
        ("gear", _I),  # 0 = reverse, 1 = neutral, 2 = first gear...
        ("rpms", _I),
        ("steerAngle", _F),
        ("speedKmh", _F),
        ("velocity", _F * 3),
        ("accG", _F * 3),
        ("wheelSlip", _F * 4),
        ("wheelLoad", _F * 4),
        ("wheelsPressure", _F * 4),
        ("wheelAngularSpeed", _F * 4),
        ("tyreWear", _F * 4),
        ("tyreDirtyLevel", _F * 4),
        ("tyreCoreTemperature", _F * 4),
        ("camberRAD", _F * 4),
        ("suspensionTravel", _F * 4),
        ("drs", _F),
        ("tc", _F),
        ("heading", _F),
        ("pitch", _F),
        ("roll", _F),
        ("cgHeight", _F),
        ("carDamage", _F * 5),
        ("numberOfTyresOut", _I),
        ("pitLimiterOn", _I),
        ("abs", _F),
        ("kersCharge", _F),
        ("kersInput", _F),
        ("autoShifterOn", _I),
        ("rideHeight", _F * 2),
        # since 1.5
        ("turboBoost", _F),
        ("ballast", _F),
        ("airDensity", _F),
        # since 1.6
        ("airTemp", _F),
        ("roadTemp", _F),
        ("localAngularVel", _F * 3),
        ("finalFF", _F),
        # since 1.7
        ("performanceMeter", _F),
        ("engineBrake", _I),
        ("ersRecoveryLevel", _I),
        ("ersPowerLevel", _I),
        ("ersHeatCharging", _I),
        ("ersIsCharging", _I),
        ("kersCurrentKJ", _F),
        ("drsAvailable", _I),
        ("drsEnabled", _I),
        ("brakeTemp", _F * 4),
        # since 1.10
        ("clutch", _F),  # in AC 1.0 = released, 0.0 = fully pressed (unverified)
        ("tyreTempI", _F * 4),
        ("tyreTempM", _F * 4),
        ("tyreTempO", _F * 4),
        # since 1.10.2
        ("isAIControlled", _I),
        # since 1.11
        ("tyreContactPoint", (_F * 3) * 4),
        ("tyreContactNormal", (_F * 3) * 4),
        ("tyreContactHeading", (_F * 3) * 4),
        ("brakeBias", _F),
        # since 1.12
        ("localVelocity", _F * 3),
    ]


class SPageFileGraphic(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("packetId", _I),
        ("status", _I),
        ("session", _I),
        ("currentTime", _wstr(15)),
        ("lastTime", _wstr(15)),
        ("bestTime", _wstr(15)),
        ("split", _wstr(15)),
        ("completedLaps", _I),
        ("position", _I),
        ("iCurrentTime", _I),
        ("iLastTime", _I),
        ("iBestTime", _I),
        ("sessionTimeLeft", _F),
        ("distanceTraveled", _F),
        ("isInPit", _I),
        ("currentSectorIndex", _I),
        ("lastSectorTime", _I),
        ("numberOfLaps", _I),
        ("tyreCompound", _wstr(33)),
        ("replayTimeMultiplier", _F),
        ("normalizedCarPosition", _F),
        ("carCoordinates", _F * 3),
        ("penaltyTime", _F),
        ("flag", _I),
        ("idealLineOn", _I),
        # since 1.5
        ("isInPitLane", _I),
        ("surfaceGrip", _F),
        # since 1.13
        ("mandatoryPitDone", _I),
    ]


class SPageFileStatic(ctypes.Structure):
    _pack_ = 4
    _fields_ = [
        ("smVersion", _wstr(15)),
        ("acVersion", _wstr(15)),
        ("numberOfSessions", _I),
        ("numCars", _I),
        ("carModel", _wstr(33)),
        ("track", _wstr(33)),
        ("playerName", _wstr(33)),
        ("playerSurname", _wstr(33)),
        ("playerNick", _wstr(33)),
        ("sectorCount", _I),
        ("maxTorque", _F),
        ("maxPower", _F),
        ("maxRpm", _I),
        ("maxFuel", _F),
        ("suspensionMaxTravel", _F * 4),
        ("tyreRadius", _F * 4),
        # since 1.5
        ("maxTurboBoost", _F),
        ("deprecated_1", _F),
        ("deprecated_2", _F),
        ("penaltiesEnabled", _I),
        ("aidFuelRate", _F),
        ("aidTireRate", _F),
        ("aidMechanicalDamage", _F),
        ("aidAllowTyreBlankets", _I),
        ("aidStability", _F),
        ("aidAutoClutch", _I),
        ("aidAutoBlip", _I),
        # since 1.7.1
        ("hasDRS", _I),
        ("hasERS", _I),
        ("hasKERS", _I),
        ("kersMaxJ", _F),
        ("engineBrakeSettingsCount", _I),
        ("ersPowerControllerCount", _I),
        # since 1.7.2
        ("trackSPlineLength", _F),
        ("trackConfiguration", _wstr(15)),
        # since 1.10.2
        ("ersMaxJ", _F),
        # since 1.13
        ("isTimedRace", _I),
        ("hasExtraLap", _I),
        ("carSkin", _wstr(33)),
        ("reversedGridPositions", _I),
        ("pitWindowStart", _I),
        ("pitWindowEnd", _I),
    ]


PHYSICS_SIZE = ctypes.sizeof(SPageFilePhysics)
GRAPHICS_SIZE = ctypes.sizeof(SPageFileGraphic)
STATIC_SIZE = ctypes.sizeof(SPageFileStatic)


class ACStatus(IntEnum):
    OFF = 0
    REPLAY = 1
    LIVE = 2
    PAUSE = 3


class ACNotRunningError(RuntimeError):
    """Assetto Corsa's shared memory is not available."""


def decode_wstr(chars: ctypes.Array[ctypes.c_uint16]) -> str:
    """Decode a fixed-size, NUL-terminated UTF-16 field."""
    raw = bytes(chars).decode("utf-16-le", errors="replace")
    return raw.split("\0", 1)[0]


def parse_physics(data: bytes) -> SPageFilePhysics:
    return SPageFilePhysics.from_buffer_copy(data[:PHYSICS_SIZE])


def parse_graphics(data: bytes) -> SPageFileGraphic:
    return SPageFileGraphic.from_buffer_copy(data[:GRAPHICS_SIZE])


def parse_static(data: bytes) -> SPageFileStatic:
    return SPageFileStatic.from_buffer_copy(data[:STATIC_SIZE])


def session_info_from_static(static: SPageFileStatic) -> SessionInfo:
    return SessionInfo(
        sim=SIM_NAME,
        track=decode_wstr(static.track),
        car=decode_wstr(static.carModel),
        track_config=decode_wstr(static.trackConfiguration),
        track_length_m=static.trackSPlineLength,
    )


def to_sample(physics: SPageFilePhysics, graphics: SPageFileGraphic, t: float) -> TelemetrySample:
    """Normalize one AC physics + graphics reading."""
    return TelemetrySample(
        t=t,
        lap_number=graphics.completedLaps,
        lap_time_ms=graphics.iCurrentTime,
        normalized_position=graphics.normalizedCarPosition,
        speed_kmh=physics.speedKmh,
        throttle=_clamp(physics.gas, 0.0, 1.0),
        brake=_clamp(physics.brake, 0.0, 1.0),
        # AC reports clutch as 1.0 released; our model uses 1.0 pressed (unverified).
        clutch=_clamp(1.0 - physics.clutch, 0.0, 1.0),
        steering=_clamp(physics.steerAngle, -1.0, 1.0),
        gear=physics.gear - 1,
        rpm=float(physics.rpms),
        pos_x=graphics.carCoordinates[0],
        pos_y=graphics.carCoordinates[1],
        pos_z=graphics.carCoordinates[2],
        in_pit=bool(graphics.isInPit or graphics.isInPitLane),
        last_lap_ms=_lap_ms(graphics.iLastTime),
        tyres_out=physics.numberOfTyresOut,
    )


_MAX_LAP_MS = 60 * 60 * 1000


def _lap_ms(value: int) -> int:
    """AC fills 'no lap yet' with placeholders; keep only plausible lap times."""
    return value if 0 < value < _MAX_LAP_MS else 0


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Raw bytes of the physics and graphics blocks, read one right after the other."""

    physics: bytes
    graphics: bytes


class SharedMemoryReader(Protocol):
    """Provides raw block contents; the real game or a recorded dump."""

    def read(self) -> Snapshot:
        """Return the current blocks. Raises EOFError when a recording runs out."""
        ...

    def read_static(self) -> bytes: ...

    def close(self) -> None: ...


class Pacer:
    """Keeps a loop at a steady rate by sleeping until the next tick.

    A fixed ``sleep(interval)`` after each iteration adds the loop's own work time
    to every period: on the PC a 120 Hz recording ran at about 69 Hz. Sleeping
    until a deadline absorbs that work. If the loop falls behind it resyncs
    instead of bursting to catch up.
    """

    def __init__(
        self, interval: float, clock: Callable[[], float], sleep: Callable[[float], None]
    ) -> None:
        self._interval = interval
        self._clock = clock
        self._sleep = sleep
        self._next: float | None = None

    def wait(self) -> None:
        now = self._clock()
        self._next = (now if self._next is None else self._next) + self._interval
        delay = self._next - now
        if delay > 0:
            self._sleep(delay)
        else:
            self._next = now


class ACSharedMemorySource:
    """TelemetrySource for Assetto Corsa.

    Polls the reader at ``poll_hz`` and yields a sample each time the physics
    packetId changes while AC is LIVE. REPLAY and PAUSE produce no samples. The
    stream ends when ``stop`` is set, when AC goes back to OFF after having been
    live, or when a recorded reader runs out of data.
    """

    def __init__(
        self,
        reader: SharedMemoryReader,
        poll_hz: float = 120.0,
        stop: Event | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if poll_hz <= 0:
            raise ValueError("poll_hz must be > 0")
        self._reader = reader
        self._interval = 1.0 / poll_hz
        self._stop = stop if stop is not None else Event()
        self._clock = clock
        self._sleep = sleep

    def session_info(self) -> SessionInfo:
        return session_info_from_static(parse_static(self._reader.read_static()))

    def samples(self) -> Iterator[TelemetrySample]:
        start: float | None = None
        last_packet: int | None = None
        was_live = False
        pacer = Pacer(self._interval, self._clock, self._sleep)
        while not self._stop.is_set():
            try:
                snapshot = self._reader.read()
            except EOFError:
                return
            graphics = parse_graphics(snapshot.graphics)
            status = _status(graphics.status)
            if status is ACStatus.OFF and was_live:
                return
            if status is ACStatus.LIVE:
                was_live = True
                physics = parse_physics(snapshot.physics)
                if physics.packetId != last_packet:
                    last_packet = physics.packetId
                    now = self._clock()
                    if start is None:
                        start = now
                    yield to_sample(physics, graphics, now - start)
            pacer.wait()


def _status(value: int) -> ACStatus:
    try:
        return ACStatus(value)
    except ValueError:
        return ACStatus.OFF


def _open_or_explain(reader_factory: Callable[[], SharedMemoryReader]) -> SharedMemoryReader:
    """Open the reader or explain clearly why it is not possible."""
    try:
        return reader_factory()
    except OSError as exc:
        raise ACNotRunningError(
            "No se encontró la memoria compartida de Assetto Corsa. "
            "Abre AC y entra en pista (no basta con el menú) antes de grabar."
        ) from exc


if sys.platform == "win32":
    from ctypes import wintypes

    _FILE_MAP_READ = 0x0004
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.OpenFileMappingW.restype = wintypes.HANDLE
    _kernel32.MapViewOfFile.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_size_t,
    ]
    _kernel32.MapViewOfFile.restype = ctypes.c_void_p
    _kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    _kernel32.UnmapViewOfFile.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    class _View:
        """A read-only view of an existing named mapping.

        We use OpenFileMappingW instead of ``mmap.mmap(-1, size, tagname)``:
        mmap silently *creates* an empty block when AC is not running, and fails
        if asked for more bytes than AC allocated. Opening only existing blocks
        lets us report "AC is not running" clearly.
        """

        def __init__(self, tag: str, size: int) -> None:
            handle = _kernel32.OpenFileMappingW(_FILE_MAP_READ, False, tag)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            address = _kernel32.MapViewOfFile(handle, _FILE_MAP_READ, 0, 0, size)
            if not address:
                error = ctypes.get_last_error()
                _kernel32.CloseHandle(handle)
                raise ctypes.WinError(error)
            self._handle = handle
            self._address: int = address
            self._size = size

        def read(self) -> bytes:
            return ctypes.string_at(self._address, self._size)

        def close(self) -> None:
            _kernel32.UnmapViewOfFile(self._address)
            _kernel32.CloseHandle(self._handle)

    class WindowsSharedMemoryReader:
        """Reads the live blocks published by a running Assetto Corsa."""

        def __init__(self) -> None:
            views: list[_View] = []
            try:
                for tag, size in (
                    (PHYSICS_TAG, PHYSICS_SIZE),
                    (GRAPHICS_TAG, GRAPHICS_SIZE),
                    (STATIC_TAG, STATIC_SIZE),
                ):
                    views.append(_View(tag, size))
            except OSError:
                for view in views:
                    view.close()
                raise
            self._physics, self._graphics, self._static = views

        def read(self) -> Snapshot:
            return Snapshot(physics=self._physics.read(), graphics=self._graphics.read())

        def read_static(self) -> bytes:
            return self._static.read()

        def close(self) -> None:
            for view in (self._physics, self._graphics, self._static):
                view.close()

    def open_live_reader() -> SharedMemoryReader:
        """Open AC's live shared memory."""
        return _open_or_explain(WindowsSharedMemoryReader)

else:

    def open_live_reader() -> SharedMemoryReader:
        """AC's shared memory only exists on Windows."""
        raise ACNotRunningError(
            "Assetto Corsa solo publica telemetría en Windows; usa esta fuente en la PC."
        )
