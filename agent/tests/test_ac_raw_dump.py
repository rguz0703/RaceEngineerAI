import gzip
from pathlib import Path

import pytest
from ac_blocks import ScriptedReader, snapshot, static_bytes

from raceengineer.adapters.ac_raw_dump import MAGIC, RawDumpReader, dump_raw
from raceengineer.adapters.ac_shared_memory import ACSharedMemorySource, ACStatus, Snapshot


class _Clock:
    def __init__(self, step: float) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        value = self.now
        self.now += self.step
        return value


class _ChangingStaticReader(ScriptedReader):
    def read_static(self) -> bytes:
        return static_bytes(track="spa" if self.reads < 2 else "monza")


def _dump(tmp_path: Path, reader: ScriptedReader, seconds: float = 10.0) -> Path:
    path = tmp_path / "dumps" / "test.acraw.gz"
    dump_raw(reader, path, seconds, clock=_Clock(0.5), sleep=lambda _: None)
    return path


def test_dump_writes_only_changed_frames_and_replays_them(tmp_path: Path) -> None:
    reader = ScriptedReader(
        [
            snapshot(1, ACStatus.OFF),
            snapshot(2, speedKmh=100.0),
            snapshot(2, speedKmh=100.0),
            snapshot(3, speedKmh=120.0),
        ]
    )
    path = tmp_path / "dump.acraw.gz"

    stats = dump_raw(reader, path, seconds=2.5, clock=_Clock(0.5), sleep=lambda _: None)

    assert stats.frames == 3
    assert stats.static_blocks == 1
    replay = RawDumpReader(path)
    source = ACSharedMemorySource(replay, clock=replay.clock, sleep=lambda _: None)
    assert source.session_info().track == "magione"
    samples = list(source.samples())
    replay.close()
    assert [s.speed_kmh for s in samples] == [100.0, 120.0]
    assert [s.t for s in samples] == [0.0, 1.0]


def test_dump_records_static_changes(tmp_path: Path) -> None:
    reader = _ChangingStaticReader([snapshot(i) for i in range(1, 5)])
    path = _dump(tmp_path, reader, seconds=2.0)

    replay = RawDumpReader(path)
    tracks = []
    try:
        while True:
            replay.read()
            tracks.append(ACSharedMemorySource(replay).session_info().track)
    except EOFError:
        pass
    replay.close()
    assert tracks[0] == "spa"
    assert tracks[-1] == "monza"


def test_dump_without_frames_replays_empty(tmp_path: Path) -> None:
    path = _dump(tmp_path, ScriptedReader([snapshot(1)]), seconds=0.0)
    replay = RawDumpReader(path)
    with pytest.raises(EOFError):
        replay.read()
    replay.close()


def test_dump_rejects_non_positive_poll_rate(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        dump_raw(ScriptedReader([]), tmp_path / "x.gz", 1.0, poll_hz=0)


def _write(path: Path, payload: bytes) -> Path:
    with gzip.open(path, "wb") as out:
        out.write(payload)
    return path


def test_reader_rejects_other_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no es un volcado"):
        RawDumpReader(_write(tmp_path / "bad.gz", b"hello\n"))


def test_reader_rejects_different_layout(tmp_path: Path) -> None:
    sizes = b'{"physics": 1, "graphics": 2, "static": 3}\n'
    with pytest.raises(ValueError, match="no coinciden"):
        RawDumpReader(_write(tmp_path / "old.gz", MAGIC + sizes))


def test_reader_rejects_unknown_records_and_truncation(tmp_path: Path) -> None:
    good = _dump(tmp_path, ScriptedReader([snapshot(1)]), seconds=1.0)
    with gzip.open(good, "rb") as f:
        data = f.read()
    header_end = data.index(b"\n", len(MAGIC)) + 1

    with pytest.raises(ValueError, match="desconocido"):
        RawDumpReader(_write(tmp_path / "x.gz", data[:header_end] + b"X" + bytes(8)))

    truncated = RawDumpReader(_write(tmp_path / "t.gz", data[:-10]))
    with pytest.raises(EOFError):
        truncated.read()
    truncated.close()


def test_snapshot_is_value_object() -> None:
    assert Snapshot(b"a", b"b") == Snapshot(b"a", b"b")
