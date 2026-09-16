---
title: "功能概览"
sidebar_label: "概览"
sidebar_position: 1
---

# 功能概览

Hermes Agent 包含一套丰富的能力，远超基础聊天范畴。从持久化记忆、文件感知上下文，到浏览器自动化和语音对话，这些功能协同工作，使 Hermes 成为一个强大的自主助手。

本页是已发布功能文档的**完整目录**。Features 下的每个页面都会在此列出一次。位于该目录之外的使用界面（CLI、TUI、桌面端、消息网关）放在开头，这样「Hermes 能做什么」有一个统一入口。

:::tip 不知道从哪开始？
`hermes setup --portal` 一次配置模型提供商以及 Tool Gateway 的四项工具（网页搜索、图像生成、TTS、浏览器）。详见 [Nous Portal](/integrations/nous-portal)。
:::

## 使用界面

同一套 Agent 核心驱动所有界面。按工作方式选择：

- **[CLI](../cli.md)** — 交互式终端 REPL，支持斜杠命令、流式工具输出、中断并改向。
- **[TUI](../tui.md)** — Ink 终端界面（`hermes --tui`），带浮层、鼠标选择和停靠小组件。
- **[桌面端](../desktop.md)** — 原生 Electron 应用（macOS、Windows、Linux），含流式对话、预览、语音和设置。
- **[Bot Mode](../bot-mode.md)** — 命名 Bot（每个都是一个 Hermes profile），带永久会话、例行任务和对等消息。
- **[消息网关](../messaging/index.md)** — 一个进程接入 Telegram、Discord、Slack、WhatsApp、Signal、iMessage、Email、SMS、Matrix 等。

## 核心功能

