#!/usr/bin/env python
import argparse
import json
import socket
import sys
import textwrap
from typing import Any, Dict, List, Optional


API_VERSION = "1.0"

DEFAULT_ROTATION_LIMIT_DEG_S = 10.0


def clamp(value: float, min_value: float = -1.0, max_value: float = 1.0) -> float:
    return max(min_value, min(max_value, value))


def parse_thrust_command(args: List[str], current_vector: List[float]) -> List[float]:
    """
    Parse a thrust command into a new thrust vector.

    Args:
        args: CLI tokens after "thrust".
        current_vector: Current thrust vector to update.

    Returns a new clamped thrust vector (sx, sy, sfwd).
    """

    try:
        magnitude = abs(float(args[0]))
    except (ValueError, IndexError):
        raise ValueError("Magnitude must be a number between 0 and 1.")

    magnitude = clamp(magnitude, 0.0, 1.0)

    direction = "forward"
    if len(args) >= 2:
        direction = args[1].lower()

    if direction == "stop":
        return [0.0, 0.0, 0.0]

    dir_map = {
        "forward": (2, 1.0),
        "back": (2, -1.0),
        "reverse": (2, -1.0),
        "backward": (2, -1.0),
        "left": (1, 1.0),
        "right": (1, -1.0),
        "up": (0, 1.0),
        "down": (0, -1.0),
    }

    if direction not in dir_map:
        raise ValueError("Direction must be one of: forward, back, left, right, up, down, stop")

    idx, sign = dir_map[direction]
    new_vec = list(current_vector)
    new_vec[idx] = clamp(sign * magnitude)
    return new_vec


def parse_rotation_command(
    axis: str,
    args: List[str],
    current_rotation: Dict[str, float],
    rotation_limits: Dict[str, float],
) -> Dict[str, float]:
    """
    Parse a rotation command for yaw/pitch/roll.

    Updates only the specified axis while keeping the other values.
    """

    axis = axis.lower()
    if axis not in ("yaw", "pitch", "roll"):
        raise ValueError("Axis must be yaw, pitch, or roll")

    limit = float(rotation_limits.get(axis, DEFAULT_ROTATION_LIMIT_DEG_S))

    direction_tokens = {
        "yaw": {"left": 1.0, "right": -1.0},
        "pitch": {"up": 1.0, "down": -1.0},
        "roll": {"left": 1.0, "right": -1.0},
    }

    # Allow shorthand stop for rotation axes
    if args and args[0].lower() == "stop":
        new_rotation = dict(current_rotation)
        new_rotation[axis] = 0.0
        return new_rotation

    try:
        magnitude = abs(float(args[0]))
    except (ValueError, IndexError):
        raise ValueError(f"{axis.capitalize()} rate must be a number (degrees per second).")

    direction = args[1].lower() if len(args) >= 2 else None
    if direction is None:
        sign = 1.0
    elif direction == "stop":
        sign = 0.0
    else:
        sign_map = direction_tokens[axis]
        if direction not in sign_map:
            raise ValueError(
                "Direction must be one of: left/right for yaw/roll, up/down for pitch, or stop"
            )
        sign = sign_map[direction]

    magnitude = clamp(magnitude, 0.0, limit)
    new_value = clamp(sign * magnitude, -limit, limit)

    new_rotation = dict(current_rotation)
    new_rotation[axis] = new_value
    return new_rotation


class ApiError(RuntimeError):
    pass


