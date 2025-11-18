from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

# Gravitational constant (SI units)
G = 6.67430e-11

Vec3 = Tuple[float, float, float]


# ---------- basic vector helpers ----------

def v_add(a: Vec3, b: Vec3) -> Vec3:
    return a[0] + b[0], a[1] + b[1], a[2] + b[2]


def v_sub(a: Vec3, b: Vec3) -> Vec3:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def v_scale(a: Vec3, s: float) -> Vec3:
    return a[0] * s, a[1] * s, a[2] * s


def v_length(a: Vec3) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def v_normalise(a: Vec3) -> Vec3:
    length = v_length(a)
    if length <= 1e-9:
        return 0.0, 0.0, 0.0
    inv = 1.0 / length
    return a[0] * inv, a[1] * inv, a[2] * inv


# ---------- gravity scaffolding ----------


@dataclass
class GravBody:
    """Simple point-mass gravity source.

    This is intentionally minimal: it is enough to model a local gravity well
    (asteroid, small moon, planet) and can be extended later with radius and
    shape information without changing the API.
    """

    id: str
    name: str
    mass_kg: float
    position: Vec3
    gravity_radius_m: float

    @property
    def mu(self) -> float:
        """Standard gravitational parameter GM for this body."""
        return G * self.mass_kg


def gravity_accel_at_point(position: Vec3, bodies: Iterable[GravBody]) -> Vec3:
    """Compute gravitational acceleration at a point from a set of bodies.

    - Each body acts as a point mass at `body.position`.
    - If the distance exceeds `gravity_radius_m`, that body is ignored.
    - This is a *local* gravity model; full orbital mechanics can be layered
      on top of the same GravBody structure later.
    """

    ax, ay, az = 0.0, 0.0, 0.0
    px, py, pz = position

    for body in bodies:
        dx = body.position[0] - px
        dy = body.position[1] - py
        dz = body.position[2] - pz
        r2 = dx * dx + dy * dy + dz * dz
        if r2 <= 1e-6:
            # Avoid singularities if we're exactly at the body's centre.
            continue
        r = math.sqrt(r2)
        if r > body.gravity_radius_m:
            # Outside this body's influence radius.
            continue

        inv_r3 = body.mu / (r2 * r)
        ax += dx * inv_r3
        ay += dy * inv_r3
        az += dz * inv_r3

    return ax, ay, az


# ---------- orientation helpers ----------


def yaw_deg_to_forward_vector(yaw_deg: float) -> Vec3:
    """Convert a yaw angle in degrees into a forward unit vector.

    For now we only model yaw (rotation about the Z axis). Pitch and roll are
    reserved for future expansion to full 6DOF.
    """
    rad = math.radians(yaw_deg)
    return math.cos(rad), math.sin(rad), 0.0


# ---------- ship & projectile integration ----------


