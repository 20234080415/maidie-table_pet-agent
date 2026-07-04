# Graph Report - C:\Users\85949\Desktop\桌宠\maidie\maidie_desktop_pet  (2026-07-04)

## Corpus Check
- 218 files · ~250,083 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1834 nodes · 4205 edges · 93 communities (81 shown, 12 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 437 edges (avg confidence: 0.53)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]

## God Nodes (most connected - your core abstractions)
1. `PetController` - 137 edges
2. `PetWindow` - 84 edges
3. `AIClient` - 56 edges
4. `AIRouter` - 50 edges
5. `SettingsDialog` - 49 edges
6. `Bounds` - 46 edges
7. `ToolRegistry` - 41 edges
8. `Vec2` - 37 edges
9. `CodingAgentTool` - 36 edges
10. `build_application()` - 35 edges

## Surprising Connections (you probably didn't know these)
- `AgentCoreTests` --uses--> `AIClient`  [INFERRED]
  tests/test_agent.py → ai/client.py
- `FakeMemory` --uses--> `AIClient`  [INFERRED]
  tests/test_agent.py → ai/client.py
- `FakeSearch` --uses--> `AIClient`  [INFERRED]
  tests/test_agent.py → ai/client.py
- `PlanningClient` --uses--> `AIClient`  [INFERRED]
  tests/test_agent.py → ai/client.py
- `RecordingTool` --uses--> `AIClient`  [INFERRED]
  tests/test_agent.py → ai/client.py

## Import Cycles
- None detected.

## Communities (93 total, 12 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (22): Live2DPreviewStatus, Live2DWebPreview, Check optional WebEngine without importing it during application startup., Phase-one capability probe and placeholder; it does not replace pet rendering., Return a safe runtime backend without mutating persistent configuration., resolve_animation_backend(), webengine_available(), AnimationModel (+14 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (17): AttentionManager, AttentionState, Any, datetime, EmotionState, Small decaying emotion vector, independent from Qt and animation names., Maidie's non-blocking experience layer., BehaviorDecision (+9 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (17): AtlasAnimationEngine, Path, QPixmap, Timed hatch-pet atlas backend; resizing never alters playback speed., AnimationBackend, Backend contract shared by sprite atlases and future Live2D engines., QPainter, QRectF (+9 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (10): CodingAgentProcessRunner, Any, CodingAgentTool, Any, Path, ToolResult, Read-only adapter for a local OpenCode or Codex CLI., Validate UI configuration without starting the coding CLI. (+2 more)

