from __future__ import annotations

import argparse
import datetime
import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Callable, List

from agents.api_client import APIClient, APIClientError


def write_result(output_dir: Path, name: str, payload: Dict[str, Any]) -> None:
    """
    Write a single step result to <output_dir>/<name>.json
    """
    path = output_dir / f"{name}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def run_step(
    client_name: str,
    name: str,
    output_dir: Path,
    summary: List[Dict[str, Any]],
    func: Callable[[], Dict[str, Any]],
) -> None:
    """
    Run a diagnostic step for a specific client, capture success/error,
    and write result to disk.
    """
    label = f"{client_name}_{name}"
    print(f"[DEBUG] Running step: {label}")
    record: Dict[str, Any] = {
        "client": client_name,
        "step": name,
        "status": "ok",
        "duration_s": None,
        "error": None,
        "traceback": None,
        "result_keys": None,
    }

    start = time.time()
    try:
        result = func()
        duration = time.time() - start
        record["duration_s"] = duration

        if isinstance(result, dict):
            record["result_keys"] = list(result.keys())

        write_result(
            output_dir,
            label,
            {"ok": True, "result": result},
        )
        print(f"[DEBUG] Step {label} OK in {duration:.3f}s")
    except Exception as exc:  # noqa: BLE001 - diagnostic tool wants everything
        duration = time.time() - start
        tb = traceback.format_exc()
        record["status"] = "error"
        record["duration_s"] = duration
        record["error"] = str(exc)
        record["traceback"] = tb

        write_result(
            output_dir,
            label,
            {"ok": False, "error": str(exc), "traceback": tb},
        )
        print(f"[DEBUG] Step {label} FAILED in {duration:.3f}s: {exc}")

    summary.append(record)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flaxos Spaceship Sim – two-client feature / physics debug tool"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="API host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="API port (default: 8765)",
    )
    parser.add_argument(
        "--ship1-id",
        default="interceptor_alpha",
        help="Ship id for client 1 (default: interceptor_alpha)",
    )
    parser.add_argument(
        "--ship2-id",
        default="target_dummy_1",
        help="Ship id for client 2 (default: target_dummy_1)",
    )
    parser.add_argument(
        "--weapon-mount-id",
        default="pd_1",
        help="Weapon mount id to use for fire_weapon tests (default: pd_1)",
    )
    parser.add_argument(
        "--output-dir",
        default="debug_two_clients",
        help="Base directory for debug output (default: ./debug_two_clients)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Socket timeout in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--physics_wait_s",
        type=float,
        default=1.0,
        help="Seconds to wait between helm input and second get_state (default: 1.0)",
    )

    args = parser.parse_args()

    base_output_dir = Path(args.output_dir)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base_output_dir / f"run_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[DEBUG] Output directory: {output_dir}")

    client1 = APIClient(host=args.host, port=args.port, timeout=args.timeout)
    client2 = APIClient(host=args.host, port=args.port, timeout=args.timeout)

    # Connect both clients
    try:
        client1.connect()
        print("[DEBUG] Client1 connected.")
        client2.connect()
        print("[DEBUG] Client2 connected.")
    except APIClientError as exc:
        top_error = {
            "ok": False,
            "error": f"Failed to connect to {args.host}:{args.port}",
            "detail": str(exc),
        }
        write_result(output_dir, "00_connection_error", top_error)
        print(f"[DEBUG] Connection failed: {exc}")
        return 1

    summary: List[Dict[str, Any]] = []

    # ---- Client 1: player ship (interceptor) ----

    run_step(
        "client1",
        "01_get_server_info",
        output_dir,
        summary,
        lambda: client1.request("get_server_info", {})["payload"],
    )

    run_step(
        "client1",
        "02_get_mission",
        output_dir,
        summary,
        lambda: client1.request("get_mission", {})["payload"],
    )

    def _c1_get_state() -> Dict[str, Any]:
        resp = client1.get_state(
            ship_id=args.ship1_id,
            include_contacts=True,
            include_projectiles=True,
            include_raw_entities=False,
        )
        return resp

    run_step(
        "client1",
        "03_get_state_ship1",
        output_dir,
        summary,
        _c1_get_state,
    )

    def _c1_ping_active() -> Dict[str, Any]:
        resp = client1.request(
            "command.ping_sensors",
            {"ship_id": args.ship1_id, "mode": "active"},
        )
        return resp.get("payload", {})

    run_step(
        "client1",
        "04_command_ping_sensors_active",
        output_dir,
        summary,
        _c1_ping_active,
    )

    def _c1_set_target() -> Dict[str, Any]:
        resp = client1.request(
            "command.set_target",
            {"ship_id": args.ship1_id, "target_entity_id": args.ship2_id},
        )
        return resp.get("payload", {})

    run_step(
        "client1",
        "05_command_set_target",
        output_dir,
        summary,
        _c1_set_target,
    )

    def _c1_fire_weapon() -> Dict[str, Any]:
        return client1.fire_weapon(args.ship1_id, args.weapon_mount_id)

    run_step(
        "client1",
        "06_command_fire_weapon",
        output_dir,
        summary,
        _c1_fire_weapon,
    )

    def _c1_set_autopilot() -> Dict[str, Any]:
        resp = client1.request(
            "command.set_autopilot_mode",
            {"ship_id": args.ship1_id, "enabled": True, "mode": "standard"},
        )
        return resp.get("payload", {})

    run_step(
        "client1",
        "07_command_set_autopilot_mode",
        output_dir,
        summary,
        _c1_set_autopilot,
    )

    # Physics / helm behaviour check
    def _c1_helm_physics_probe() -> Dict[str, Any]:
        """
        Send a helm input, wait a bit, then compare positions.
        If unchanged, we mark this as 'not_implemented' in the summary.
        """
        # Initial state
        state_before = client1.get_state(
            ship_id=args.ship1_id,
            include_contacts=False,
            include_projectiles=False,
            include_raw_entities=False,
        )
        pos_before = (state_before.get("own_ship") or {}).get("position")

        # Send helm command
        resp_cmd = client1.request(
            "command.set_helm_input",
            {
                "ship_id": args.ship1_id,
                "thrust_vector": [0.0, 0.0, 1.0],
                "rotation_input_deg_s": 5.0,
            },
        )
        payload_cmd = resp_cmd.get("payload", {})

        # Wait for the sim to tick
        time.sleep(args.physics_wait_s)

        # Check state again
        state_after = client1.get_state(
            ship_id=args.ship1_id,
            include_contacts=False,
            include_projectiles=False,
            include_raw_entities=False,
        )
        pos_after = (state_after.get("own_ship") or {}).get("position")

        return {
            "command_payload": payload_cmd,
            "state_before": state_before,
            "state_after": state_after,
            "position_before": pos_before,
            "position_after": pos_after,
        }

    # We run the helm probe manually so we can adjust status based on position delta.
    step_name = "08_command_set_helm_input_physics_probe"
    print(f"[DEBUG] Running step: client1_{step_name}")
    record = {
        "client": "client1",
        "step": step_name,
        "status": "ok",
        "duration_s": None,
        "error": None,
        "traceback": None,
        "result_keys": None,
        "physics_observation": None,
    }
    start = time.time()
    try:
        result = _c1_helm_physics_probe()
        duration = time.time() - start
        record["duration_s"] = duration

        pos_before = result.get("position_before")
        pos_after = result.get("position_after")

        # Compare positions; if they are identical, we treat physics as not implemented.
        if pos_before == pos_after:
            record["status"] = "not_implemented"
            record["physics_observation"] = (
                "Position did not change after helm input; "
                "physics/impulse not implemented in this v1.0 demo."
            )
        else:
            record["physics_observation"] = (
                "Position changed after helm input; physics appears to be active."
            )

        if isinstance(result, dict):
            record["result_keys"] = list(result.keys())

        write_result(
            output_dir,
            f"client1_{step_name}",
            {"ok": True, "result": result},
        )
        print(
            f"[DEBUG] Step client1_{step_name} {record['status']} "
            f"in {duration:.3f}s"
        )
    except Exception as exc:
        duration = time.time() - start
        tb = traceback.format_exc()
        record["status"] = "error"
        record["duration_s"] = duration
        record["error"] = str(exc)
        record["traceback"] = tb

        write_result(
            output_dir,
            f"client1_{step_name}",
            {"ok": False, "error": str(exc), "traceback": tb},
        )
        print(
            f"[DEBUG] Step client1_{step_name} FAILED in {duration:.3f}s: {exc}"
        )

    summary.append(record)

    # ---- Client 2: target ship ----

    def _c2_get_state() -> Dict[str, Any]:
        resp = client2.get_state(
            ship_id=args.ship2_id,
            include_contacts=True,
            include_projectiles=True,
            include_raw_entities=False,
        )
        return resp

    run_step(
        "client2",
        "01_get_state_ship2",
        output_dir,
        summary,
        _c2_get_state,
    )

    # Write summary
    summary_path = output_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({"steps": summary}, f, indent=2, sort_keys=True)

    print("\n[DEBUG] Two-client feature probe complete.")
    print(f"[DEBUG] Summary written to: {summary_path}")
    print(f"[DEBUG] Per-step results in: {output_dir}")

    client1.close()
    client2.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