class ApiClientV1:
    """
    Minimal TCP JSON client for the Flaxos Spaceship Sim API v1.0.
    Uses newline-delimited JSON envelopes.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.sock_file = None
        self._next_request_id = 1

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port))
        # text mode for simple readline/write line
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

        response_line = self.sock_file.readline()
        if not response_line:
            raise ApiError("Server closed connection")

        try:
            resp = json.loads(response_line)
        except json.JSONDecodeError as e:
            raise ApiError(f"Invalid JSON from server: {e}") from e

        status = resp.get("status", "error")
        if status != "ok":
            raise ApiError(f"API error: {resp.get('error')}")

        return resp

    # Convenience wrappers

    def get_server_info(self) -> Dict[str, Any]:
        return self.send_request("get_server_info", {})["payload"]

    def get_mission(self) -> Dict[str, Any]:
        return self.send_request("get_mission", {})["payload"]

    def get_state(self, ship_id: str) -> Dict[str, Any]:
        payload = {"ship_id": ship_id}
        return self.send_request("get_state", payload)["payload"]

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

    def ping_sensors(self, ship_id: str, mode: str) -> Dict[str, Any]:
        payload = {
            "ship_id": ship_id,
            "mode": mode,
        }
        return self.send_request("command.ping_sensors", payload)["payload"]


class ShipOsShell:
    """
    Simple in-universe ShipOS shell:
      - Connects to the API v1.0 TCP server
      - Maintains a current ship and context (helm/nav/sensors/weapons)
      - Exposes basic commands for manual control & inspection
    """

    def __init__(
        self,
        client: ApiClientV1,
        ship_id: str,
        context: str,
    ) -> None:
        self.client = client
        self.ship_id = ship_id
        self.context = context

        # Local cached control state for helm
        self.thrust_vector: List[float] = [0.0, 0.0, 0.0]
        self.rotation_deg_s: Dict[str, float] = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
        self.rotation_limits: Dict[str, float] = {
            "yaw": DEFAULT_ROTATION_LIMIT_DEG_S,
            "pitch": DEFAULT_ROTATION_LIMIT_DEG_S,
            "roll": DEFAULT_ROTATION_LIMIT_DEG_S,
        }

    # ----------------- Utility & printing helpers -----------------

    def print_banner(self) -> None:
        print("ShipOS shell connected. Type 'help' for commands, 'quit' to exit.")

    def prompt(self) -> str:
        return f"{self.ship_id}@{self.context}> "

    @staticmethod
    def pretty_print(obj: Any) -> None:
        print(json.dumps(obj, indent=2, sort_keys=False))

    def load_initial_state(self) -> None:
        """
        Optionally fetch initial ship controls from get_state
        so we don't stomp anything unexpectedly.
        """
        try:
            state = self.client.get_state(self.ship_id)
        except Exception as e:
            print(f"[WARN] Could not fetch initial state: {e}")
            return

        own = state.get("own_ship") or {}
        controls = own.get("controls") or {}
        thrust_vec = controls.get("thrust_vector")
        rot = controls.get("rotation_deg_s")
        physics = own.get("physics") or {}

        if isinstance(thrust_vec, list) and len(thrust_vec) == 3:
            self.thrust_vector = [float(thrust_vec[0]), float(thrust_vec[1]), float(thrust_vec[2])]
        if isinstance(rot, dict):
            self.rotation_deg_s["yaw"] = float(rot.get("yaw", 0.0))
            self.rotation_deg_s["pitch"] = float(rot.get("pitch", 0.0))
            self.rotation_deg_s["roll"] = float(rot.get("roll", 0.0))
        self.rotation_limits["yaw"] = float(
            physics.get("max_rcs_yaw_deg_s", self.rotation_limits["yaw"])
        )
        self.rotation_limits["pitch"] = float(
            physics.get("max_rcs_pitch_deg_s", self.rotation_limits["pitch"])
        )
        self.rotation_limits["roll"] = float(
            physics.get("max_rcs_roll_deg_s", self.rotation_limits["roll"])
        )

    # ----------------- Command loop -----------------

    def run(self) -> None:
        self.print_banner()
        self.load_initial_state()

        while True:
            try:
                line = input(self.prompt())
            except EOFError:
                print()
                break

            line = line.strip()
            if not line:
                continue

            if line.lower() in ("quit", "exit"):
                break

            try:
                self.handle_line(line)
            except ApiError as e:
                print(f"[API ERROR] {e}")
            except Exception as e:
                print(f"[ERROR] Internal error: {e}")

    def handle_line(self, line: str) -> None:
        parts = line.split()
        cmd = parts[0].lower()

        # Global commands
        if cmd == "help":
            self.show_help()
            return
        if cmd == "context":
            self.cmd_context(parts[1:])
            return
        if cmd == "state":
            self.cmd_state()
            return
        if cmd == "mission":
            self.cmd_mission()
            return

        # Context-specific commands
        if self.context == "helm":
            self.handle_helm_command(cmd, parts[1:])
        elif self.context == "nav":
            self.handle_nav_command(cmd, parts[1:])
        elif self.context == "sensors":
            self.handle_sensors_command(cmd, parts[1:])
        elif self.context == "weapons":
            self.handle_weapons_command(cmd, parts[1:])
        else:
            print(f"[WARN] Unknown context '{self.context}'. Use: context helm|nav|sensors|weapons.")

    # ----------------- Global commands -----------------

    def show_help(self) -> None:
        msg = """
        Global:
          help                     Show this help
          context <ctx>            Switch context: helm, nav, sensors, weapons
          state                    Fetch current ship state
          mission                  Fetch mission info
          quit / exit              Leave the shell

        Helm context (context helm):
          thrust <mag> [forward|back|left|right|up|down|stop]
                                   Set thrust vector component (0..1). Default direction=forward.
          yaw <deg_per_s> [left|right|stop]
                                   Set yaw rotation (deg/sec). Default=left. Shorthand: yaw <deg>.
          pitch <deg_per_s> [up|down|stop]
                                   Set pitch rotation (deg/sec). Default=up. Shorthand: pitch <deg>.
          roll <deg_per_s> [left|right|stop]
                                   Set roll rotation (deg/sec). Default=left. Shorthand: roll <deg>.
          rot stop                  Zero all rotation rates.

        Nav context (context nav):
          autopilot manual         Disable AP (manual control)
          autopilot coast          Enable AP coast mode
          autopilot kill-velocity  Enable AP kill_vel mode
          autopilot chase <target_id> [range_m]
                                   Enable AP chase_target mode

        Sensors context (context sensors):
          ping active              Active sensor ping
          ping passive             Passive refresh (where supported)

        Weapons context (context weapons):
          (Reserved for future expansion)
        """
        print(textwrap.dedent(msg).strip())

    def cmd_context(self, args: List[str]) -> None:
        if not args:
            print(f"Current context: {self.context}")
            return
        new_ctx = args[0].lower()
        if new_ctx not in ("helm", "nav", "sensors", "weapons"):
            print("Valid contexts: helm, nav, sensors, weapons")
            return
        self.context = new_ctx

    def cmd_state(self) -> None:
        state = self.client.get_state(self.ship_id)
        own = state.get("own_ship") or {}

        orientation_euler = own.get("orientation_euler_deg")
        if not isinstance(orientation_euler, dict):
            orientation_euler = {
                "yaw": float(own.get("orientation_deg", 0.0)),
                "pitch": 0.0,
                "roll": 0.0,
            }

        summary = {
            "server_time": state.get("server_time"),
            "own_ship": {
                "id": own.get("id"),
                "position": own.get("position"),
                "velocity": own.get("velocity"),
                "orientation_euler_deg": orientation_euler,
                "controls": own.get("controls"),
            },
        }
        self.pretty_print(summary)

    def cmd_mission(self) -> None:
        mission = self.client.get_mission()
        self.pretty_print(mission)

    # ----------------- HELM -----------------

    def handle_helm_command(self, cmd: str, args: List[str]) -> None:
        if cmd == "thrust":
            self.cmd_helm_thrust(args)
        elif cmd == "yaw":
            self.cmd_helm_yaw(args)
        elif cmd == "pitch":
            self.cmd_helm_pitch(args)
        elif cmd == "roll":
            self.cmd_helm_roll(args)
        elif cmd == "rot":
            self.cmd_helm_rot_stop(args)
        else:
            print(
                f"[WARN] Unknown helm command '{cmd}'. Try: thrust, yaw, pitch, roll, rot, or 'help'."
            )

    def cmd_helm_thrust(self, args: List[str]) -> None:
        if not args:
            print("Usage: thrust <magnitude 0..1> [forward|back|left|right|up|down|stop]")
            return

        try:
            self.thrust_vector = parse_thrust_command(args, self.thrust_vector)
        except ValueError as exc:
            print(exc)
            return

        self._send_helm_update()
        print(
            json.dumps(
                {
                    "ship_id": self.ship_id,
                    "thrust_vector": self.thrust_vector,
                },
                indent=2,
            )
        )

    def cmd_helm_yaw(self, args: List[str]) -> None:
        if not args:
            print("Usage: yaw <deg_per_s> [left|right|stop]")
            return

        try:
            self.rotation_deg_s = parse_rotation_command(
                axis="yaw",
                args=args,
                current_rotation=self.rotation_deg_s,
                rotation_limits=self.rotation_limits,
            )
        except ValueError as exc:
            print(exc)
            return

        self._send_helm_update()
        self._print_rotation_state()

    def cmd_helm_pitch(self, args: List[str]) -> None:
        if not args:
            print("Usage: pitch <deg_per_s> [up|down|stop]")
            return

        try:
            self.rotation_deg_s = parse_rotation_command(
                axis="pitch",
                args=args,
                current_rotation=self.rotation_deg_s,
                rotation_limits=self.rotation_limits,
            )
        except ValueError as exc:
            print(exc)
            return

        self._send_helm_update()
        self._print_rotation_state()

    def cmd_helm_roll(self, args: List[str]) -> None:
        if not args:
            print("Usage: roll <deg_per_s> [left|right|stop]")
            return

        try:
            self.rotation_deg_s = parse_rotation_command(
                axis="roll",
                args=args,
                current_rotation=self.rotation_deg_s,
                rotation_limits=self.rotation_limits,
            )
        except ValueError as exc:
            print(exc)
            return

        self._send_helm_update()
        self._print_rotation_state()

    def cmd_helm_rot_stop(self, args: List[str]) -> None:
        if args and args[0].lower() not in ("stop", "0", "zero"):
            print("Usage: rot stop")
            return

        self.rotation_deg_s = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
        self._send_helm_update()
        self._print_rotation_state()

    def _send_helm_update(self) -> None:
        self.client.set_helm_input(
            ship_id=self.ship_id,
            thrust_vector=self.thrust_vector,
            rotation_deg_s=self.rotation_deg_s,
        )

    def _print_rotation_state(self) -> None:
        print(
            json.dumps(
                {
                    "ship_id": self.ship_id,
                    "rotation_deg_s": self.rotation_deg_s,
                },
                indent=2,
            )
        )

    # ----------------- NAV -----------------

    def handle_nav_command(self, cmd: str, args: List[str]) -> None:
        if cmd == "autopilot":
            self.cmd_nav_autopilot(args)
        else:
            print(f"[WARN] Unknown nav command '{cmd}'. Try: autopilot ...")

    def cmd_nav_autopilot(self, args: List[str]) -> None:
        if not args:
            print("Usage: autopilot manual|coast|kill-velocity|chase <target_id> [range_m]")
            return

        mode = args[0].lower()
        if mode == "manual":
            payload = self.client.set_autopilot_mode(
                ship_id=self.ship_id,
                enabled=False,
                mode="manual",
                params={},
            )
            self.pretty_print(payload)
            return

        if mode == "coast":
            payload = self.client.set_autopilot_mode(
                ship_id=self.ship_id,
                enabled=True,
                mode="coast",
                params={},
            )
            self.pretty_print(payload)
            return

        if mode in ("kill-velocity", "kill_vel", "killvel"):
            payload = self.client.set_autopilot_mode(
                ship_id=self.ship_id,
                enabled=True,
                mode="kill_vel",
                params={},
            )
            self.pretty_print(payload)
            return

        if mode == "chase":
            if len(args) < 2:
                print("Usage: autopilot chase <target_id> [range_m]")
                return
            target_id = args[1]
            desired_range_m = 1000.0
            if len(args) >= 3:
                try:
                    desired_range_m = float(args[2])
                except ValueError:
                    print("Range must be a number (metres). Using default 1000.")
            params = {
                "target_id": target_id,
                "desired_range_m": desired_range_m,
            }
            payload = self.client.set_autopilot_mode(
                ship_id=self.ship_id,
                enabled=True,
                mode="chase_target",
                params=params,
            )
            self.pretty_print(payload)
            return

        print("Unknown autopilot mode. Use: manual, coast, kill-velocity, chase ...")

    # ----------------- SENSORS -----------------

    def handle_sensors_command(self, cmd: str, args: List[str]) -> None:
        if cmd == "ping":
            self.cmd_sensors_ping(args)
        else:
            print(f"[WARN] Unknown sensors command '{cmd}'. Try: ping active|passive")

    def cmd_sensors_ping(self, args: List[str]) -> None:
        if not args:
            print("Usage: ping active|passive")
            return
        mode = args[0].lower()
        if mode not in ("active", "passive"):
            print("Mode must be 'active' or 'passive'")
            return

        payload = self.client.ping_sensors(self.ship_id, mode)
        self.pretty_print(payload)

    # ----------------- WEAPONS -----------------

    def handle_weapons_command(self, cmd: str, args: List[str]) -> None:
        # Placeholder for future PD / torp commands
        print("[INFO] Weapons context not implemented yet.")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ShipOS CLI shell for Flaxos Spaceship Sim")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Server TCP port (default: 8765)",
    )
    parser.add_argument(
        "--ship",
        required=True,
        help="Ship ID to control (e.g. interceptor_alpha)",
    )
    parser.add_argument(
        "--context",
        default="helm",
        choices=["helm", "nav", "sensors", "weapons"],
        help="Initial context (default: helm)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    client = ApiClientV1(args.host, args.port)
    try:
        client.connect()
    except Exception as e:
        print(f"[FATAL] Could not connect to {args.host}:{args.port}: {e}")
        return 1

    shell = ShipOsShell(client=client, ship_id=args.ship, context=args.context)
    try:
        shell.run()
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
