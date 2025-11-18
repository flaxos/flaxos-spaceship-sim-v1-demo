from __future__ import annotations

import argparse
import math
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .api_client import APIClient, APIClientError


@dataclass
class PDAgentConfig:
    ship_id: str
    engagement_range_km: float = 10.0
    max_simultaneous_targets: int = 2
    poll_interval_s: float = 0.2
    min_fire_interval_s: float = 0.2

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PDAgentConfig":
        sid = data.get("ship_id")
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError("PDAgentConfig requires non-empty 'ship_id'")
        return cls(
            ship_id=sid,
            engagement_range_km=float(data.get("engagement_range_km", 10.0)),
            max_simultaneous_targets=int(data.get("max_simultaneous_targets", 2)),
            poll_interval_s=float(data.get("poll_interval_s", 0.2)),
            min_fire_interval_s=float(data.get("min_fire_interval_s", 0.2)),
        )


class PDAgent:
    def __init__(self, client: APIClient, config: PDAgentConfig) -> None:
        self.client = client
        self.config = config
        self._last_fire_time: Dict[str, float] = {}
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        print(
            f"[PD] Starting PD agent for ship '{self.config.ship_id}' "
            f"(range={self.config.engagement_range_km} km, max_targets={self.config.max_simultaneous_targets})"
        )
        while self._running:
            try:
                state = self.client.get_state(
                    ship_id=self.config.ship_id,
                    include_contacts=False,
                    include_projectiles=True,
                    include_raw_entities=False,
                )
            except APIClientError as exc:
                print(f"[PD] API error: {exc}", file=sys.stderr)
                time.sleep(self.config.poll_interval_s)
                continue
            self._tick(state)
            time.sleep(self.config.poll_interval_s)
        print("[PD] Agent stopped.")

    def _tick(self, state: Dict[str, Any]) -> None:
        server_time = float(state.get("server_time", 0.0))
        own_ship = state.get("own_ship") or {}
        projectiles = state.get("projectiles") or []
        pd_mounts = self._extract_pd_mounts(own_ship)
        if not pd_mounts or not projectiles:
            return
        own_pos = own_ship.get("position", [0.0, 0.0, 0.0])
        own_team = own_ship.get("team")
        threats = self._identify_threats(own_pos, own_team, projectiles, self.config.engagement_range_km)
        if not threats:
            return
        threats.sort(key=lambda t: t["distance_km"])
        max_targets = max(1, self.config.max_simultaneous_targets)
        self._engage_threats(server_time, pd_mounts, threats[:max_targets])

    def _extract_pd_mounts(self, ship: Dict[str, Any]) -> List[Dict[str, Any]]:
        systems = ship.get("systems") or {}
        pd = systems.get("point_defence") or {}
        mounts = pd.get("systems") or []
        return [m for m in mounts if isinstance(m.get("id"), str)]

    def _identify_threats(self, own_pos, own_team, projectiles, engagement_range_km):
        threats = []
        for proj in projectiles:
            pid = proj.get("id")
            ppos = proj.get("position")
            if pid is None or ppos is None:
                continue
            pteam = proj.get("team")
            if own_team is not None and pteam == own_team:
                continue
            d = self._distance_km(own_pos, ppos)
            if d > engagement_range_km:
                continue
            threats.append({"projectile_id": pid, "position": ppos, "distance_km": d})
        return threats

    def _engage_threats(self, server_time, pd_mounts, threats):
        it = iter(threats)
        for mount in pd_mounts:
            try:
                threat = next(it)
            except StopIteration:
                break
            mid = mount.get("id")
            if not self._can_fire_mount(mid, server_time):
                continue
            self._fire_pd_mount(mid, threat, server_time)

    def _can_fire_mount(self, mount_id: str, server_time: float) -> bool:
        last = self._last_fire_time.get(mount_id, -1e9)
        return server_time - last >= self.config.min_fire_interval_s

    def _fire_pd_mount(self, mount_id: str, threat: Dict[str, Any], server_time: float) -> None:
        pid = threat["projectile_id"]
        d = threat["distance_km"]
        try:
            payload = self.client.fire_weapon(self.config.ship_id, mount_id)
        except APIClientError as exc:
            print(f"[PD] Failed to fire {mount_id} at {pid}: {exc}", file=sys.stderr)
            return
        self._last_fire_time[mount_id] = server_time
        print(f"[PD] Fired {mount_id} at {pid} ({d:.2f} km). Response: {payload}")

    @staticmethod
    def _distance_km(a, b):
        ax, ay, az = (a + [0, 0, 0])[:3] if isinstance(a, list) else (0.0, 0.0, 0.0)
        bx, by, bz = (b + [0, 0, 0])[:3] if isinstance(b, list) else (0.0, 0.0, 0.0)
        dx, dy, dz = bx - ax, by - ay, bz - az
        return (dx * dx + dy * dy + dz * dz) ** 0.5 / 1000.0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PD agent for Flaxos Spaceship Sim")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--ship-id", required=True)
    args = parser.parse_args(argv)

    cfg = PDAgentConfig(ship_id=args.ship_id)
    client = APIClient(host=args.host, port=args.port)
    client.connect()
    agent = PDAgent(client, cfg)

    def _sig(_sig, _frame):
        agent.stop()

    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    try:
        agent.run()
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
