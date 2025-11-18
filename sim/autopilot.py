"""Simple autopilot helpers for Flaxos Spaceship Sim.

These helpers operate on raw ship dicts and return helm input payloads that
respect the physics_v2 control contract:

{
  "thrust_vector": [sx, sy, sfwd],
  "rotation_deg_s": {"yaw": ..., "pitch": ..., "roll": ...}
}
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional


Vector3 = List[float]


def _normalise_vector(vec: Iterable[float]) -> Vector3:
    x, y, z = float(vec[0]), float(vec[1]), float(vec[2])
    mag = math.sqrt(x * x + y * y + z * z)
    if mag <= 1e-9:
        return [0.0, 0.0, 0.0]
    inv = 1.0 / mag
    return [x * inv, y * inv, z * inv]


def _wrap_angle_deg(angle: float) -> float:
    """Wrap an angle to the range [-180, 180]."""

    return (angle + 180.0) % 360.0 - 180.0


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _extract_euler(ship: Dict[str, Any]) -> Dict[str, float]:
    euler = ship.get("orientation_euler_deg") or {}
    return {
        "yaw": float(euler.get("yaw", ship.get("orientation_deg", 0.0))),
        "pitch": float(euler.get("pitch", 0.0)),
        "roll": float(euler.get("roll", 0.0)),
    }


def _physics_limits(ship: Dict[str, Any]) -> Dict[str, float]:
    physics = ship.get("physics") or {}
    yaw = float(physics.get("max_rcs_yaw_deg_s", 10.0))
    pitch = float(physics.get("max_rcs_pitch_deg_s", yaw))
    roll = float(physics.get("max_rcs_roll_deg_s", yaw))
    return {"yaw": yaw, "pitch": pitch, "roll": roll}


def _mass_and_thrust(ship: Dict[str, Any]) -> Dict[str, float]:
    physics = ship.get("physics") or {}
    return {
        "mass": float(ship.get("mass_kg", 1_000_000.0)),
        "max_thrust": float(physics.get("max_main_thrust_newton", 1_000_000.0)),
    }


def _desired_angles_for_direction(direction: Vector3) -> Dict[str, float]:
    """Return yaw/pitch angles (deg) to face the given world-space direction."""

    dx, dy, dz = direction
    yaw = math.degrees(math.atan2(dy, dx))
    horiz_mag = math.sqrt(dx * dx + dy * dy)
    pitch = math.degrees(math.atan2(dz, horiz_mag))
    return {"yaw": yaw, "pitch": pitch}


def _rotation_command_towards(euler: Dict[str, float], desired: Dict[str, float], limits: Dict[str, float]) -> Dict[str, float]:
    yaw_err = _wrap_angle_deg(desired["yaw"] - euler["yaw"])
    pitch_err = _wrap_angle_deg(desired["pitch"] - euler["pitch"])
    roll_err = _wrap_angle_deg(0.0 - euler["roll"])

    k = 1.0
    return {
        "yaw": _clamp(k * yaw_err, -limits["yaw"], limits["yaw"]),
        "pitch": _clamp(k * pitch_err, -limits["pitch"], limits["pitch"]),
        "roll": _clamp(k * roll_err, -limits["roll"], limits["roll"]),
    }


def compute_kill_velocity_helm_inputs(ship: Dict[str, Any]) -> Dict[str, Any]:
    """Compute helm inputs that try to cancel the ship's velocity vector.

    This is a conservative controller that points the ship roughly opposite the
    current velocity vector and applies a braking thrust along the main drive.
    """

    velocity = ship.get("velocity") or [0.0, 0.0, 0.0]
    vel_vec = [float(velocity[0]), float(velocity[1]), float(velocity[2])]
    speed = math.sqrt(vel_vec[0] ** 2 + vel_vec[1] ** 2 + vel_vec[2] ** 2)

    if speed <= 1e-6:
        return {
            "thrust_vector": [0.0, 0.0, 0.0],
            "rotation_deg_s": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
        }

    desired_dir = _normalise_vector([-vel_vec[0], -vel_vec[1], -vel_vec[2]])
    desired_angles = _desired_angles_for_direction(desired_dir)

    euler = _extract_euler(ship)
    limits = _physics_limits(ship)
    rotation_cmd = _rotation_command_towards(euler, desired_angles, limits)

    # Throttle proportionally to speed and ship capability (very simple model)
    phys = _mass_and_thrust(ship)
    max_accel = phys["max_thrust"] / max(phys["mass"], 1.0)
    throttle = _clamp(speed / max(max_accel * 5.0, 1e-3), 0.1, 1.0)

    return {
        "thrust_vector": [0.0, 0.0, throttle],
        "rotation_deg_s": rotation_cmd,
    }


def compute_point_at_target_helm_inputs(ship: Dict[str, Any], target_position: List[float]) -> Optional[Dict[str, Any]]:
    """Compute helm inputs to orient the ship toward a target position.

    Thrust is not applied in this mode (orientation only).
    """

    if not (isinstance(target_position, (list, tuple)) and len(target_position) == 3):
        return None

    ship_pos = ship.get("position") or [0.0, 0.0, 0.0]
    dx = float(target_position[0]) - float(ship_pos[0])
    dy = float(target_position[1]) - float(ship_pos[1])
    dz = float(target_position[2]) - float(ship_pos[2])

    dir_vec = _normalise_vector([dx, dy, dz])
    if dir_vec == [0.0, 0.0, 0.0]:
        return None

    desired_angles = _desired_angles_for_direction(dir_vec)
    euler = _extract_euler(ship)
    limits = _physics_limits(ship)
    rotation_cmd = _rotation_command_towards(euler, desired_angles, limits)

    return {
        "thrust_vector": [0.0, 0.0, 0.0],
        "rotation_deg_s": rotation_cmd,
    }

