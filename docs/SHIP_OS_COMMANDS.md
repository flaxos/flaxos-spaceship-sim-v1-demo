# SHIP_OS_COMMANDS.md – ShipOS Command Layer (Sprint 2)

This document describes the ShipOS text command layer that sits above
API v1.0. Sprint 2 delivers a first implementation of this shell in
`tools/ship_os_shell.py`.

## 1. Contexts

- `ship>` – global context (all roles available).
- `helm>` – helm-focused commands.
- `nav>` – navigation and autopilot.
- `weapons>` – weapons and targeting.
- `sensors>` – sensor ops.

Example:

```text
ship> context helm
interceptor_alpha@helm>
```

## 2. Commands and API mappings

### 2.1 Global

- `ship select <ship_id>` → `get_state` (for validation only).
- `status` → `get_state` for the current ship.
- `mission` → `get_mission`.
- `contacts` → `get_state` with `include_contacts=true`.

### 2.2 Helm

- `thrust <value> [forward|reverse]`
  - `command.set_helm_input` with `thrust_vector = [0, 0, ±value]`.

- `yaw <rate> [left|right]`
  - `command.set_helm_input` with `rotation_input_deg_s.yaw = ±rate`.

- `kill-rotation`
  - `command.set_helm_input` with zero thrust and zero rotation.

- `stop`
  - `command.set_helm_input` with zero thrust and zero rotation.

### 2.3 Navigation & autopilot

- `set-target <entity_id>`
  - `command.set_target`.

- `autopilot manual`
  - `command.set_autopilot_mode` with `enabled=false`, `mode="manual"`.

- `autopilot coast`
  - `command.set_autopilot_mode` with `enabled=true`, `mode="coast"`.
  - Behaviour: AP zeroes thrust and rotation each tick; ship coasts.

- `autopilot kill-velocity`
  - `command.set_autopilot_mode` with `enabled=true`, `mode="kill_vel"`.
  - Behaviour: AP rotates ship so its forward vector opposes current
    velocity and applies forward thrust until speed is near zero, then
    disables itself (mode returns to `"manual"`).

- `autopilot chase-target`
  - `command.set_autopilot_mode` with `enabled=true`, `mode="chase_target"`.
  - Behaviour: AP rotates towards `current_target_id` and applies forward
    thrust; distance behaviour uses `params.desired_range_m` and
    `params.min_range_m` to slow down when close.

### 2.4 Weapons

- `fire <mount_id>`
  - `command.fire_weapon` with `weapon_mount_id = mount_id`.

### 2.5 Sensors

- `ping [active|passive]`
  - `command.ping_sensors` (default `mode="active"`).

- `events`
  - `get_events`.
