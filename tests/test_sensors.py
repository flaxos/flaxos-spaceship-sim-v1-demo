from __future__ import annotations

from sim.sensors import SensorsManager


def test_passive_detection_range_and_fov():
    mgr = SensorsManager()
    ship = {
        "id": "sensor",
        "position": [0.0, 0.0, 0.0],
        "orientation_deg": 0.0,
        "systems": {
            "sensors": {
                "passive": {"range_km": 10.0, "fov_deg": 180.0, "sensitivity": 1.0}
            },
            "ecm_eccm": {"ecm_strength": 0.0, "eccm_strength": 0.0},
        },
    }
    inside = {"id": "t1", "position": [5000.0, 0.0, 0.0], "signature": {"base_radar": 1.0}}
    outside = {"id": "t2", "position": [20000.0, 0.0, 0.0], "signature": {"base_radar": 1.0}}
    behind = {"id": "t3", "position": [0.0, -5000.0, 0.0], "signature": {"base_radar": 1.0}}

    mgr.update_passive_for_ship(0.0, ship, [ship, inside, outside, behind])
    contacts = mgr.get_contacts_for_ship("sensor")
    ids = {c["target_entity_id"] for c in contacts}
    assert "t1" in ids
    assert "t2" not in ids
    assert "t3" not in ids
