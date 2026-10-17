"""Builders for synthetic Assetto Corsa shared memory blocks."""

import ctypes
from collections.abc import Sequence

from raceengineer.adapters.ac_shared_memory import (
    ACStatus,
    Snapshot,
    SPageFileGraphic,
    SPageFilePhysics,
    SPageFileStatic,
)


def set_wstr(field: ctypes.Array[ctypes.c_uint16], text: str) -> None:
    encoded = text.encode("utf-16-le")
    for i in range(len(field)):
        field[i] = 0
    for i in range(len(encoded) // 2):
        field[i] = int.from_bytes(encoded[2 * i : 2 * i + 2], "little")


def physics_bytes(packet_id: int = 1, **values: float) -> bytes:
    physics = SPageFilePhysics(packetId=packet_id, clutch=1.0, gear=1)
    for name, value in values.items():
        setattr(physics, name, value)
    return bytes(physics)


def graphics_bytes(
    packet_id: int = 1,
    status: ACStatus = ACStatus.LIVE,
    coordinates: Sequence[float] = (0.0, 0.0, 0.0),
    **values: float,
) -> bytes:
    graphics = SPageFileGraphic(packetId=packet_id, status=int(status))
    for i, c in enumerate(coordinates):
        graphics.carCoordinates[i] = c
    for name, value in values.items():
        setattr(graphics, name, value)
    return bytes(graphics)


def static_bytes(car: str = "ks_mazda_mx5_cup", track: str = "magione", config: str = "") -> bytes:
    static = SPageFileStatic()
    set_wstr(static.smVersion, "1.7")
    set_wstr(static.carModel, car)
    set_wstr(static.track, track)
    set_wstr(static.trackConfiguration, config)
    return bytes(static)


def snapshot(packet_id: int, status: ACStatus = ACStatus.LIVE, **physics: float) -> Snapshot:
    return Snapshot(
        physics=physics_bytes(packet_id, **physics),
        graphics=graphics_bytes(packet_id, status),
    )


class ScriptedReader:
    """Returns the given snapshots in order, then raises EOFError.

    With ``repeat_last`` it keeps returning the last one instead, like a paused game.
    """

    def __init__(
        self,
        snapshots: Sequence[Snapshot],
        static: bytes | None = None,
        repeat_last: bool = False,
    ) -> None:
        self._snapshots = list(snapshots)
        self._repeat_last = repeat_last
        self._static = static if static is not None else static_bytes()
        self.reads = 0
        self.closed = False

    def read(self) -> Snapshot:
        if self.reads >= len(self._snapshots):
            if self._repeat_last and self._snapshots:
                return self._snapshots[-1]
            raise EOFError
        self.reads += 1
        return self._snapshots[self.reads - 1]

    def read_static(self) -> bytes:
        return self._static

    def close(self) -> None:
        self.closed = True


class FakeTime:
    """A clock that only advances when someone sleeps."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
