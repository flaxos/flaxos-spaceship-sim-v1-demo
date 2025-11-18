from __future__ import annotations

import json
import socket
import threading
from typing import Any, Dict, Optional


class APIClientError(Exception):
    pass


class APIClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._next_request_id = 1

    def connect(self) -> None:
        if self._sock is not None:
            return
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        self._sock = sock

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> "APIClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _recv_line(self) -> str:
        assert self._sock is not None
        chunks = []
        while True:
            chunk = self._sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        if not chunks:
            raise APIClientError("Connection closed by server")
        line = b"".join(chunks).split(b"\n", 1)[0]
        return line.decode("utf-8").strip()

    def request(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._sock is None:
            raise APIClientError("Client not connected")
        with self._lock:
            req_id = str(self._next_request_id)
            self._next_request_id += 1
            obj = {
                "api_version": "1.0",
                "request_id": req_id,
                "action": action,
                "payload": payload,
            }
            data = json.dumps(obj).encode("utf-8") + b"\n"
            self._sock.sendall(data)
            resp_line = self._recv_line()
            resp = json.loads(resp_line)
            if resp.get("status") != "ok":
                raise APIClientError(resp.get("error") or "Unknown error")
            return resp

    def get_state(self, ship_id: Optional[str], include_contacts=True, include_projectiles=True, include_raw_entities=False) -> Dict[str, Any]:
        resp = self.request(
            "get_state",
            {
                "ship_id": ship_id,
                "include_contacts": include_contacts,
                "include_projectiles": include_projectiles,
                "include_raw_entities": include_raw_entities,
            },
        )
        return resp["payload"]

    def get_mission(self) -> Dict[str, Any]:
        return self.request("get_mission", {})["payload"]

    def get_server_info(self) -> Dict[str, Any]:
        return self.request("get_server_info", {})["payload"]

    def fire_weapon(self, ship_id: str, weapon_mount_id: str) -> Dict[str, Any]:
        return self.request(
            "command.fire_weapon",
            {"ship_id": ship_id, "weapon_mount_id": weapon_mount_id},
        )["payload"]
