---
title: "Features Overview"
sidebar_label: "Overview"
sidebar_position: 1
---

# Features Overview

Hermes Agent includes a rich set of capabilities that extend far beyond basic chat. From persistent memory and file-aware context to browser automation and voice conversations, these features work together to make Hermes a powerful autonomous assistant.

This page is the **complete catalog** of shipped feature docs. Every page under Features is listed here once. Surfaces that live outside this folder (CLI, TUI, desktop, messaging) are linked at the top so "what can Hermes do?" has a single start.

:::tip Don't know where to start?
`hermes setup --portal` covers a model provider plus all four Tool Gateway tools (web search, image generation, TTS, browser) in one command. See [Nous Portal](/integrations/nous-portal).
:::

## Surfaces

The same agent core drives every surface. Pick the one that matches how you work:

- **[CLI](../cli.md)** — Interactive terminal REPL with slash commands, streaming tool output, and interrupt-and-redirect.
- **[TUI](../tui.md)** — Ink terminal UI (`hermes --tui`) with overlays, mouse selection, and docked widgets.
- **[Desktop](../desktop.md)** — Native Electron app (macOS, Windows, Linux) with streaming chat, previews, voice, and settings.
- **[Bot Mode](../bot-mode.md)** — Named bots (each a Hermes profile) with a canonical forever-chat, routines, and peer messaging.
- **[Messaging Gateway](../messaging/index.md)** — Telegram, Discord, Slack, WhatsApp, Signal, iMessage, Email, SMS, Matrix, and more from one process.

## Core

