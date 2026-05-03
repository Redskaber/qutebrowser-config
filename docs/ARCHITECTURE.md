# Architecture Deep-Dive (v13)

> For the quick-start and overview, see [README.md](README.md).
> This document targets contributors and layer authors.

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [Module Map](#module-map)
3. [Layer System](#layer-system)
4. [Pipeline System](#pipeline-system)
5. [State Machine](#state-machine)
6. [Message Protocol](#message-protocol)
7. [Strategy & Policy System](#strategy--policy-system)
8. [Incremental Apply](#incremental-apply)
9. [Context Layer](#context-layer)
10. [Session Layer](#session-layer) ← v11
11. [Audit System](#audit-system) ← v11
12. [Metrics System](#metrics-system) ← v12
13. [ComposeLayer](#composelayer) ← v13
14. [EventFilter Middleware](#eventfilter-middleware) ← v13
15. [LayerHotSwap](#layerhotswap) ← v13
16. [ConfigValidator](#configvalidator) ← v13
17. [Health Check System](#health-check-system)
18. [Data Flow (annotated)](#data-flow-annotated)
19. [Dependency Graph](#dependency-graph)
20. [Extension Points](#extension-points)
21. [Testing Strategy](#testing-strategy)
22. [Changelog](#changelog)

---

## Design Philosophy

This config is built like a compiler front-end:

| Compiler Stage    | Config Equivalent                                        |
| ----------------- | -------------------------------------------------------- |
| Source files      | Layer `_settings()` methods                              |
| Parse + validate  | `validate()` + `ValidateStage` + `ConfigValidator` ← v13 |
| IR / AST          | `ConfigPacket`                                           |
| Optimization pass | `PipeStage` chain                                        |
| Code generation   | `ConfigApplier.apply_*()`                                |
| Linker            | `LayerStack.resolve()`                                   |
| Runtime           | qutebrowser's config API                                 |

The result: config is **data** flowing through **transforms**, not imperative Python statements scattered across a file.

### Core Principles

**Dependency Inversion** — every module depends on an abstraction, not a concrete. `LayerStack` depends on `LayerProtocol`, not `BaseLayer`.

**Single Source of Truth** — transitions live in `state.py::TRANSITIONS`. Colors live in `ColorScheme`. Host rules live in `policies/host.py`.

**Open/Closed** — adding a layer, strategy, policy, or pipeline stage never modifies existing code. Registration is the extension mechanism.

**Pure Build** — `layer.build()` and `layer.validate()` are pure functions. No side effects. Testable without a browser.

**Explicit State** — the FSM (`ConfigStateMachine`) owns all lifecycle state. No flags scattered across objects.

**Observable** — every meaningful phase emits events. Zero coupling between emitter and observer.

**Auditable** ← v11 — every config lifecycle event is recorded in a structured, queryable ring-buffer (`AuditLog`). Diagnostics, debugging, and incident investigation are first-class citizens.

**Measurable** ← v12 — telemetry is a dedicated module (`MetricsCollector`), not scattered inline. Every phase's performance is recorded, queryable, and exportable.

**Composable** ← v13 — layers can be bundled into named `ComposeLayer` units. `EventBus` is extended via chainable `EventFilter` middleware without modifying the bus. Layer replacement is surgical via `LayerHotSwap`.

**Schema-Validated** ← v13 — structural validation (`ConfigValidator`) is separated from semantic health checks (`HealthChecker`). Schema runs at build time per-layer; health runs at apply time on the merged config.

---

## Module Map

```
core/
  types.py           ← ConfigDict, Keybind  (zero-dep primitives)
  layer.py           ← LayerProtocol, LayerStack, BaseConfigLayer
  pipeline.py        ← ConfigPacket, PipeStage, Pipeline
                        + v11: ReduceStage, BranchStage, CacheStage, AuditStage
                        + v12: TeeStage, RetryStage, CompositeStage
  state.py           ← ConfigStateMachine, TRANSITIONS table
  lifecycle.py       ← LifecycleManager, LifecycleHook
  protocol.py        ← EventBus, CommandBus, QueryBus, typed messages
                        + v12: GetMetricsSummaryQuery
  strategy.py        ← Policy, PolicyChain, StrategyRegistry
  health.py          ← HealthCheck, HealthChecker, 21 built-in checks
  incremental.py     ← ConfigSnapshot, ConfigDiffer, IncrementalApplier
  audit.py           ← AuditLog, AuditEntry, AuditFilter, AuditLevel  ← v11
  metrics.py         ← MetricsCollector, MetricsSample, PhaseTimer     ← v12
  compose.py         ← ComposeLayer, compose(), LayerCompositionError  ← v13
  event_filter.py    ← EventFilter, Middleware, MiddlewareChain        ← v13
  hot_swap.py        ← LayerHotSwap, HotSwapResult                    ← v13
  hot_swap_events.py ← LayerSwappedEvent                              ← v13
  validator.py       ← ConfigValidator, FieldSpec, SchemaRegistry      ← v13

layers/
  base.py        [p=10]   foundational defaults, search engines
  privacy.py     [p=20]   security & tracking protection
  appearance.py  [p=30]   themes, fonts, colors
  behavior.py    [p=40]   UX, keybindings, per-host rules
  context.py     [p=45]   situational mode (work/research/media/dev/…)
  performance.py [p=50]   cache & rendering tuning
  session.py     [p=55]   time-aware session (day/evening/night/…)  ← v11
  user.py        [p=90]   personal overrides (always wins)

orchestrator.py     ← composition root: wires all modules
config.py           ← qutebrowser entry point (edit CONFIGURATION SECTION only)
```

---

## Layer System

Each layer:

1. Declares a unique `name` and integer `priority`
2. Implements `_settings() → ConfigDict`
3. Optionally implements `_keybindings()`, `_aliases()`
4. Optionally provides a `pipeline()` for post-processing

`LayerStack.resolve()` merges in priority order (lowest first). Higher priority layers override lower-priority keys.

### Priority Table

| Layer       | Priority | Purpose                             |
| ----------- | -------- | ----------------------------------- |
| base        | 10       | Foundational defaults               |
| privacy     | 20       | Security & tracking protection      |
| appearance  | 30       | Theme, fonts, colors                |
| behavior    | 40       | UX, keybindings, per-host rules     |
| context     | 45       | Situational mode overrides          |
| performance | 50       | Cache & rendering tuning            |
| session     | **55**   | Time-aware mode (day/night/…) ← v11 |
| compose     | **60+**  | Named layer bundles ← v13           |
| _(custom)_  | 60–80    | Recommended range for user layers   |
| user        | 90       | Personal overrides (always wins)    |

**Layer interaction: session vs. context vs. user:**

- `context` (p=45) sets _which sites_ you visit and their search engines.
- `session` (p=55) sets _how the browser behaves_ — zoom, font density, chrome visibility.
- `user` (p=90) overrides both; `USER_ZOOM`, `USER_FONT_SIZE_WEB` beat session values.

### LayerStack API

```python
stack = LayerStack()
stack.register(MyLayer(), enabled=True, tags=["custom"])

stack.enable("my_layer")        # re-enable a disabled layer
stack.disable("my_layer")       # disable without removing
stack.get("my_layer")           # → Optional[LayerProtocol]
stack.layers()                  # → Iterator[LayerProtocol]
stack.resolve()                 # → Dict[name, ConfigPacket]  (triggers merge)
stack.merged                    # → ConfigDict  (after resolve())
stack.summary()                 # → str (human-readable priority table)
```

### Deep merge semantics

`LayerStack._deep_merge()` rules (by key type):

| Value type                          | Rule                                                 |
| ----------------------------------- | ---------------------------------------------------- |
| `dict`                              | Recurse — all layers contribute nested keys          |
| `list` at top-level `"keybindings"` | Accumulate (extend) — all layers' bindings collected |
| `list` inside `"settings"`          | Replace — higher priority wins outright              |
| scalar                              | Replace — higher priority wins                       |

---

## Pipeline System

Config data flows as `ConfigPacket` through composable `PipeStage` chains.

```
ConfigSource → [Transform] → [Validate] → [Merge] → ConfigSink
```

### ConfigPacket

```python
@dataclass
class ConfigPacket:
    source:   str            # e.g. "layer:base"
    data:     ConfigDict     # the settings delta
    errors:   List[str]      # accumulate per-stage
    warnings: List[str]
    meta:     Dict[str, Any] # stage-level side-channel data

    # Constructors
    .with_errors(msgs)    → ConfigPacket   # bulk-add errors (immutable copy)
    .with_warnings(msgs)  → ConfigPacket
```

### Stage reference (all versions)

| Stage            | Since | Description                                                    |
| ---------------- | ----- | -------------------------------------------------------------- |
| `LogStage`       | v1    | Log packet contents at DEBUG                                   |
| `ValidateStage`  | v1    | Assert key→predicate constraints; add errors on failure        |
| `TransformStage` | v1    | Apply `fn: ConfigDict → ConfigDict`                            |
| `FilterStage`    | v1    | Keep only keys matching `predicate(k, v)`                      |
| `MergeStage`     | v1    | Deep-merge a static dict into the packet                       |
| `ReduceStage`    | v11   | Fold `(acc, k, v)`; result stored in `packet.meta[result_key]` |
| `BranchStage`    | v11   | Conditional routing to true/false sub-pipelines                |
| `CacheStage`     | v11   | Memoize inner stage on SHA-1 content hash; `invalidate()`      |
| `AuditStage`     | v11   | Record passage to `AuditLog`; zero-cost at DEBUG level         |
| `TeeStage`       | v12   | Fan-out: observer sees packet; main flow continues unchanged   |
| `RetryStage`     | v12   | Retry inner stage up to N times; warnings on each failure      |
| `CompositeStage` | v12   | Wrap sub-pipeline as a single named stage                      |

### Pipeline API

```python
p = (
    Pipeline("my-pipeline")
    .pipe(ValidateStage({...}))
    .pipe(TransformStage(fn, "label"))
    .pipe(LogStage("post"))
)

result = p.run(packet)    # → ConfigPacket
p.describe()              # → "my-pipeline: validate → transform:label → log:post"
p.fork()                  # → independent copy
for stage in p:           # iterate stages
    ...

# Two-stage sugar
combined = LogStage("pre") + ValidateStage({...})
```

---

## State Machine

`ConfigStateMachine` owns all lifecycle state. Transitions are pure data in `TRANSITIONS`.

```
IDLE
  └─ START_LOAD     → LOADING
       └─ LOAD_DONE      → VALIDATING
       └─ LOAD_FAIL       → ERROR

VALIDATING
  └─ VALIDATE_DONE  → APPLYING
  └─ VALIDATE_FAIL  → ERROR

APPLYING
  └─ APPLY_DONE     → ACTIVE
  └─ APPLY_FAIL     → ERROR

ACTIVE
  └─ RELOAD         → RELOADING
       └─ LOAD_DONE      → VALIDATING   (resumes normal path)

ERROR
  └─ RESET          → IDLE
```

```python
fsm = ConfigStateMachine()
fsm.send(ConfigEvent.START_LOAD)   # triggers transition
print(fsm.state)                   # ConfigState.LOADING
print(fsm)                         # "ConfigStateMachine[LOADING]"
```

---

## Message Protocol

Three buses wired behind `MessageRouter`. No module imports another directly.

```
MessageRouter
  ├── EventBus    — fire-and-forget pub/sub
  │     └── [EventFilter middleware chain]  ← v13
  ├── CommandBus  — exactly one handler; may fail
  └── QueryBus    — request/response; exactly one handler
```

### Typed Events

| Event                    | Since | Trigger                                      |
| ------------------------ | ----- | -------------------------------------------- |
| `LayerAppliedEvent`      | v1    | After each layer is applied                  |
| `ConfigErrorEvent`       | v1    | On apply error                               |
| `ThemeChangedEvent`      | v5    | When theme changes                           |
| `ContextSwitchedEvent`   | v6    | When context switches                        |
| `HealthReportReadyEvent` | v5    | After health check run                       |
| `ConfigReloadedEvent`    | v9    | After hot-reload completes                   |
| `SnapshotTakenEvent`     | v9    | When `IncrementalApplier` records a snapshot |
| `LayerConflictEvent`     | v9    | When a key override occurs during merge      |
| `PolicyDeniedEvent`      | v9    | When a `PolicyChain` DENY fires              |
| `MetricsEvent`           | v9    | After each build/apply/reload phase          |
| `LayerSwappedEvent`      | v13   | After a `LayerHotSwap` operation completes   |

### Typed Queries

| Query                    | Since | Returns                      |
| ------------------------ | ----- | ---------------------------- |
| `GetMergedConfigQuery`   | v5    | `Dict[str, Any]`             |
| `GetHealthReportQuery`   | v5    | `Optional[HealthReport]`     |
| `GetSnapshotQuery`       | v9    | `Optional[ConfigSnapshot]`   |
| `GetLayerDiffQuery`      | v9    | `List[ConfigChange]`         |
| `GetLayerNamesQuery`     | v9    | `List[str]` (priority order) |
| `GetMetricsSummaryQuery` | v12   | `str` (formatted table)      |

### MessageRouter convenience emitters

```python
router.emit_health(ok, error_count, warning_count, info_count)
router.emit_reload(changes_count, errors_count, duration_ms, reason)
router.emit_snapshot(label, key_count, version)
router.emit_conflict(key, winner_layer, loser_layer)
router.emit_policy_denied(key, value, reason, layer_name)
router.emit_metrics(phase, duration_ms, key_count)
```

---

## Strategy & Policy System

`core/strategy.py` provides composable strategies and policies.

### StrategyRegistry

```python
registry: StrategyRegistry[T] = StrategyRegistry(default=MyDefaultStrategy())
registry.register(MyStrategy())
result: T = registry.apply("my_strategy", context_dict)
```

### PolicyChain

Each `Policy` returns `Optional[PolicyDecision]`:

```
PolicyAction.ALLOW   — pass through
PolicyAction.MODIFY  — rewrite value; apply modified
PolicyAction.WARN    — log warning; apply original
PolicyAction.DENY    — skip key; emit PolicyDeniedEvent
```

Policies run in ascending `priority` order. First non-None decision wins.

---

## Incremental Apply

`core/incremental.py` — diff-only hot-reload for settings.

```
SnapshotStore      — capped history of ConfigSnapshot objects (default: 10)
ConfigDiffer       — static diff(old, new) → List[ConfigChange]
IncrementalApplier — wraps SnapshotStore; record() + compute_delta() + apply_delta()

ConfigChange
  key:       str
  kind:      ChangeKind  (ADDED | CHANGED | REMOVED | SAME)
  old_value: Any
  new_value: Any
```

On hot-reload:

1. Snapshot current merged config (`"pre-reload"`)
2. Rebuild all layers
3. Snapshot new merged config (`"post-reload"`)
4. `compute_delta()` → only ADDED + CHANGED keys
5. `apply_delta(changes, apply_fn)` → write only those keys

---

## Context Layer

`layers/context.py` — Priority 45

A context is a named situation with its own search engines, behavioral overrides, and keybindings.

```
ContextMode  DEFAULT | WORK | RESEARCH | MEDIA | DEV | WRITING | GAMING

Resolution order (highest wins):
  1. constructor ``context`` param  (from config.py ACTIVE_CONTEXT)
  2. QUTE_CONTEXT environment variable
  3. ~/.config/qutebrowser/.context  (written by context_switch.py)
  4. ContextMode.DEFAULT fallback
```

**Runtime keybindings** (`,C` prefix):

| Key    | Context  | Purpose                                |
| ------ | -------- | -------------------------------------- |
| `,Cw`  | work     | Jira, GitLab, corporate search         |
| `,Cr`  | research | arXiv, Scholar, Wikipedia              |
| `,Cm`  | media    | YouTube, Bilibili, autoplay ON         |
| `,Cd`  | dev      | GitHub, MDN, crates, npm, DevDocs      |
| `,Cwt` | writing  | Dict, Thesaurus, Grammarly, focus mode |
| `,Cg`  | gaming   | Steam, Twitch, ProtonDB                |
| `,C0`  | default  | Reset to base defaults                 |
| `,Ci`  | —        | Show current context in message bar    |

---

## Session Layer

`layers/session.py` — Priority 55 ← v11

A session is a time/situation slot that adjusts zoom, font size, and chrome visibility.

```
SessionMode  AUTO | DAY | EVENING | NIGHT | FOCUS | COMMUTE | PRESENT

Resolution order (highest wins):
  1. constructor ``session`` param  (from config.py ACTIVE_SESSION)
  2. QUTE_SESSION environment variable
  3. ~/.config/qutebrowser/.session  (written by session_switch.py)
  4. SessionMode.AUTO → derived from datetime.now().hour
```

**Defaults per mode:**

| Mode    | Hours       | zoom | font px | chrome                           |
| ------- | ----------- | ---- | ------- | -------------------------------- |
| DAY     | 08:00–18:00 | 100% | 16      | full                             |
| EVENING | 18:00–22:00 | 105% | 18      | full                             |
| NIGHT   | 22:00–06:00 | 110% | 20      | statusbar=in-mode, tabs=multiple |
| FOCUS   | (manual)    | 100% | 18      | statusbar=never, tabs=never      |
| COMMUTE | (manual)    | 100% | 16      | images=off, autoplay=off         |
| PRESENT | (manual)    | 125% | 22      | full                             |

**Runtime keybindings** (`,S` prefix):

| Key   | Mode         |
| ----- | ------------ |
| `,Sd` | day          |
| `,Se` | evening      |
| `,Sn` | night        |
| `,Sf` | focus        |
| `,Sc` | commute      |
| `,Sp` | present      |
| `,S0` | auto         |
| `,Si` | show current |

---

## Audit System

`core/audit.py` ← v11

```
AuditLevel  DEBUG < INFO < WARN < ERROR

AuditEntry (frozen dataclass)
  ts:        datetime (UTC)
  level:     AuditLevel
  component: str
  message:   str
  meta:      Dict[str, Any]
  seq:       int  (monotonic session-wide)

AuditLog (thread-safe ring buffer, capacity=512)
  record(level, component, message, **meta) → AuditEntry
  query(flt?)                  → List[AuditEntry]
  last_n(n, flt?)              → List[AuditEntry]
  errors()                     → List[AuditEntry]
  warnings_and_above()         → List[AuditEntry]
  export_text(flt?)            → str
  export_json(flt?)            → str (JSON array)
  export_markdown(flt?)        → str (Markdown table)
  summary(last_n)              → str

AuditFilter (composable predicate)
  level_min, level_max, component, message_contains, since_seq
  .matches(entry) → bool
  .errors_and_warnings() — classmethod
  .errors_only()         — classmethod

Global singleton:
  get_audit_log()    → AuditLog
  reset_audit_log()  → AuditLog  (for tests)

Module helpers:
  audit_debug(component, message, **meta)
  audit_info(component, message, **meta)
  audit_warn(component, message, **meta)
  audit_error(component, message, **meta)
```

The `AuditLog` is a **zero-coupling side channel**: components record into it independently. Consumed by `scripts/diagnostics.py audit` and `orchestrator.audit_trail()`.

---

## Metrics System

`core/metrics.py` ← v12

Extracts `_last_metrics: Dict[str, float]` from `ConfigOrchestrator` into a dedicated, composable module (SRP).

```
MetricsSample (frozen dataclass)
  phase:       str    — "build" | "apply" | "reload" | "host_policies"
  duration_ms: float
  key_count:   int
  timestamp:   UTC datetime
  meta:        Dict[str, Any]

PhaseTimer  (context manager)
  with PhaseTimer() as t:
      ...work...
  ms = t.elapsed_ms

MetricsCollector  (thread-safe ring buffer, capacity=128)
  emit(phase, duration_ms, key_count, **meta) → MetricsSample
  get(phase)            → Optional[MetricsSample]  (latest)
  last_n(n)             → List[MetricsSample]
  iter_phase(phase)     → Iterator[MetricsSample]
  all_phases()          → List[str]
  totals_by_phase()     → Dict[str, float]
  summary(last_n)       → str
  on_emit(callback)     → self  (fluent)
  clear()

Module singleton:
  get_metrics_collector()   → MetricsCollector
  reset_metrics_collector() → MetricsCollector  (for tests)

Convenience:
  with metrics_time() as t:
      ...
  collector.emit("phase", t.elapsed_ms)
```

**Orchestrator integration:**

```python
# __init__:
self._metrics = MetricsCollector(capacity=64)
self._metrics.on_emit(
    lambda ph, ms, n: self._router.emit_metrics(phase=ph, duration_ms=ms, key_count=n)
)

# In build():
self._emit_metrics("build", duration_ms, key_count=n_sets, layer_count=n)
```

**Query via QueryBus:**

```python
summary = router.ask(GetMetricsSummaryQuery(last_n=10))
# → "Metrics (last 10 samples):\n  [14:32:01] build  2.3ms  keys=47\n  ..."
```

**Zero-import policy** — `core/metrics.py` does not import from any other project module.

---

## ComposeLayer

`core/compose.py` ← v13

Bundles N layers into one named priority slot.

```
ComposeLayer("situation", priority=57)
  ├─ ContextLayer("dev",   p=45)  ← child
  └─ SessionLayer("focus", p=55)  ← child
```

Internally runs a mini-stack merge of its children in priority order. Presents a single delta to the outer `LayerStack`.

### API

```python
from core.compose import ComposeLayer, compose

# Constructor
cl = ComposeLayer("bundle", priority=60, children=[LayerA(), LayerB()])

# Fluent builder
cl = ComposeLayer("bundle", priority=60).add(LayerA()).add(LayerB())

# Factory shorthand
cl = compose("bundle", LayerA(), LayerB(), priority=60, description="...")

# Inspection
cl.name            # "bundle"
cl.priority        # 60
cl.child_names()   # ["a", "b"]  (priority order)
cl.describe()      # multi-line summary
cl.remove("a")     # returns self
```

### Composition rules

- Duplicate child names raise `LayerCompositionError`
- A child may not share the name of its parent
- `ComposeLayer` implements `LayerProtocol` fully — can be nested, hot-swapped, or registered in any `LayerStack`
- Child `build()` exceptions are caught and logged; that child is skipped
- `pipeline()` returns `None` (the compose-level pipeline is applied inside `build()`)

### Pattern

Composite (GoF) + Decorator (pipeline wrapping) + Template Method (`build()` always runs children).

---

## EventFilter Middleware

`core/event_filter.py` ← v13

Adds composable middleware to `EventBus` without modifying it.

```
producer.publish(event)
    ↓
EventFilter.publish(event)
    ↓
MiddlewareChain[0] → … → MiddlewareChain[N] → EventBus.publish(event)
```

`EventFilter` is a drop-in `EventBus` replacement. All `subscribe*` calls delegate to the wrapped bus. Only `publish()` is intercepted.

### Wiring

```python
from core.event_filter import EventFilter, LoggingMiddleware, DedupeMiddleware

router.events = (
    EventFilter(router.events)
    .use(LoggingMiddleware())
    .use(DedupeMiddleware(ttl=0.1))
)
```

### Built-in Middleware

| Class                | Behaviour                                                      |
| -------------------- | -------------------------------------------------------------- |
| `LoggingMiddleware`  | DEBUG-log every event (or a specific type only)                |
| `DedupeMiddleware`   | Suppress duplicate topic within TTL window (thread-safe)       |
| `ThrottleMiddleware` | Rate-limit event type to N per second                          |
| `FilterMiddleware`   | Pass only events matching a predicate                          |
| `AuditMiddleware`    | Record every event to `AuditLog` at DEBUG                      |
| `CountingMiddleware` | Count events by topic; `.count(topic)`, `.total()`, `.reset()` |

### Custom middleware

```python
from core.event_filter import Middleware
from core.protocol import Event

class MyMiddleware(Middleware):
    def __call__(self, event: Event, next_fn) -> int:
        # side-effect, transform, or block
        return next_fn(event)   # always call next_fn unless blocking
```

### Pattern

Chain of Responsibility (`MiddlewareChain`) + Decorator (`EventFilter` wraps `EventBus`) + Strategy (each `Middleware`).

---

## LayerHotSwap

`core/hot_swap.py` ← v13

Surgical layer replacement: applies only the diff between old and new merged configs — no full `:config-source` reload.

```
hot_swap.swap("context", ContextLayer("research"))
    ↓  1. snapshot merged["settings"] BEFORE
    ↓  2. replace layer record in LayerStack
    ↓  3. stack.resolve()
    ↓  4. snapshot merged["settings"] AFTER
    ↓  5. ConfigDiffer.diff(before, after) → changes
    ↓  6. apply_fn(key, value) for each ADDED/CHANGED key
    ↓  7. router.emit(LayerSwappedEvent(...))
    → HotSwapResult(operation="swap", layer_name="context",
                    changes=3, errors=[], duration_ms=0.4)
```

### API

```python
from core.hot_swap import LayerHotSwap

hs = LayerHotSwap(
    stack    = orchestrator._stack,
    apply_fn = lambda k, v: applier.apply_settings({k: v}),
    router   = router,   # optional — for LayerSwappedEvent
)

result = hs.swap("context", ContextLayer("research"))
result = hs.remove("session")
result = hs.insert(MyNewLayer())

result.ok           # True if no errors
result.changes      # int: keys written
result.duration_ms  # float: wall-clock time
str(result)         # "HotSwap[swap:context] changes=3 OK 0.4ms"
```

### HotSwapResult

```python
@dataclass(frozen=True)
class HotSwapResult:
    operation:   str        # "swap" | "remove" | "insert"
    layer_name:  str
    changes:     int
    errors:      List[str]
    duration_ms: float

    @property
    def ok(self) -> bool: ...
```

### LayerSwappedEvent

```python
@dataclass(frozen=True)
class LayerSwappedEvent(Event):
    operation:  str   # "swap" | "remove" | "insert"
    layer_name: str
    changes:    int
    errors:     int   # count of apply errors
```

### Pattern

Command (each swap is a reversible operation) + Memento (snapshot before swap) + Strategy (`apply_fn` injected).

---

## ConfigValidator

`core/validator.py` ← v13

Separates **structural schema validation** (build time, per-layer) from **semantic health checks** (`core/health.py`, apply time, merged config).

| Module         | When       | What                                             |
| -------------- | ---------- | ------------------------------------------------ |
| `validator.py` | Build time | Type, range, pattern, choices, custom function   |
| `health.py`    | Apply time | Proxy format, BCP-47 tags, editor placeholder, … |

### FieldSpec

```python
@dataclass(frozen=True)
class FieldSpec:
    type_:       Optional[type | tuple[type, ...]] = None
    required:    bool                               = False
    choices:     Optional[Set[Any]]                 = None
    min_:        Optional[float]                    = None
    max_:        Optional[float]                    = None
    pattern:     Optional[str]                      = None   # re.search
    custom:      Optional[Callable[[Any], str|None]]= None
    description: str                                = ""
```

### ConfigValidator

```python
result = ConfigValidator(schema, strict=False).validate(settings_dict)
result.ok         # bool
result.errors     # List[str]
result.warnings   # List[str]
str(result)       # human-readable
result.merge(other)  # combine two results
```

### COMMON_SCHEMA

`COMMON_SCHEMA` is a partial schema for 15+ frequently configured keys:

```
content.javascript.enabled   bool
content.blocking.enabled     bool
content.autoplay             bool
content.cookies.accept       str, choices={"all","no-3rdparty",…}
content.webrtc_ip_handling_policy  str, choices={…}
content.proxy                str, custom=scheme check
zoom.default                 str, pattern=r"^\d+%$"
fonts.default_family         str
fonts.default_size           str, pattern=r"^\d+(pt|px)$"
fonts.web.size.default       int, min=1, max=200
fonts.web.size.minimum       int, min=0, max=100
tabs.position                str, choices={"top","bottom","left","right"}
tabs.show                    str, choices={…}
downloads.location.prompt    bool
messages.timeout             int, min=0
spellcheck.languages         list
editor.command               list, custom=placeholder check
```

### SchemaRegistry

```python
reg = get_schema_registry()
reg.register("my_layer", {"my_key": FieldSpec(type_=int)})
reg.extend("my_layer", {"other_key": FieldSpec(type_=str)})
result = reg.validate_all(merged_settings)
reset_schema_registry()   # for tests
```

### Zero-import policy

`core/validator.py` does not import from any other project module.

---

## Health Check System

`core/health.py`

Validates the fully-merged settings dict after `build()` and before or during `apply()`. Catches operational misconfiguration that the schema cannot detect (BCP-47 validity, proxy host:port format, etc.).

```
HealthCheck (ABC)  — push model: run(settings, report)
HealthReport       — collects HealthIssue objects
HealthIssue        — severity (INFO | WARNING | ERROR) + message
HealthChecker      — runs a set of checks; HealthChecker.default() has all 21
```

**Built-in checks (21 total, v9.1):**

`BlockingEnabledCheck`, `BlockingListCheck`, `SearchEngineDefaultCheck`,
`SearchEngineUrlCheck`, `WebRTCPolicyCheck`, `CookieAcceptCheck`,
`StartPageCheck`, `EditorCommandCheck`, `DownloadDirCheck`,
`TabTitleFormatCheck`, `ProxySchemeCheck`, `ZoomDefaultCheck`,
`FontFamilyCheck`, `SpellcheckLangCheck`, `ContentHeaderCheck`,
`SearchEngineCountCheck`, `ProxySchemeDetailCheck`, `DownloadPromptCheck`

**Factory:**

```python
checker = HealthChecker.default()          # all 21 built-in checks
checker = HealthChecker.with_checks(A(), B())  # targeted subset
report  = checker.check(merged_settings)
report.ok           # bool
report.errors       # List[HealthIssue]  (ERROR severity)
report.warnings     # List[HealthIssue]  (WARNING severity)
report.infos        # List[HealthIssue]  (INFO severity)
report.summary()    # str
```

---

## Data Flow (annotated)

```
qutebrowser forks Python → loads config.py
    │
    ├─ sys.path.insert(0, config_dir)
    │
    └─ _build_orchestrator()
           ├─ MessageRouter()
           │     └─ [EventFilter middleware wired here]  ← v13 optional
           ├─ LifecycleManager()
           ├─ ConfigStateMachine()
           ├─ build_default_host_registry(...)
           └─ LayerStack()
                 ├─ register(BaseLayer())           [p=10]
                 ├─ register(PrivacyLayer())         [p=20]
                 ├─ register(AppearanceLayer())      [p=30]
                 ├─ register(BehaviorLayer())        [p=40]
                 ├─ register(ContextLayer())         [p=45]
                 ├─ register(PerformanceLayer())     [p=50]
                 ├─ register(SessionLayer())         [p=55]  ← v11
                 ├─ register(ComposeLayer(...))      [p=60+] ← v13 optional
                 └─ register(UserLayer())            [p=90]

orchestrator.build()
    ├─ fsm.send(START_LOAD) → IDLE→LOADING
    ├─ lifecycle.run(PRE_INIT)
    ├─ stack.resolve()
    │     for each layer (priority order):
    │       layer.build()     → ConfigPacket
    │       layer.validate()  → errors
    │       pipe = layer.pipeline()
    │       if pipe: packet = pipe.run(packet)
    │       _merged = deep_merge(_merged, packet.data)
    ├─ fsm.send(LOAD_DONE) → LOADING→VALIDATING
    ├─ fsm.send(VALIDATE_DONE) → VALIDATING→APPLYING
    ├─ lifecycle.run(POST_INIT)
    ├─ router.emit_metrics("build", ...)
    └─ audit.record("build", "layers resolved", ...)

orchestrator.apply(applier)
    ├─ lifecycle.run(PRE_APPLY)
    ├─ applier.apply_settings(merged["settings"], policy_chain, router)
    │     per key: policy_chain.evaluate(key, value) → decision
    │       ALLOW  → config.set(key, value)
    │       MODIFY → config.set(key, modified_value)
    │       WARN   → log + config.set(key, value)
    │       DENY   → skip + router.emit(PolicyDeniedEvent)
    ├─ applier.apply_keybindings(merged["keybindings"])
    ├─ applier.apply_aliases(merged["aliases"])
    ├─ HealthChecker.default().check(settings) → HealthReport
    ├─ router.emit_health(ok, errors, warnings, infos)
    ├─ lifecycle.run(POST_APPLY)
    ├─ fsm.send(APPLY_DONE) → APPLYING→ACTIVE
    ├─ router.emit_metrics("apply", ...)
    └─ audit.record("apply", "complete", ...)

orchestrator.apply_host_policies(applier)
    ├─ HostPolicyRegistry.active() → [HostRule]
    │     config.set(k, v, pattern=rule.pattern)
    ├─ BehaviorLayer.host_policies() (non-duplicate patterns only)
    ├─ router.emit_metrics("host_policies", ...)
    └─ audit.record("host_policies", f"{n} rules", ...)

orchestrator.reload(applier)
    ├─ fsm.send(RELOAD) → ACTIVE→RELOADING
    ├─ lifecycle.run(PRE_RELOAD)
    ├─ incremental_applier.record(current, "pre-reload")
    ├─ orchestrator.build()
    ├─ incremental_applier.record(new, "post-reload")
    ├─ changes = incremental_applier.compute_delta()
    ├─ incremental_applier.apply_delta(changes, apply_fn)
    ├─ applier.apply_keybindings(...)
    ├─ applier.apply_aliases(...)
    ├─ orchestrator.apply_host_policies(applier)
    ├─ router.emit_reload(changes, errors, ms)
    ├─ router.emit_metrics("reload", ...)
    ├─ audit.record("reload", f"{n} changes", ...)
    └─ lifecycle.run(POST_RELOAD)

hot_swap.swap(name, new_layer)                    ← v13
    ├─ snapshot before (merged["settings"])
    ├─ replace/insert layer in LayerStack
    ├─ stack.resolve()
    ├─ snapshot after (merged["settings"])
    ├─ ConfigDiffer.diff(before, after)
    ├─ apply_fn(key, value) for ADDED/CHANGED keys
    └─ router.emit(LayerSwappedEvent(...))
```

---

## Dependency Graph

```
core/types.py          (zero project-level deps)
core/audit.py          (zero project-level deps)
core/validator.py      (zero project-level deps; imports core.types)  ← v13
     ↑
core/layer.py   keybindings/catalog.py
     ↑
core/pipeline.py ←→ core/audit.py (optional, guarded try/except)
core/state.py
core/lifecycle.py
core/protocol.py
core/strategy.py
core/health.py
core/incremental.py
core/metrics.py        (zero project-level deps; callback-injected)
core/compose.py        (imports core.layer, core.pipeline)            ← v13
core/event_filter.py   (imports core.protocol)                        ← v13
core/hot_swap.py       (imports core.layer, core.incremental)         ← v13
core/hot_swap_events.py(imports core.protocol)                        ← v13
     ↑
orchestrator.py
     ↑
config.py
```

**Invariants (enforced, never violate):**

- `layers/*` never imports from `layers/*`
- `core/*` never imports from `layers/*` or `strategies/*`
- `core/audit.py`, `core/types.py`, `core/metrics.py`, `core/validator.py` have zero project-level imports
- All `core/audit` references in `orchestrator.py` are wrapped in `try/except ImportError`
- `core/hot_swap_events.py` kept separate from `core/hot_swap.py` to avoid circular imports

---

## Extension Points

### Add a Layer

```python
# layers/work.py
from core.layer import BaseConfigLayer
from core.types import ConfigDict, Keybind
from typing import List

class WorkLayer(BaseConfigLayer):
    name        = "work"
    priority    = 60
    description = "Corporate intranet search and shortcuts"

    def __init__(self, leader: str = ",") -> None:
        self._leader = leader

    def _settings(self) -> ConfigDict:
        return {
            "url.searchengines": {
                "DEFAULT": "https://intranet.corp/?q={}",
                "jira":    "https://jira.corp/issues/?jql=text+~+{}",
            },
        }

    def _keybindings(self) -> List[Keybind]:
        L = self._leader
        return [(f"{L}wi", "open https://intranet.corp", "normal")]
```

Register in `config.py`'s `_build_orchestrator()`:

```python
if LAYERS.get("work"):
    stack.register(WorkLayer(leader=LEADER_KEY))
```

**Layer author rules:**

- `build()` must be **pure** — no `config.set()`, no I/O, no side effects
- Never import from another `layers/*` module
- Always accept and honour the `leader` parameter
- Priority 60–80 is the recommended range for custom layers

### Add a ComposeLayer ← v13

```python
from core.compose import compose
from layers.context import ContextLayer
from layers.session import SessionLayer

dev_focus = compose(
    "dev_focus",
    ContextLayer("dev"),
    SessionLayer("focus"),
    priority = 57,
    description = "Dev work in focus mode",
)
stack.register(dev_focus)
```

### Add a Session Mode

```python
# In layers/session.py:

class SessionMode(str, Enum):
    ...
    READING = "reading"   # 1. extend enum

_SESSION_TABLE[SessionMode.READING] = SessionSpec(   # 2. add spec
    mode        = SessionMode.READING,
    description = "Reading — large font, minimal chrome",
    settings_delta = {
        "fonts.web.size.default": 22,
        "zoom.default":           "115%",
        "statusbar.show":         "in-mode",
        "tabs.show":              "multiple",
    },
    zoom_hint = "115%",
)

# 3. Add keybinding in _keybindings():
# (f"{L}Sr", "spawn --userscript session_switch.py reading", "normal"),

# 4. Add to session_switch.py VALID_SESSIONS
```

### Add a Context Mode

```python
# In layers/context.py:

class ContextMode(str, Enum):
    ...
    SCIENCE = "science"   # 1. extend enum

_CONTEXT_TABLE[ContextMode.SCIENCE] = ContextSpec(   # 2. add spec
    mode        = ContextMode.SCIENCE,
    description = "Science — arXiv, PubMed, NCBI",
    search_engines = {
        "DEFAULT": "https://pubmed.ncbi.nlm.nih.gov/?term={}",
        "arxiv":   "https://arxiv.org/search/?searchtype=all&query={}",
        "ncbi":    "https://www.ncbi.nlm.nih.gov/search/research-articles/?term={}",
    },
    settings_delta = {
        "content.autoplay":              False,
        "content.notifications.enabled": False,
    },
)
# 3. Add ,Cs keybinding in _keybindings()
```

### Add a Per-Host Rule

```python
# In policies/host.py:

HostRule(
    pattern     = "*.mycompany.com",
    settings    = {
        "content.javascript.enabled": True,
        "content.cookies.accept":     "all",
    },
    description = "Corporate intranet — JS + cookies required",
    category    = "work",
    enabled     = True,
)
```

### Add a Health Check

```python
from core.health import HealthCheck, HealthReport
from core.types import ConfigDict

class MyCheck(HealthCheck):
    @property
    def name(self) -> str:
        return "my_check"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        if settings.get("my.key") == "bad_value":
            report.add(self._error("my.key must not be 'bad_value'"))
        elif settings.get("my.key") == "suboptimal":
            report.add(self._warning("my.key: prefer a different value"))

# Inject for one run:
checker = HealthChecker.default()
report  = checker.check(settings)

# Compose a targeted subset:
checker = HealthChecker.with_checks(MyCheck())
```

### Add a Policy

```python
from core.strategy import Policy, PolicyDecision, PolicyAction

class BlockTrackerPolicy(Policy):
    name     = "block_tracker"
    priority = 30

    def evaluate(self, key, value, context):
        if key == "content.blocking.enabled" and value is False:
            return PolicyDecision(
                action        = PolicyAction.DENY,
                reason        = "blocking must stay enabled",
                modified_value= None,
            )
        return None
```

### Add a Lifecycle Hook

```python
from core.lifecycle import LifecycleHook

@lifecycle.decorator(LifecycleHook.POST_APPLY, priority=50)
def _on_applied() -> None:
    audit_info("my-hook", "POST_APPLY ran")

_ = _on_applied   # suppress Pyright reportUnusedFunction
```

### Add a Pipeline Stage

```python
from core.pipeline import PipeStage, ConfigPacket

class StripDebugKeysStage(PipeStage):
    @property
    def name(self) -> str:
        return "strip-debug"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        clean = {k: v for k, v in packet.data.items()
                 if not k.startswith("debug.")}
        return ConfigPacket(source=packet.source, data=clean,
                            errors=packet.errors, warnings=packet.warnings)
```

### Add an Event Middleware ← v13

```python
from core.event_filter import EventFilter, Middleware
from core.protocol import Event

class SlackNotifyMiddleware(Middleware):
    """Notify Slack on any ERROR event."""
    def __call__(self, event: Event, next_fn) -> int:
        if isinstance(event, ConfigErrorEvent):
            slack.post(f"qutebrowser error: {event.error_msg}")
        return next_fn(event)

router.events = EventFilter(router.events).use(SlackNotifyMiddleware())
```

### Subscribe to Events

```python
@router.events.subscribe(ConfigReloadedEvent)
def on_reload(event: ConfigReloadedEvent) -> None:
    logger.info("Reload: %d changes, %d errors, %.1fms",
                event.change_count, event.error_count, event.duration_ms)

# Subscribe to ALL events (wildcard):
router.events.subscribe_all(lambda e: print(e.topic()))
```

---

## Testing Strategy

```
tests/
  test_architecture.py  ← Layer / Stack / Orchestrator integration
  test_incremental.py   ← ConfigDiffer, IncrementalApplier, SnapshotStore
  test_extensions.py    ← Context, strategies, host policies, catalog
  test_health.py        ← All 21 health checks
  test_v10.py           ← v10 fixes
  test_v11.py           ← AuditLog, SessionLayer, pipeline v11
  test_v12.py           ← MetricsCollector, TeeStage, RetryStage, CompositeStage
  test_v13.py           ← ComposeLayer, EventFilter, LayerHotSwap, ConfigValidator
```

**Total: ~385 tests. All run without a live qutebrowser instance.**

### Test isolation helpers

```python
reset_audit_log()          # fresh AuditLog singleton
reset_metrics_collector()  # fresh MetricsCollector singleton
reset_schema_registry()    # fresh SchemaRegistry singleton  ← v13
EventBus.unsubscribe_all() # clear all wildcard handlers
SnapshotStore.clear()      # reset snapshot history
HealthChecker.with_checks(...)  # targeted check composition
```

### Running tests

```bash
# All tests
python3 -m pytest tests/ -v

# Single suite
python3 -m pytest tests/test_v13.py -v

# Quick smoke test (no qutebrowser needed)
python3 scripts/diagnostics.py health
python3 scripts/diagnostics.py summary
```

---

## Changelog

### v13 (current)

**New: `core/compose.py`**

- `LayerCompositionError` — raised on composition rule violations
- `ComposeLayer(LayerProtocol)` — meta-layer wrapping N children
  - `build()` — pure; merges children in priority order; child exceptions caught and logged
  - `validate()` — collects all child validation errors
  - `add(layer)` / `remove(name)` — fluent mutation; duplicate-name guard
  - `child_names()` / `describe()` — introspection
  - Implements full `LayerProtocol`; nestable and hot-swappable
- `compose(name, *children, priority, description)` — factory shorthand

**New: `core/event_filter.py`**

- `Middleware` base class — Chain of Responsibility node
- `MiddlewareChain` — ordered list; terminal calls `EventBus.publish()`
- `EventFilter(EventBus)` — drop-in wrapper; `.use(mw)`, `.prepend(mw)`, `.describe()`
- Built-in middleware: `LoggingMiddleware`, `DedupeMiddleware`, `ThrottleMiddleware`,
  `FilterMiddleware`, `AuditMiddleware`, `CountingMiddleware`
- `build_default_filter()` — production-ready AuditMW + LoggingMW + DedupeMiddleware(0.1s)

**New: `core/hot_swap.py` + `core/hot_swap_events.py`**

- `HotSwapResult` — frozen dataclass: operation, layer_name, changes, errors, duration_ms; `.ok`
- `ApplyFn = Callable[[str, Any], List[str]]` — injected apply function
- `LayerHotSwap(stack, apply_fn, router)` — surgical layer replacement
  - `swap(name, new_layer)` / `remove(name)` / `insert(new_layer)` → `HotSwapResult`
  - Snapshot → structural change → re-resolve → diff → apply delta → emit event
- `LayerSwappedEvent(Event)` — operation, layer_name, changes, errors

**New: `core/validator.py`**

- `FieldSpec` — frozen dataclass: type*, required, choices, min*, max\_, pattern, custom, description
- `ValidationResult(errors, warnings)` — `.ok`, `.merge()`, `__str__`
- `ConfigValidator(schema, strict)` — validates `ConfigDict` against `SchemaType`
  - Type check, required check, choices, min/max, pattern (re.search), custom callable
  - `strict=True` → unknown keys produce warnings
- `COMMON_SCHEMA` — partial schema for 17 common qutebrowser keys
- `SchemaRegistry` — named schema store: `register()`, `extend()`, `validate_all()`, `names()`
- `get_schema_registry()` / `reset_schema_registry()` — thread-safe singleton

**New: `tests/test_v13.py`**

70 tests covering all v13 additions.

**Total test count: ~385 (was ~315)**

---

### v12

**New: `core/metrics.py`** — MetricsCollector, MetricsSample, PhaseTimer, get/reset singletons, metrics_time()

**Updated: `core/pipeline.py`** — TeeStage, RetryStage, CompositeStage; Pipeline.**iter**

**Updated: `orchestrator.py`** — MetricsCollector wired; audit_trail(); metrics_summary(); GetMetricsSummaryQuery handler; FSM transitions to AuditLog

**New: `tests/test_v12.py`** — 56 tests

---

### v11

**New: `core/audit.py`** — AuditLevel, AuditEntry, AuditLog, AuditFilter, singleton, helpers

**New: `layers/session.py`** (p=55) — SessionMode, SessionSpec, \_SESSION_TABLE, \_resolve_active_session, ,S keybindings

**New: `scripts/session_switch.py`** — runtime session switching userscript

**New: `scripts/diagnostics.py`** — CLI: layers, health, audit, contexts, sessions, themes, keybindings, summary; --format text|json|markdown

**Updated: `core/pipeline.py`** — ReduceStage, BranchStage, CacheStage, AuditStage; Pipeline.fork(), describe(), **iter**; PipeStage.**add**; ConfigPacket.with_errors/warnings

**New: `tests/test_v11.py`** — 40+ tests

---

### v10

`core/types.py` (zero-dep primitives); `LayerStack._layers` property fix; `core/__init__.py` full exports; `conftest.py`

---

### v9

Incremental hot-reload; event system v2 (ConfigReloadedEvent, SnapshotTakenEvent, PolicyDeniedEvent, MetricsEvent); health checks v2 (SearchEngineCountCheck, ProxySchemeDetailCheck, DownloadPromptCheck); QueryBus introspection (GetSnapshotQuery, GetLayerDiffQuery, GetLayerNamesQuery)

---

### v8

Extended themes (nord, dracula, glass, …); SessionStore; font override parameters

---

### v7

HOST_POLICY_DEV fix; BehaviorLayer deduplication; keybinding catalog

---

### v6

ContextLayer (work/research/media/dev/writing); context_switch.py userscript
