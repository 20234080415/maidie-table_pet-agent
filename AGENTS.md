# Maidie Engineering Rules

## Core Architecture

Maidie uses this production pipeline:

User / Proactive
→ PetController
→ BrainRouter
→ BrainPlanner
→ BrainExecutor
→ ToolRegistry
→ Synthesizer
→ UI / Animation

Do not bypass this pipeline.

## Hard Rules

1. PetController must remain a coordinator, not a God Object.
2. Do not add new business logic directly into PetController unless the task explicitly says so.
3. PyQt UI updates must only happen on the main thread.
4. OCR, network, file scanning, screenshot processing, and model calls must not run on the GUI thread.
5. Tool output must be structured data, not final user-facing text.
6. Synthesizer is the only layer allowed to generate final user-facing text.
7. Planner and LLM-generated params are untrusted.
8. SystemTool write operations must require real user confirmation.
9. Do not introduce a second AI pipeline.
10. Do not modify legacy ai/router.py or core/agent/* unless the task explicitly says legacy compatibility work.
11. Every change must include or update unittest tests.
12. After changes, run:

python -m unittest discover -v

## Forbidden

- Large cross-module rewrites without a migration plan.
- Adding new state changes through random force=True calls.
- Letting background threads touch QWidget, bubble, sprite, window, or QTimer.
- Adding new tools directly inside BrainRouter.
- Letting Router execute tool logic directly.
- Letting Planner decide security confirmation.
- Swallowing exceptions without structured error output.

## Preferred Structure

- core/brain: routing, planning, execution, synthesis
- core/tools: tool implementations
- core/experience: speech, emotion, attention, behavior
- core/proactive: proactive runtime and coordinator
- core/session: AI session lifecycle
- core/movement: movement coordination
- ui: widgets and presentation only