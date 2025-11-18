# Flaxos Spaceship Sim – Sprint 2 Patch (Autopilot & ShipOS Shell)

This patch zip is intended to be extracted on top of an existing
`flaxos_spaceship_sim_v1.0.0_demo` checkout that already includes the
Sprint 1 (control & command contract) updates.

It contains:

- Updated demo controller (`server/demo_server_v2.py`)
  - Adds behavioural autopilot modes:
    - `manual`: AP disabled.
    - `coast`: zero thrust/rotation each tick (coasting).
    - `kill_vel`: rotate to oppose current velocity and burn to reduce speed.
    - `chase_target`: rotate towards current target and burn towards it using
      simple range logic.
- Updated physics feature probe (`tools/physics_feature_probe.py`)
  - Adds tests for:
    - `kill_vel` autopilot behaviour (speed reduction to near zero).
    - `coast` autopilot behaviour (speed remains approximately constant).
- New ShipOS text shell (`tools/ship_os_shell.py`)
  - CLI that connects via API v1.0 and lets you:
    - Select a ship.
    - Issue helm commands (thrust, yaw, stop).
    - Configure autopilot modes (manual, coast, kill-velocity, chase-target).
    - Fire weapons and ping sensors.
    - Inspect mission and contact data.
- Documentation updates:
  - `docs/API_SPEC.md` – autopilot modes now described with behaviour.
  - `docs/SHIP_OS_COMMANDS.md` – ShipOS command mapping and semantics.

## Quick start

1. Extract this zip over your existing demo repo, preserving directory
   structure.

2. Start the demo server v2 (physics-enabled, Sprint 2 autopilot):

   ```bash
   python server/demo_server_v2.py
   ```

3. Run the physics feature probe to validate physics + autopilot:

   ```bash
   python tools/physics_feature_probe.py
   ```

   A new directory will appear under `physics_runs/` with JSON outputs and
   a `summary.json` including the new autopilot checks.

4. Try the ShipOS shell to manually fly the interceptor:

   ```bash
   python tools/ship_os_shell.py --ship interceptor_alpha --context helm
   ```

   Example session:

   ```text
   interceptor_alpha@helm> thrust 0.5 forward
   interceptor_alpha@helm> yaw 10 left
   interceptor_alpha@nav> context nav
   interceptor_alpha@nav> autopilot kill-velocity
   interceptor_alpha@sensors> context sensors
   interceptor_alpha@sensors> ping active
   ```
