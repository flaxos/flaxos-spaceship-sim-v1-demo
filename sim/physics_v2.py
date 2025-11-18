"""
sim/physics_v2.py

Newtonian 3D physics and simple gravity wells for Flaxos Spaceship Sim.

This module is intentionally dict-based so it can be dropped into the existing
sim without needing to change your internal ship state structures.

Assumptions (from current get_state payloads):
- Ship dict shape roughly:

  {
    "id": "interceptor_alpha",
    "mass_kg": 1_000_000,
    "position": [x, y, z],          # km
    "velocity": [vx, vy, vz],       # km/s
    "orientation_deg": 0.0,         # legacy: yaw-only
    "orientation_euler_deg": {      # new, optional
        "yaw": 0.0,
        "pitch": 0.0,
        "roll": 0.0
    },
    "controls": {
        "thrust_vector": [sx, sy, sfwd],   # control -1..1
        "rotation_deg_s": {
            "yaw": 0.0, "pitch": 0.0, "roll": 0.0
        }
    },
    "physics": {
        "max_main_thrust_newton": 1_000_000.0,
        "max_rcs_yaw_deg_s": 10.0,
        "max_rcs_pitch_deg_s": 10.0,
        "max_rcs_roll_deg_s": 10.0,
        "max_rcs_linear_m_s2": 1.0
    }
  }

- We treat thrust_vector[2] (index 2) as the "forward" control component for
  backward compatibility with the v1.0 demo.

- World coordinate system:
    x, y, z in km
    velocities in km/s
    accelerations in km/s^2

- Gravity bodies come from mission config (see below).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Gravitational constant in km^3 / (kg * s^2)
G_CONST_KM = 6.67430e-20


Vector3 = List[float]
ShipDict = Dict[str, Any]
GravBodyDict = Dict[str, Any]


def _ensure_orientation_euler(ship: ShipDict) -> Dict[str, float]:
    """
    Ensure ship has an orientation_euler_deg dict with yaw/pitch/roll.

    If only legacy orientation_deg is present, treat it as yaw.
    """
    euler = ship.get("orientation_euler_deg")
    if not isinstance(euler, dict):
        yaw = float(ship.get("orientation_deg", 0.0))
        euler = {"yaw": yaw, "pitch": 0.0, "roll": 0.0}
        ship["orientation_euler_deg"] = euler
    else:
        euler.setdefault("yaw", float(ship.get("orientation_deg", 0.0)))
        euler.setdefault("pitch", 0.0)
        euler.setdefault("roll", 0.0)

    # Keep legacy orientation_deg in sync with yaw for API backward compatibility
    ship["orientation_deg"] = float(euler["yaw"])
    return euler


def _get_controls(ship: ShipDict) -> Tuple[Vector3, Dict[str, float]]:
    controls = ship.get("controls")
    if not isinstance(controls, dict):
        controls = {}
        ship["controls"] = controls

    thrust_vec = controls.get("thrust_vector")
    if not (isinstance(thrust_vec, list) and len(thrust_vec) == 3):
        thrust_vec = [0.0, 0.0, 0.0]
        controls["thrust_vector"] = thrust_vec

    rot = controls.get("rotation_deg_s")
    if not isinstance(rot, dict):
        rot = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
        controls["rotation_deg_s"] = rot
    else:
        rot.setdefault("yaw", 0.0)
        rot.setdefault("pitch", 0.0)
        rot.setdefault("roll", 0.0)

    return thrust_vec, rot


def _get_physics_limits(ship: ShipDict) -> Dict[str, float]:
    physics = ship.get("physics")
    if not isinstance(physics, dict):
        physics = {}
        ship["physics"] = physics

    physics.setdefault("max_main_thrust_newton", 1_000_000.0)
    physics.setdefault("max_rcs_yaw_deg_s", 10.0)
    physics.setdefault("max_rcs_pitch_deg_s", physics["max_rcs_yaw_deg_s"])
    physics.setdefault("max_rcs_roll_deg_s", physics["max_rcs_yaw_deg_s"])
    physics.setdefault("max_rcs_linear_m_s2", 1.0)

    return physics


def _deg_to_rad(deg: float) -> float:
    return deg * math.pi / 180.0


def _compose_rotation_matrix_yaw_pitch_roll(
    yaw_deg: float, pitch_deg: float, roll_deg: float
) -> List[List[float]]:
    """
    Construct a 3x3 rotation matrix from yaw, pitch, roll (in degrees).

    Convention:
        - Yaw   about +Z (turning in X/Y plane)
        - Pitch about +Y (nose up/down)
        - Roll  about +X (roll around forward axis)

    Rotation order: Rz(yaw) * Ry(pitch) * Rx(roll)
    """
    yaw = _deg_to_rad(yaw_deg)
    pitch = _deg_to_rad(pitch_deg)
    roll = _deg_to_rad(roll_deg)

    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)

    # Rx
    rx = [
        [1.0, 0.0, 0.0],
        [0.0, cr, -sr],
        [0.0, sr, cr],
    ]

    # Ry
    ry = [
        [cp, 0.0, sp],
        [0.0, 1.0, 0.0],
        [-sp, 0.0, cp],
    ]

    # Rz
    rz = [
        [cy, -sy, 0.0],
        [sy, cy, 0.0],
        [0.0, 0.0, 1.0],
    ]

    def mat_mul(a: List[List[float]], b: List[List[float]]) -> List[List[float]]:
        out = [[0.0, 0.0, 0.0] for _ in range(3)]
        for i in range(3):
            for j in range(3):
                out[i][j] = (
                    a[i][0] * b[0][j]
                    + a[i][1] * b[1][j]
                    + a[i][2] * b[2][j]
                )
        return out

    rzy = mat_mul(rz, ry)
    r = mat_mul(rzy, rx)
    return r


def _apply_rotation(mat: List[List[float]], v: Vector3) -> Vector3:
    x = mat[0][0] * v[0] + mat[0][1] * v[1] + mat[0][2] * v[2]
    y = mat[1][0] * v[0] + mat[1][1] * v[1] + mat[1][2] * v[2]
    z = mat[2][0] * v[0] + mat[2][1] * v[1] + mat[2][2] * v[2]
    return [x, y, z]


def compute_gravity_accel(
    position_km: Vector3, grav_bodies: Sequence[GravBodyDict]
) -> Vector3:
    """
    Compute gravitational acceleration at a given position due to a set of grav bodies.

    Grav body shape (mission-level schema):

    {
      "id": "ceres",
      "mass_kg": 9.4e20,
      "position": [x, y, z],           # km
      "radius_km": 473.0,
      "gravity_enabled": true,
      "cutoff_radius_km": 1.0e6
    }
    """
    ax = ay = az = 0.0
    px, py, pz = position_km

    for body in grav_bodies:
        if not body.get("gravity_enabled", True):
            continue

        bx, by, bz = body.get("position", [0.0, 0.0, 0.0])
        dx = px - bx
        dy = py - by
        dz = pz - bz
        r2 = dx * dx + dy * dy + dz * dz
        if r2 <= 1e-12:
            continue

        cutoff = body.get("cutoff_radius_km")
        if cutoff is not None and r2 > cutoff * cutoff:
            continue

        mass = float(body.get("mass_kg", 0.0))
        if mass <= 0.0:
            continue

        r = math.sqrt(r2)
        factor = -G_CONST_KM * mass / (r2 * r)
        ax += factor * dx
        ay += factor * dy
        az += factor * dz

    return [ax, ay, az]


def update_ship_physics(
    ship: ShipDict,
    dt_s: float,
    grav_bodies: Optional[Sequence[GravBodyDict]] = None,
) -> None:
    """
    Advance a single ship's physics state by dt_s.

    - Applies RCS-driven orientation updates based on rotation_deg_s and max_rcs_* limits.
    - Applies main drive thrust along ship forward axis (using thrust_vector[2] as 'forward' control).
    - Adds gravity acceleration from grav_bodies if provided.

    Mutates the ship dict in-place.
    """
    if dt_s <= 0.0:
        return

    grav_bodies = grav_bodies or []

    mass_kg = float(ship.get("mass_kg", 1_000_000.0))

    pos = ship.get("position")
    if not (isinstance(pos, list) and len(pos) == 3):
        pos = [0.0, 0.0, 0.0]
        ship["position"] = pos

    vel = ship.get("velocity")
    if not (isinstance(vel, list) and len(vel) == 3):
        vel = [0.0, 0.0, 0.0]
        ship["velocity"] = vel

    euler = _ensure_orientation_euler(ship)
    thrust_vec, rot_input = _get_controls(ship)
    physics = _get_physics_limits(ship)

    # --- 1) Update orientation from rotation_deg_s (RCS) ---
    yaw_rate = float(rot_input.get("yaw", 0.0))
    pitch_rate = float(rot_input.get("pitch", 0.0))
    roll_rate = float(rot_input.get("roll", 0.0))

    max_yaw = float(physics["max_rcs_yaw_deg_s"])
    max_pitch = float(physics["max_rcs_pitch_deg_s"])
    max_roll = float(physics["max_rcs_roll_deg_s"])

    yaw_rate = max(-max_yaw, min(max_yaw, yaw_rate))
    pitch_rate = max(-max_pitch, min(max_pitch, pitch_rate))
    roll_rate = max(-max_roll, min(max_roll, roll_rate))

    euler["yaw"] = (float(euler["yaw"]) + yaw_rate * dt_s) % 360.0
    euler["pitch"] = max(-89.9, min(89.9, float(euler["pitch"]) + pitch_rate * dt_s))
    euler["roll"] = (float(euler["roll"]) + roll_rate * dt_s) % 360.0

    ship["orientation_deg"] = float(euler["yaw"])

    # --- 2) Compute thrust acceleration in ship-local frame ---
    sx, sy, sfwd = float(thrust_vec[0]), float(thrust_vec[1]), float(thrust_vec[2])
    max_main_thrust = float(physics.get("max_main_thrust_newton", 1_000_000.0))

    main_accel_m_s2 = (sfwd * max_main_thrust) / mass_kg
    main_accel_km_s2 = main_accel_m_s2 / 1000.0

    # For now, main drive thrusts along local +X axis; RCS translation reserved for future
    local_accel = [main_accel_km_s2, 0.0, 0.0]

    rot_mat = _compose_rotation_matrix_yaw_pitch_roll(
        euler["yaw"], euler["pitch"], euler["roll"]
    )
    accel_world = _apply_rotation(rot_mat, local_accel)

    grav_accel = compute_gravity_accel(pos, grav_bodies)
    accel_world[0] += grav_accel[0]
    accel_world[1] += grav_accel[1]
    accel_world[2] += grav_accel[2]

    vel[0] += accel_world[0] * dt_s
    vel[1] += accel_world[1] * dt_s
    vel[2] += accel_world[2] * dt_s

    pos[0] += vel[0] * dt_s
    pos[1] += vel[1] * dt_s
    pos[2] += vel[2] * dt_s

    ship["velocity"] = vel
    ship["position"] = pos
    ship["orientation_euler_deg"] = euler
