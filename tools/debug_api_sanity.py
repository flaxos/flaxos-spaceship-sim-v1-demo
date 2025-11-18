from __future__ import annotations

import argparse
import datetime
import json
import traceback
import time
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
    name: str,
    output_dir: Path,
    summary: List[Dict[str, Any]],
    func: Callable[[], Dict[str, Any]],
) -> None:
    """
    Run a single diagnostic step, capture success/error, and write result to disk.
    """
    print(f"[DEBUG] Running step: {name}")
    record: Dict[str, Any] = {
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

        write_result(output_dir, name, {"ok": True, "result": result})
        print(f"[DEBUG] Step {name} OK in {duration:.3f}s")
    except Exception as exc:  # noqa: BLE001 - we want to catch everything for diagnostics
        duration = time.time() - start
        tb = traceback.format_exc()
        record["status"] = "error"
        record["duration_s"] = duration
        record["error"] = str(exc)
        record["traceback"] = tb

        write_result(
            output_dir,
            name,
            {
                "ok": False,
                "error": str(exc),
                "traceback": tb,
            },
        )
        print(f"[DEBUG] Step {name} FAILED in {duration:.3f}s: {exc}")

    summary.append(record)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Flaxos Spaceship Sim – API sanity check / debug tool"
    )
    parser.add_argument("--host", default="127.0.0.1", help="API host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="API port (default: 8765)")
    parser.add_argument(
        "--ship-id",
        default="interceptor_alpha",
        help="Player ship id to use for tests (default: interceptor_alpha)",
    )
    parser.add_argument(
        "--target-id",
        default="target_dummy_1",
        help="Target entity id to use for set_target test (default: target_dummy_1)",
    )
    parser.add_argument(
        "--weapon-mount-id",
        default="pd_1",
        help="Weapon mount id to use for fire_weapon test (default: pd_1)",
    )
    parser.add_argument(
        "--output-dir",
        default="debug_runs",
        help="Base directory for debug output (default: ./debug_runs)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Socket timeout in seconds (default: 5.0)",
    )

    args = parser.parse_args()

    base_output_dir = Path(args.output_dir)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = base_output_dir / f"run_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[DEBUG] Output directory: {output_dir}")

    client = APIClient(host=args.host, port=args.port, timeout=args.timeout)

    try:
        client.connect()
    except APIClientError as exc:
        # If we cannot even connect, record a top-level failure and bail.
        top_error = {
            "ok": False,
            "error": f"Failed to connect to {args.host}:{args.port}",
            "detail": str(exc),
        }
        write_result(output_dir, "00_connection_error", top_error)
        print(f"[DEBUG] Connection failed: {exc}")
        return 1

    summary: List[Dict[str, Any]] = []

    # 1) Basic: get_server_info
    run_step(
        "01_get_server_info",
        output_dir,
        summary,
        lambda: client.get_server_info(),
    )

    # 2) get_mission
    run_step(
        "02_get_mission",
        output_dir,
        summary,
        lambda: client.get_mission(),
    )

    # 3) get_state for the player ship
    run_step(
        "03_get_state_player",
        output_dir,
        summary,
        lambda: client.get_state(
            ship_id=args.ship_id,
            include_contacts=True,
            include_projectiles=True,
            include_raw_entities=False,
        ),
    )

    # 4) ping_sensors (active)
    def _ping_sensors() -> Dict[str, Any]:
        resp = client.request(
            "command.ping_sensors",
            {"ship_id": args.ship_id, "mode": "active"},
        )
        return resp.get("payload", {})

    run_step(
        "04_command_ping_sensors_active",
        output_dir,
        summary,
        _ping_sensors,
    )

    # 5) set_target
    def _set_target() -> Dict[str, Any]:
        resp = client.request(
            "command.set_target",
            {"ship_id": args.ship_id, "target_entity_id": args.target_id},
        )
        return resp.get("payload", {})

    run_step(
        "05_command_set_target",
        output_dir,
        summary,
        _set_target,
    )

    # 6) fire_weapon (PD mount)
    def _fire_weapon() -> Dict[str, Any]:
        return client.fire_weapon(args.ship_id, args.weapon_mount_id)

    run_step(
        "06_command_fire_weapon",
        output_dir,
        summary,
        _fire_weapon,
    )

    # 7) set_autopilot_mode
    def _set_autopilot() -> Dict[str, Any]:
        resp = client.request(
            "command.set_autopilot_mode",
            {"ship_id": args.ship_id, "enabled": True, "mode": "standard"},
        )
        return resp.get("payload", {})

    run_step(
        "07_command_set_autopilot_mode",
        output_dir,
        summary,
        _set_autopilot,
    )

    # 8) set_helm_input (simple forward thrust)
    def _set_helm() -> Dict[str, Any]:
        resp = client.request(
            "command.set_helm_input",
            {
                "ship_id": args.ship_id,
                "thrust_vector": [0.0, 0.0, 1.0],
                "rotation_input_deg_s": 5.0,
            },
        )
        return resp.get("payload", {})

    run_step(
        "08_command_set_helm_input",
        output_dir,
        summary,
        _set_helm,
    )

    # Write summary
    summary_path = output_dir / "summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({"steps": summary}, f, indent=2, sort_keys=True)

    print("\n[DEBUG] Sanity check complete.")
    print(f"[DEBUG] Summary written to: {summary_path}")
    print(f"[DEBUG] Per-step results in: {output_dir}")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
