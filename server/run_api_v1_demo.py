from __future__ import annotations

import argparse
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from server.api_server_v1 import run_api_server
from sim.missions import load_mission_and_fleet
from sim.sensors import SensorsManager
from sim.physics import GravBody, update_world, yaw_deg_to_forward_vector

logger = logging.getLogger("demo")


class DemoSimController:
    """
    Demo simulation controller for Flaxos Spaceship Sim v1.0.

    - Loads mission + fleet (canonical JSON).
    - Instantiates ships.
    - Runs a tick loop:
        - Newtonian physics (ships + projectiles) with gravity hooks.
        - Sensors/contacts.
    - Exposes methods required by the v1.0 API server.
    """

    def __init__(self, mission_path: Path) -> None:
        self.mission_path = mission_path
        self.mission, self.fleet = load_mission_and_fleet(mission_path)

        self.sim_time: float = 0.0
        self.dt: float = 0.1  # seconds per tick

        self.ships: List[Dict[str, Any]] = self._instantiate_ships()
        self.projectiles: List[Dict[str, Any]] = []
        self._next_projectile_id: int = 1

        self.sensors = SensorsManager()

        # Placeholder for orbital mechanics:
        # Add planets/asteroids/moons here later and everything (ships + torps)
        # will feel their gravity within gravity_radius_m.
        self.gravity_bodies: List[GravBody] = []

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _instantiate_ships(self) -> List[Dict[str, Any]]:
        """
        Instantiate ships from fleet entries using the canonical loader.

        Also attaches 'controls' and 'physics' scaffolding needed for the
        physics engine to work.
        """
        ships: List[Dict[str, Any]] = []
        from config.canonical_loader import load_ship_config

        for entry in self.fleet["ships"]:
            ship_cfg_path = Path(entry["ship_config_file"])
            ship_cfg = load_ship_config(ship_cfg_path)
            ship: Dict[str, Any] = dict(ship_cfg)

            spawn = entry["spawn"]
            ship["position"] = [
                float(spawn["position"][0]),
                float(spawn["position"][1]),
                float(spawn["position"][2]),
            ]
            ship["velocity"] = [
                float(spawn["velocity"][0]),
                float(spawn["velocity"][1]),
                float(spawn["velocity"][2]),
            ]
            ship["orientation_deg"] = float(entry["orientation_deg"])
            ship["team"] = entry.get("team", ship.get("team"))
            ship["is_player"] = bool(entry.get("is_player", False))

            # Controls + physics required by sim.physics.update_ship_kinematics
            ship.setdefault(
                "controls",
                {
                    "thrust_vector": [0.0, 0.0, 0.0],
                    "rotation_deg_s": 0.0,
                },
            )
            ship.setdefault(
                "physics",
                {
                    # Default main drive & RCS capability – can be overridden
                    # per ship config JSON later.
                    "max_main_thrust_newton": 1_000_000.0,
                    "max_rcs_yaw_deg_s": 10.0,
                },
            )

            ships.append(ship)

        logger.info(
            "Instantiated %d ships from fleet '%s'",
            len(ships),
            self.fleet.get("id"),
        )
        return ships

    # ------------------------------------------------------------------
    # Main sim loop
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        logger.info("DemoSimController loop started.")
        while self._running:
            self.sim_time += self.dt

            # Physics: ships + projectiles under gravity
            update_world(self.ships, self.projectiles, self.gravity_bodies, self.dt)

            # Sensors: ships detect ships + projectiles
            self._update_sensors()

            time.sleep(self.dt)

    def _update_sensors(self) -> None:
        entities: List[Dict[str, Any]] = list(self.ships) + list(self.projectiles)
        for ship in self.ships:
            self.sensors.update_passive_for_ship(self.sim_time, ship, entities)
        self.sensors.advance_time(self.sim_time)

    # ------------------------------------------------------------------
    # API methods (used by api_server_v1)
    # ------------------------------------------------------------------

    def get_state(
        self,
        ship_id: Optional[str] = None,
        include_contacts: bool = True,
        include_projectiles: bool = True,
        include_raw_entities: bool = False,  # kept for API signature compatibility
    ) -> Dict[str, Any]:
        """
        Return state for a given ship_id (or first ship if None).

        For v1.0 demo we return:
          - server_time
          - own_ship
          - contacts
          - projectiles

        (We ignore include_raw_entities for now to keep output lean.)
        """
        own_ship: Optional[Dict[str, Any]] = None
        for s in self.ships:
            if ship_id is None or s["id"] == ship_id:
                own_ship = s
                break

        if own_ship is None:
            contacts = []
        else:
            contacts = (
                self.sensors.get_contacts_for_ship(own_ship["id"])
                if include_contacts
                else []
            )

        projectiles = list(self.projectiles) if include_projectiles else []

        return {
            "server_time": self.sim_time,
            "own_ship": own_ship,
            "contacts": contacts,
            "projectiles": projectiles,
        }

    def get_events(self, since_time: Optional[float] = None) -> Dict[str, Any]:
        """
        Sensor-related events only for now.
        'since_time' is currently ignored in this demo.
        """
        events = []
        for ev in self.sensors.get_events_since(0):
            events.append(
                {
                    "id": ev["id"],
                    "time": ev["time"],
                    "type": ev["type"],
                    "sensor_ship_id": ev["sensor_ship_id"],
                    "target_entity_id": ev["target_entity_id"],
                    "data": ev["data"],
                }
            )
        return {"events": events}

    def get_mission(self) -> Dict[str, Any]:
        return self.mission.to_public_dict(self.fleet)

    def set_target(self, ship_id: str, target_entity_id: str) -> Dict[str, Any]:
        logger.info("set_target: %s -> %s", ship_id, target_entity_id)
        return {"ship_id": ship_id, "current_target_id": target_entity_id}

    def fire_weapon(self, ship_id: str, weapon_mount_id: str) -> Dict[str, Any]:
        """
        Fire a weapon from a ship.

        v1.0 demo behaviour:
          - Spawns a simple ballistic torpedo influenced by gravity.
          - Launch velocity = ship velocity + forward muzzle velocity.
        """
        ship = next((s for s in self.ships if s["id"] == ship_id), None)
        if ship is None:
            logger.warning("fire_weapon: unknown ship_id=%s", ship_id)
            return {"error": "unknown_ship", "ship_id": ship_id}

        ship_pos = ship.get("position") or [0.0, 0.0, 0.0]
        ship_vel = ship.get("velocity") or [0.0, 0.0, 0.0]
        yaw = float(ship.get("orientation_deg", 0.0))

        forward = yaw_deg_to_forward_vector(yaw)

        muzzle_velocity = 2000.0  # m/s – tweak later
        vx = float(ship_vel[0]) + forward[0] * muzzle_velocity
        vy = float(ship_vel[1]) + forward[1] * muzzle_velocity
        vz = float(ship_vel[2]) + forward[2] * muzzle_velocity

        proj_id = f"{ship_id}_proj_{self._next_projectile_id}"
        self._next_projectile_id += 1

        projectile: Dict[str, Any] = {
            "id": proj_id,
            "type": "torpedo",
            "team": ship.get("team"),
            "position": [
                float(ship_pos[0]),
                float(ship_pos[1]),
                float(ship_pos[2]),
            ],
            "velocity": [vx, vy, vz],
            "mass_kg": 100.0,
            "ttl": 300.0,
            "signature": {
                "base_radar": 0.3,
                "base_thermal": 0.5,
            },
        }

        self.projectiles.append(projectile)
        logger.info(
            "fire_weapon: %s fired %s, spawned projectile %s",
            ship_id,
            weapon_mount_id,
            proj_id,
        )
        return {"projectile_id": proj_id}

    def ping_sensors(self, ship_id: str, mode: str) -> Dict[str, Any]:
        ship = next((s for s in self.ships if s["id"] == ship_id), None)
        if ship is None:
            logger.warning("ping_sensors: unknown ship_id=%s", ship_id)
            return {"error": "unknown_ship", "ship_id": ship_id, "mode": mode}

        entities = list(self.ships) + list(self.projectiles)
        contacts = self.sensors.execute_active_ping(self.sim_time, ship, entities, mode=mode)
        return {"ship_id": ship_id, "mode": mode, "contacts": contacts}

    def set_autopilot_mode(self, ship_id: str, enabled: bool, mode: Optional[str]) -> Dict[str, Any]:
        """
        Autopilot placeholder.

        For now we just store the desired mode; in a later sprint, nav/helm
        logic can use this to drive flip-and-burn, waypoints, etc.
        """
        ship = next((s for s in self.ships if s["id"] == ship_id), None)
        if ship is None:
            logger.warning("set_autopilot_mode: unknown ship_id=%s", ship_id)
            return {
                "error": "unknown_ship",
                "ship_id": ship_id,
                "enabled": enabled,
                "mode": mode,
            }

        ship.setdefault("autopilot", {})
        ship["autopilot"]["enabled"] = bool(enabled)
        ship["autopilot"]["mode"] = mode

        logger.info("set_autopilot_mode: %s enabled=%s mode=%s", ship_id, enabled, mode)
        return {"ship_id": ship_id, "autopilot_enabled": enabled, "mode": mode}

    def set_helm_input(
        self,
        ship_id: str,
        thrust_vector: List[float],
        rotation_input_deg_s: Any,
    ) -> Dict[str, Any]:
        """
        Update helm controls.

        - thrust_vector[2] = forward throttle [-1, 1]
        - rotation_input_deg_s = yaw rate (deg/s) or dict {yaw,pitch,roll}

        The physics loop consumes these fields each tick and moves the ship.
        """
        ship = next((s for s in self.ships if s["id"] == ship_id), None)
        if ship is None:
            logger.warning("set_helm_input: unknown ship_id=%s", ship_id)
            return {"error": "unknown_ship", "ship_id": ship_id}

        if isinstance(rotation_input_deg_s, dict):
            rotation_payload = {
                "yaw": float(rotation_input_deg_s.get("yaw", 0.0)),
                "pitch": float(rotation_input_deg_s.get("pitch", 0.0)),
                "roll": float(rotation_input_deg_s.get("roll", 0.0)),
            }
        else:
            rotation_payload = float(rotation_input_deg_s)

        controls = ship.setdefault("controls", {})
        controls["thrust_vector"] = list(thrust_vector)
        controls["rotation_deg_s"] = rotation_payload

        logger.info(
            "set_helm_input: %s thrust=%s rotation_deg_s=%s",
            ship_id,
            thrust_vector,
            rotation_input_deg_s,
        )
        return {"ship_id": ship_id}

    def stop(self) -> None:
        self._running = False


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting Flaxos Spaceship Sim demo server")

    parser = argparse.ArgumentParser(description="Run Flaxos Spaceship Sim API demo server")
    parser.add_argument(
        "--mission",
        default="missions/mission_interceptor_vs_target.json",
        help="Mission JSON path (default: missions/mission_interceptor_vs_target.json)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface to bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port for API server (default: 8765)",
    )

    args = parser.parse_args(argv)

    mission_path = Path(args.mission)
    if not mission_path.exists():
        logger.error("Mission file not found: %s", mission_path)
        return 1

    sim = DemoSimController(mission_path)
    run_api_server(sim, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
