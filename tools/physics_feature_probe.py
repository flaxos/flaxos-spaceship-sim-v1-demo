#!/usr/bin/env python
"""
tools/physics_feature_probe.py

API-level physics feature probe for Flaxos Spaceship Sim.

This script:
  - Connects to the TCP API v1.0.
  - Runs a sequence of actions to exercise 3D thrust, rotation, and gravity.
  - Captures outputs to JSON files for offline inspection.

It does NOT require direct access to sim internals; everything is via the public API.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


API_VERSION = "1.0"


class ApiError(RuntimeError):
    pass


class ApiClientV1:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.sock_file = None
        self._next_request_id = 1

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port))
        self.sock_file = self.sock.makefile("rw", encoding="utf-8", newline="\n")

    def close(self) -> None:
        try:
            if self.sock_file:
                self.sock_file.close()
        finally:
            if self.sock:
                self.sock.close()

    def _next_id(self) -> str:
        rid = str(self._next_request_id)
        self._next_request_id += 1
        return rid

    def send_request(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.sock_file:
            raise RuntimeError("Client not connected")

        envelope = {
            "api_version": API_VERSION,
            "request_id": self._next_id(),
            "action": action,
            "payload": payload,
        }
        line = json.dumps(envelope)
        self.sock_file.write(line + "\n")
        self.sock_file.flush()

        resp_line = self.sock_file.readline()
        if not resp_line:
            raise ApiError("Server closed connection")

        try:
            resp = json.loads(resp_line)
        except json.JSONDecodeError as e:
            raise ApiError(f"Invalid JSON from server: {e}") from e

        if resp.get("status") != "ok":
            raise ApiError(f"API error: {resp.get('error')}")

        return resp

    # Convenience methods

    def get_server_info(self) -> Dict[str, Any]:
        return self.send_request("get_server_info", {})["payload"]

    def get_mission(self) -> Dict[str, Any]:
        return self.send_request("get_mission", {})["payload"]

    def get_state(self, ship_id: str) -> Dict[str, Any]:
        return self.send_request("get_state", {"ship_id": ship_id})["payload"]

    def set_helm_input(
        self,
        ship_id: str,
        thrust_vector: List[float],
        rotation_deg_s: Dict[str, float],
    ) -> Dict[str, Any]:
        payload = {
            "ship_id": ship_id,
            "thrust_vector": thrust_vector,
            "rotation_deg_s": rotation_deg_s,
        }
        return self.send_request("command.set_helm_input", payload)["payload"]

    def set_autopilot_mode(
        self,
        ship_id: str,
        enabled: bool,
        mode: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "ship_id": ship_id,
            "enabled": enabled,
            "mode": mode,
            "params": params or {},
        }
        return self.send_request("command.set_autopilot_mode", payload)["payload"]


def _write_json(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=False)


def _extract_own_ship_state(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload.get("own_ship") or {}


def _vec_diff(a: List[float], b: List[float]) -> List[float]:
    return [b[i] - a[i] for i in range(3)]


def run_probe(
    host: str,
    port: int,
    ship_id: str,
    out_dir_root: str = "debug_physics",
) -> str:
    ts = datetime.utcnow().strftime("run_%Y%m%d_%H%M%S")
    out_dir = os.path.join(out_dir_root, ts)
    os.makedirs(out_dir, exist_ok=True)

    summary: Dict[str, Dict[str, Any]] = {}
    client = ApiClientV1(host, port)
    client.connect()

    try:
        # 01: server info
        step_name = "01_get_server_info"
        t0 = time.time()
        try:
            info = client.get_server_info()
            _write_json(os.path.join(out_dir, f"{step_name}.json"), info)
            summary[step_name] = {"status": "ok", "duration_s": time.time() - t0}
        except Exception as e:
            summary[step_name] = {"status": "error", "error": str(e)}
            return out_dir

        # 02: mission info
        step_name = "02_get_mission"
        t0 = time.time()
        try:
            mission = client.get_mission()
            _write_json(os.path.join(out_dir, f"{step_name}.json"), mission)
            summary[step_name] = {"status": "ok", "duration_s": time.time() - t0}
        except Exception as e:
            summary[step_name] = {"status": "error", "error": str(e)}
            return out_dir

        # 03: baseline state
        step_name = "03_get_state_baseline"
        t0 = time.time()
        baseline_state = client.get_state(ship_id)
        _write_json(os.path.join(out_dir, f"{step_name}.json"), baseline_state)
        summary[step_name] = {"status": "ok", "duration_s": time.time() - t0}

        own0 = _extract_own_ship_state(baseline_state)
        pos0 = own0.get("position", [0.0, 0.0, 0.0])
        vel0 = own0.get("velocity", [0.0, 0.0, 0.0])

        # 04: thrust_forward_motion (main drive along forward axis)
        step_name = "04_thrust_forward_motion"
        t0 = time.time()
        try:
            client.set_autopilot_mode(ship_id, enabled=False, mode="manual", params={})
            client.set_helm_input(
                ship_id=ship_id,
                thrust_vector=[0.0, 0.0, 0.5],
                rotation_deg_s={"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            )

            time.sleep(5.0)  # let the sim tick
            state_after = client.get_state(ship_id)
            _write_json(os.path.join(out_dir, f"{step_name}.json"), state_after)
            own = _extract_own_ship_state(state_after)
            pos = own.get("position", [0.0, 0.0, 0.0])
            vel = own.get("velocity", [0.0, 0.0, 0.0])

            delta_pos = _vec_diff(pos0, pos)
            delta_vel = _vec_diff(vel0, vel)

            summary[step_name] = {
                "status": "ok",
                "duration_s": time.time() - t0,
                "delta_pos": delta_pos,
                "delta_vel": delta_vel,
            }
        except Exception as e:
            summary[step_name] = {"status": "error", "error": str(e)}

        # 05: rotation_rcs (yaw change)
        step_name = "05_rotation_rcs"
        t0 = time.time()
        try:
            # zero thrust, rotate yaw
            client.set_helm_input(
                ship_id=ship_id,
                thrust_vector=[0.0, 0.0, 0.0],
                rotation_deg_s={"yaw": 5.0, "pitch": 0.0, "roll": 0.0},
            )
            time.sleep(4.0)

            state_after = client.get_state(ship_id)
            _write_json(os.path.join(out_dir, f"{step_name}.json"), state_after)
            own = _extract_own_ship_state(state_after)
            euler = own.get("orientation_euler_deg", {})
            yaw = euler.get("yaw", own.get("orientation_deg", 0.0))

            summary[step_name] = {
                "status": "ok",
                "duration_s": time.time() - t0,
                "yaw_deg": yaw,
            }
        except Exception as e:
            summary[step_name] = {"status": "error", "error": str(e)}

        # 06: 3D_off_axis_thrust (e.g. "up" + "forward")
        step_name = "06_3d_off_axis_thrust"
        t0 = time.time()
        try:
            # reset to manual, low yaw rate
            client.set_autopilot_mode(ship_id, enabled=False, mode="manual", params={})
            # start from current state
            state_before = client.get_state(ship_id)
            own_before = _extract_own_ship_state(state_before)
            pos_before = own_before.get("position", [0.0, 0.0, 0.0])
            vel_before = own_before.get("velocity", [0.0, 0.0, 0.0])

            # thrust somewhat "up" (y) and "forward" (z) in control space
            client.set_helm_input(
                ship_id=ship_id,
                thrust_vector=[0.0, 0.5, 0.5],
                rotation_deg_s={"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            )
            time.sleep(5.0)

            state_after = client.get_state(ship_id)
            _write_json(os.path.join(out_dir, f"{step_name}.json"), state_after)
            own_after = _extract_own_ship_state(state_after)
            pos_after = own_after.get("position", [0.0, 0.0, 0.0])
            vel_after = own_after.get("velocity", [0.0, 0.0, 0.0])

            delta_pos = _vec_diff(pos_before, pos_after)
            delta_vel = _vec_diff(vel_before, vel_after)

            summary[step_name] = {
                "status": "ok",
                "duration_s": time.time() - t0,
                "delta_pos": delta_pos,
                "delta_vel": delta_vel,
            }
        except Exception as e:
            summary[step_name] = {"status": "error", "error": str(e)}

        # 07: gravity_probe (optional, depends on mission having grav_bodies)
        step_name = "07_gravity_probe"
        t0 = time.time()
        try:
            # Gravity effect is subtle; we simply observe velocity changes
            # over a coast period and record them. Interpretation is manual.
            client.set_autopilot_mode(ship_id, enabled=False, mode="manual", params={})
            client.set_helm_input(
                ship_id=ship_id,
                thrust_vector=[0.0, 0.0, 0.0],
                rotation_deg_s={"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            )

            state_before = client.get_state(ship_id)
            own_before = _extract_own_ship_state(state_before)
            pos_before = own_before.get("position", [0.0, 0.0, 0.0])
            vel_before = own_before.get("velocity", [0.0, 0.0, 0.0])

            # coast for 10 seconds
            time.sleep(10.0)

            state_after = client.get_state(ship_id)
            _write_json(os.path.join(out_dir, f"{step_name}.json"), state_after)
            own_after = _extract_own_ship_state(state_after)
            pos_after = own_after.get("position", [0.0, 0.0, 0.0])
            vel_after = own_after.get("velocity", [0.0, 0.0, 0.0])

            delta_pos = _vec_diff(pos_before, pos_after)
            delta_vel = _vec_diff(vel_before, vel_after)

            summary[step_name] = {
                "status": "ok",
                "duration_s": time.time() - t0,
                "delta_pos": delta_pos,
                "delta_vel": delta_vel,
                "note": "If grav_bodies exist, expect non-linear drift; otherwise, velocity should stay constant.",
            }
        except Exception as e:
            summary[step_name] = {"status": "error", "error": str(e)}

        # 08: notes_axes (documentation snapshot)
        step_name = "08_notes_axes"
        t0 = time.time()
        try:
            notes = {
                "ship_id": ship_id,
                "axes_convention": {
                    "position": "x,y,z in km (world frame)",
                    "velocity": "vx,vy,vz in km/s (world frame)",
                    "thrust_vector": "[sx, sy, sfwd] in control space; sfwd drives main engine",
                    "orientation_euler_deg": "yaw, pitch, roll in degrees; yaw also mirrored to orientation_deg",
                },
                "recommendation": "Use ShipOS 'thr 0.5 forward' / 'yaw 5 left' and watch position/orientation in get_state.",
            }
            _write_json(os.path.join(out_dir, f"{step_name}.json"), notes)
            summary[step_name] = {"status": "ok", "duration_s": time.time() - t0}
        except Exception as e:
            summary[step_name] = {"status": "error", "error": str(e)}

    finally:
        client.close()

    _write_json(os.path.join(out_dir, "summary.json"), summary)
    return out_dir


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    host = "127.0.0.1"
    port = 8765
    ship_id = "interceptor_alpha"

    for arg in argv:
        if arg.startswith("--host="):
            host = arg.split("=", 1)[1]
        elif arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg.startswith("--ship="):
            ship_id = arg.split("=", 1)[1]

    out_dir = run_probe(host, port, ship_id)
    print(f"[DEBUG] Physics feature probe complete. Output in: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
