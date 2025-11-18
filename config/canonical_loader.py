from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from sim.config_validation import validate_fleet_config, validate_ship_config, ConfigError


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_ship_config(path: Path) -> Dict[str, Any]:
    data = load_json(path)
    cfg = validate_ship_config(data)
    return cfg.raw


def load_canonical_fleet_from_dir(fleet_dir: Path, fleet_file: str = "fleet.json") -> Dict[str, Any]:
    fleet_path = fleet_dir / fleet_file
    if not fleet_path.exists():
        raise ConfigError(f"Fleet file not found: {fleet_path}")
    fleet_data = load_json(fleet_path)
    fleet_cfg = validate_fleet_config(fleet_data)
    raw = fleet_cfg.raw
    raw.setdefault("_meta", {})
    raw["_meta"].setdefault("fleet_dir", str(fleet_dir.name))
    raw["_meta"].setdefault("classification", "canonical")
    raw["_meta"].setdefault("source_file", str(fleet_path))
    return raw