- **[Tools & Toolsets](tools.md)** — Tools are functions that extend the agent's capabilities. They're organized into logical toolsets that can be enabled or disabled per platform, covering web search, terminal execution, file editing, memory, delegation, and more.
- **[Nous Tool Gateway](tool-gateway.md)** — One Nous Portal subscription routes web search, image generation, TTS, and cloud browser calls so you don't collect a separate key per vendor.
- **[Document Extraction](document-extraction.md)** — `read_file` converts PDFs, Office documents, and notebooks to text, and warns when a scanned PDF has no text layer.
- **[Tool Search](tool-search.md)** — Progressive disclosure for MCP and plugin tools: the model searches and loads schemas on demand instead of paying for every schema every turn.
- **[Skills System](skills.md)** — On-demand knowledge documents the agent can load when needed. Skills follow a progressive disclosure pattern to minimize token usage and are compatible with the [agentskills.io](https://agentskills.io/specification) open standard.
- **[LSP — Semantic Diagnostics](lsp.md)** — Real language servers (pyright, gopls, rust-analyzer, …) feed type and project errors into the post-write check used by `write_file` and `patch`.
- **[Curator](curator.md)** — Background maintenance for agent-created skills: usage tracking, staleness, archival, and LLM-driven review. Bundled and hub-installed skills are off-limits.
- **[Persistent Memory](memory.md)** — Bounded, curated memory that persists across sessions. Hermes remembers your preferences, projects, environment, and things it has learned via `MEMORY.md` and `USER.md`.
- **[Memory Providers](memory-providers.md)** — Plug in external memory backends (Honcho, OpenViking, Mem0, Hindsight, Holographic, RetainDB, ByteRover, Supermemory) for cross-session user modeling beyond the built-in files.
- **[Honcho Memory](honcho.md)** — Dialectic user modeling and multi-agent personalization via the Honcho memory provider.
- **[Context Files](context-files.md)** — Hermes automatically discovers and loads project context files (`.hermes.md`, `AGENTS.md`, `CLAUDE.md`, `SOUL.md`, `.cursorrules`) that shape how it behaves in your project.
- **[Context References](context-references.md)** — Type `@` followed by a reference to inject files, folders, git diffs, and URLs directly into your messages. Hermes expands the reference inline and appends the content automatically.
- **[Mixture of Agents](mixture-of-agents.md)** — Named MoA presets appear as selectable models: reference models analyze first, then an aggregator runs the normal agent loop with tools.
- **[Checkpoints](../checkpoints-and-rollback.md)** — Hermes automatically snapshots your working directory before making file changes, giving you a safety net to roll back with `/rollback` if something goes wrong.
- **[Personality & SOUL.md](personality.md)** — Fully customizable agent personality. `SOUL.md` is the primary identity file — the first thing in the system prompt — and you can swap in built-in or custom `/personality` presets per session.
- **[Skins & Themes](skins.md)** — Customize the CLI's visual presentation: banner colors, spinner faces and verbs, response-box labels, branding text, and the tool activity prefix.
- **[Plugins](plugins.md)** — Add custom tools, hooks, and integrations without modifying core code. Three plugin types: general plugins (tools/hooks), memory providers (cross-session knowledge), and context engines (alternative context management). Managed via the unified `hermes plugins` interactive UI.
- **[Built-in Plugins](built-in-plugins.md)** — Shipped opt-in plugins: disk-cleanup, security-guidance, Langfuse, Spotify, Google Meet, Teams pipeline, image-gen backends, achievements, and the kanban dashboard.

## Automation

- **[Scheduled Tasks (Cron)](cron.md)** — Schedule tasks to run automatically with natural language or cron expressions. Jobs can attach skills, deliver results to any platform, and support pause/resume/edit operations.
- **[Subagent Delegation](delegation.md)** — The `delegate_task` tool spawns child agent instances with isolated context, restricted toolsets, and their own terminal sessions. Run 3 concurrent subagents by default (configurable) for parallel workstreams.
- **[Kanban (Multi-Agent Board)](kanban.md)** — Durable SQLite-backed board for coordinating multiple Hermes profiles: claim, review, block, attachments, and a dispatcher that lives in the gateway.
- **[Kanban Tutorial](kanban-tutorial.md)** — Walkthrough of the four kanban use-cases with the dashboard open.
- **[Kanban Worker Lanes](kanban-worker-lanes.md)** — Contract for dispatcher lanes — profile workers, external CLI workers, and how assignees map to spawn mechanisms.
- **[Persistent Goals](goals.md)** — `/goal` keeps a standing objective in this session. A judge model continues the loop until the goal is done, paused, or the turn budget runs out.
- **[Session Heartbeats](heartbeat.md)** — `/heartbeat` re-enters the current conversation on an idle interval, as a normal user message, so the prompt cache stays intact.
- **[Recurring Loops](loops.md)** — `/loop` re-runs a prompt or slash command on a timer (or self-paced) inside this session until you stop it.
- **[Code Execution](code-execution.md)** — The `execute_code` tool lets the agent write Python scripts that call Hermes tools programmatically, collapsing multi-step workflows into a single LLM turn via sandboxed RPC execution.
- **[Event Hooks](hooks.md)** — Run custom code at key lifecycle points. Gateway hooks handle logging, alerts, and webhooks; plugin hooks handle tool interception, metrics, and guardrails.
- **[Batch Processing](batch-processing.md)** — Run the Hermes agent across hundreds or thousands of prompts in parallel, generating structured ShareGPT-format trajectory data for training data generation or evaluation.
- **[Codex App-Server Runtime](codex-app-server-runtime.md)** — Opt-in: hand OpenAI/Codex turns to the Codex CLI app-server (sandbox, native plugins) while Hermes keeps sessions, memory, and extra tools via MCP callback.

## Media & Web

- **[Voice Mode](voice-mode.md)** — Full voice interaction across CLI and messaging platforms. Talk to the agent using your microphone, hear spoken replies, and have live voice conversations in Discord voice channels.
- **[Wake Word](wake-word.md)** — Hands-free "Hey Hermes" trigger for the CLI, TUI, and desktop app. An on-device hotword listener starts a voice session when you speak the wake phrase.
- **[Web Search & Extract](web-search.md)** — `web_search` and `web_extract` with interchangeable backends (Firecrawl, Brave, Exa, Tavily, Perplexity, SearXNG, DuckDuckGo, and more).
- **[X (Twitter) Search](x-search.md)** — Read-only public X discovery via xAI's `x_search` tool when SuperGrok OAuth or `XAI_API_KEY` is configured.
- **[Browser Automation](browser.md)** — Full browser automation with multiple backends: Browserbase cloud, Browser Use cloud, local Chrome/Brave/Chromium/Edge via CDP, or local Chromium. Navigate websites, fill forms, and extract information.
- **[Computer Use](computer-use.md)** — Background desktop control (macOS, Windows, Linux) via cua-driver: screenshots, mouse, keyboard, and accessibility trees without stealing your cursor or focus.
- **[Vision & Image Paste](vision.md)** — Multimodal vision support. Paste images from your clipboard into the CLI and ask the agent to analyze, describe, or work with them using any vision-capable model.
- **[Image Generation](image-generation.md)** — Generate images from text prompts using FAL.ai. Eleven models supported (FLUX 2 Klein/Pro, GPT-Image 1.5/2, Nano Banana Pro, Ideogram V3, Recraft V4 Pro, Qwen, Z-Image Turbo, Krea V2 Medium/Large); pick one via `hermes tools`.
- **[Spotify](spotify.md)** — Native Spotify playback, queue, search, playlists, albums, and library via PKCE OAuth (`hermes auth spotify`).
- **[Pets](pets.md)** — Optional animated petdex mascot that reacts to agent activity on the CLI, TUI, and desktop. Cosmetic only — no token or cache impact.
- **[Voice & TTS](tts.md)** — Text-to-speech output and voice message transcription across all messaging platforms, with ten native provider options: Edge TTS (free), ElevenLabs, OpenAI TTS, MiniMax, Mistral Voxtral, Google Gemini, xAI, NeuTTS, KittenTTS, and Piper — plus custom command providers for any local TTS CLI.
- **[Deliverable Mode](deliverable-mode.md)** — On messaging platforms, generated files (charts, PDFs, spreadsheets, audio) in the reply are uploaded as native attachments.

## Management

- **[Web Dashboard](web-dashboard.md)** — Browser-based administration: config, keys, MCP, pairing, webhooks, gateway, memory, sessions, logs, analytics, cron, and skills. Primary chat embeds the real TUI over a PTY.
- **[Extending the Dashboard](extending-the-dashboard.md)** — Drop-in dashboard themes and UI/backend plugins (tabs, shell slots, FastAPI routes) without forking the SPA.
- **[API Server](api-server.md)** — Expose Hermes as an OpenAI-compatible HTTP endpoint. Connect any frontend that speaks the OpenAI format — Open WebUI, LobeChat, LibreChat, and more.
- **[Subscription Proxy](subscription-proxy.md)** — Local OpenAI-compatible proxy that attaches your Portal/OAuth credentials so other apps can use the model without the agent loop.

## Integrations

- **[MCP Integration](mcp.md)** — Connect to any MCP server via stdio or HTTP transport. Access external tools from GitHub, databases, file systems, and internal APIs without writing native Hermes tools. Includes per-server tool filtering and sampling support.
- **[Provider Routing](provider-routing.md)** — Fine-grained control over which AI providers handle your requests. Optimize for cost, speed, or quality with sorting, whitelists, blacklists, and priority ordering.
- **[Fallback Providers](fallback-providers.md)** — Automatic failover to backup LLM providers when your primary model encounters errors, including independent fallback for auxiliary tasks like vision and compression.
- **[Credential Pools](credential-pools.md)** — Distribute API calls across multiple keys for the same provider. Automatic rotation on rate limits or failures.
- **[Prompt caching](../configuration#prompt-caching)** — Built-in cross-session 1-hour prefix cache for Claude on native Anthropic, OpenRouter, and Nous Portal. Always-on; no configuration required.
- **[IDE Integration (ACP)](acp.md)** — Use Hermes inside ACP-compatible editors such as VS Code, Zed, and JetBrains. Chat, tool activity, file diffs, and terminal commands render inside your editor.
