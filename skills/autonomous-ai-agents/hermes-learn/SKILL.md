---
name: hermes-learn
description: "Store a lesson in Hermes persistent memory."
version: 1.0.0
author: Matt Parker (Mjparker-toolate), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [memory, learn, fleet, clawhub]
    category: autonomous-ai-agents
    related_skills: [hermes-agent, hermes-fleet]
---

# Hermes Learn Skill

Capture a short lesson from a fleet or ClawHub turn. In an agent session
use the `memory` tool so the note is gated and cache-safe. n8n has no
agent turn: `scripts/run.py` appends JSONL under
`$HERMES_HOME/memories/fleet-lessons.jsonl` and does **not** rewrite
`MEMORY.md`.

## When to Use

- A fleet worker should remember a durable fact for later sessions.
- n8n finished a specialist turn and wants a sidecar note.

Do not use this to store API keys.

## Prerequisites

- Agent path: `memory` tool available.
- n8n path: writable `HERMES_HOME` (profile-aware).

## How to Run

Agent: call `memory` with the lesson text. n8n: env `FLEET_INSTRUCTION`
or stdin into `scripts/run.py`. Read this file with `read_file` first.

## Quick Reference

| Surface | Destination |
|---------|-------------|
| Agent | `memory` tool (MEMORY.md / USER.md, next session) |
| n8n | `$HERMES_HOME/memories/fleet-lessons.jsonl` |

## Procedure

1. Keep the lesson names-only for secrets.
2. Prefer `memory` when a Hermes turn is running.
3. n8n appends JSONL so the current prompt cache stays untouched.

## Pitfalls

- Mid-session MEMORY.md edits do not refresh the cached system prompt.
- `scripts/run.py` takes no argv secrets.

## Verification

- n8n run creates a JSONL line and prints `status: ok`.
- The line contains the instruction text, not a token.
