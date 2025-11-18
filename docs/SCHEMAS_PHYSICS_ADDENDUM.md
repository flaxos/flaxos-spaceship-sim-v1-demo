# SCHEMAS – Physics & Gravity Addendum (Patch v3)

This addendum documents the new fields introduced in Patch v3. It is intended
to sit alongside the existing `SCHEMAS.md` without replacing it.

## Ship Kinematics & Controls

```jsonc
"position": [x, y, z],           // km, world frame
"velocity": [vx, vy, vz],        // km/s, world frame

"orientation_deg": 0.0,          // legacy yaw, kept for backward compatibility
"orientation_euler_deg": {       // canonical orientation
  "yaw": 0.0,                    // deg
  "pitch": 0.0,                  // deg
  "roll": 0.0                    // deg
},

"controls": {
  "thrust_vector": [sx, sy, sfwd],      // control inputs -1..1; sfwd drives main engine
  "rotation_deg_s": {
    "yaw": 0.0, "pitch": 0.0, "roll": 0.0   // desired rotational rates, deg/s
  }
},

"physics": {
  "max_main_thrust_newton": 1000000.0,
  "max_rcs_yaw_deg_s": 10.0,
  "max_rcs_pitch_deg_s": 10.0,
  "max_rcs_roll_deg_s": 10.0,
  "max_rcs_linear_m_s2": 1.0          // optional, for future translational RCS
}
```

## Mission Gravity Bodies

```jsonc
"grav_bodies": [
  {
    "id": "ceres",
    "type": "asteroid",            // or "planet", "moon", etc.
    "mass_kg": 9.4e20,
    "position": [0.0, 0.0, 0.0],   // km, world frame
    "radius_km": 473.0,
    "gravity_enabled": true,
    "cutoff_radius_km": 100000.0   // optional, ignore gravity beyond this distance
  }
]
```

If `grav_bodies` is omitted or empty, the world is treated as gravity-free.