### Community 4 - "Community 4"
Cohesion: 0.07
Nodes (15): Any, Deprecated compatibility layer; production execution uses :mod:`core.brain`., Executes data steps. No step may produce an answer to the user., ToolExecutor, Any, ToolResult, Explicit OS operations with deny-by-default mutation controls., SystemTool (+7 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (11): QMenu, QResizeEvent, QWheelEvent, PetWindow, Path, QKeyEvent, QMouseEvent, QRect (+3 more)

### Community 6 - "Community 6"
Cohesion: 0.08
Nodes (12): Single source of truth for Maidie application identity., QDialog, _Controller, HelpAndAboutPageTests, VersionInformationTests, AboutDialog, CodingAgentConsole, HelpDialog (+4 more)

### Community 7 - "Community 7"
Cohesion: 0.07
Nodes (11): MaidieStyle, Any, The final, non-optional personality guard for every V4 response., Central prompt definitions for Maidie's production pipeline., build_personality_prompt(), ConfigStore, Any, Path (+3 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (5): PetController, Any, Translate the experience state without coupling EmotionState to UI assets., Single source of truth for state, priorities, motion and AI orchestration., Apply a user-edited fence rectangle and keep it inside the screen.

### Community 9 - "Community 9"
Cohesion: 0.10
Nodes (13): AwarenessContext, Any, Run the mandatory OCR + app + window pipeline for an explicit query., App, Client, Idle, Memory, Mouse (+5 more)

### Community 10 - "Community 10"
Cohesion: 0.08
Nodes (17): MemoryTool, Any, ToolResult, Any, ToolResult, SearchTool, build_application(), main() (+9 more)

### Community 11 - "Community 11"
Cohesion: 0.08
Nodes (7): _Clock, _Executor, FastResponseTests, _Future, _ImmediateExecutor, _Memory, _Response

### Community 12 - "Community 12"
Cohesion: 0.12
Nodes (14): DirectionManager, Update from horizontal displacement; zero preserves the last facing., Stores the pet's last meaningful horizontal facing direction., BehaviorPriority, PetState, Framework-neutral state store. Only PetController owns an instance., StateMachine, StateSnapshot (+6 more)

### Community 13 - "Community 13"
Cohesion: 0.08
Nodes (8): Chooses a brief, non-final conversational cue for an active request., ThinkingFeedbackPool, ToolResult, ScreenTool, _Client, CursorRegionTests, _Memory, VisionInteractionTests

### Community 14 - "Community 14"
Cohesion: 0.14
Nodes (4): QLabel, QLineEdit, QWidget, SettingsDialog

### Community 15 - "Community 15"
Cohesion: 0.10
Nodes (7): Connection, ConversationMemory, Any, Path, SQLite-backed recent chat and long-term user memory store., Keep retry context in memory only; it is not persisted as chat., MemorySystemTests

### Community 16 - "Community 16"
Cohesion: 0.11
Nodes (10): ActionDefinition, ActionRegistry, Any, Path, Data-driven action metadata and per-action cooldown tracking., PetGestureRecognizer, QPoint, Distinguishes horizontal head stroking from ordinary window dragging. (+2 more)

### Community 17 - "Community 17"
Cohesion: 0.16
Nodes (8): Any, The only V4 layer allowed to turn facts into words for the user., Synthesizer, build_synthesizer_prompt(), Any, OfflineClient, PersonaClient, SynthesizerTimeDeltaTests

### Community 18 - "Community 18"
Cohesion: 0.10
Nodes (8): Deprecated compatibility layer; production planning uses :mod:`core.brain`.  D, AgentCoreTests, FakeMemory, FakeSearch, PlanningClient, Compatibility tests for the deprecated core.agent AI pipeline., RecordingTool, SynthesisClient

### Community 19 - "Community 19"
Cohesion: 0.17
Nodes (6): FenceController, FenceZone, Semantic controller name retained for integration sites., Widget-free rectangular movement constraint for the whole pet window., Bounds, FenceZoneTests

### Community 20 - "Community 20"
Cohesion: 0.13
Nodes (7): IntentDetector, Any, Deterministic, high-priority intent gate for Agent Router V2., Client, Memory, RouterV2AcceptanceTests, Search

### Community 21 - "Community 21"
Cohesion: 0.13
Nodes (3): The only state transition interface in the application., Play a local head-pat reaction without spending an API request., Apply a worker result from the Qt-thread polling entry point.

### Community 22 - "Community 22"
Cohesion: 0.11
Nodes (8): OpenAICompatibleClient, Path, Ask the model for router JSON without Maidie response normalization., Extract durable, non-sensitive user memories from one exchange., Ask the configured model for a strict tool plan; never answer the task here., Reusable OpenAI-compatible backend for chat or Codex-style reasoning., AIStreamingTests, _StreamResponse

### Community 23 - "Community 23"
Cohesion: 0.15
Nodes (7): A screenshot could not be captured., VisionCaptureError, Image, Return the nearest visible non-Maidie window in desktop Z order., ScreenCapture, RegionCaptureTests, VisionScopeDetectionTests

### Community 24 - "Community 24"
Cohesion: 0.13
Nodes (7): BrainExecutor, Any, Executes planner steps and returns structured tool data only., _Memory, _OfflineClient, _ResultTool, ScreenProblemSolvingTests

### Community 25 - "Community 25"
Cohesion: 0.20
Nodes (14): fast_route(), is_coding_agent_request(), is_simple_time_query(), is_simple_weather_query(), is_weather_query(), Any, _route(), detect_vision_scope() (+6 more)

### Community 26 - "Community 26"
Cohesion: 0.14
Nodes (6): Any, VisionContext, Keeps only the latest structured visual context for short follow-ups., VisionSession, VisionContextTests, VisionSessionTests

### Community 27 - "Community 27"
Cohesion: 0.15
Nodes (6): LongResponsePanelTests, _Memory, LongResponsePanel, Any, QRect, Scrollable, personality-neutral presentation for long results.

### Community 28 - "Community 28"
Cohesion: 0.20
Nodes (6): BrainPlanner, Any, Builds deterministic data plans and never produces user-facing prose., Turn normalized router metadata into a deterministic tool plan., CodingAgentPlannerTests, TechnicalSearchRoutingTests

### Community 29 - "Community 29"
Cohesion: 0.15
Nodes (8): Deprecated compatibility layer; production routing uses :mod:`core.brain`.  Do, ConfirmationBroker, Any, Bridges worker-thread system actions to a main-thread PyQt confirmation., Deprecated compatibility layer; production orchestration uses :mod:`core.brain`., Legacy AI compatibility exports plus the active ConfirmationBroker.  Productio, Intent, build_memory_extraction_prompt()

### Community 30 - "Community 30"
Cohesion: 0.16
Nodes (9): inject_capability_context(), Attach the non-negotiable desktop-agent contract to an LLM input., AIRouter, AIResponse, Any, Agent Router V2: classify first; facts and decisions use the agent pipeline., CountingClient, CountingSearch (+1 more)

### Community 31 - "Community 31"
Cohesion: 0.19
Nodes (5): LLMIntentRouter, Any, LLM-first intent gate with regex fallback only for failures., StructuredClient, StubClient

### Community 32 - "Community 32"
Cohesion: 0.18
Nodes (7): ToolResult, A deterministic capability that never invokes a language model., Return whether this tool handles the query., Return structured data (type, raw, source), never user-facing text., Tool, Built-in tools used before search and language-model routing., Compatibility tests for the deprecated AIRouter/core.agent pipeline.

### Community 33 - "Community 33"
Cohesion: 0.16
Nodes (5): ChatStreamer, Backward-compatible name for the Experience Layer speech player., Incrementally extracts complete sentences from streamed text., SentenceSplitter, SentenceSplitterTests

### Community 34 - "Community 34"
Cohesion: 0.21
Nodes (4): CodingAnalysisFormatter, Any, Convert coding-agent facts into a neutral display structure., CodingAnalysisFormatterTests

### Community 35 - "Community 35"
Cohesion: 0.18
Nodes (4): AISessionTests, _Executor, _Future, _Memory

### Community 36 - "Community 36"
Cohesion: 0.19
Nodes (4): _Executor, _Future, _Memory, ProactiveNonblockingTests

### Community 37 - "Community 37"
Cohesion: 0.14
Nodes (6): AISessionCoordinator, Any, Logger, Owns one AI request and its paced streaming lifecycle., QObject, QTimer

### Community 38 - "Community 38"
Cohesion: 0.26
Nodes (6): NetworkPlugin, Any, NetworkPluginTests, Compatibility tests for the deprecated AIRouter; production uses core.brain., StubClient, StubSearch

### Community 39 - "Community 39"
Cohesion: 0.24
Nodes (9): The remote vision service could not be called., The vision response was not valid structured data., Base exception for the opt-in vision pipeline., Vision provider configuration is missing or invalid., VisionAPIError, VisionConfigError, VisionError, VisionParseError (+1 more)

### Community 40 - "Community 40"
Cohesion: 0.18
Nodes (4): InputManager, Continuously observes global cursor proximity and emits semantic input., _Memory, ShutdownTests

### Community 42 - "Community 42"
Cohesion: 0.29
Nodes (5): AgentCore, AIResponse, Any, Planner -> data tools -> Synthesizer pipeline., Collect desktop reality first, then let the LLM explain only that data.

### Community 43 - "Community 43"
Cohesion: 0.24
Nodes (7): IntentClassifier, Regex fallback used only when the LLM intent router fails., begin(), finish(), mark(), PerformanceTrace, Any

### Community 44 - "Community 44"
Cohesion: 0.15
Nodes (5): ProactiveEngine, Any, Observes first, then emits a throttled intent for the normal Agent pipeline., AgentV2Tests, Clock

### Community 45 - "Community 45"
Cohesion: 0.26
Nodes (6): Any, datetime, Path, Small persistent scheduler for once, cron-like, and contextual tasks., ScheduledTask, TaskScheduler

### Community 46 - "Community 46"
Cohesion: 0.19
Nodes (5): Tool, ToolResult, ToolRegistry, BrainExecutorTests, _Tool

### Community 47 - "Community 47"
Cohesion: 0.21
Nodes (7): FenceOverlayWindow, QMouseEvent, QPoint, QRect, Non-activating fence frame with a click-through center., Apply global fence coordinates; Bounds/tuples use left, top, right, bottom., Only the thin frame receives input; its center remains click-through.

### Community 48 - "Community 48"
Cohesion: 0.21
Nodes (7): Safe, optional network lookup support for Maidie., NetworkResult, Any, Search provider adapter. Version one supports Tavily., SearchService, Reserved interface for a future opt-in webpage text extractor., WebPageExtractor

### Community 49 - "Community 49"
Cohesion: 0.19
Nodes (3): _Memory, _Router, StreamingUiTests

### Community 50 - "Community 50"
Cohesion: 0.30
Nodes (3): BrainRouter, Any, Maidie Core Brain V4: the sole production gate for chat and tools.

### Community 51 - "Community 51"
Cohesion: 0.24
Nodes (5): MovementController, Target-seeking motion with acceleration, damping and edge clamping., Vec2, Logger, MovementTests

### Community 52 - "Community 52"
Cohesion: 0.22
Nodes (4): datetime, ToolResult, TimeTool, TimeToolDeltaTests

### Community 53 - "Community 53"
Cohesion: 0.18
Nodes (5): QKeyEvent, QMouseEvent, QRect, Non-blocking top-level overlay for selecting a global screen rectangle., RegionSelector

### Community 54 - "Community 54"
Cohesion: 0.20
Nodes (4): AppTracker, Identifies the foreground executable and semantic app category., ClipboardTracker, Detects clipboard changes without reading clipboard contents.

### Community 55 - "Community 55"
Cohesion: 0.19
Nodes (4): IdleDetector, Tracks inactivity without platform hooks; activity is fed by input observers., MouseTracker, Turns cursor samples into speed and active/idle semantic state.

### Community 56 - "Community 56"
Cohesion: 0.33
Nodes (6): AIClient, normalize_response(), AIResponse, Any, Recover when a model puts its JSON object inside the text field., _unwrap_nested_response()

### Community 57 - "Community 57"
Cohesion: 0.33
Nodes (3): Any, Reads and classifies the foreground window title without capturing content., WindowTracker

### Community 58 - "Community 58"
Cohesion: 0.26
Nodes (5): Any, Resolve explicit and contextual search requests without involving the LLM., ResolvedSearchQuery, SearchQueryResolver, Memory

### Community 59 - "Community 59"
Cohesion: 0.23
Nodes (4): Any, ToolResult, WeatherTool, ToolSystemTests

### Community 60 - "Community 60"
Cohesion: 0.21
Nodes (3): Apply saved UI settings while keeping environment variables authoritative., VisionService, VisionServiceTests

### Community 63 - "Community 63"
Cohesion: 0.19
Nodes (3): _ChatClient, _Memory, ScreenPipelineSafetyTests

### Community 65 - "Community 65"
Cohesion: 0.30
Nodes (3): AutonomousBehaviorController, BehaviorIntent, Plans infrequent purposeful actions instead of frame-by-frame jitter.

### Community 66 - "Community 66"
Cohesion: 0.27
Nodes (5): ProblemAnalyzer, ProblemContext, Any, Derive problem facts from VisionContext without generating a reply., Any

### Community 67 - "Community 67"
Cohesion: 0.26
Nodes (4): Any, Keeps explicit event times for immediate conversational follow-ups., ShortTermTaskContext, ShortTermTaskContextTests

### Community 68 - "Community 68"
Cohesion: 0.26
Nodes (5): Edge, EdgeResizeController, QPoint, Ask the OS window manager to resize; reliable for transparent windows., Reusable frameless-window edge resize logic.

### Community 69 - "Community 69"
Cohesion: 0.21
Nodes (4): QWidget, QMouseEvent, Small bottom-right affordance backed by the native window resizer., SubtleResizeHandle

### Community 70 - "Community 70"
Cohesion: 0.22
Nodes (3): QFocusEvent, ChatInput, QKeyEvent

### Community 71 - "Community 71"
Cohesion: 0.31
Nodes (10): import_strip(), keep_largest_component(), main(), normalize_transparency(), Image, Path, Import a chroma-key horizontal pose strip as a Maidie action row., Zero hidden RGB in fully transparent pixels to prevent scaling halos. (+2 more)

### Community 72 - "Community 72"
Cohesion: 0.47
Nodes (3): Planner, Any, Creates and validates data-gathering plans; it never answers users.

### Community 73 - "Community 73"
Cohesion: 0.27
Nodes (3): DialoguePool, Pure-Python event dialogue selector with per-event repeat avoidance., DialoguePoolTests

### Community 74 - "Community 74"
Cohesion: 0.38
Nodes (4): ProactiveDecision, ProactiveRuntime, Any, Coordinates Awareness -> Scheduler/Proactive -> Tools; UI/LLM stay in PetControl

### Community 75 - "Community 75"
Cohesion: 0.38
Nodes (5): encode_jpeg_base64(), preprocess_for_vl(), Image, resize_image(), ImagePreprocessTests

### Community 78 - "Community 78"
Cohesion: 0.33
Nodes (3): Any, QwenVLClient, QwenClientTests

### Community 80 - "Community 80"
Cohesion: 0.36
Nodes (6): BehaviorKind, Emotion, EmotionSystem, Normalizes provider output without coupling it to the UI., Enum, str

### Community 83 - "Community 83"
Cohesion: 0.38
Nodes (4): ABC, Plugin, Any, Base extension point for voice, music and system-monitor plugins.

### Community 84 - "Community 84"
Cohesion: 0.43
Nodes (3): BubbleController, Any, Owns the streaming bubble lifecycle without rebuilding its text.

### Community 85 - "Community 85"
Cohesion: 0.29
Nodes (3): NetworkClient, Any, Small requests wrapper that never lets transport errors escape.

## Knowledge Gaps
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `PetController` connect `Community 8` to `Community 10`, `Community 11`, `Community 12`, `Community 19`, `Community 21`, `Community 23`, `Community 25`, `Community 27`, `Community 33`, `Community 35`, `Community 36`, `Community 37`, `Community 40`, `Community 49`, `Community 51`, `Community 61`, `Community 65`, `Community 73`, `Community 79`, `Community 80`, `Community 81`, `Community 82`?**
  _High betweenness centrality (0.207) - this node is a cross-community bridge._
- **Why does `PetWindow` connect `Community 5` to `Community 0`, `Community 2`, `Community 6`, `Community 10`, `Community 14`, `Community 16`, `Community 19`, `Community 27`, `Community 33`, `Community 40`, `Community 41`, `Community 47`, `Community 49`, `Community 53`, `Community 61`, `Community 65`, `Community 68`, `Community 69`, `Community 70`, `Community 73`, `Community 82`, `Community 84`?**
  _High betweenness centrality (0.188) - this node is a cross-community bridge._
- **Why does `build_application()` connect `Community 10` to `Community 0`, `Community 3`, `Community 4`, `Community 5`, `Community 7`, `Community 8`, `Community 9`, `Community 13`, `Community 15`, `Community 16`, `Community 17`, `Community 22`, `Community 29`, `Community 38`, `Community 40`, `Community 44`, `Community 45`, `Community 46`, `Community 50`, `Community 52`, `Community 54`, `Community 55`, `Community 57`, `Community 59`, `Community 60`, `Community 74`, `Community 76`?**
  _High betweenness centrality (0.184) - this node is a cross-community bridge._
- **Are the 43 inferred relationships involving `PetController` (e.g. with `DirectionManager` and `AutonomousBehaviorController`) actually correct?**
  _`PetController` has 43 INFERRED edges - model-reasoned connections that need verification._
- **Are the 28 inferred relationships involving `PetWindow` (e.g. with `_Memory` and `_Router`) actually correct?**
  _`PetWindow` has 28 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `AIClient` (e.g. with `AIRouter` and `AgentCoreTests`) actually correct?**
  _`AIClient` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `AIRouter` (e.g. with `AIClient` and `Intent`) actually correct?**
  _`AIRouter` has 27 INFERRED edges - model-reasoned connections that need verification._