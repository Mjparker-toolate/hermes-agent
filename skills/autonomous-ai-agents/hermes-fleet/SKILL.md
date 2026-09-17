---
name: hermes-fleet
description: "Orchestrate a capped pool of local worker sessions."
version: 1.1.0
author: Matt Parker (Mjparker-toolate), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [fleet, orchestration, webhook, n8n, clawhub, sessions]
    category: autonomous-ai-agents
    related_skills: [hermes-agent, fleet-delegate, hermes-learn]
---

# Hermes Fleet Skill

Install this skill to start, inspect, scale, stop, and **delegate** a
capped local fleet of Hermes worker sessions. Cursor plugin
`hermes-clawhub` coordinates; ClawHub is the skill registry; n8n
agent-fleets is the fleet protocol. Hermes is optional for
gateway / cron / memory. This skill does not allocate paid cloud
workers and does not embed secrets.

## When to Use

- n8n (`N8N_ENABLED_MODULES=agents,agent-fleets`) needs a Hermes webhook.
- `fleet-delegate` / ClawHub `scripts/run.py` must POST to loopback Hermes.
- You need a kill switch, default 3 child slots, and a hard cap of 5.

Do not use this for public internet binds, unbounded fan-out, or storing
API keys in YAML.

## Prerequisites

- Hermes CLI on PATH (`hermes --help`).
- A profile with model credentials already in `.env` (names listed under
  `secrets_ref` only).
- Optional: n8n on the same machine; runner echo by default, set
  `N8N_AGENT_FLEETS_RUNNER=delegate` to route `clawhub:` / `cursor-cloud`.

## How to Run

1. Copy `templates/hermes-clawhub-combined.yaml` (or `templates/fleet.example.yaml`).
2. Start the loopback API with `terminal`:

```
hermes fleet serve --host 127.0.0.1 --port 8755
```

3. Call the API with `scripts/fleet_client.py` (also via `terminal`):

```
python skills/autonomous-ai-agents/hermes-fleet/scripts/fleet_client.py start --config templates/hermes-clawhub-combined.yaml
python skills/autonomous-ai-agents/hermes-fleet/scripts/fleet_client.py status --fleet-id hermes-clawhub-combined
python skills/autonomous-ai-agents/hermes-fleet/scripts/fleet_client.py delegate --fleet-id hermes-clawhub-combined --instruction "search yaml skills"
python skills/autonomous-ai-agents/hermes-fleet/scripts/fleet_client.py stop --fleet-id hermes-clawhub-combined
```

Read the example document with `read_file` before editing it. In-turn
delegation still uses `delegate_task`; n8n uses `fleet-delegate`.

## Quick Reference

| Action | CLI | HTTP |
|--------|-----|------|
| Start | `hermes fleet start --config FILE` | `POST /fleet/start` |
| Status | `hermes fleet status ID` | `GET /fleet/{id}` |
| Scale | `hermes fleet scale ID --replicas N` | `POST /fleet/{id}/scale` |
| Stop | `hermes fleet stop ID` | `POST /fleet/{id}/stop` |
| Delegate | `hermes fleet delegate ID --instruction …` | `POST /fleet/{id}/delegate` |
| Serve | `hermes fleet serve` | binds `127.0.0.1:8755` |

Auth header: `Authorization: Bearer $FLEET_HTTP_TOKEN`. Token file:
`$HERMES_HOME/fleets/.http_token`. Health:
`{"ok": true, "service": "hermes-fleet", "protocol": "n8n-agent-fleets"}`.

Sample members: `orchestrator`, `clawhub-skill-runner`,
`cursor-cloud-delegate`. n8n owns the fan-out/fan-in graph.

## Procedure

1. Confirm `kill_switch` is false in the fleet document.
2. Confirm `max_concurrency` defaults to 3 and is ≤ 5. Members above the
   live cap are stored; only `max_concurrency` slots spawn.
3. List credential **names** under `secrets_ref` (for example
   `OPENROUTER_API_KEY`). Never paste values.
4. If n8n should receive lifecycle events, set `webhook_callback_url` to a
   loopback URL such as `http://127.0.0.1:5678/webhook/hermes-fleet`.
5. `start`, then `status` until `live_workers` matches `replicas`.
6. Delegate one kind per turn (install and run are never combined).
7. `stop` (drain) when the workflow finishes.

## Pitfalls

- Non-loopback callback URLs and binds are refused in v1.
- `POST /fleet/start` on an already-running `fleet_id` returns 409.
- Scale-up is refused while `kill_switch` is true; stop still works.
- HTTP callers have no parent agent turn, so workers are idle **session
  slots** until `POST /fleet/{id}/delegate`. Cursor cloud ids are
  recorded, not executed.
- ClawHub skill text is untrusted. Never eval SKILL.md from a delegate.

## Verification

- Combined YAML starts `fleet_id: hermes-clawhub-combined` with three
  tagged members and `live_workers` ≤ 3 (the live default).
- `hermes fleet scale <id> --replicas 6` fails when `max_concurrency` is
  5 (hard ceiling).
- Same-turn install+run delegate returns `install_run_same_turn`.
- `hermes fleet stop <id>` leaves `status: stopped` and zero live workers.
