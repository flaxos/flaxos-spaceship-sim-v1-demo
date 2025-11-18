from __future__ import annotations

import json
import logging
import socketserver
from typing import Any, Callable, Dict, Optional

from .api_envelope import (
    APIRequest,
    APIProtocolError,
    make_response,
    normalise_request,
    API_VERSION,
)
from version import __version__ as SERVER_VERSION

logger = logging.getLogger("server.api_v1")
logger.setLevel(logging.INFO)


class APIV1TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, server_address, RequestHandlerClass, sim_controller):
        super().__init__(server_address, RequestHandlerClass)
        self.sim_controller = sim_controller
        self.handlers: Dict[str, Callable[[APIRequest], Dict[str, Any]]] = {
            "get_state": self._handle_get_state,
            "get_events": self._handle_get_events,
            "get_mission": self._handle_get_mission,
            "get_server_info": self._handle_get_server_info,
            "command.set_target": self._handle_command_set_target,
            "command.fire_weapon": self._handle_command_fire_weapon,
            "command.ping_sensors": self._handle_command_ping_sensors,
            "command.set_autopilot_mode": self._handle_command_set_autopilot_mode,
            "command.set_helm_input": self._handle_command_set_helm_input,
        }

    def dispatch_request(self, req: APIRequest) -> Dict[str, Any]:
        handler = self.handlers.get(req.action)
        if handler is None:
            logger.warning("Unknown action '%s'", req.action)
            return make_response(
                req,
                status="error",
                payload={},
                error=f"Unknown action '{req.action}'",
            )
        try:
            payload = handler(req)
            return make_response(req, status="ok", payload=payload, error=None)
        except Exception as exc:
            logger.exception("Error while handling action '%s'", req.action)
            return make_response(
                req,
                status="error",
                payload={},
                error=f"Internal error: {exc}",
            )

    def _handle_get_state(self, req: APIRequest) -> Dict[str, Any]:
        p = req.payload
        ship_id = p.get("ship_id")
        include_contacts = bool(p.get("include_contacts", True))
        include_projectiles = bool(p.get("include_projectiles", True))
        include_raw_entities = bool(p.get("include_raw_entities", False))
        return self.sim_controller.get_state(
            ship_id=ship_id,
            include_contacts=include_contacts,
            include_projectiles=include_projectiles,
            include_raw_entities=include_raw_entities,
        )

    def _handle_get_events(self, req: APIRequest) -> Dict[str, Any]:
        p = req.payload
        since_time = p.get("since_time")
        return self.sim_controller.get_events(since_time=since_time)

    def _handle_get_mission(self, req: APIRequest) -> Dict[str, Any]:
        mission = self.sim_controller.get_mission()
        if isinstance(mission, dict):
            mission = dict(mission)
            mission.setdefault("server_info", {})
            mission["server_info"]["server_version"] = SERVER_VERSION
            mission["server_info"]["api_version"] = API_VERSION
        return mission

    def _handle_get_server_info(self, req: APIRequest) -> Dict[str, Any]:
        return {
            "server_version": SERVER_VERSION,
            "api_version": API_VERSION,
            "capabilities": list(self.handlers.keys()),
        }

    def _handle_command_set_target(self, req: APIRequest) -> Dict[str, Any]:
        p = req.payload
        ship_id = p.get("ship_id")
        target_entity_id = p.get("target_entity_id")
        if not ship_id or not target_entity_id:
            raise ValueError("ship_id and target_entity_id are required")
        return self.sim_controller.set_target(
            ship_id=ship_id, target_entity_id=target_entity_id
        )

    def _handle_command_fire_weapon(self, req: APIRequest) -> Dict[str, Any]:
        p = req.payload
        ship_id = p.get("ship_id")
        weapon_mount_id = p.get("weapon_mount_id")
        if not ship_id or not weapon_mount_id:
            raise ValueError("ship_id and weapon_mount_id are required")
        return self.sim_controller.fire_weapon(
            ship_id=ship_id, weapon_mount_id=weapon_mount_id
        )

    def _handle_command_ping_sensors(self, req: APIRequest) -> Dict[str, Any]:
        p = req.payload
        ship_id = p.get("ship_id")
        mode = p.get("mode", "active")
        if not ship_id:
            raise ValueError("ship_id is required")
        return self.sim_controller.ping_sensors(ship_id=ship_id, mode=mode)

    def _handle_command_set_autopilot_mode(self, req: APIRequest) -> Dict[str, Any]:
        p = req.payload
        ship_id = p.get("ship_id")
        enabled = bool(p.get("enabled", True))
        mode = p.get("mode")
        params = p.get("params") or {}
        if not ship_id:
            raise ValueError("ship_id is required")
        return self.sim_controller.set_autopilot_mode(
            ship_id=ship_id, enabled=enabled, mode=mode, params=params
        )

    def _handle_command_set_helm_input(self, req: APIRequest) -> Dict[str, Any]:
        p = req.payload
        ship_id = p.get("ship_id")
        thrust_vector = p.get("thrust_vector", [0.0, 0.0, 0.0])
        rotation_input_deg_s = p.get("rotation_deg_s", p.get("rotation_input_deg_s", 0.0))
        if not ship_id:
            raise ValueError("ship_id is required")
        if not isinstance(thrust_vector, (list, tuple)) or len(thrust_vector) != 3:
            raise ValueError("thrust_vector must be a 3-element list")
        # Rotation input can be a single yaw rate or a dict including pitch/roll.
        if isinstance(rotation_input_deg_s, dict):
            rotation_payload = {
                "yaw": float(rotation_input_deg_s.get("yaw", 0.0)),
                "pitch": float(rotation_input_deg_s.get("pitch", 0.0)),
                "roll": float(rotation_input_deg_s.get("roll", 0.0)),
            }
        else:
            rotation_payload = float(rotation_input_deg_s)
        return self.sim_controller.set_helm_input(
            ship_id=ship_id,
            thrust_vector=list(thrust_vector),
            rotation_input_deg_s=rotation_payload,
        )


class APIV1RequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        for raw_line in self.rfile:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            req = None
            try:
                raw_obj = json.loads(line)
                req = normalise_request(raw_obj)
                response = self.server.dispatch_request(req)
            except json.JSONDecodeError as exc:
                logger.warning("Invalid JSON from client: %s", exc)
                response = make_response(
                    None, status="error", payload={}, error=f"Invalid JSON: {exc}"
                )
            except APIProtocolError as exc:
                logger.warning("Protocol error from client: %s", exc)
                response = make_response(
                    None, status="error", payload={}, error=str(exc)
                )
            try:
                data = json.dumps(response).encode("utf-8") + b"\n"
                self.wfile.write(data)
                self.wfile.flush()
            except Exception as exc:
                logger.exception("Failed to send response: %s", exc)
                break


def run_api_server(sim_controller, host: str = "0.0.0.0", port: int = 8765) -> None:
    server = APIV1TCPServer((host, port), APIV1RequestHandler, sim_controller)
    logger.info(
        "API v1.0 server listening on %s:%d (api_version=%s, server_version=%s)",
        host,
        port,
        API_VERSION,
        SERVER_VERSION,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("API v1.0 server interrupted, shutting down")
    finally:
        server.server_close()
