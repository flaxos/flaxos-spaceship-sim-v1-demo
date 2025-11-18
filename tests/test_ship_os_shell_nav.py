from tools.ship_os_shell import ShipOsShell


class FakeClient:
    def __init__(self) -> None:
        self.autopilot_calls = []

    def set_autopilot_mode(self, ship_id, enabled, mode, params=None):
        call = {
            "ship_id": ship_id,
            "enabled": enabled,
            "mode": mode,
            "params": params or {},
        }
        self.autopilot_calls.append(call)
        return {"autopilot": call}

    def get_state(self, ship_id):
        return {"own_ship": {"id": ship_id, "controls": {}, "physics": {}}}


def build_shell():
    client = FakeClient()
    shell = ShipOsShell(client=client, ship_id="ship_alpha", context="nav")
    return shell, client


def test_nav_autopilot_manual_disables():
    shell, client = build_shell()
    shell.handle_line("autopilot manual")

    assert client.autopilot_calls[-1] == {
        "ship_id": "ship_alpha",
        "enabled": False,
        "mode": "manual",
        "params": {},
    }


def test_nav_autopilot_kill_velocity():
    shell, client = build_shell()
    shell.handle_line("autopilot kill-velocity")

    assert client.autopilot_calls[-1]["mode"] == "kill_vel"
    assert client.autopilot_calls[-1]["enabled"] is True


def test_nav_autopilot_point_at():
    shell, client = build_shell()
    shell.handle_line("autopilot point-at target_dummy_1")

    assert client.autopilot_calls[-1] == {
        "ship_id": "ship_alpha",
        "enabled": True,
        "mode": "point_at_target",
        "params": {"target_entity_id": "target_dummy_1"},
    }
