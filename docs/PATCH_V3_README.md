# Flaxos Spaceship Sim – Patch v3 (Physics & Probes)

This patch adds:

- `sim/physics_v2.py` – 3D Newtonian physics with yaw/pitch/roll and gravity wells.
- `tools/physics_feature_probe.py` – API-level physics test harness.
- Docs addendum for the new fields (`orientation_euler_deg`, `thrust_vector` shape, `grav_bodies`).

## How to apply

1. Copy the contents of this patch into the root of your existing
   `flaxos_spaceship_sim_v1.0.0_demo` directory, so that:

   - `sim/physics_v2.py` ends up at `sim/physics_v2.py`
   - `tools/physics_feature_probe.py` ends up at `tools/physics_feature_probe.py`
   - `docs/SCHEMAS_PHYSICS_ADDENDUM.md` ends up under `docs/`
   - `docs/PATCH_V3_README.md` ends up under `docs/`

2. Wire the new physics into the sim tick (one code change):

   In `server/demo_server_v2.py`:

   - Add at the top:

     ```python
     from sim import physics_v2
     ```

   - In the method that advances the simulation each frame
     (usually something like `_tick_sim(self, dt_s)`), replace
     your ship position/velocity update loop with:

     ```python
     def _tick_sim(self, dt_s: float) -> None:
         if dt_s <= 0.0:
             return

         mission = getattr(self, "mission", None)
         if isinstance(mission, dict):
             grav_bodies = mission.get("grav_bodies", []) or []
         else:
             grav_bodies = []

         for ship in self.ships.values():
             physics_v2.update_ship_physics(
                 ship=ship,
                 dt_s=dt_s,
                 grav_bodies=grav_bodies,
             )

         # keep any existing projectile / mission logic below this
     ```

3. (Optional) Add gravity wells to your mission JSON by following
   `docs/SCHEMAS_PHYSICS_ADDENDUM.md`.

## How to run the physics probe

1. Start the demo server v2:

   ```powershell
   (.venv) PS ...\flaxos_spaceship_sim_v1.0.0_demo> python .\server\demo_server_v2.py
   ```

2. In a second terminal, run the probe:

   ```powershell
   (.venv) PS ...\flaxos_spaceship_sim_v1.0.0_demo\tools> py.exe .\physics_feature_probe.py --ship interceptor_alpha
   ```

3. Inspect the output in the `debug_physics\run_YYYYMMDD_HHMMSS\`
   folder, especially `summary.json`.
