import ctypes
from threading import Event

import pytest
from ac_blocks import (
    FakeTime,
    ScriptedReader,
    graphics_bytes,
    physics_bytes,
    snapshot,
    static_bytes,
)

from raceengineer.adapters.ac_shared_memory import (
    GRAPHICS_SIZE,
    PHYSICS_SIZE,
    STATIC_SIZE,
    ACNotRunningError,
    ACSharedMemorySource,
    ACStatus,
    Pacer,
    SPageFileGraphic,
    SPageFilePhysics,
    SPageFileStatic,
    open_live_reader,
    parse_graphics,
    parse_physics,
    parse_static,
    session_info_from_static,
    to_sample,
)


def test_block_sizes_match_shared_memory_v1_7() -> None:
    assert (PHYSICS_SIZE, GRAPHICS_SIZE, STATIC_SIZE) == (580, 288, 648)


@pytest.mark.parametrize(
    ("struct", "field", "offset"),
    [
        (SPageFilePhysics, "packetId", 0),
        (SPageFilePhysics, "gear", 16),
        (SPageFilePhysics, "speedKmh", 28),
        (SPageFilePhysics, "clutch", 364),
        (SPageFileGraphic, "status", 4),
        (SPageFileGraphic, "completedLaps", 132),
        (SPageFileGraphic, "iCurrentTime", 140),
        (SPageFileGraphic, "normalizedCarPosition", 248),
        (SPageFileStatic, "carModel", 68),
        (SPageFileStatic, "track", 134),
        (SPageFileStatic, "sectorCount", 400),
        (SPageFileStatic, "trackConfiguration", 524),
    ],
)
def test_field_offsets(struct: type[ctypes.Structure], field: str, offset: int) -> None:
    assert getattr(struct, field).offset == offset


def test_to_sample_normalizes_values() -> None:
    physics = parse_physics(
        physics_bytes(
            7, gas=0.8, brake=1.2, clutch=0.25, steerAngle=-1.5, gear=4, rpms=6500, speedKmh=152.5
        )
    )
    graphics = parse_graphics(
        graphics_bytes(
            3,
            coordinates=(10.0, 2.0, -30.0),
            completedLaps=2,
            iCurrentTime=45_123,
            normalizedCarPosition=0.42,
            isInPitLane=1,
        )
    )

    sample = to_sample(physics, graphics, t=12.5)

    assert sample.t == 12.5
    assert sample.lap_number == 2
    assert sample.lap_time_ms == 45_123
    assert sample.normalized_position == pytest.approx(0.42)
    assert sample.speed_kmh == pytest.approx(152.5)
    assert sample.throttle == pytest.approx(0.8)
    assert sample.brake == 1.0
    assert sample.clutch == pytest.approx(0.75)
    assert sample.steering == -1.0
    assert sample.gear == 3
    assert sample.rpm == 6500.0
    assert (sample.pos_x, sample.pos_y, sample.pos_z) == (10.0, 2.0, -30.0)
    assert sample.in_pit is True


@pytest.mark.parametrize(("ac_gear", "gear"), [(0, -1), (1, 0), (2, 1)])
def test_gear_mapping(ac_gear: int, gear: int) -> None:
    physics = parse_physics(physics_bytes(gear=ac_gear))
    assert to_sample(physics, parse_graphics(graphics_bytes()), 0.0).gear == gear


def test_session_info_from_static() -> None:
    info = session_info_from_static(
        parse_static(static_bytes(car="ks_ferrari_488_gt3", track="ks_nurburgring", config="gp"))
    )
    assert info.sim == "assetto_corsa"
    assert info.car == "ks_ferrari_488_gt3"
    assert info.track == "ks_nurburgring"
    assert info.track_config == "gp"


def test_parsers_accept_longer_blocks_from_newer_versions() -> None:
    data = physics_bytes(9, speedKmh=88.0) + b"\xff" * 64
    assert parse_physics(data).speedKmh == pytest.approx(88.0)


def _source(reader: ScriptedReader, stop: Event | None = None) -> ACSharedMemorySource:
    time = FakeTime(start=100.0)
    return ACSharedMemorySource(reader, poll_hz=100, stop=stop, clock=time.clock, sleep=time.sleep)


def test_emits_only_live_samples_with_new_packet_ids() -> None:
    reader = ScriptedReader(
        [
            snapshot(1, ACStatus.OFF),
            snapshot(2, speedKmh=10.0),
            snapshot(2, speedKmh=10.0),
            snapshot(3, ACStatus.PAUSE),
            snapshot(4, ACStatus.REPLAY),
            snapshot(5, speedKmh=50.0),
        ]
    )

    samples = list(_source(reader).samples())

    assert [s.speed_kmh for s in samples] == [10.0, 50.0]
    assert samples[0].t == 0.0
    assert samples[1].t == pytest.approx(0.04)


