---
title: "Fleet Orchestration"
description: "v1 local Hermes worker-fleet glue for n8n agent-fleets and ClawHub skills"
---

# Fleet Orchestration (v1)

Hermes exposes a **capped pool of worker sessions** plus a loopback
**delegate** webhook that n8n `fleet-delegate` can call. Architecture
(do not invert):

| Piece | Role |
|-------|------|
| Cursor plugin `hermes-clawhub` | Coordinates the workflow |
| Hermes | Optional: gateway / cron / memory, plus this fleet manager |
| ClawHub | Skill registry (`clawhub-search` / `install` / `run`) |
| n8n agent-fleets | Fleet protocol (fan-out/fan-in graph, echo runner by default) |

n8n owns the task graph. Hermes stores `members`, defaults
`max_concurrency` to **3**, hard-caps it at **5**, and records specialist
turns. It does **not** call Cursor cloud (Cloud lane) or eval untrusted
ClawHub `SKILL.md`.

This slice wraps existing Hermes primitives instead of inventing a process
supervisor:

| Need | Existing primitive |
|------|--------------------|
| Worker identity | `SessionDB.create_session(source='fleet')` |
| In-turn child run | Public [subagent lifecycle API](./subagent-lifecycle-api.md) (same host path as `delegate_task`) |
| Durable follow-up work | `cronjob` / gateway webhook (unchanged) |
| Local HTTP trigger | `hermes fleet serve` (loopback only) |
| n8n specialist turn | `POST /fleet/{id}/delegate` via `fleet-delegate/scripts/run.py` |

v1 does **not** stand up paid cloud, bind a public interface, or embed
secrets in fleet documents.

## Key files

| File | Purpose |
|------|---------|
| `hermes_cli/fleet_schema.py` | YAML/JSON schema + n8n camelCase coerce |
| `hermes_cli/fleet_manager.py` | Create / scale / drain / delegate + inflight cap |
| `hermes_cli/fleet_store.py` | `$HERMES_HOME/fleets/<id>.json` |
| `hermes_cli/fleet_http.py` | Loopback HTTP surface |
| `hermes_cli/fleet.py` | `hermes fleet` CLI |
| `skills/autonomous-ai-agents/hermes-fleet/` | Manager skill + sample YAML |
| `skills/autonomous-ai-agents/fleet-delegate/` | n8n `scripts/run.py` glue |

## Fleet document

Snake_case Hermes documents and n8n camelCase documents both work.
Sample `fleetId: hermes-clawhub-combined`:

```yaml
fleetId: hermes-clawhub-combined
maxConcurrency: 3
members:
  - agentId: orchestrator
    role: coordinator
    tools: []
  - agentId: clawhub-skill-runner
    role: specialist
    tools:
      - clawhub:clawhub-search
      - clawhub:clawhub-install
      - clawhub:clawhub-run
  - agentId: cursor-cloud-delegate
    role: specialist
    tools: [cursor-cloud]
webhookCallbackUrl: http://127.0.0.1:5678/webhook/hermes-fleet
secretsRef:
  - OPENROUTER_API_KEY      # names only — never values
killSwitch: false
```

