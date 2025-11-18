# Flaxos Spaceship Sim – v1.0.0 Demo

Hard-ish sci‑fi spaceship simulator skeleton with:

- Canonical ship / fleet / mission schemas
- Centralised sensors & contacts
- TCP JSON API v1.0
- Simple demo sim controller
- Example PD agent using the public API

This zip is a minimal, self-contained v1.0 demo – not a full game – but it’s
enough to spin up a server, hit it over TCP, and run a PD agent.

## 1. Requirements

- Python 3.10 or newer (3.11+ recommended)
- No external dependencies for the demo server and agent

(Optional) For tests:

- `pytest` (install with `pip install pytest`)

## 2. Quick Start – Run the Demo Server

From the extracted project root:

```bash
python -m server.run_api_v1_demo
```

This will:

- Load `missions/mission_interceptor_vs_target.json`
- Load `hybrid_fleet/fleet.json`
- Instantiate:
  - `interceptor_alpha` (player ship, blue team)
  - `target_dummy_1` (red team, PDC + ECM)
- Start the TCP API server on `0.0.0.0:8765`

You should see log output similar to:

```text
INFO:server.api_v1:API v1.0 server listening on 0.0.0.0:8765 (api_version=1.0, server_version=1.0.0)
```

## 3. Talk to the API by Hand

In another terminal, from the project root:

```bash
printf '{"api_version":"1.0","request_id":"1","action":"get_server_info","payload":{}}\n'   | nc 127.0.0.1 8765
```

You should get back JSON like:

```json
{
  "api_version": "1.0",
  "request_id": "1",
  "action": "get_server_info",
  "status": "ok",
  "payload": {
    "server_version": "1.0.0",
    "api_version": "1.0",
    "capabilities": [
      "get_state",
      "get_events",
      "get_mission",
      "get_server_info",
      "command.set_target",
      "command.fire_weapon",
      "command.ping_sensors",
      "command.set_autopilot_mode",
      "command.set_helm_input"
    ]
  },
  "error": null
}
```

You can also query mission info:

```bash
printf '{"api_version":"1.0","request_id":"2","action":"get_mission","payload":{}}\n'   | nc 127.0.0.1 8765
```

## 4. Run the PD Agent

With the server still running, start the PD agent in a new terminal:

```bash
python -m agents.pd_agent --host 127.0.0.1 --port 8765 --ship-id interceptor_alpha
```

The agent will:

- Poll `get_state` for `interceptor_alpha`
- Look for hostile projectiles (in this minimal demo there are none yet)
- Fire PD mounts via `command.fire_weapon` when it sees threats

Right now, the `DemoSimController` doesn’t spawn real projectiles – it’s just
the plumbing. Extending the sim to spawn incoming threats is the next step.

## 5. Project Layout

Key bits:

- `version.py` – project version (`__version__ = "1.0.0"`)
- `server/`
  - `api_envelope.py` – request/response envelope helpers
  - `api_server_v1.py` – TCP API server implementation
  - `run_api_v1_demo.py` – demo entrypoint + `DemoSimController`
- `sim/`
  - `config_validation.py` – validates ship & fleet configs, applies defaults
  - `missions.py` – mission loading & mission → fleet wiring
  - `sensors.py` – centralised sensor + contact model
- `config/`
  - `canonical_loader.py` – loads & validates canonical fleet configs
- `ships/`
  - `interceptor.json` – player interceptor config
  - `target_dummy_pdc_ecm.json` – target dummy with PDC + ECM
- `hybrid_fleet/`
  - `fleet.json` – canonical demo fleet definition
- `missions/`
  - `mission_interceptor_vs_target.json` – main demo mission
  - `mission_pd_stress_test.json` – PD stress-test skeleton
- `agents/`
  - `api_client.py` – simple TCP client for the v1.0 API
  - `pd_agent.py` – reference PD agent
- `tools/`
  - `validate_fleet.py` – validate a fleet directory
- `tests/`
  - `test_api_server_v1.py` – basic API tests
  - `test_sensors.py` – basic sensor behaviour test

## 6. Validating Content

You can validate the demo fleet:

```bash
python tools/validate_fleet.py hybrid_fleet
```

You should see:

```text
Fleet OK: demo_interceptor_vs_target – Interceptor vs Target (Sprint 2 Demo)
```

## 7. Running Tests (Optional)

If you have `pytest` installed:

```bash
pytest
```

This will run:

- API server round-trip test for `get_server_info`
- Sensor range/FOV detection test

## 8. Next Steps

This v1.0 demo gives you:

- A stable TCP API to build HUDs and agents against
- A working sensor/contact pipeline
- Canonical schemas for ships, fleets, and missions

What’s *not* here yet:

- Real physics (impulse, RCS, orbits)
- Projectile trajectories / real combat resolution
- A proper HUD / GUI

Those can be built on top without breaking the core API or content format.