- **[工具与工具集](tools.md)** — 工具是扩展 Agent 能力的函数。它们被组织成逻辑工具集，可按平台启用或禁用，涵盖网络搜索、终端执行、文件编辑、记忆、委派等功能。
- **[Nous Tool Gateway](tool-gateway.md)** — 一份 Nous Portal 订阅即可路由网页搜索、图像生成、TTS 和云端浏览器，无需为每个厂商单独申请密钥。
- **[文档提取](document-extraction.md)** — `read_file` 将 PDF、Office 文档和笔记本转为文本，并在扫描件没有文字层时发出警告。
- **[工具搜索](tool-search.md)** — 对 MCP 与插件工具的渐进式披露：模型按需搜索并加载 schema，而不是每轮都为全部 schema 付费。
- **[技能系统](skills.md)** — Agent 可按需加载的知识文档。技能遵循渐进式披露模式以最小化 token 用量，并兼容 [agentskills.io](https://agentskills.io/specification) 开放标准。
- **[LSP — 语义诊断](lsp.md)** — 真实语言服务器（pyright、gopls、rust-analyzer 等）把类型错误和项目级问题送入 `write_file` / `patch` 的写后检查。
- **[Curator](curator.md)** — 对 Agent 自建技能的后台维护：用量追踪、过期、归档与 LLM 评审。内置和 Hub 安装的技能不在范围内。
- **[持久化记忆](memory.md)** — 跨会话持久保存的有界、精选记忆。Hermes 通过 `MEMORY.md` 和 `USER.md` 记住你的偏好、项目、环境及已学习的内容。
- **[记忆提供商](memory-providers.md)** — 接入外部记忆后端（Honcho、OpenViking、Mem0、Hindsight、Holographic、RetainDB、ByteRover、Supermemory），实现超越内置文件的跨会话用户建模。
- **[Honcho 记忆](honcho.md)** — 通过 Honcho 记忆提供商进行辩证用户建模与多 Agent 个性化。
- **[上下文文件](context-files.md)** — Hermes 自动发现并加载项目上下文文件（`.hermes.md`、`AGENTS.md`、`CLAUDE.md`、`SOUL.md`、`.cursorrules`），这些文件决定了它在你项目中的行为方式。
- **[上下文引用](context-references.md)** — 输入 `@` 后跟引用内容，可将文件、文件夹、git diff 和 URL 直接注入消息中。Hermes 会内联展开引用并自动附加相应内容。
- **[Mixture of Agents](mixture-of-agents.md)** — 命名 MoA 预设可作为模型选择：参考模型先分析，再由聚合模型带着工具跑正常 Agent 循环。
- **[检查点](../checkpoints-and-rollback.md)** — Hermes 在进行文件更改前自动为工作目录创建快照，提供安全网，可通过 `/rollback` 回滚至出错前的状态。
- **[个性与 SOUL.md](personality.md)** — 完全可自定义的 Agent 个性。`SOUL.md` 是主要身份文件——系统提示词中的第一项——你可以在每个会话中切换内置或自定义的 `/personality` 预设。
- **[皮肤与主题](skins.md)** — 自定义 CLI 的视觉呈现：横幅颜色、加载动画图标和动词、响应框标签、品牌文字，以及工具活动前缀。
- **[插件](plugins.md)** — 无需修改核心代码即可添加自定义工具、hook 和集成。三种插件类型：通用插件（工具/hook）、记忆提供商（跨会话知识）和上下文引擎（替代上下文管理）。通过统一的 `hermes plugins` 交互式界面管理。
- **[内置插件](built-in-plugins.md)** — 随仓库提供、默认关闭的插件：磁盘清理、安全提示、Langfuse、Spotify、Google Meet、Teams 流水线、图像生成后端、成就系统和 Kanban 看板。

## 自动化

- **[定时任务（Cron）](cron.md)** — 使用自然语言或 cron 表达式调度自动运行的任务。任务可附加技能、将结果推送至任意平台，并支持暂停/恢复/编辑操作。
- **[子 Agent 委派](delegation.md)** — `delegate_task` 工具可生成具有独立上下文、受限工具集和独立终端会话的子 Agent 实例。默认并发运行 3 个子 Agent（可配置），支持并行工作流。
- **[Kanban（多 Agent 看板）](kanban.md)** — 基于 SQLite 的持久看板，用于协调多个 Hermes profile：认领、评审、阻塞、附件，以及运行在网关内的调度器。
- **[Kanban 教程](kanban-tutorial.md)** — 在仪表板打开的情况下，走完 Kanban 的四种使用场景。
- **[Kanban Worker Lanes](kanban-worker-lanes.md)** — 调度器通道契约：profile worker、外部 CLI worker，以及 assignee 如何映射到拉起方式。
- **[持久目标](goals.md)** — `/goal` 在本会话中保持一项长期目标。评判模型会继续循环，直到目标完成、暂停或轮次预算用尽。
- **[会话心跳](heartbeat.md)** — `/heartbeat` 在会话空闲时按间隔重新进入当前对话，作为普通用户消息注入，不破坏 prompt 缓存。
- **[循环（Loop）](loops.md)** — `/loop` 按定时（或自适应节奏）在本会话中重复执行 prompt 或斜杠命令，直到你停止它。
- **[代码执行](code-execution.md)** — `execute_code` 工具允许 Agent 编写以编程方式调用 Hermes 工具的 Python 脚本，通过沙箱 RPC 执行将多步骤工作流压缩为单次 LLM 调用。
- **[事件 Hook](hooks.md)** — 在关键生命周期节点运行自定义代码。Gateway hook 处理日志、告警和 webhook；plugin hook 处理工具拦截、指标和护栏。
- **[批处理](batch-processing.md)** — 跨数百或数千个 prompt 并行运行 Hermes Agent，生成 ShareGPT 格式的结构化轨迹数据，用于训练数据生成或评估。
- **[Codex App-Server 运行时](codex-app-server-runtime.md)** — 可选：把 OpenAI/Codex 轮次交给 Codex CLI app-server（沙箱、原生插件），Hermes 仍负责会话、记忆，并通过 MCP 回调提供额外工具。

## 媒体与网络

- **[语音模式](voice-mode.md)** — 跨 CLI 和消息平台的完整语音交互。使用麦克风与 Agent 对话，收听语音回复，并在 Discord 语音频道中进行实时语音对话。
- **[唤醒词](wake-word.md)** — CLI、TUI 和桌面端的「Hey Hermes」免提触发。设备端热词监听在你说出唤醒词后开启语音会话。
- **[网页搜索与提取](web-search.md)** — `web_search` 与 `web_extract`，可切换后端（Firecrawl、Brave、Exa、Tavily、Perplexity、SearXNG、DuckDuckGo 等）。
- **[X（Twitter）搜索](x-search.md)** — 在配置 SuperGrok OAuth 或 `XAI_API_KEY` 时，通过 xAI 的 `x_search` 只读发现公开 X 内容。
- **[浏览器自动化](browser.md)** — 支持多种后端的完整浏览器自动化：Browserbase 云端、Browser Use 云端、通过 CDP 连接的本地 Chrome/Brave/Chromium/Edge，或本地 Chromium。可导航网站、填写表单并提取信息。
- **[Computer Use](computer-use.md)** — 通过 cua-driver 在后台控制桌面（macOS、Windows、Linux）：截屏、鼠标、键盘和无障碍树，且不抢占光标或焦点。
- **[视觉与图片粘贴](vision.md)** — 多模态视觉支持。将剪贴板中的图片粘贴到 CLI，并使用任意支持视觉的模型请求 Agent 分析、描述或处理图片。
- **[图像生成](image-generation.md)** — 使用 FAL.ai 从文本 prompt 生成图像。支持十一种模型（FLUX 2 Klein/Pro、GPT-Image 1.5/2、Nano Banana Pro、Ideogram V3、Recraft V4 Pro、Qwen、Z-Image Turbo、Krea V2 Medium/Large）；可通过 `hermes tools` 选择。
- **[Spotify](spotify.md)** — 通过 PKCE OAuth（`hermes auth spotify`）原生控制播放、队列、搜索、播放列表、专辑和曲库。
- **[Pets](pets.md)** — 可选的 petdex 动态吉祥物，在 CLI、TUI 和桌面端对 Agent 活动做出反应。纯外观，不影响 token 或缓存。
- **[语音与 TTS](tts.md)** — 跨所有消息平台的文字转语音输出和语音消息转录，提供十种原生提供商选项：Edge TTS（免费）、ElevenLabs、OpenAI TTS、MiniMax、Mistral Voxtral、Google Gemini、xAI、NeuTTS、KittenTTS 和 Piper——以及支持任意本地 TTS CLI 的自定义命令提供商。
- **[交付模式](deliverable-mode.md)** — 在消息平台上，回复中的生成文件（图表、PDF、表格、音频）会作为原生附件上传。

## 管理

- **[Web 仪表板](web-dashboard.md)** — 基于浏览器的管理面板：配置、密钥、MCP、配对、webhook、网关、记忆、会话、日志、分析、cron 和技能。主聊天通过 PTY 嵌入真正的 TUI。
- **[扩展仪表板](extending-the-dashboard.md)** — 无需分叉 SPA，即可投放仪表板主题以及 UI/后端插件（标签页、shell 槽位、FastAPI 路由）。
- **[API 服务器](api-server.md)** — 将 Hermes 作为兼容 OpenAI 的 HTTP 端点暴露。连接任何支持 OpenAI 格式的前端——Open WebUI、LobeChat、LibreChat 等。
- **[订阅代理](subscription-proxy.md)** — 本地兼容 OpenAI 的代理，自动附带 Portal/OAuth 凭证，让其他应用只使用模型、不走 Agent 循环。

## 集成

- **[MCP 集成](mcp.md)** — 通过 stdio 或 HTTP 传输连接任意 MCP 服务器。无需编写原生 Hermes 工具，即可访问来自 GitHub、数据库、文件系统和内部 API 的外部工具。支持按服务器过滤工具及 sampling。
- **[提供商路由](provider-routing.md)** — 对 AI 提供商处理请求的方式进行精细控制。通过排序、白名单、黑名单和优先级排序，在成本、速度或质量之间优化。
- **[备用提供商](fallback-providers.md)** — 当主模型遇到错误时自动故障转移至备用 LLM 提供商，包括针对视觉和压缩等辅助任务的独立备用机制。
- **[凭证池](credential-pools.md)** — 在同一提供商的多个密钥之间分发 API 调用。在触发速率限制或发生故障时自动轮换。
- **[Prompt 缓存](../configuration#prompt-caching)** — 针对原生 Anthropic、OpenRouter 和 Nous Portal 上的 Claude，内置跨会话 1 小时前缀缓存。始终开启，无需配置。
- **[IDE 集成（ACP）](acp.md)** — 在兼容 ACP 的编辑器（如 VS Code、Zed 和 JetBrains）中使用 Hermes。聊天、工具活动、文件 diff 和终端命令均在编辑器内渲染。
