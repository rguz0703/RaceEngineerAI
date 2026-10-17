"""Raw dumps of Assetto Corsa's shared memory, for fixtures and offline replay.

File format (gzip-compressed):

- Header line: ``RACEENG-ACRAW 1`` followed by a JSON line with the block sizes.
- Records, each ``tag (1 byte) + t (float64 little-endian, seconds)`` then:
  - ``S``: the static block (written at start and whenever it changes).
  - ``F``: the physics block followed by the graphics block (written whenever
    either packetId changes).

Every state (OFF, REPLAY, LIVE, PAUSE) is dumped, so a dump also documents how
the game behaves in menus and pauses.
"""

import gzip
import json
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from raceengineer.adapters.ac_shared_memory import (
    GRAPHICS_SIZE,
    PHYSICS_SIZE,
    STATIC_SIZE,
    SharedMemoryReader,
    Snapshot,
)

MAGIC = b"RACEENG-ACRAW 1\n"
_RECORD_HEADER = struct.Struct("<cd")
_PACKET_ID = struct.Struct("<i")
_STATIC = b"S"
_FRAME = b"F"


@dataclass(frozen=True, slots=True)
class DumpStats:
    frames: int
    static_blocks: int
    seconds: float


def dump_raw(
    reader: SharedMemoryReader,
    path: Path,
    seconds: float,
    poll_hz: float = 200.0,
    stop: Event | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> DumpStats:
    """Poll ``reader`` for ``seconds`` (or until ``stop``) and write a dump to ``path``."""
    if poll_hz <= 0:
        raise ValueError("poll_hz must be > 0")
    stop = stop if stop is not None else Event()
    interval = 1.0 / poll_hz
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = statics = 0
    last_static: bytes | None = None
    last_ids: tuple[int, int] | None = None
    start = clock()
    elapsed = 0.0
    with gzip.open(path, "wb") as out:
        _write_header(out)
        while not stop.is_set():
            elapsed = clock() - start
            if elapsed >= seconds:
                break
            static = reader.read_static()
            if static != last_static:
                _write_record(out, _STATIC, elapsed, static)
                last_static = static
                statics += 1
            snapshot = reader.read()
            ids = (_packet_id(snapshot.physics), _packet_id(snapshot.graphics))
            if ids != last_ids:
                _write_record(out, _FRAME, elapsed, snapshot.physics + snapshot.graphics)
                last_ids = ids
                frames += 1
            sleep(interval)
    return DumpStats(frames=frames, static_blocks=statics, seconds=elapsed)


class RawDumpReader:
    """Replays a dump as a SharedMemoryReader, one recorded frame per ``read()``."""

    def __init__(self, path: Path) -> None:
        self._file = gzip.open(path, "rb")  # noqa: SIM115 - kept open until close()
        if self._file.readline() != MAGIC:
            self._file.close()
            raise ValueError(f"{path} no es un volcado crudo de RaceEngineerAI")
        sizes = json.loads(self._file.readline())
        expected = {"physics": PHYSICS_SIZE, "graphics": GRAPHICS_SIZE, "static": STATIC_SIZE}
        if sizes != expected:
            self._file.close()
            raise ValueError(f"Tamaños de bloque {sizes} no coinciden con {expected}")
        self._static = bytes(STATIC_SIZE)
        self._t = 0.0
        self._pending: Snapshot | None = None
        # Load the first static block so session_info works before any read().
        try:
            self._pending = self._next_frame()
        except EOFError:
            pass
        except ValueError:
            self._file.close()
            raise

    def read(self) -> Snapshot:
        if self._pending is not None:
            frame, self._pending = self._pending, None
            return frame
        return self._next_frame()

    def read_static(self) -> bytes:
        return self._static

    def clock(self) -> float:
        """Recorded time of the last frame returned, for replaying with original timing."""
        return self._t

    def close(self) -> None:
        self._file.close()

    def _next_frame(self) -> Snapshot:
        while True:
            header = self._file.read(_RECORD_HEADER.size)
            if len(header) < _RECORD_HEADER.size:
                raise EOFError
            tag, t = _RECORD_HEADER.unpack(header)
            if tag == _STATIC:
                self._static = self._read_exact(STATIC_SIZE)
            elif tag == _FRAME:
                self._t = t
                return Snapshot(
                    physics=self._read_exact(PHYSICS_SIZE),
                    graphics=self._read_exact(GRAPHICS_SIZE),
                )
            else:
                raise ValueError(f"Registro desconocido {tag!r} en el volcado")

    def _read_exact(self, size: int) -> bytes:
        data = self._file.read(size)
        if len(data) < size:
            raise EOFError
        return data


def _write_header(out: gzip.GzipFile) -> None:
    out.write(MAGIC)
    sizes = {"physics": PHYSICS_SIZE, "graphics": GRAPHICS_SIZE, "static": STATIC_SIZE}
    out.write(json.dumps(sizes).encode() + b"\n")


def _write_record(out: gzip.GzipFile, tag: bytes, t: float, payload: bytes) -> None:
    out.write(_RECORD_HEADER.pack(tag, t))
    out.write(payload)


def _packet_id(block: bytes) -> int:
    value: int = _PACKET_ID.unpack_from(block)[0]
    return value
