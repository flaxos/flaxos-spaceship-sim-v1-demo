# SCHEMAS.md – Flaxos Spaceship Sim – Sprint 1

This document describes the canonical JSON schemas for ships, fleets and
missions, with particular focus on the control and autopilot fields
introduced/clarified in Sprint 1.

The schemas here are conceptual; individual JSON files may omit optional
fields if reasonable defaults exist.

## 1. Ship schema (selected fields)

```jsonc
{
  "id": "interceptor_alpha",
  "name": "Interceptor Alpha",
  "class": "light_frigate",
  "team": "blue",

  "mass_kg": 1000000.0,

  "position": [0.0, 0.0, 0.0],
  "velocity": [0.0, 0.0, 0.0],
  "orientation_deg": 0.0,

  "physics": {
    "max_main_thrust_newton": 1000000.0,
    "max_rcs_yaw_deg_s": 10.0
    // Future extensions:
    // "max_rcs_pitch_deg_s": 10.0,
    // "max_rcs_roll_deg_s": 10.0
  },

  "controls": {
    "thrust_vector": [0.0, 0.0, 0.0],
    "rotation_deg_s": {
      "yaw": 0.0,
      "pitch": 0.0,
      "roll": 0.0
    },
    "mode": "manual"
  },

  "autopilot": {
    "enabled": false,
    "mode": "manual",
    "params": {}
  }
}
```

- `mass_kg`: ship mass in kilograms, used by physics.
- `position` / `velocity`: world-space coordinates (metres, m/s).
- `orientation_deg`: yaw angle around Z axis (degrees). Pitch/roll can be
  added later without breaking existing clients.
- `physics`: per-ship capability caps for thrust and RCS.
- `controls`: last helm input applied to this ship.
  - `thrust_vector`: `[tx, ty, tz]` in ship-local axes, each in `[-1, 1]`.
    - Sprint 1: only `tz` is used for main drive.
  - `rotation_deg_s`: rotational rates in deg/s; Sprint 1 applies yaw only.
  - `mode`: optional string hint (e.g. `"manual"`, `"assist"`).
- `autopilot`: configuration for AP behaviour.
  - Sprint 1: stored and reported by API, no behaviour yet.

## 2. Fleet schema (summary)

```jsonc
{
  "id": "demo_interceptor_vs_target",
  "name": "Demo Interceptor vs Target",
  "ships": [
    {
      "id": "interceptor_alpha",
      "ship_config_file": "ships/interceptor_alpha.json",
      "team": "blue",
      "is_player": true,
      "spawn": {
        "position": [0.0, 0.0, 0.0],
        "velocity": [0.0, 0.0, 0.0]
      },
      "orientation_deg": 0.0
    },
    {
      "id": "target_dummy_1",
      "ship_config_file": "ships/target_dummy.json",
      "team": "red",
      "is_player": false,
      "spawn": {
        "position": [0.0, 20000.0, 0.0],
        "velocity": [0.0, 0.0, 0.0]
      },
      "orientation_deg": 180.0
    }
  ]
}
```

The fleet entry references ship config files which are expected to conform
to the ship schema above.

## 3. Mission schema (summary)

```jsonc
{
  "id": "mission_interceptor_vs_target",
  "title": "Interceptor vs Target (Demo)",
  "description": "Simple two-ship scenario for testing.",
  "fleet_file": "fleets/demo_interceptor_vs_target.json",
  "objectives": [
    {
      "id": "destroy_target",
      "type": "destroy_team",
      "team": "red"
    }
  ]
}
```

Missions reference fleets and define objectives. The mission loader attaches
mission metadata to the simulation and exposes a public representation via
the `get_mission` API.
### Ship kinematics & controls

```jsonc
"position": [x, y, z],           // km, world frame
"velocity": [vx, vy, vz],        // km/s, world frame

"orientation_deg": 0.0,          // legacy yaw, kept for backward compatibility
"orientation_euler_deg": {       // new canonical orientation
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

API_SPEC.md mostly stays valid; the only tweak is: `get_state` can now include `orientation_euler_deg` in addition to `orientation_deg`.

---
