# Flaxos Spaceship Sim – Sprint 1 Patch (Control & Command Contract)

This patch zip is intended to be extracted on top of an existing
`flaxos_spaceship_sim_v1.0.0_demo` checkout.

It contains:

- Updated physics integration (`sim/physics.py`)
  - Canonical handling of `controls.thrust_vector` and `controls.rotation_deg_s`.
  - Yaw-only rotation for now, with placeholders for pitch/roll and lateral RCS.
- Updated demo controller (`server/demo_server_v2.py`)
  - Normalises controls/autopilot per ship.
  - Implements the Sprint 1 contract for `command.set_helm_input` and
    `command.set_autopilot_mode`.
- Convenience launcher for the v2 demo (`tools/start_demo_server_v2.py`).
- Extended physics feature probe (`tools/physics_feature_probe.py`)
  - Tests:
    - Forward thrust motion.
    - Yaw rotation.
    - Coasting with zero thrust/rotation.
    - Reverse-thrust braking.
    - Active sensor ping.
    - Projectile spawn and motion.
- Documentation updates:
  - `docs/API_SPEC.md` – API v1.0 with Sprint 1 control/autopilot contract.
  - `docs/SCHEMAS.md` – ship/fleet/mission schema excerpts.
  - `docs/SHIP_OS_COMMANDS.md` – ShipOS command-layer design.

## Quick start

1. Extract this zip over your existing demo repo, preserving directory
   structure.

2. Ensure your virtualenv is active and dependencies are installed.

3. Start the demo server v2 (physics-enabled):

   ```bash
   python tools/start_demo_server_v2.py
   ```

4. In a second terminal, run the physics feature probe:

   ```bash
   python tools/physics_feature_probe.py
   ```

   This will create a new directory under `physics_runs/` with
   per-step JSON files and a `summary.json` describing the probe
   results (including status fields for each step).

5. You can still use your existing debug tools (e.g.
   `debug_api_sanity.py`, `debug_two_clients.py`); the Sprint 1
   changes are backwards compatible with previous `set_helm_input`
   usage that passes a numeric `rotation_input_deg_s`.
