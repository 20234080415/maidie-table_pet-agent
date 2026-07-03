# AGENTS.md

## Project Overview

Maidie Desktop Pet is a Python + PyQt6 desktop AI pet and local desktop Agent. It includes desktop pet UI, animation, interaction, Brain-based Agent routing, structured tools, optional screen/vision understanding, local memory, and strict privacy boundaries.

Maidie is not a generic command executor. Do not add unrestricted shell, file deletion, silent screenshot upload, or silent clipboard exfiltration.

---

## Core Architecture

Production pipeline:

```text
User / Proactive Event
  -> PetController
  -> BrainRouter / LLMIntentRouter
  -> BrainPlanner
  -> BrainExecutor / ToolRegistry
  -> Synthesizer
  -> MaidieStyle
  -> PyQt UI / Animation
```

Rules:

1. `PetController` coordinates state, UI, movement, and AI sessions. Do not turn it into a business-logic God class.
2. Router decides intent only.
3. Planner creates structured tool plans only.
4. Executor validates and runs tools only.
5. Tools return structured facts only.
6. Synthesizer creates the final user-facing reply.
7. MaidieStyle preserves Maidie's character voice.
8. UI updates must stay on the Qt main thread.

---

## Important Directories

```text
main.py              # startup and dependency wiring
ai/                  # legacy-compatible AI clients and prompts
core/brain/          # production Router / Planner / Executor / Synthesizer
core/tools/          # structured tools and ToolRegistry
core/vision/         # Qwen VL / screen understanding
core/awareness/      # window, app, mouse, clipboard awareness
core/personality/    # final Maidie speaking style
core/settings.py     # config and personality presets
ui/                  # PyQt6 UI
memory/              # local memory and scheduled task storage
assets/              # sprites, actions, icons
tests/               # unittest and Qt offscreen tests
docs/                # documentation
packaging/           # packaging config
```

Avoid adding new production logic to deprecated layers:

```text
ai/router.py
core/agent/*
```

Prefer new Agent logic in:

```text
core/brain/
core/tools/
core/vision/
core/awareness/
core/prompts/
```

---

## Prompt Rules

Do not scatter large prompts across random modules. Prefer:

```text
core/prompts/personality.py
core/prompts/router.py
core/prompts/planner.py
core/prompts/synthesizer.py
core/prompts/vision.py
core/prompts/memory.py
```

`SettingsManager.personality_prompt()` should remain the compatibility entry point for selected personality behavior.

Maidie should sound like a desktop pet, not customer support: cute, helpful, lightly playful or tsundere, usually brief, and never exposing internal architecture in normal replies.

Do not mention internal terms in user-facing replies unless the user asks about the codebase:

```text
Router, Planner, Executor, Synthesizer, ToolRegistry, pipeline, tool call, system prompt
```

---

## Safety and Privacy

Never commit or expose:

```text
config/config.json
memory/*.db
memory/*.db-wal
memory/*.db-shm
memory/conversations.json
logs/
.env
*.key
*.pem
```

API keys should use environment variables when possible.

Dangerous operations must remain blocked unless explicitly designed, confirmed, tested, and documented:

```text
delete_file
execute_script
system_command
arbitrary shell execution
unconfirmed destructive writes
silent clipboard reading
silent screenshot upload
```

Planner output is not trusted. Executor must validate permissions and parameters again.

---

## PyQt6 Threading Rules

Never block the GUI thread with network requests, AI calls, OCR, file scans, image processing, subprocesses, or tests.

Background workers must not directly mutate `QWidget`, `QTimer`, `QPixmap`, pet windows, bubble windows, or overlay windows. Send results back to the Qt main thread safely.

---

## Configuration Rules

User config:

```text
config/config.json
```

Packaged default config:

```text
packaging/config.json
```

When adding config fields, update defaults, packaging config, settings UI if relevant, docs, and tests. Keep schema backward compatible.

---

## Testing

Before finishing meaningful changes, run:

```powershell
python -m unittest discover -v
```

For Qt tests:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m unittest discover -v
```

For focused changes, run targeted tests first, then full tests when possible.

Do not claim tests passed unless they were actually run.

---

## Assets and Actions

Main sprite/action assets live in:

```text
assets/
assets/actions/
assets/actions/actions.json
```

When adding actions, prefer `ActionRegistry` and action metadata. Do not hard-code new action triggers in `PetController`.

---

## Search and Clipboard

Search logic should handle explicit queries and safe follow-ups. If the clipboard changed recently and the user says “帮我搜一下”, prefer a confirmation flow or safe recent-clipboard resolution instead of failing with an empty query.

---

## Codex / OpenCode Tooling

Do not treat `codex` or `opencode` as production tools unless they are registered in `ToolRegistry`.

If implementing local coding ability, add real tools under `core/tools/`, restrict workspace paths, require confirmation before writes, block arbitrary shell execution by default, add tests, and update architecture/privacy docs.

---

## Final Response Expectations

When completing a task, summarize:

1. What changed.
2. Which files changed.
3. Why it changed.
4. What tests were run.
5. Risks or follow-up work.

Be honest about failures or unrun tests. Do not include API keys, secrets, private screenshots, or local private data.
