from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any, Dict

from server.api_server_v1 import APIV1TCPServer, APIV1RequestHandler
from server.api_envelope import API_VERSION
from version import __version__ as SERVER_VERSION


class DummySimController:
    def __init__(self) -> None:
        self.calls = []

    def get_state(self, ship_id, include_contacts, include_projectiles, include_raw_entities):
        self.calls.append(("get_state", ship_id))
        return {"server_time": 0.0, "own_ship": {"id": ship_id}, "contacts": [], "projectiles": []}

    def get_events(self, since_time):
        self.calls.append(("get_events", since_time))
        return {"events": []}

    def get_mission(self):
        self.calls.append(("get_mission", None))
        return {
            "id": "test_mission",
            "title": "Test Mission",
            "description": "Test",
            "fleet": {"fleet_dir": "hybrid_fleet", "fleet_file": "fleet.json"},
            "win_condition": {"type": "destroy_team", "team": "red"},
            "lose_condition": {"type": "destroy_team", "team": "blue"},
            "time_limit_s": None,
            "metadata": {},
        }

    def set_target(self, ship_id, target_entity_id):
        return {"ship_id": ship_id, "current_target_id": target_entity_id}

    def fire_weapon(self, ship_id, weapon_mount_id):
        return {"projectile_id": "p_001"}

    def ping_sensors(self, ship_id, mode):
        return {"ship_id": ship_id, "mode": mode, "contacts": []}

    def set_autopilot_mode(self, ship_id, enabled, mode):
        return {"ship_id": ship_id, "autopilot_enabled": enabled, "mode": mode}

    def set_helm_input(self, ship_id, thrust_vector, rotation_input_deg_s):
        return {"ship_id": ship_id}


def _start_server(port: int) -> APIV1TCPServer:
    sim = DummySimController()
    server = APIV1TCPServer(("127.0.0.1", port), APIV1RequestHandler, sim)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.1)
    return server


def _send(port: int, obj: Dict[str, Any]) -> Dict[str, Any]:
    with socket.create_connection(("127.0.0.1", port), timeout=2.0) as sock:
        data = json.dumps(obj).encode("utf-8") + b"\n"
        sock.sendall(data)
        resp = b""
        while not resp.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            resp += chunk
    return json.loads(resp.decode("utf-8").strip())


def test_get_server_info():
    server = _start_server(9876)
    try:
        req = {"api_version": API_VERSION, "request_id": "1", "action": "get_server_info", "payload": {}}
        resp = _send(9876, req)
        assert resp["status"] == "ok"
        payload = resp["payload"]
        assert payload["server_version"] == SERVER_VERSION
        assert payload["api_version"] == API_VERSION
        assert "get_state" in payload["capabilities"]
    finally:
        server.shutdown()
        server.server_close()
