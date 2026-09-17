---
name: hermes-fleet
description: "Orchestrate a capped pool of local worker sessions."
version: 1.0.0
author: Matt Parker (Mjparker-toolate), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [fleet, orchestration, webhook, n8n, clawhub, sessions]
    category: autonomous-ai-agents
    related_skills: [hermes-agent]
---

# Hermes Fleet Skill

Install this skill to start, inspect, scale, and stop a **capped local
fleet** of Hermes worker sessions. ClawHub is the registry that publishes
the skill; Hermes is the runtime. This skill does not allocate paid cloud
workers and does not embed secrets.

## When to Use

- An n8n (or similar) workflow needs a small pool of Hermes sessions.
- A ClawHub-installed agent must call the local fleet HTTP API.
- You need a kill switch and a hard concurrency cap (v1 max 5).

Do not use this for public internet binds, unbounded fan-out, or storing
API keys in YAML.

## Prerequisites

- Hermes CLI on PATH (`hermes --help`).
- A profile with model credentials already in `.env` (names listed under
  `secrets_ref` only).
- Optional: n8n on the same machine for webhook callbacks.

## How to Run

1. Copy `templates/fleet.example.yaml` and set `fleet_id` / `replicas`.
2. Start the loopback API with `terminal`:

```
hermes fleet serve --host 127.0.0.1 --port 8755
```

3. Call the API with `scripts/fleet_client.py` (also via `terminal`):

```
python skills/autonomous-ai-agents/hermes-fleet/scripts/fleet_client.py start --config templates/fleet.example.yaml
python skills/autonomous-ai-agents/hermes-fleet/scripts/fleet_client.py status --fleet-id local-dev
python skills/autonomous-ai-agents/hermes-fleet/scripts/fleet_client.py scale --fleet-id local-dev --replicas 2
python skills/autonomous-ai-agents/hermes-fleet/scripts/fleet_client.py stop --fleet-id local-dev
```

Read the example document with `read_file` before editing it. In-turn
delegation still uses `delegate_task`; this skill only manages the fleet
of sessions around that.

## Quick Reference

| Action | CLI | HTTP |
|--------|-----|------|
| Start | `hermes fleet start --config FILE` | `POST /fleet/start` |
| Status | `hermes fleet status ID` | `GET /fleet/{id}` |
| Scale | `hermes fleet scale ID --replicas N` | `POST /fleet/{id}/scale` |
| Stop | `hermes fleet stop ID` | `POST /fleet/{id}/stop` |
| Serve | `hermes fleet serve` | binds `127.0.0.1:8755` |

Auth header: `Authorization: Bearer $FLEET_HTTP_TOKEN`. Token file:
`$HERMES_HOME/fleets/.http_token`.

## Procedure

1. Confirm `kill_switch` is false in the fleet document.
2. Confirm `max_concurrency` is ≤ 5 and `replicas` ≤ that cap.
3. List credential **names** under `secrets_ref` (for example
   `OPENROUTER_API_KEY`). Never paste values.
4. If n8n should receive lifecycle events, set `webhook_callback_url` to a
   loopback URL such as `http://127.0.0.1:5678/webhook/hermes-fleet`.
5. `start`, then `status` until `live_workers` matches `replicas`.
6. `stop` (drain) when the workflow finishes.

## Pitfalls

- Non-loopback callback URLs and binds are refused in v1.
- `POST /fleet/start` on an already-running `fleet_id` returns 409.
- Scale-up is refused while `kill_switch` is true; stop still works.
- HTTP callers have no parent agent turn, so workers are idle **session
  slots**. Drive LLM work through the existing gateway webhook or
  `cronjob` / `delegate_task` paths.

## Verification

- `hermes fleet start` then `hermes fleet status <id>` shows
  `live_workers` equal to `replicas`.
- `hermes fleet scale <id> --replicas 6` fails when `max_concurrency` is
  5.
- `hermes fleet stop <id>` leaves `status: stopped` and zero live workers.
