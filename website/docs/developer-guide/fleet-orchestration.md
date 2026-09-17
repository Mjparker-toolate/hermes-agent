---
title: "Fleet Orchestration"
description: "v1 local Hermes worker-fleet glue for n8n and ClawHub-installed skills"
---

# Fleet Orchestration (v1)

Hermes can expose a **capped pool of worker sessions** that an orchestrator
(n8n today, a ClawHub-installed skill later) starts, inspects, scales, and
stops. ClawHub remains a **skill/plugin registry**, not a runtime: OpenClaw
and Hermes run agents; ClawHub publishes and installs skills.

This slice wraps existing Hermes primitives instead of inventing a process
supervisor:

| Need | Existing primitive |
|------|--------------------|
| Worker identity | `SessionDB.create_session(source='fleet')` |
| In-turn child run | Public [subagent lifecycle API](./subagent-lifecycle-api.md) (same host path as `delegate_task`) |
| Durable follow-up work | `cronjob` / gateway webhook (unchanged) |
| Local HTTP trigger | `hermes fleet serve` (loopback only) |

v1 does **not** stand up paid cloud, bind a public interface, or embed
secrets in fleet documents.

## Key files

| File | Purpose |
|------|---------|
| `hermes_cli/fleet_schema.py` | YAML/JSON schema + v1 invariants |
| `hermes_cli/fleet_manager.py` | Create / list / scale / drain + concurrency cap |
| `hermes_cli/fleet_store.py` | `$HERMES_HOME/fleets/<id>.json` |
| `hermes_cli/fleet_http.py` | Loopback HTTP surface |
| `hermes_cli/fleet.py` | `hermes fleet` CLI |
| `skills/autonomous-ai-agents/hermes-fleet/` | ClawHub-publishable skill stub |

## Fleet document

```yaml
fleet_id: local-dev
max_concurrency: 3          # hard v1 ceiling is 5
worker_template:
  model: ""                 # inherit the profile default
  provider: ""
  tools: [terminal, file]
  skills: [hermes-fleet]
  role: leaf                # leaf | orchestrator
  goal: ""
webhook_callback_url: http://127.0.0.1:5678/webhook/hermes-fleet
secrets_ref:
  - OPENROUTER_API_KEY      # names only — never values
backoff:
  initial_seconds: 1
  max_seconds: 30
  multiplier: 2
retry:
  max_attempts: 2
kill_switch: false
replicas: 1
```

Invariants enforced by `normalize_fleet_config()`:

- `max_concurrency` is an integer in `1..5`.
- `replicas` cannot exceed `max_concurrency`.
- `secrets_ref` entries must look like env-var **names**. Keys such as
  `api_key` / `token` / `password` with a non-empty value are rejected.
- `webhook_callback_url`, when set, must be `http(s)` on loopback
  (`127.0.0.1`, `localhost`, `::1`).
- `kill_switch: true` refuses `start` and scale-up; stop/drain still work.

Behavioral knobs live under `fleet:` in `config.yaml` (not `HERMES_*` env
vars). The HTTP bearer token is a secret: `FLEET_HTTP_TOKEN` in `.env`, or
an auto-generated file at `$HERMES_HOME/fleets/.http_token` (mode `0600`).

## Worker lifecycle

Each worker is a session slot:

1. `POST /fleet/start` (or `hermes fleet start`) creates the fleet record
   and `replicas` sessions with `source='fleet'`.
2. If a parent agent turn is bound (`get_active_subagent_parent()`), the
   manager also launches a leaf through `SubagentLifecycleService`.
3. HTTP/n8n callers have no parent turn, so workers stay **idle session
   slots**. Drive actual LLM work later via the gateway webhook platform or
   a cron job — those paths already spawn agent turns without a new
   supervisor.
4. `POST /fleet/{id}/scale` with `{"replicas": N}` spawns or drains until
   the live set matches `N` (live = `pending|idle|running|draining`).
5. `POST /fleet/{id}/stop` drains every live worker, ends the sessions
   (`end_reason=fleet_drain`), and marks the fleet `stopped`.

Failed workers honor `retry.max_attempts` and `backoff.*`. Exhausted
retries become `failed` and no longer count against the cap.

## HTTP contract (loopback)

```bash
hermes fleet serve --host 127.0.0.1 --port 8755
```

The server refuses a non-loopback bind. Every mutating route requires:

```
Authorization: Bearer <FLEET_HTTP_TOKEN>
Content-Type: application/json
```

| Method | Path | Body | Success |
|--------|------|------|---------|
| `GET` | `/health` | — | `{"ok": true, "service": "hermes-fleet"}` (no auth) |
| `POST` | `/fleet/start` | fleet document (+ optional `replicas`) | `201` fleet status |
| `GET` | `/fleet/{id}` | — | `200` fleet status |
| `POST` | `/fleet/{id}/scale` | `{"replicas": N}` | `200` fleet status |
| `POST` | `/fleet/{id}/stop` | `{}` | `200` fleet status |

Error envelope:

```json
{"error": "human-readable message", "code": "concurrency_cap"}
```

| HTTP | `code` |
|------|--------|
| 400 | `invalid_config`, `invalid_json`, `secrets_embedded`, `callback_not_loopback` |
| 401 | `unauthorized` |
| 403 | `kill_switch` |
| 404 | `not_found` |
| 409 | `concurrency_cap`, `already_running` |
| 413 | `body_too_large` |

### Status payload

```json
{
  "fleet_id": "local-dev",
  "status": "running",
  "kill_switch": false,
  "max_concurrency": 3,
  "replicas": 2,
  "live_workers": 2,
  "webhook_callback_url": "http://127.0.0.1:5678/webhook/hermes-fleet",
  "secrets_ref": ["OPENROUTER_API_KEY"],
  "workers": [
    {
      "worker_id": "w-01-ab12cd34",
      "session_id": "fleet_local-dev_w-01-ab12cd34_deadbeef",
      "status": "idle",
      "attempts": 0,
      "error": null
    }
  ]
}
```

On start / scale / stop the manager POSTs `{event, fleet}` to
`webhook_callback_url` when that URL is loopback. Failures are ignored;
fleet state is already on disk.

## CLI

```bash
hermes fleet start --config path/to/fleet.yaml --replicas 2
hermes fleet status local-dev
hermes fleet scale local-dev --replicas 1
hermes fleet stop local-dev
hermes fleet list    # alias: ls
hermes fleet serve --port 8755
```

## n8n

1. Run `hermes fleet serve` on the same machine as n8n.
2. Store the bearer token in an n8n credential (not in the fleet YAML).
3. HTTP Request nodes against `http://127.0.0.1:8755` using the table above.
4. Optional: an n8n webhook node on `http://127.0.0.1:5678/webhook/hermes-fleet`
   receives lifecycle callbacks.

Sister lanes: Automations owns n8n/towelie webhooks; Cloud owns infra
quotas. This module does not allocate cloud workers.

## ClawHub

Ship `skills/autonomous-ai-agents/hermes-fleet/` as a skill. A ClawHub agent
installs it (`hermes skills install …`) and follows `SKILL.md` to call the
local HTTP surface. No registry upload is required for this slice.

## Out of scope (v1)

- Public / non-loopback binds
- Paid cloud worker pools
- A new core model tool (footprint ladder: CLI + skill)
- Embedding secret values in YAML
- Surviving process restart for in-flight `SubagentLifecycleService` children
  (same contract as the public subagent API; session rows remain)
