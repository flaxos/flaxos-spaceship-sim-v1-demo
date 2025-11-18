import pytest

from tools.ship_os_shell import (
    DEFAULT_ROTATION_LIMIT_DEG_S,
    parse_rotation_command,
    parse_thrust_command,
)


def test_parse_thrust_forward_sets_forward_component_only():
    result = parse_thrust_command(["0.5", "forward"], [0.0, 0.1, 0.0])
    assert result == [0.0, 0.1, 0.5]


def test_parse_thrust_lateral_and_vertical_components():
    vec = parse_thrust_command(["0.3", "left"], [0.0, 0.0, 0.0])
    assert vec == [0.0, 0.3, 0.0]

    vec = parse_thrust_command(["0.2", "up"], vec)
    assert vec == [0.2, 0.3, 0.0]


def test_parse_thrust_stop_resets_vector():
    vec = parse_thrust_command(["0.7", "stop"], [0.1, 0.2, 0.3])
    assert vec == [0.0, 0.0, 0.0]


def test_parse_thrust_clamps_to_one():
    vec = parse_thrust_command(["2.5", "forward"], [0.0, 0.0, 0.0])
    assert vec == [0.0, 0.0, 1.0]


def test_parse_rotation_command_defaults_and_directions():
    rotation = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
    limits = {"yaw": 15.0, "pitch": 20.0, "roll": 10.0}

    rotation = parse_rotation_command("yaw", ["5"], rotation, limits)
    assert rotation == {"yaw": 5.0, "pitch": 0.0, "roll": 0.0}

    rotation = parse_rotation_command("pitch", ["3", "down"], rotation, limits)
    assert rotation == {"yaw": 5.0, "pitch": -3.0, "roll": 0.0}

    rotation = parse_rotation_command("roll", ["2", "right"], rotation, limits)
    assert rotation == {"yaw": 5.0, "pitch": -3.0, "roll": -2.0}


def test_parse_rotation_stop_and_clamp():
    rotation = {"yaw": 5.0, "pitch": 5.0, "roll": 5.0}
    limits = {"yaw": DEFAULT_ROTATION_LIMIT_DEG_S, "pitch": 5.0, "roll": 5.0}

    rotation = parse_rotation_command("pitch", ["stop"], rotation, limits)
    assert rotation["pitch"] == 0.0

    rotation = parse_rotation_command("roll", ["9", "left"], rotation, limits)
    assert rotation["roll"] == 5.0


def test_parse_rotation_invalid_direction():
    with pytest.raises(ValueError):
        parse_rotation_command(
            "pitch",
            ["1", "sideways"],
            {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            {},
        )
