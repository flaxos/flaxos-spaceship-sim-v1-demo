from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


class ConfigError(Exception):
    pass


@dataclass
class ShipConfig:
    raw: Dict[str, Any]


@dataclass
class FleetConfig:
    raw: Dict[str, Any]


def _ensure_vec3(value, default=None):
    if default is None:
        default = [0.0, 0.0, 0.0]
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return list(default)
    return [float(x) for x in value]


def validate_ship_config(data: Dict[str, Any]) -> ShipConfig:
    if not isinstance(data, dict):
        raise ConfigError("Ship config must be an object")

    ship_id = data.get("id")
    if not isinstance(ship_id, str) or not ship_id.strip():
        raise ConfigError("Ship config requires non-empty 'id'")

    # Defaults
    data.setdefault("position", [0.0, 0.0, 0.0])
    data.setdefault("velocity", [0.0, 0.0, 0.0])
    data["position"] = _ensure_vec3(data["position"])
    data["velocity"] = _ensure_vec3(data["velocity"])
    data.setdefault("orientation_deg", 0.0)

    signature = data.setdefault("signature", {})
    if not isinstance(signature, dict):
        raise ConfigError("'signature' must be an object")
    signature.setdefault("base_radar", 1.0)
    signature.setdefault("base_thermal", 1.0)

    systems = data.setdefault("systems", {})
    if not isinstance(systems, dict):
        raise ConfigError("'systems' must be an object")
    sensors = systems.setdefault("sensors", {})
    if not isinstance(sensors, dict):
        raise ConfigError("'systems.sensors' must be an object")
    sensors.setdefault("passive", {})
    sensors.setdefault("active", {})

    ecm = systems.setdefault("ecm_eccm", {})
    if not isinstance(ecm, dict):
        raise ConfigError("'systems.ecm_eccm' must be an object")
    ecm.setdefault("ecm_strength", 0.0)
    ecm.setdefault("eccm_strength", 0.0)

    pd = systems.setdefault("point_defence", {})
    if not isinstance(pd, dict):
        raise ConfigError("'systems.point_defence' must be an object")
    pd.setdefault("systems", [])

    return ShipConfig(raw=data)


def validate_fleet_config(data: Dict[str, Any]) -> FleetConfig:
    if not isinstance(data, dict):
        raise ConfigError("Fleet config must be an object")

    fid = data.get("id")
    name = data.get("name")
    if not isinstance(fid, str) or not fid.strip():
        raise ConfigError("Fleet requires non-empty 'id'")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("Fleet requires non-empty 'name'")

    ships = data.get("ships")
    if not isinstance(ships, list) or not ships:
        raise ConfigError("Fleet requires non-empty 'ships' list")

    for idx, entry in enumerate(ships):
        if not isinstance(entry, dict):
            raise ConfigError(f"Fleet ships[{idx}] must be an object")
        scf = entry.get("ship_config_file")
        if not isinstance(scf, str) or not scf.strip():
            raise ConfigError(f"Fleet ships[{idx}] missing 'ship_config_file'")
        spawn = entry.setdefault("spawn", {})
        if not isinstance(spawn, dict):
            raise ConfigError(f"Fleet ships[{idx}].spawn must be an object")
        spawn.setdefault("position", [0.0, 0.0, 0.0])
        spawn.setdefault("velocity", [0.0, 0.0, 0.0])
        spawn["position"] = _ensure_vec3(spawn["position"])
        spawn["velocity"] = _ensure_vec3(spawn["velocity"])
        entry.setdefault("orientation_deg", 0.0)

    return FleetConfig(raw=data)
