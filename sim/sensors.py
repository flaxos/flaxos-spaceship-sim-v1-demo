from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import math


@dataclass
class Contact:
    contact_id: str
    sensor_ship_id: str
    target_entity_id: str
    first_seen_time: float
    last_seen_time: float
    last_detection_type: str
    range_km: float
    bearing_deg: float
    strength: float
    stale: bool = False

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "contact_id": self.contact_id,
            "sensor_ship_id": self.sensor_ship_id,
            "target_entity_id": self.target_entity_id,
            "first_seen_time": self.first_seen_time,
            "last_seen_time": self.last_seen_time,
            "last_detection_type": self.last_detection_type,
            "range_km": self.range_km,
            "bearing_deg": self.bearing_deg,
            "strength": self.strength,
            "stale": self.stale,
        }


@dataclass
class SensorEvent:
    id: int
    time: float
    type: str
    sensor_ship_id: str
    target_entity_id: Optional[str]
    data: Dict[str, Any]


class SensorsManager:
    def __init__(
        self,
        stale_after_s: float = 5.0,
        drop_after_s: float = 10.0,
        min_detection_strength: float = 0.05,
    ) -> None:
        self.stale_after_s = stale_after_s
        self.drop_after_s = drop_after_s
        self.min_detection_strength = min_detection_strength
        self.contacts: Dict[str, Dict[str, Contact]] = {}
        self.events: List[SensorEvent] = []
        self._next_event_id = 1
        self._last_ping_time: Dict[str, float] = {}

    def _emit(self, time_s: float, type_: str, sensor_ship_id: str, target_entity_id: Optional[str], data: Dict[str, Any]) -> None:
        ev = SensorEvent(
            id=self._next_event_id,
            time=time_s,
            type=type_,
            sensor_ship_id=sensor_ship_id,
            target_entity_id=target_entity_id,
            data=data,
        )
        self._next_event_id += 1
        self.events.append(ev)

    def get_events_since(self, last_event_id: int) -> List[Dict[str, Any]]:
        return [
            {
                "id": ev.id,
                "time": ev.time,
                "type": ev.type,
                "sensor_ship_id": ev.sensor_ship_id,
                "target_entity_id": ev.target_entity_id,
                "data": ev.data,
            }
            for ev in self.events
            if ev.id > last_event_id
        ]

    def get_contacts_for_ship(self, ship_id: str) -> List[Dict[str, Any]]:
        d = self.contacts.get(ship_id, {})
        return [c.to_public_dict() for c in d.values()]

    def update_passive_for_ship(self, sim_time: float, ship: Dict[str, Any], entities: List[Dict[str, Any]]) -> None:
        sensors = (ship.get("systems") or {}).get("sensors") or {}
        passive = sensors.get("passive") or {}
        range_km = float(passive.get("range_km", 0.0))
        if range_km <= 0:
            return
        fov_deg = float(passive.get("fov_deg", 360.0))
        sensitivity = float(passive.get("sensitivity", 1.0))

        ecm_block = (ship.get("systems") or {}).get("ecm_eccm") or {}
        eccm = float(ecm_block.get("eccm_strength", 0.0))

        own_pos = ship.get("position", [0.0, 0.0, 0.0])
        orientation_deg = float(ship.get("orientation_deg", 0.0))

        for ent in entities:
            if ent.get("id") == ship.get("id"):
                continue
            target_sig = (ent.get("signature") or {}).get("base_radar", 1.0)
            ecm_target = (ent.get("systems") or {}).get("ecm_eccm") or {}
            ecm = float(ecm_target.get("ecm_strength", 0.0))

            rng_km, bearing_deg = self._range_and_bearing(own_pos, ent.get("position", [0.0, 0.0, 0.0]))
            if rng_km > range_km:
                continue
            if not self._within_fov(orientation_deg, bearing_deg, fov_deg):
                continue

            strength = self._detection_strength(target_sig, rng_km, range_km, ecm, eccm, sensitivity)
            if strength < self.min_detection_strength:
                continue
            self._update_contact(
                sim_time,
                sensor_ship_id=ship["id"],
                target_entity_id=ent["id"],
                detection_type="passive",
                rng_km=rng_km,
                bearing_deg=bearing_deg,
                strength=strength,
            )

    def execute_active_ping(self, sim_time: float, ship: Dict[str, Any], entities: List[Dict[str, Any]], mode: str = "standard") -> List[Dict[str, Any]]:
        ship_id = ship["id"]
        sensors = (ship.get("systems") or {}).get("sensors") or {}
        active = sensors.get("active") or {}
        range_km = float(active.get("range_km", 0.0))
        if range_km <= 0:
            self._emit(sim_time, "sensor_ping", ship_id, None, {"performed": False, "reason": "no_active"})
            return self.get_contacts_for_ship(ship_id)
        fov_deg = float(active.get("fov_deg", 60.0))
        cooldown = float(active.get("ping_cooldown_s", 5.0))
        last = self._last_ping_time.get(ship_id, -1e9)
        if sim_time - last < cooldown:
            self._emit(sim_time, "sensor_ping", ship_id, None, {"performed": False, "reason": "cooldown"})
            return self.get_contacts_for_ship(ship_id)

        self._last_ping_time[ship_id] = sim_time
        self._emit(sim_time, "sensor_ping", ship_id, None, {"performed": True, "mode": mode})

        ecm_block = (ship.get("systems") or {}).get("ecm_eccm") or {}
        eccm = float(ecm_block.get("eccm_strength", 0.0))
        own_pos = ship.get("position", [0.0, 0.0, 0.0])
        orientation_deg = float(ship.get("orientation_deg", 0.0))

        for ent in entities:
            if ent.get("id") == ship_id:
                continue
            target_sig = (ent.get("signature") or {}).get("base_radar", 1.0)
            ecm_target = (ent.get("systems") or {}).get("ecm_eccm") or {}
            ecm = float(ecm_target.get("ecm_strength", 0.0))
            rng_km, bearing_deg = self._range_and_bearing(own_pos, ent.get("position", [0.0, 0.0, 0.0]))
            if rng_km > range_km:
                continue
            if not self._within_fov(orientation_deg, bearing_deg, fov_deg):
                continue
            strength = self._detection_strength(target_sig, rng_km, range_km, ecm, eccm, sensitivity=1.5)
            if strength < self.min_detection_strength:
                continue
            self._update_contact(
                sim_time,
                sensor_ship_id=ship_id,
                target_entity_id=ent["id"],
                detection_type="active",
                rng_km=rng_km,
                bearing_deg=bearing_deg,
                strength=strength,
            )
        return self.get_contacts_for_ship(ship_id)

    def advance_time(self, sim_time: float) -> None:
        for sensor_id, contacts in list(self.contacts.items()):
            for target_id, c in list(contacts.items()):
                age = sim_time - c.last_seen_time
                if age >= self.drop_after_s:
                    self._emit(sim_time, "contact_lost", sensor_id, target_id, {})
                    del contacts[target_id]
                elif age >= self.stale_after_s and not c.stale:
                    c.stale = True
            if not contacts:
                del self.contacts[sensor_id]

    def _update_contact(
        self,
        sim_time: float,
        sensor_ship_id: str,
        target_entity_id: str,
        detection_type: str,
        rng_km: float,
        bearing_deg: float,
        strength: float,
    ) -> None:
        contacts_for_ship = self.contacts.setdefault(sensor_ship_id, {})
        cid = f"{sensor_ship_id}::{target_entity_id}"
        if cid in contacts_for_ship:
            c = contacts_for_ship[cid]
            c.last_seen_time = sim_time
            c.last_detection_type = detection_type
            c.range_km = rng_km
            c.bearing_deg = bearing_deg
            c.strength = strength
            c.stale = False
            self._emit(sim_time, "contact_updated", sensor_ship_id, target_entity_id, {})
        else:
            c = Contact(
                contact_id=cid,
                sensor_ship_id=sensor_ship_id,
                target_entity_id=target_entity_id,
                first_seen_time=sim_time,
                last_seen_time=sim_time,
                last_detection_type=detection_type,
                range_km=rng_km,
                bearing_deg=bearing_deg,
                strength=strength,
                stale=False,
            )
            contacts_for_ship[cid] = c
            self._emit(sim_time, "contact_acquired", sensor_ship_id, target_entity_id, {})

    @staticmethod
    def _range_and_bearing(a, b):
        ax, ay, az = (a + [0, 0, 0])[:3] if isinstance(a, list) else (0.0, 0.0, 0.0)
        bx, by, bz = (b + [0, 0, 0])[:3] if isinstance(b, list) else (0.0, 0.0, 0.0)
        dx = bx - ax
        dy = by - ay
        dz = bz - az
        dist_m = math.sqrt(dx * dx + dy * dy + dz * dz)
        rng_km = dist_m / 1000.0
        bearing = math.degrees(math.atan2(dy, dx)) % 360.0
        return rng_km, bearing

    @staticmethod
    def _within_fov(orientation_deg: float, bearing_deg: float, fov_deg: float) -> bool:
        if fov_deg >= 360.0:
            return True
        half = fov_deg / 2.0
        diff = (bearing_deg - orientation_deg + 540.0) % 360.0 - 180.0
        # Use strict bounds so edge-on targets (diff == +/- half) are excluded.
        return -half < diff < half

    @staticmethod
    def _detection_strength(base_sig: float, rng_km: float, sensor_range_km: float, ecm: float, eccm: float, sensitivity: float) -> float:
        eff = base_sig * max(0.1, min(2.0, 1.0 - ecm + eccm))
        range_factor = max(0.0, 1.0 - rng_km / max(sensor_range_km, 0.001))
        return sensitivity * eff * range_factor
