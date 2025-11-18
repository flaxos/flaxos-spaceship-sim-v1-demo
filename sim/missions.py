from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from sim.config_validation import ConfigError
from config.canonical_loader import load_canonical_fleet_from_dir


@dataclass
class Mission:
    raw: Dict[str, Any]
    fleet_dir: Path
    fleet_file: str

    def to_public_dict(self, fleet: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(self.raw)
        data.setdefault("fleet", {})
        data["fleet"].update(
            {
                "fleet_dir": str(self.fleet_dir.name),
                "fleet_file": self.fleet_file,
                "fleet_id": fleet.get("id"),
                "fleet_name": fleet.get("name"),
            }
        )
        return data


def load_mission(path: Path) -> Mission:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ConfigError("Mission must be an object")
    mid = raw.get("id")
    title = raw.get("title")
    if not isinstance(mid, str) or not mid.strip():
        raise ConfigError("Mission requires non-empty 'id'")
    if not isinstance(title, str) or not title.strip():
        raise ConfigError("Mission requires non-empty 'title'")
    fleet = raw.get("fleet") or {}
    fleet_dir_name = fleet.get("fleet_dir")
    fleet_file = fleet.get("fleet_file", "fleet.json")
    if not isinstance(fleet_dir_name, str) or not fleet_dir_name.strip():
        raise ConfigError("Mission requires fleet.fleet_dir")
    fleet_dir = path.parent.parent / fleet_dir_name
    return Mission(raw=raw, fleet_dir=fleet_dir, fleet_file=fleet_file)


def load_mission_and_fleet(path: Path) -> (Mission, Dict[str, Any]):
    mission = load_mission(path)
    fleet = load_canonical_fleet_from_dir(mission.fleet_dir, mission.fleet_file)
    return mission, fleet
