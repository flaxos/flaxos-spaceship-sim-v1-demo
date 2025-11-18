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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo")


class DemoSimController:
    def __init__(self, mission_path: Path) -> None:
        """
        Minimal demo simulation controller.

        - Loads a mission and its fleet using the canonical loaders.
        - Instantiates ships.
        - Runs a simple tick loop that updates sensors.
        - Exposes the methods expected by the API server handlers.
        """
        self.mission_path = mission_path
        self.mission, self.fleet = load_mission_and_fleet(mission_path)
        self.sim_time: float = 0.0
        self.dt: float = 0.1

        self.ships: List[Dict[str, Any]] = self._instantiate_ships()
        self.sensors = SensorsManager()

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _instantiate_ships(self) -> List[Dict[str, Any]]:
        """
        Instantiate ships from the canonical fleet definition.
        For this demo, we just copy the ship configs and apply spawn overrides.
        """
        ships: List[Dict[str, Any]] = []
        from config.canonical_loader import load_ship_config

        fleet_dir = self.mission.fleet_dir
        for entry in self.fleet["ships"]:
            ship_cfg_path = Path(entry["ship_config_file"])
            ship_cfg = load_ship_config(ship_cfg_path)
            ship = dict(ship_cfg)

            spawn = entry["spawn"]
            ship["position"] = spawn["position"]
            ship["velocity"] = spawn["velocity"]
            ship["orientation_deg"] = entry["orientation_deg"]
            ship["team"] = entry.get("team", ship.get("team"))
            ship["is_player"] = entry.get("is_player", False)

            ships.append(ship)

        logger.info("Instantiated %d ships from fleet '%s'", len(ships), self.fleet.get("id"))
        return ships

    def _loop(self) -> None:
        """
        Very simple simulation loop:

        - Advances time.
        - Updates passive sensors.
        - Ages contacts.

        No real physics or projectiles yet; this is a plumbing demo.
        """
        logger.info("DemoSimController loop started.")
        while self._running:
            self.sim_time += self.dt
            self._update_sensors()
            time.sleep(self.dt)

    def _update_sensors(self) -> None:
        entities = list(self.ships)  # only ships for now
        for ship in self.ships:
            self.sensors.update_passive_for_ship(self.sim_time, ship, entities)
        self.sensors.advance_time(self.sim_time)

    # -------------------------------------------------------------------------
    # API methods used by api_server_v1
    # -------------------------------------------------------------------------

    def get_state(
        self,
        ship_id: Optional[str] = None,
        include_contacts: bool = True,
        include_projectiles: bool = True,
        include_raw_entities: bool = False,
    ) -> Dict[str, Any]:
        """
        Return a simple state view for a given ship_id (or the first ship if None).
        """
        own_ship: Optional[Dict[str, Any]] = None
        for s in self.ships:
            if ship_id is None or s["id"] == ship_id:
                own_ship = s
                break

        contacts = []
        if own_ship is not None and include_contacts:
            contacts = self.sensors.get_contacts_for_ship(own_ship["id"])

        # Projectiles not implemented in this demo
        projectiles: List[Dict[str, Any]] = []
        raw_entities: List[Dict[str, Any]] = entities if include_raw_entities else []

        return {
            "server_time": self.sim_time,
            "own_ship": own_ship,
            "contacts": contacts,
            "projectiles": projectiles,
            "entities": raw_entities,
        }

    def get_events(self, since_time: Optional[float] = None) -> Dict[str, Any]:
        """
        Return sensor-related events only for now.
        """
        # For simplicity, we ignore since_time and just dump all events.
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
        # Stub – no real fire-control yet, but API plumbing is in place.
        logger.info("set_target: %s -> %s", ship_id, target_entity_id)
        return {"ship_id": ship_id, "current_target_id": target_entity_id}

    def fire_weapon(self, ship_id: str, weapon_mount_id: str) -> Dict[str, Any]:
        # Stub – no real projectiles yet.
        logger.info("fire_weapon: %s fired %s", ship_id, weapon_mount_id)
        return {"projectile_id": "p_001"}

    def ping_sensors(self, ship_id: str, mode: str) -> Dict[str, Any]:
        ship = next(s for s in self.ships if s["id"] == ship_id)
        contacts = self.sensors.execute_active_ping(self.sim_time, ship, self.ships, mode=mode)
        return {"ship_id": ship_id, "mode": mode, "contacts": contacts}

    def set_autopilot_mode(self, ship_id: str, enabled: bool, mode: Optional[str]) -> Dict[str, Any]:
        # Stub – no actual autopilot logic yet.
        logger.info("set_autopilot_mode: %s enabled=%s mode=%s", ship_id, enabled, mode)
        return {"ship_id": ship_id, "autopilot_enabled": enabled, "mode": mode}

    def set_helm_input(
        self,
        ship_id: str,
        thrust_vector: List[float],
        rotation_input_deg_s: float,
    ) -> Dict[str, Any]:
        # Stub – no real physics yet.
        logger.info(
            "set_helm_input: %s thrust=%s rotation_deg_s=%s",
            ship_id,
            thrust_vector,
            rotation_input_deg_s,
        )
        return {"ship_id": ship_id}


def main(argv: Optional[List[str]] = None) -> int:
    """
    Entry point for the demo server.

    - When called as a script/module (python -m server.run_api_v1_demo),
      argv will be None and argparse will consume sys.argv[1:].
    - When called programmatically (e.g. from tools/start_demo_server.py),
      argv can be an explicit list of CLI-style arguments.
    """
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
