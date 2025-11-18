from __future__ import annotations

import argparse
import logging
import math
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from sim import physics_v2
from server.api_server_v1 import run_api_server
from sim.missions import load_mission_and_fleet
from sim.sensors import SensorsManager
from sim.physics import GravBody, update_world, yaw_deg_to_forward_vector
from config.canonical_loader import load_ship_config

logger = logging.getLogger("demo_v2")
class DemoSimControllerV2:
    """Physics-enabled demo controller using API v1.0.

    This controller is the reference implementation for:
    - Ship instantiation from canonical mission + fleet configs.
    - Physics integration (via sim.physics).
    - Sensor/contact management (via sim.sensors).
    - API v1.0 handler methods (get_state, commands, etc.).

    Sprint 1 introduced the canonical control and autopilot fields.
    Sprint 2 adds behavioural autopilot for `coast`, `kill_vel` and a
    simple `chase_target` mode.
    """

    def __init__(self, mission_path: Path) -> None:
        self.mission_path = mission_path
        self.mission, self.fleet = load_mission_and_fleet(mission_path)

        self.sim_time: float = 0.0
        self.dt: float = 0.1

        self.ships: List[Dict[str, Any]] = self._instantiate_ships()
        self.projectiles: List[Dict[str, Any]] = []
        self._next_projectile_id: int = 1

        self.sensors = SensorsManager()
        self.gravity_bodies: List[GravBody] = []

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def _instantiate_ships(self) -> List[Dict[str, Any]]:
        ships: List[Dict[str, Any]] = []

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

            # Controls: canonical structure.
            controls = ship.get("controls") or {}
            thrust_vec = controls.get("thrust_vector") or [0.0, 0.0, 0.0]
            rotation_ctrl = controls.get("rotation_deg_s") or 0.0

            # Normalise thrust vector.
            if not isinstance(thrust_vec, (list, tuple)):
                thrust_vec = [0.0, 0.0, 0.0]
            if len(thrust_vec) < 3:
                thrust_vec = list(thrust_vec) + [0.0] * (3 - len(thrust_vec))
            elif len(thrust_vec) > 3:
                thrust_vec = list(thrust_vec[:3])

            # Normalise rotation control into a dict.
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

            ship["controls"] = {
                "thrust_vector": [
                    float(thrust_vec[0]),
                    float(thrust_vec[1]),
                    float(thrust_vec[2]),
                ],
                "rotation_deg_s": {
                    "yaw": yaw_rate,
                    "pitch": pitch_rate,
                    "roll": roll_rate,
                },
            }

            # Physics defaults (can be overridden per ship config).
            ship.setdefault(
                "physics",
                {
                    "max_main_thrust_newton": 1_000_000.0,
                    "max_rcs_yaw_deg_s": 10.0,
                },
            )

            # Autopilot structure.
            ship.setdefault(
                "autopilot",
                {
                    "enabled": False,
                    "mode": "manual",
                    "params": {},
                },
            )

            logger.info(
                "Ship instantiated: id=%s pos=%s vel=%s physics=%s controls=%s autopilot=%s",
                ship.get("id"),
                ship.get("position"),
                ship.get("velocity"),
                ship.get("physics"),
                ship.get("controls"),
                ship.get("autopilot"),
            )

            ships.append(ship)

        logger.info(
            "Instantiated %d ships from fleet '%s'",
            len(ships),
            self.fleet.get("id"),
        )
        return ships

    def _loop(self) -> None:
        logger.info("DemoSimControllerV2 loop started.")
        while self._running:
            self.sim_time += self.dt

            # Apply behavioural autopilot before physics integration.
            self._apply_autopilot()

            update_world(self.ships, self.projectiles, self.gravity_bodies, self.dt)
            self._update_sensors()
            time.sleep(self.dt)

    def _update_sensors(self) -> None:
        entities: List[Dict[str, Any]] = list(self.ships) + list(self.projectiles)
        for ship in self.ships:
            self.sensors.update_passive_for_ship(self.sim_time, ship, entities)
        self.sensors.advance_time(self.sim_time)

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Autopilot implementation
    # ------------------------------------------------------------------

    def _apply_autopilot(self) -> None:
        """Apply autopilot to all ships for this tick.

        Implemented modes:

        - manual: AP disabled; no changes to controls.
        - coast: sets thrust and rotation to zero (ship coasts).
        - kill_vel: rotate to oppose current velocity vector and burn to
          reduce speed; disables AP when speed is near zero.
        - chase_target: rotate towards current_target_id and apply forward
          thrust to reduce range.
        """

        for ship in self.ships:
            ap = ship.get("autopilot") or {}
            if not ap.get("enabled", False):
                continue

            mode = ap.get("mode", "manual")
            if mode == "manual":
                # Explicitly disabled.
                continue
            elif mode == "coast":
                self._ap_mode_coast(ship, ap)
            elif mode == "kill_vel":
                self._ap_mode_kill_vel(ship, ap)
            elif mode == "chase_target":
                self._ap_mode_chase_target(ship, ap)
            else:
                logger.debug(
                    "Unknown autopilot mode '%s' for ship %s; disabling",
                    mode,
                    ship.get("id"),
                )
                ap["enabled"] = False
                ap["mode"] = "manual"

    def _ap_mode_coast(self, ship: Dict[str, Any], ap: Dict[str, Any]) -> None:
        """Coast: zero thrust and rotation, preserve current velocity."""
        ship_id = ship.get("id")
        self.set_helm_input(
            ship_id=ship_id,
            thrust_vector=[0.0, 0.0, 0.0],
            rotation_input_deg_s={"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            mode="autopilot_coast",
        )

    def _ap_mode_kill_vel(self, ship: Dict[str, Any], ap: Dict[str, Any]) -> None:
        """Kill velocity: attempt to null current velocity vector."""
        ship_id = ship.get("id")
        vel = ship.get("velocity") or [0.0, 0.0, 0.0]
        vx, vy, vz = float(vel[0]), float(vel[1]), float(vel[2])
        speed = math.sqrt(vx * vx + vy * vy + vz * vz)

        stop_threshold = 0.5
        if speed < stop_threshold:
            self.set_helm_input(
                ship_id=ship_id,
                thrust_vector=[0.0, 0.0, 0.0],
                rotation_input_deg_s={"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
                mode="autopilot_kill_vel_complete",
            )
            ap["enabled"] = False
            ap["mode"] = "manual"
            logger.info("kill_vel complete for %s; speed=%.3f m/s", ship_id, speed)
            return

        yaw_current = float(ship.get("orientation_deg", 0.0))
        yaw_target = math.degrees(math.atan2(-vy, -vx))
        yaw_error = (yaw_target - yaw_current + 540.0) % 360.0 - 180.0

        k_yaw = 1.0
        yaw_cmd = k_yaw * yaw_error

        physics_cfg = ship.get("physics") or {}
        max_yaw_rate = float(physics_cfg.get("max_rcs_yaw_deg_s", 10.0))
        if yaw_cmd > max_yaw_rate:
            yaw_cmd = max_yaw_rate
        elif yaw_cmd < -max_yaw_rate:
            yaw_cmd = -max_yaw_rate

        throttle = min(1.0, speed / 20.0)
        if throttle < 0.1:
            throttle = 0.1

        self.set_helm_input(
            ship_id=ship_id,
            thrust_vector=[0.0, 0.0, throttle],
            rotation_input_deg_s={"yaw": yaw_cmd, "pitch": 0.0, "roll": 0.0},
            mode="autopilot_kill_vel",
        )

    def _ap_mode_chase_target(self, ship: Dict[str, Any], ap: Dict[str, Any]) -> None:
        """Chase target: orient towards target and apply forward thrust."""
        ship_id = ship.get("id")
        target_id = ship.get("current_target_id")
        if not target_id:
            logger.debug("chase_target: ship %s has no target; coasting", ship_id)
            self._ap_mode_coast(ship, ap)
            return

        target = None
        for entity in self.ships + self.projectiles:
            if entity.get("id") == target_id:
                target = entity
                break

        if target is None:
            logger.debug(
                "chase_target: ship %s target %s not found; disabling AP",
                ship_id,
                target_id,
            )
            ap["enabled"] = False
            ap["mode"] = "manual"
            return

        ship_pos = ship.get("position") or [0.0, 0.0, 0.0]
        tx = float(target.get("position", [0.0, 0.0, 0.0])[0])
        ty = float(target.get("position", [0.0, 0.0, 0.0])[1])
        tz = float(target.get("position", [0.0, 0.0, 0.0])[2])
        sx = float(ship_pos[0])
        sy = float(ship_pos[1])
        sz = float(ship_pos[2])

        dx = tx - sx
        dy = ty - sy
        dz = tz - sz
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        desired_range = float(ap.get("params", {}).get("desired_range_m", 5_000.0))
        min_range = float(ap.get("params", {}).get("min_range_m", 1_000.0))

        yaw_current = float(ship.get("orientation_deg", 0.0))
        yaw_target = math.degrees(math.atan2(dy, dx))
        yaw_error = (yaw_target - yaw_current + 540.0) % 360.0 - 180.0

        k_yaw = 1.0
        yaw_cmd = k_yaw * yaw_error

        physics_cfg = ship.get("physics") or {}
        max_yaw_rate = float(physics_cfg.get("max_rcs_yaw_deg_s", 10.0))
        if yaw_cmd > max_yaw_rate:
            yaw_cmd = max_yaw_rate
        elif yaw_cmd < -max_yaw_rate:
            yaw_cmd = -max_yaw_rate

        if dist < min_range:
            throttle = 0.0
        elif dist < desired_range:
            throttle = 0.3
        else:
            throttle = 0.8

        self.set_helm_input(
            ship_id=ship_id,
            thrust_vector=[0.0, 0.0, throttle],
            rotation_input_deg_s={"yaw": yaw_cmd, "pitch": 0.0, "roll": 0.0},
            mode="autopilot_chase_target",
        )

    # ------------------------------------------------------------------
    # API v1.0 handlers
    # ------------------------------------------------------------------

    def get_state(
        self,
        ship_id: Optional[str] = None,
        include_contacts: bool = True,
        include_projectiles: bool = True,
        include_raw_entities: bool = False,
    ) -> Dict[str, Any]:
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

        payload: Dict[str, Any] = {
            "server_time": self.sim_time,
            "own_ship": own_ship,
            "contacts": contacts,
            "projectiles": projectiles,
        }
        if include_raw_entities:
            payload["entities"] = {
                "ships": self.ships,
                "projectiles": self.projectiles,
            }

        return payload

    def get_events(self, since_time: Optional[float] = None) -> Dict[str, Any]:
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
        ship = next((s for s in self.ships if s["id"] == ship_id), None)
        if ship is None:
            return {"error": "unknown_ship", "ship_id": ship_id}
        ship["current_target_id"] = target_entity_id
        return {
            "ship_id": ship_id,
            "current_target_id": target_entity_id,
        }

    def fire_weapon(self, ship_id: str, weapon_mount_id: str) -> Dict[str, Any]:
        ship = next((s for s in self.ships if s["id"] == ship_id), None)
        if ship is None:
            logger.warning("fire_weapon: unknown ship_id=%s", ship_id)
            return {"error": "unknown_ship", "ship_id": ship_id}

        ship_pos = ship.get("position") or [0.0, 0.0, 0.0]
        ship_vel = ship.get("velocity") or [0.0, 0.0, 0.0]
        yaw = float(ship.get("orientation_deg", 0.0))

        forward = yaw_deg_to_forward_vector(yaw)

        muzzle_velocity = 2000.0
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
        contacts = self.sensors.execute_active_ping(
            self.sim_time,
            ship,
            entities,
            mode=mode,
        )
        return {"ship_id": ship_id, "mode": mode, "contacts": contacts}

    def set_autopilot_mode(
        self,
        ship_id: str,
        enabled: bool,
        mode: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ship = next((s for s in self.ships if s["id"] == ship_id), None)
        if ship is None:
            logger.warning("set_autopilot_mode: unknown ship_id=%s", ship_id)
            return {
                "error": "unknown_ship",
                "ship_id": ship_id,
                "enabled": enabled,
                "mode": mode,
            }

        allowed_modes = {"manual", "coast", "kill_vel", "chase_target"}
        chosen_mode = mode or "manual"
        if chosen_mode not in allowed_modes:
            logger.warning("set_autopilot_mode: invalid mode %s for ship %s", chosen_mode, ship_id)
            return {
                "error": "invalid_mode",
                "ship_id": ship_id,
                "enabled": enabled,
                "mode": chosen_mode,
                "allowed_modes": sorted(allowed_modes),
            }

        ap = ship.setdefault("autopilot", {})
        ap["enabled"] = bool(enabled) and (chosen_mode != "manual")
        ap["mode"] = chosen_mode
        ap["params"] = params or {}

        logger.info(
            "set_autopilot_mode: ship=%s enabled=%s mode=%s params=%s",
            ship_id,
            ap["enabled"],
            ap["mode"],
            ap["params"],
        )
        return {
            "ship_id": ship_id,
            "autopilot": {
                "enabled": ap["enabled"],
                "mode": ap["mode"],
                "params": ap["params"],
            },
        }

    def set_helm_input(
        self,
        ship_id: str,
        thrust_vector: List[float],
        rotation_input_deg_s: Any,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        ship = next((s for s in self.ships if s["id"] == ship_id), None)
        if ship is None:
            logger.warning("set_helm_input: unknown_ship_id=%s", ship_id)
            return {"error": "unknown_ship", "ship_id": ship_id}

        if not isinstance(thrust_vector, (list, tuple)):
            thrust = [0.0, 0.0, 0.0]
        else:
            thrust = list(thrust_vector)
        if len(thrust) < 3:
            thrust = thrust + [0.0] * (3 - len(thrust))
        elif len(thrust) > 3:
            thrust = thrust[:3]
        thrust = [max(-1.0, min(1.0, float(c))) for c in thrust]

        if isinstance(rotation_input_deg_s, (int, float)):
            yaw_rate = float(rotation_input_deg_s)
            pitch_rate = 0.0
            roll_rate = 0.0
        elif isinstance(rotation_input_deg_s, dict):
            yaw_rate = float(rotation_input_deg_s.get("yaw", 0.0))
            pitch_rate = float(rotation_input_deg_s.get("pitch", 0.0))
            roll_rate = float(rotation_input_deg_s.get("roll", 0.0))
        else:
            yaw_rate = 0.0
            pitch_rate = 0.0
            roll_rate = 0.0

        physics_cfg = ship.get("physics") or {}
        max_yaw_rate_deg_s = float(physics_cfg.get("max_rcs_yaw_deg_s", 10.0))

        if yaw_rate > max_yaw_rate_deg_s:
            yaw_rate = max_yaw_rate_deg_s
        elif yaw_rate < -max_yaw_rate_deg_s:
            yaw_rate = -max_yaw_rate_deg_s

        controls = ship.setdefault("controls", {})
        controls["thrust_vector"] = thrust
        controls["rotation_deg_s"] = {
            "yaw": yaw_rate,
            "pitch": pitch_rate,
            "roll": roll_rate,
        }
        if mode is not None:
            controls["mode"] = str(mode)

        logger.info(
            "set_helm_input: ship=%s thrust=%s yaw=%.3f pitch=%.3f roll=%.3f mode=%s",
            ship_id,
            thrust,
            yaw_rate,
            pitch_rate,
            roll_rate,
            controls.get("mode"),
        )
        return {
            "ship_id": ship_id,
            "controls": controls,
        }


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Starting Flaxos Spaceship Sim demo server v2 "
        "(physics-enabled, Sprint 2 autopilot)"
    )

    parser = argparse.ArgumentParser(description="Run Flaxos Spaceship Sim API demo server v2")
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

    sim = DemoSimControllerV2(mission_path)
    run_api_server(sim, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
