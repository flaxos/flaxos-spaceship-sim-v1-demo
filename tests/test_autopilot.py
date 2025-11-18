from sim import autopilot


def test_kill_velocity_uses_yaw_pitch_and_thrust():
    ship = {
        "velocity": [1.0, 0.0, 0.5],
        "orientation_euler_deg": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
        "physics": {
            "max_rcs_yaw_deg_s": 5.0,
            "max_rcs_pitch_deg_s": 4.0,
            "max_rcs_roll_deg_s": 3.0,
            "max_main_thrust_newton": 500_000.0,
        },
        "mass_kg": 500_000.0,
    }

    helm = autopilot.compute_kill_velocity_helm_inputs(ship)

    rot = helm["rotation_deg_s"]
    assert rot["yaw"] <= 0.0  # needs to turn toward 180 degrees
    assert abs(rot["yaw"]) <= 5.0
    assert rot["pitch"] < 0.0  # needs to nose down to oppose +Z velocity
    assert abs(rot["pitch"]) <= 4.0
    assert abs(rot["roll"]) <= 3.0

    thrust = helm["thrust_vector"]
    assert thrust[0] == 0.0 and thrust[1] == 0.0
    assert 0.1 <= thrust[2] <= 1.0


def test_point_at_target_orients_without_thrust():
    ship = {
        "position": [0.0, 0.0, 0.0],
        "orientation_euler_deg": {"yaw": 90.0, "pitch": 0.0, "roll": 10.0},
        "physics": {
            "max_rcs_yaw_deg_s": 10.0,
            "max_rcs_pitch_deg_s": 10.0,
            "max_rcs_roll_deg_s": 10.0,
        },
    }

    helm = autopilot.compute_point_at_target_helm_inputs(ship, [1.0, 0.0, 1.0])
    assert helm is not None
    assert helm["thrust_vector"] == [0.0, 0.0, 0.0]

    rot = helm["rotation_deg_s"]
    # Facing +X from yaw 90 should command negative yaw, positive pitch up toward +Z
    assert rot["yaw"] < 0.0
    assert rot["pitch"] > 0.0
    assert abs(rot["roll"]) <= 10.0
