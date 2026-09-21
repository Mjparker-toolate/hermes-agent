# Hermes subagents — a fan-out hierarchy with an improvement loop

These are [Cursor subagents](https://cursor.com/docs) tuned to the `hermes-agent` codebase.
They form a **fan-out hierarchy**: one orchestrator delegates independent work to specialists,
then feeds their results into an **improvement loop** that ends at a rubric gate. Every prompt
is grounded in the root and area `AGENTS.md` files so delegated work inherits the project's
invariants instead of rediscovering them.

## Hierarchy

```
                        hermes-architect  (orchestrator / root of the fan-out)
                                │  reads AGENTS.md routing table, plans, delegates
        ┌───────────────┬───────┴───────┬─────────────────┬──────────────────┐
        ▼               ▼               ▼                 ▼                  ▼
 hermes-explorer  hermes-refactorer  hermes-test-author  hermes-docs-syncer  hermes-reviewer
 (navigate the    (split god-files   (invariant tests    (keep docs in       (rubric +
  facade+siblings  into facade +      via                 sync when a         invariants
  layout, map      <stem>_<topic>     scripts/run_tests   symbol moves)       gate; verify
  call paths)      siblings)          .sh)                                    the premise)
```

| Subagent | Role | Grounded in |
|---|---|---|
| `hermes-architect` | Orchestrator; classifies, routes by area, fans out, synthesizes | root `AGENTS.md` + routing table + Footprint Ladder |
| `hermes-explorer` | Find code by topic, map call paths + patch seams | facade+siblings layout, dependency chain |
| `hermes-refactorer` | Decompose god-files (>~2k lines / fn >~300 / CC 30) | facade + `<stem>_<topic>` rules, `static_metrics.py` |
| `hermes-test-author` | 1–2 invariant tests, CI-parity runner | Testing section (`scripts/run_tests.sh`) |
| `hermes-docs-syncer` | Update `website/docs` / `docs` / `skills` / `AGENTS.md` on any move | "Moving a symbol means fixing its docs" |
| `hermes-reviewer` | Gate against the contribution rubric + invariants | "What We Want / What We Don't", pinning policy |

## The improvement loop

The specialists are wired into a closed loop so a change gets better each pass instead of
landing on the first draft:

```
   ┌──────────────────────────────────────────────────────────────────┐
   │                                                                    │
   ▼                                                                    │
1. EXPLORE   → hermes-explorer maps the area + invariants (file:line)   │
2. PLAN      → hermes-architect assigns each piece to a specialist      │
3. CHANGE    → hermes-refactorer / feature work (edit at the edges)     │
4. TEST      → hermes-test-author proves red-on-base → green            │
5. DOC-SYNC  → hermes-docs-syncer removes every stale reference         │
6. REVIEW    → hermes-reviewer returns ship / fix / needs-human ────────┘
                        │ ship
                        ▼
                     done
```

When step 6 returns **fix**, the architect re-enters the loop at the step the reviewer named
(usually 3 or 4) with the reviewer's `file:line` notes as new input — that is the "improvement"
part: each iteration is strictly better-informed than the last. When it returns
**needs-human**, the loop pauses rather than guessing at intent.

## How to invoke

- Let it happen automatically — the `description` fields use proactive language, so Cursor
  delegates when the task matches.
- Or ask explicitly: `Use the hermes-architect subagent to plan splitting hermes_state.py`.
- Parallelize within a stage: the architect launches independent specialists in one batch.
  Never parallelize dependent steps (explore → change → test → review is sequential).

## Design rules these prompts follow

- **Fan out only independent work**; sequence dependent stages.
- **Inherit invariants, don't restate opinions** — every prompt cites the `AGENTS.md` clause it
  enforces (prompt caching, role alternation, Footprint Ladder, pinning).
- **Evidence over assertion** — specialists return `file:line`, before/after metrics, and exact
  test commands, so the orchestrator synthesizes facts, not vibes.

Project subagents live in `.cursor/agents/` and are checked in so the whole team (and Cloud
Agents) share them; user-level overrides can live in `~/.cursor/agents/`.