def test_ends_when_game_returns_to_off_after_being_live() -> None:
    reader = ScriptedReader([snapshot(1), snapshot(2, ACStatus.OFF), snapshot(3)])
    assert len(list(_source(reader).samples())) == 1
    assert reader.reads == 2


def test_unknown_status_is_treated_as_off() -> None:
    reader = ScriptedReader([snapshot(1, ACStatus.LIVE), snapshot(2, 99)])  # type: ignore[arg-type]
    assert len(list(_source(reader).samples())) == 1


def test_stop_event_ends_stream() -> None:
    stop = Event()
    reader = ScriptedReader([snapshot(i) for i in range(1, 10)])
    source = _source(reader, stop)
    stream = source.samples()
    next(stream)
    stop.set()
    assert list(stream) == []


def test_session_info_reads_static_block() -> None:
    reader = ScriptedReader([], static=static_bytes(track="spa"))
    assert _source(reader).session_info().track == "spa"


def test_rejects_non_positive_poll_rate() -> None:
    with pytest.raises(ValueError):
        ACSharedMemorySource(ScriptedReader([]), poll_hz=0)


def test_open_live_reader_without_game_explains_error() -> None:
    # On macOS: AC is Windows only. On Windows CI: AC is not running.
    with pytest.raises(ACNotRunningError):
        open_live_reader()


def test_pacer_absorbs_loop_work_time() -> None:
    time = FakeTime()
    pacer = Pacer(0.01, time.clock, time.sleep)
    for _ in range(3):
        time.now += 0.004  # work done by the loop body
        pacer.wait()
    assert time.sleeps == pytest.approx([0.01, 0.006, 0.006])


def test_pacer_resyncs_when_behind() -> None:
    time = FakeTime()
    pacer = Pacer(0.01, time.clock, time.sleep)
    pacer.wait()
    time.now += 0.05  # a long stall
    pacer.wait()
    pacer.wait()
    assert time.sleeps == pytest.approx([0.01, 0.01])


def test_to_sample_reads_car_state_and_slip() -> None:
    physics = parse_physics(physics_bytes(speedKmh=72.0, brakeBias=0.6, abs=0.2, fuel=40.0))
    physics.wheelsPressure[0] = 27.5
    physics.tyreTempI[3] = 91.0
    physics.wheelAngularSpeed[0] = 0.0  # locked
    physics.wheelAngularSpeed[1] = 20.0 / 0.3  # rolling: 20 m/s
    physics.localAngularVel[1] = -0.4

    sample = to_sample(physics, parse_graphics(graphics_bytes()), 0.0, [0.3, 0.3, 0.3, 0.3])

    assert sample.tyre_pressure_fl == pytest.approx(27.5)
    assert sample.tyre_temp_inner_rr == pytest.approx(91.0)
    assert sample.slip_ratio_fl == -1.0
    assert sample.slip_ratio_fr == pytest.approx(0.0, abs=1e-6)
    assert sample.yaw_rate == pytest.approx(-0.4)
    assert (sample.brake_bias, sample.abs, sample.fuel) == pytest.approx((0.6, 0.2, 40.0))


def test_slip_ratio_is_zero_when_slow_or_without_radius() -> None:
    physics = parse_physics(physics_bytes(speedKmh=10.0))
    assert to_sample(physics, parse_graphics(graphics_bytes()), 0.0, [0.3] * 4).slip_ratio_fl == 0
    fast = parse_physics(physics_bytes(speedKmh=100.0))
    assert to_sample(fast, parse_graphics(graphics_bytes()), 0.0).slip_ratio_fl == 0


def test_session_info_includes_compound_from_graphics() -> None:
    graphics = SPageFileGraphic(status=2)
    for i, ch in enumerate("Slick Cup (H)"):
        graphics.tyreCompound[i] = ord(ch)
    info = session_info_from_static(parse_static(static_bytes()), graphics)
    assert info.tyre_compound == "Slick Cup (H)"


def test_probe_game_states() -> None:
    from raceengineer.adapters.ac_shared_memory import probe_game

    def opener(*snapshots: object) -> object:
        return lambda: ScriptedReader(list(snapshots), static=static_bytes(track="spa"))  # type: ignore[arg-type]

    live = probe_game(opener(snapshot(1)))  # type: ignore[arg-type]
    assert (live.state, live.track) == ("live", "spa")
    assert probe_game(opener(snapshot(1, ACStatus.OFF))).state == "off"  # type: ignore[arg-type]
    assert probe_game(opener(snapshot(1, ACStatus.PAUSE))).state == "pause"  # type: ignore[arg-type]
    assert probe_game(opener()).state == "closed"  # type: ignore[arg-type]

    def missing() -> ScriptedReader:
        raise ACNotRunningError("no")

    gone = probe_game(missing)
    assert gone.state in ("closed", "unavailable")
    assert gone.message == "no"