def update_ship_kinematics(
    ship: Dict[str, Any],
    dt: float,
    grav_bodies: Iterable[GravBody],
) -> None:
    """Integrate a single ship's position and velocity for one tick.

    This function is the canonical place where:
    - Mass-based thrust is applied.
    - Gravity wells act on ships.
    - Rotational input (yaw) is applied.

    Control contract (Sprint 1):

    - ship["controls"]["thrust_vector"] is a 3-element list [tx, ty, tz]
      in ship-local axes, clamped to [-1, 1].  In v2.1 only tz (main drive)
      is applied; tx/ty are reserved for future lateral/vertical RCS.
    - ship["controls"]["rotation_deg_s"] is a dict:
      {"yaw": yaw_rate, "pitch": pitch_rate, "roll": roll_rate}
      In v2.1 only yaw_rate is applied; pitch/roll are placeholders.
    """

    # --- position / velocity ---
    pos_list = ship.get("position") or [0.0, 0.0, 0.0]
    vel_list = ship.get("velocity") or [0.0, 0.0, 0.0]
    pos: Vec3 = (float(pos_list[0]), float(pos_list[1]), float(pos_list[2]))
    vel: Vec3 = (float(vel_list[0]), float(vel_list[1]), float(vel_list[2]))

    mass_kg = float(ship.get("mass_kg", 1_000_000.0))
    yaw = float(ship.get("orientation_deg", 0.0))

    controls = ship.get("controls") or {}

    # Normalise thrust_vector to length 3 and clamp components to [-1, 1].
    thrust_vec = controls.get("thrust_vector") or [0.0, 0.0, 0.0]
    if not isinstance(thrust_vec, (list, tuple)):
        thrust_vec = [0.0, 0.0, 0.0]
    if len(thrust_vec) < 3:
        thrust_vec = list(thrust_vec) + [0.0] * (3 - len(thrust_vec))
    elif len(thrust_vec) > 3:
        thrust_vec = list(thrust_vec[:3])
    thrust_vec = [max(-1.0, min(1.0, float(c))) for c in thrust_vec]

    # Normalise rotation_deg_s into a dict {yaw, pitch, roll}.
    rotation_ctrl = controls.get("rotation_deg_s") or 0.0
    if isinstance(rotation_ctrl, (int, float)):
        yaw_rate = float(rotation_ctrl)
        pitch_rate = 0.0
        roll_rate = 0.0
    elif isinstance(rotation_ctrl, dict):
        yaw_rate = float(rotation_ctrl.get("yaw", 0.0))
        pitch_rate = float(rotation_ctrl.get("pitch", 0.0))
        roll_rate = float(rotation_ctrl.get("roll", 0.0))
    else:
        yaw_rate = 0.0
        pitch_rate = 0.0
        roll_rate = 0.0

    # Physics configuration (per-ship capability caps).
    physics_cfg = ship.get("physics") or {}
    max_thrust_newton = float(physics_cfg.get("max_main_thrust_newton", 1_000_000.0))
    max_yaw_rate_deg_s = float(physics_cfg.get("max_rcs_yaw_deg_s", 10.0))
    # Pitch/roll limits reserved for future extension.
    # max_pitch_rate_deg_s = float(physics_cfg.get("max_rcs_pitch_deg_s", max_yaw_rate_deg_s))
    # max_roll_rate_deg_s = float(physics_cfg.get("max_rcs_roll_deg_s", max_yaw_rate_deg_s))

    # Clamp yaw rate to ship capability.
    if yaw_rate > max_yaw_rate_deg_s:
        yaw_rate = max_yaw_rate_deg_s
    elif yaw_rate < -max_yaw_rate_deg_s:
        yaw_rate = -max_yaw_rate_deg_s

    # --- main drive thrust ---
    forward_throttle = float(thrust_vec[2])
    forward_throttle = max(-1.0, min(1.0, forward_throttle))

    thrust_accel: Vec3 = (0.0, 0.0, 0.0)
    if abs(forward_throttle) > 1e-3 and mass_kg > 1.0:
        forward_world = yaw_deg_to_forward_vector(yaw)
        accel_mag = (max_thrust_newton * forward_throttle) / mass_kg
        thrust_accel = v_scale(forward_world, accel_mag)

    # --- gravity ---
    grav_accel = gravity_accel_at_point(pos, grav_bodies)

    # --- integrate linear motion ---
    ax = thrust_accel[0] + grav_accel[0]
    ay = thrust_accel[1] + grav_accel[1]
    az = thrust_accel[2] + grav_accel[2]

    vel = (vel[0] + ax * dt, vel[1] + ay * dt, vel[2] + az * dt)
    pos = (pos[0] + vel[0] * dt, pos[1] + vel[1] * dt, pos[2] + vel[2] * dt)

    # --- integrate rotation (yaw only, for now) ---
    yaw = (yaw + yaw_rate * dt) % 360.0

    # --- write back normalised control structure ---
    ship["position"] = [pos[0], pos[1], pos[2]]
    ship["velocity"] = [vel[0], vel[1], vel[2]]
    ship["orientation_deg"] = yaw
    ship["controls"] = {
        "thrust_vector": thrust_vec,
        "rotation_deg_s": {
            "yaw": yaw_rate,
            "pitch": pitch_rate,
            "roll": roll_rate,
        },
    }


def update_projectiles(
    projectiles: List[Dict[str, Any]],
    dt: float,
    grav_bodies: Iterable[GravBody],
) -> None:
    """Integrate all projectiles in-place.

    Projectiles are treated as simple point masses influenced by gravity
    (no thrust). TTL and a simple distance cap keep them from blowing out
    simulation ranges.
    """

    survivors: List[Dict[str, Any]] = []
    for p in projectiles:
        pos_list = p.get("position") or [0.0, 0.0, 0.0]
        vel_list = p.get("velocity") or [0.0, 0.0, 0.0]
        pos: Vec3 = (float(pos_list[0]), float(pos_list[1]), float(pos_list[2]))
        vel: Vec3 = (float(vel_list[0]), float(vel_list[1]), float(vel_list[2]))

        grav_accel = gravity_accel_at_point(pos, grav_bodies)
        vel = (
            vel[0] + grav_accel[0] * dt,
            vel[1] + grav_accel[1] * dt,
            vel[2] + grav_accel[2] * dt,
        )
        pos = (pos[0] + vel[0] * dt, pos[1] + vel[1] * dt, pos[2] + vel[2] * dt)

        ttl = float(p.get("ttl", 0.0)) - dt
        if ttl <= 0.0:
            continue

        # Hard safety cap to prevent unbounded growth of coordinates.
        if v_length(pos) > 1.0e9:
            continue

        p["position"] = [pos[0], pos[1], pos[2]]
        p["velocity"] = [vel[0], vel[1], vel[2]]
        p["ttl"] = ttl
        survivors.append(p)

    projectiles[:] = survivors


def update_world(
    ships: List[Dict[str, Any]],
    projectiles: List[Dict[str, Any]],
    grav_bodies: Iterable[GravBody],
    dt: float,
) -> None:
    """Advance all dynamic entities by one tick."""
    for ship in ships:
        update_ship_kinematics(ship, dt, grav_bodies)
    update_projectiles(projectiles, dt, grav_bodies)