`coordinator`/`orchestrator` map to worker role `orchestrator`;
`specialist`/`leaf` map to `leaf`. When `replicas` is omitted, Hermes
spawns `min(len(members), max_concurrency)` slots and keeps the full
member list (n8n's graph may list more members than live workers).

Invariants enforced by `normalize_fleet_config()`:

- Omitted `max_concurrency` defaults to **3** (`config.yaml` `fleet.max_concurrency`).
- `max_concurrency` is an integer in `1..5` (hard ceiling 5 until live cost signal).
- Explicit `replicas` cannot exceed `max_concurrency`.
- `secrets_ref` entries must look like env-var **names**. Keys such as
  `api_key` / `token` / `password` with a non-empty value are rejected.
- `webhook_callback_url`, when set, must be `http(s)` on loopback
  (`127.0.0.1`, `localhost`, `::1`).
- `kill_switch: true` refuses `start`, scale-up, and delegate; stop/drain
  still work.
- n8n-only keys (`taskGraph`, `fanOut`, …) are ignored — the graph stays
  in n8n.

Behavioral knobs live under `fleet:` in `config.yaml` (not `HERMES_*` env
vars). The HTTP bearer token is a secret: `FLEET_HTTP_TOKEN` in `.env`, or
an auto-generated file at `$HERMES_HOME/fleets/.http_token` (mode `0600`).

## Worker lifecycle

Each worker is a session slot, tagged with `agent_id` when `members` are
present:

1. `POST /fleet/start` creates the fleet record and `replicas` sessions
   with `source='fleet'`.
2. If a parent agent turn is bound (`get_active_subagent_parent()`), the
   manager also launches a leaf through `SubagentLifecycleService`.
3. HTTP/n8n callers have no parent turn, so workers stay **idle session
   slots** until `POST /fleet/{id}/delegate`.
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
| `GET` | `/health` | — | `{"ok": true, "service": "hermes-fleet", "protocol": "n8n-agent-fleets"}` (no auth) |
| `POST` | `/fleet/start` | fleet document (`fleetId` + `members` accepted) | `201` fleet status |
| `GET` | `/fleet/{id}` | — | `200` fleet status |
| `POST` | `/fleet/{id}/scale` | `{"replicas": N}` | `200` fleet status |
| `POST` | `/fleet/{id}/stop` | `{}` | `200` fleet status |
| `POST` | `/fleet/{id}/delegate` | `{instruction, nodeId, agentId, tools, kind}` | `200` `{status, output, error, nodeId, agentId}` |

Delegate also accepts snake_case (`node_id`, `agent_id`). Instruction max
10000 characters. Overlapping POSTs increment an inflight counter; a
request that would exceed `max_concurrency` returns `409 concurrency_cap`.
Sequential nodes reuse idle slots.

Safety on delegate:

- Install + run tool ids in the same turn → `409 install_run_same_turn`.
- `cursor-cloud` is **accepted and recorded**, never executed (no
  `CURSOR_API_KEY` on argv, no Cursor HTTP).
- ClawHub skill text is untrusted and is not evaluated.

Error envelope (start/scale/stop):

```json
{"error": "human-readable message", "code": "concurrency_cap"}
```

| HTTP | `code` |
|------|--------|
| 400 | `invalid_config`, `invalid_json`, `secrets_embedded`, `callback_not_loopback` |
| 401 | `unauthorized` |
| 403 | `kill_switch` |
| 404 | `not_found` |
| 409 | `concurrency_cap`, `already_running`, `install_run_same_turn`, `not_running` |
| 413 | `body_too_large` |

On start / scale / stop the manager POSTs `{event, fleet}` to
`webhook_callback_url` when that URL is loopback. Failures are ignored;
fleet state is already on disk. Delegate does not fire that callback.

## CLI

```bash
hermes fleet start --config path/to/hermes-clawhub-combined.yaml
hermes fleet status hermes-clawhub-combined
hermes fleet delegate hermes-clawhub-combined --instruction "search yaml skills"
hermes fleet scale hermes-clawhub-combined --replicas 1
hermes fleet stop hermes-clawhub-combined
hermes fleet list    # alias: ls
hermes fleet serve --port 8755
```

## n8n

Enable `N8N_ENABLED_MODULES=agents,agent-fleets`. The echo runner is the
default; `N8N_AGENT_FLEETS_RUNNER=delegate` routes `clawhub:<slug>` and
`cursor-cloud` to each skill's `scripts/run.py` (env
`FLEET_INSTRUCTION` / `FLEET_NODE_ID` / `FLEET_AGENT_ID` + stdin — never
secrets on argv).

1. Run `hermes fleet serve` on the same machine as n8n.
2. Store the bearer token in an n8n credential (not in the fleet YAML).
3. `POST /fleet/start` with the combined document (or `hermes fleet start`).
4. n8n `fleet-delegate` → `skills/autonomous-ai-agents/fleet-delegate/scripts/run.py`
   → `POST http://127.0.0.1:8755/fleet/{id}/delegate`.
5. Optional: an n8n webhook node on `http://127.0.0.1:5678/webhook/hermes-fleet`
   receives lifecycle callbacks.

Sister lanes: Automations owns n8n/towelie webhooks; Cloud owns infra
quotas and Cursor API calls. This module does not allocate cloud workers.
Stacked n8n PRs live on `Mjparker-toolate/n8n` (agent-fleets + delegate runner).

## ClawHub skills

| Skill | Job |
|-------|-----|
| `clawhub-search` | Registry lookup; do not eval SKILL.md |
| `clawhub-install` | Install only; never run this turn |
| `clawhub-run` | Run an already-installed skill via fleet-delegate |
| `hermes-learn` | Persist a lesson (`memory` in-agent; JSONL for n8n) |
| `fleet-delegate` | POST to this HTTP surface |
| `hermes-fleet` | Start/scale/stop the manager |

## Out of scope (v1)

- Public / non-loopback binds
- Paid cloud worker pools / executing Cursor cloud
- Evaluating ClawHub SKILL.md
- A new core model tool (footprint ladder: CLI + skill)
- Embedding secret values in YAML
- Reimplementing n8n's fan-out/fan-in orchestrator
- Surviving process restart for in-flight `SubagentLifecycleService` children
  (same contract as the public subagent API; session rows remain)
