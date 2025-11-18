from __future__ import annotations

import argparse
from pathlib import Path

from config.canonical_loader import load_canonical_fleet_from_dir
from sim.config_validation import ConfigError


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate fleet config")
    parser.add_argument("fleet_dir", help="Fleet directory path")
    parser.add_argument("--fleet-file", default="fleet.json")
    args = parser.parse_args()

    try:
        fleet = load_canonical_fleet_from_dir(Path(args.fleet_dir), args.fleet_file)
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 1

    print(f"Fleet OK: {fleet.get('id')} – {fleet.get('name')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
