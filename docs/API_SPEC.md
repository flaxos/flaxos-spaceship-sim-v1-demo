# API_SPEC.md – Flaxos Spaceship Sim – API v1.0 (Sprint 2)

This document describes the TCP JSON API exposed by the demo server for
Flaxos Spaceship Sim, as of Sprint 2.

The API is designed to be role-agnostic: any client (HUD, CLI, ShipOS shell,
AI agent) uses the same actions and payloads.

## 1. Transport

- TCP socket, default `host=0.0.0.0`, `port=8765`.
- Messages are **newline-delimited JSON** (`\n`).
- Each request and response is a single JSON object per line.

## 2. Envelope

Every request MUST follow this structure:

```json
{
  "api_version": "1.0",
  "request_id": "string-or-int",
  "action": "get_state",
  "actor": {
    "client_id": "optional-client-id",
    "role": "optional-role",
    "user": "optional-user-name-or-id"
  },
  "payload": { }
}
```

Responses:

```json
{
  "api_version": "1.0",
  "request_id": "same-as-request",
  "status": "ok" | "error",
  "error": {
    "code": "optional-error-code",
    "message": "human readable explanation"
  },
  "action": "get_state",
  "payload": { }
}
```

## 3. Core actions

### 3.1 `get_server_info`

Request payload: `{}`

Response payload:

```json
{
  "server_version": "1.0.0",
  "api_version": "1.0",
  "uptime_s": 123.45
}
```

### 3.2 `get_mission`

Request payload: `{}`

Response payload (shape, not exact values):

```json
{
  "id": "mission_interceptor_vs_target",
  "title": "Interceptor vs Target (Demo)",
  "description": "Short description...",
  "fleet_id": "demo_interceptor_vs_target",
  "objectives": [
    {
      "id": "destroy_target",
      "type": "destroy_team",
      "team": "red"
    }
  ]
}
```

### 3.3 `get_state`

Request payload:

```json
{
  "ship_id": "interceptor_alpha",
  "include_contacts": true,
  "include_projectiles": true,
  "include_raw_entities": false
}
```

Response payload:

```json
{
  "server_time": 12.3,
  "own_ship": {
    "id": "interceptor_alpha",
    "position": [x, y, z],
    "velocity": [vx, vy, vz],
    "orientation_deg": 42.0,
    "mass_kg": 1000000.0,
    "team": "blue",
    "controls": {
      "thrust_vector": [tx, ty, tz],
      "rotation_deg_s": {
        "yaw": yaw_rate,
        "pitch": pitch_rate,
        "roll": roll_rate
      },
      "mode": "manual"
    },
    "autopilot": {
      "enabled": false,
      "mode": "manual",
      "params": { }
    },
    "current_target_id": "target_dummy_1"
  },
  "contacts": [ /* contact list */ ],
  "projectiles": [ /* projectile list */ ]
}
```

### 3.4 `get_events`

Request payload:

```json
{
  "since_time": 0.0
}
```

Response payload:

```json
{
  "events": [
    {
      "id": "ev_1",
      "time": 12.0,
      "type": "sensor_contact_new",
      "sensor_ship_id": "interceptor_alpha",
      "target_entity_id": "target_dummy_1",
      "data": { "range_m": 20000.0, "bearing_deg": 0.0 }
    }
  ]
}
```

### 3.5 `command.set_target`

Request payload:

```json
{
  "ship_id": "interceptor_alpha",
  "target_entity_id": "target_dummy_1"
}
```

Response payload (success):

```json
{
  "ship_id": "interceptor_alpha",
  "current_target_id": "target_dummy_1"
}
```

### 3.6 `command.fire_weapon`

Request payload:

```json
{
  "ship_id": "interceptor_alpha",
  "weapon_mount_id": "pd_1"
}
```

Response payload:

```json
{
  "projectile_id": "interceptor_alpha_proj_1"
}
```

### 3.7 `command.ping_sensors`

Request payload:

```json
{
  "ship_id": "interceptor_alpha",
  "mode": "active"
}
```

Response payload:

```json
{
  "ship_id": "interceptor_alpha",
  "mode": "active",
  "contacts": [ /* same shape as get_state.contacts */ ]
}
```

### 3.8 `command.set_autopilot_mode`

Request payload (Sprint 2 behaviour):

```json
{
  "ship_id": "interceptor_alpha",
  "enabled": true,
  "mode": "kill_vel",
  "params": {}
}
```

- `mode` one of:
  - `"manual"` – AP disabled; manual helm control.
  - `"coast"` – AP zeroes thrust and rotation each tick; ship coasts.
  - `"kill_vel"` – AP rotates to oppose current velocity and burns to reduce speed; when speed is near zero, AP disables itself and returns to `"manual"`.
  - `"chase_target"` – AP rotates towards `current_target_id` and applies forward thrust; distance behaviour governed by `params` (see below).

For `"chase_target"` Sprint 2 uses:

- `params.desired_range_m` (default 5000.0)
- `params.min_range_m` (default 1000.0)

Response payload (success):

```json
{
  "ship_id": "interceptor_alpha",
  "autopilot": {
    "enabled": true,
    "mode": "kill_vel",
    "params": {}
  }
}
```

On error (invalid mode):

```json
{
  "error": "invalid_mode",
  "ship_id": "interceptor_alpha",
  "enabled": true,
  "mode": "warp_drive",
  "allowed_modes": ["chase_target", "coast", "kill_vel", "manual"]
}
```

### 3.9 `command.set_helm_input`

Request payload:

```json
{
  "ship_id": "interceptor_alpha",
  "thrust_vector": [0.0, 0.0, 1.0],
  "rotation_input_deg_s": {
    "yaw": 10.0,
    "pitch": 0.0,
    "roll": 0.0
  },
  "mode": "manual"
}
```

- `thrust_vector` components are clamped to [-1, 1].
- `rotation_input_deg_s` may be a float (yaw only) or a full dict.

Response payload (success):

```json
{
  "ship_id": "interceptor_alpha",
  "controls": {
    "thrust_vector": [0.0, 0.0, 1.0],
    "rotation_deg_s": {
      "yaw": 10.0,
      "pitch": 0.0,
      "roll": 0.0
    },
    "mode": "manual"
  }
}
```
