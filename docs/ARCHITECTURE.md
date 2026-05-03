# Architecture Deep-Dive (v12)

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
13. [Health Check System](#health-check-system)
14. [Data Flow (annotated)](#data-flow-annotated)
15. [Dependency Graph](#dependency-graph)
16. [Extension Points](#extension-points)
17. [Testing Strategy](#testing-strategy)
18. [Changelog](#changelog)

---

## Design Philosophy

This config is built like a compiler front-end:

| Compiler Stage    | Config Equivalent              |
| ----------------- | ------------------------------ |
| Source files      | Layer `_settings()` methods    |
| Parse + validate  | `validate()` + `ValidateStage` |
| IR / AST          | `ConfigPacket`                 |
| Optimization pass | `PipeStage` chain              |
| Code generation   | `ConfigApplier.apply_*()`      |
| Linker            | `LayerStack.resolve()`         |
| Runtime           | qutebrowser's config API       |

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

---

## Module Map

```
core/
  types.py          ← ConfigDict, Keybind  (zero-dep primitives)
  layer.py          ← LayerProtocol, LayerStack, BaseConfigLayer
  pipeline.py       ← ConfigPacket, PipeStage, Pipeline
                       + v11: ReduceStage, BranchStage, CacheStage, AuditStage
                       + v12: TeeStage, RetryStage, CompositeStage
  state.py          ← ConfigStateMachine, TRANSITIONS table
  lifecycle.py      ← LifecycleManager, LifecycleHook
  protocol.py       ← EventBus, CommandBus, QueryBus, typed messages
                       + v12: GetMetricsSummaryQuery
  strategy.py       ← Policy, PolicyChain, StrategyRegistry
  health.py         ← HealthCheck, HealthChecker, 21 built-in checks
  incremental.py    ← ConfigSnapshot, ConfigDiffer, IncrementalApplier
  audit.py          ← AuditLog, AuditEntry, AuditFilter, AuditLevel  ← v11
  metrics.py        ← MetricsCollector, MetricsSample, PhaseTimer     ← v12

layers/
  base.py        [p=10]  foundational defaults, search engines
  privacy.py     [p=20]  security & tracking protection
  appearance.py  [p=30]  themes, fonts, colors
  behavior.py    [p=40]  UX, keybindings, per-host rules
  context.py     [p=45]  situational mode (work/research/media/dev/…)
  performance.py [p=50]  cache & rendering tuning
  session.py     [p=55]  time-aware session (day/evening/night/…)  ← v11
  user.py        [p=90]  personal overrides (always wins)

orchestrator.py     ← composition root: wires all modules
config.py           ← qutebrowser entry point
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
| user        | 90       | Personal overrides (always wins)    |

**Layer interaction: session vs. context vs. user:**

- `context` (p=45) sets _which sites_ you visit and their search engines.
- `session` (p=55) sets _how the browser behaves_ — zoom, font density, chrome visibility.
- `user` (p=90) overrides both; `USER_ZOOM`, `USER_FONT_SIZE_WEB` beat session values.

---

## Pipeline System

```
ConfigPacket
  source:   str            ← origin label ("layer:base")
  data:     ConfigDict     ← current settings dict
  errors:   List[str]      ← accumulated error strings
  warnings: List[str]      ← non-fatal issues
  meta:     Dict[str,Any]  ← arbitrary metadata for stages

PipeStage (ABC)
  name: str
  process(packet) → ConfigPacket    ← pure transform

Pipeline
  stages: List[PipeStage]
  run(packet) → ConfigPacket        ← fold: reduce over stages
  fork()  → Pipeline                ← independent copy  ← v11
  describe() → str                  ← human summary     ← v11

PipeStage.__add__(other) → Pipeline ← 2-stage composition  ← v11

Built-in stages (original):
  LogStage         → debug-logs packet contents; pass-through
  ValidateStage    → runs predicate(value) → bool; appends errors
  TransformStage   → applies an arbitrary ConfigDict → ConfigDict fn
  FilterStage      → removes keys failing a (key, value) predicate
  MergeStage       → merges a static overlay dict into packet data

Built-in stages v11 (new):
  ReduceStage      → fold (k,v) pairs; result stored in packet.meta
  BranchStage      → conditional routing: true/false sub-pipelines
  CacheStage       → memoize expensive inner stage; SHA-1 keyed
  AuditStage       → record pipeline passage into global AuditLog

ConfigPacket v11 additions:
  with_errors(msgs)    → bulk-add multiple errors (immutable)
  with_warnings(msgs)  → bulk-add multiple warnings (immutable)
```

### ReduceStage usage

```python
# Count boolean-valued keys in a packet
ReduceStage(
    reducer    = lambda acc, k, v: acc + (1 if isinstance(v, bool) else 0),
    initial    = 0,
    result_key = "bool_count",
)
```

### BranchStage usage

```python
# Apply extra hardening only in PARANOID privacy mode
BranchStage(
    predicate    = lambda p: p.meta.get("privacy_profile") == "PARANOID",
    true_branch  = Pipeline("harden").pipe(hardenTransform),
    false_branch = None,   # pass-through on false
)
```

### CacheStage usage

```python
# Memoize an expensive transform across hot-reloads
CacheStage(
    inner = TransformStage(expensive_fn, "expensive"),
    label = "expensive-cache",
)
# Invalidate after a manual rebuild:
cache_stage.invalidate()
```

---

## Session Layer (v11)

The `SessionLayer` (priority=55) is a **time-aware, situation-aware** configuration delta.

```
SessionMode (enum)
  AUTO    → resolved from local time at init
  DAY     → 08:00–18:00: standard defaults
  EVENING → 18:00–22:00: 18px font, 105% zoom
  NIGHT   → 22:00–06:00: 20px font, 110% zoom, minimal chrome
  FOCUS   → deep-work: hide statusbar, 18px font, no notifications
  COMMUTE → bandwidth-constrained: no images, no autoplay
  PRESENT → screen-share: 22px font, 125% zoom, full chrome

Resolution order (highest wins):
  1. constructor ``session`` param  (from config.py ACTIVE_SESSION)
  2. QUTE_SESSION env var
  3. ~/.config/qutebrowser/.session  (written by session_switch.py)
  4. auto-detect from datetime.now().hour
```

**Keybindings** (`,S` prefix, registered by SessionLayer itself):

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

## Audit System (v11)

```
AuditLevel  DEBUG < INFO < WARN < ERROR

AuditEntry (frozen dataclass)
  ts:        datetime (UTC)
  level:     AuditLevel
  component: str
  message:   str
  meta:      Dict[str, Any]
  seq:       int (monotonic session-wide)

AuditLog (thread-safe ring buffer, capacity=512)
  record(level, component, message, **meta) → AuditEntry
  query(flt?) → List[AuditEntry]
  last_n(n, flt?) → List[AuditEntry]
  errors() → List[AuditEntry]
  warnings_and_above() → List[AuditEntry]
  export_text(flt?)     → str
  export_json(flt?)     → str (JSON array)
  export_markdown(flt?) → str (Markdown table)
  summary(last_n)       → str

AuditFilter (composable predicate)
  level_min, level_max, component, message_contains, since_seq
  .matches(entry) → bool
  .errors_and_warnings() classmethod
  .errors_only() classmethod

Global singleton:
  get_audit_log() → AuditLog   (created on first call)
  reset_audit_log() → AuditLog (for tests)

Module helpers:
  audit_debug(component, message, **meta)
  audit_info(component, message, **meta)
  audit_warn(component, message, **meta)
  audit_error(component, message, **meta)
```

The AuditLog is a **zero-coupling side channel**: components record into it independently. The log is consumed by:

- `scripts/diagnostics.py audit`
- `orchestrator.audit_trail()` → summary string
- Tests asserting specific events were recorded

---

## Health Check System

See original ARCHITECTURE.md §Health Check System. No changes in v11.

Built-in checks (18 total, v9.1):
`BlockingEnabledCheck`, `BlockingListCheck`, `SearchEngineDefaultCheck`,
`SearchEngineUrlCheck`, `WebRTCPolicyCheck`, `CookieAcceptCheck`,
`StartPageCheck`, `EditorCommandCheck`, `DownloadDirCheck`,
`TabTitleFormatCheck`, `ProxySchemeCheck`, `ZoomDefaultCheck`,
`FontFamilyCheck`, `SpellcheckLangCheck`, `ContentHeaderCheck`,
`SearchEngineCountCheck`, `ProxySchemeDetailCheck`, `DownloadPromptCheck`

---

## Data Flow (annotated)

```
qutebrowser forks Python → loads config.py
    │
    ├─ sys.path.insert(0, config_dir)
    │
    └─ _build_orchestrator()
           ├─ MessageRouter()
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
                 └─ register(UserLayer())            [p=90]

orchestrator.build()
    ├─ fsm.send(START_LOAD) → IDLE→LOADING
    ├─ lifecycle.run(PRE_INIT)
    ├─ stack.resolve()  ← merge pipeline
    │     for each layer (priority order):
    │       layer.build() → ConfigPacket
    │       layer.validate(data) → errors
    │       pipe = layer.pipeline()
    │       if pipe: packet = pipe.run(packet)
    │       _merged = deep_merge(_merged, packet.data)
    ├─ fsm.send(LOAD_DONE) → LOADING→VALIDATING
    ├─ fsm.send(VALIDATE_DONE) → VALIDATING→APPLYING
    ├─ lifecycle.run(POST_INIT)
    ├─ router.emit_metrics("build", ...)
    └─ audit.record("build", "layers resolved", ...)   ← v11

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
    └─ audit.record("apply", "complete", ...)          ← v11

orchestrator.apply_host_policies(applier)
    ├─ HostPolicyRegistry.active() → [HostRule]
    │     config.set(k, v, pattern=rule.pattern)
    ├─ BehaviorLayer.host_policies() (non-duplicate patterns only)
    ├─ router.emit_metrics("host_policies", ...)
    └─ audit.record("host_policies", f"{n} rules", ...)  ← v11

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
    ├─ audit.record("reload", f"{n} changes", ...)       ← v11
    └─ lifecycle.run(POST_RELOAD)
```

---

## Dependency Graph

```
core/types.py          (zero project-level deps)
     ↑
core/layer.py   keybindings/catalog.py
     ↑
core/pipeline.py ←→ core/audit.py (optional, guarded by try/except)
core/state.py
core/lifecycle.py
core/protocol.py
core/strategy.py
core/health.py
core/incremental.py
     ↑
orchestrator.py
     ↑
config.py
```

**Invariants:**

- `layers/*` never imports from `layers/*`
- `core/*` never imports from `layers/*` or `strategies/*`
- `core/audit.py` has zero project-level imports (like `core/types.py`)
- All `core/audit` references in orchestrator are wrapped in `try/except ImportError`

---

## Extension Points

### Add a Layer

```python
# layers/work.py
from core.layer import BaseConfigLayer
class WorkLayer(BaseConfigLayer):
    name = "work"; priority = 60
    def _settings(self):
        return {"url.searchengines": {"DEFAULT": "https://intranet.co?q={}"}}
```

Register in `config.py`'s `_build_orchestrator()`:

```python
if LAYERS.get("work"):
    stack.register(WorkLayer(leader=LEADER_KEY))
```

### Add a Session Mode

Add a `SessionSpec(…)` to `_SESSION_TABLE` in `layers/session.py`, add the mode to `SessionMode` enum, and add keybindings to `_keybindings()`.

### Add a Per-Host Rule

Add a `HostRule(…)` to the appropriate list in `policies/host.py`.

### Add a Health Check

```python
from core.health import HealthCheck, HealthIssue, Severity
class MyCheck(HealthCheck):
    name = "my_check"
    def run(self, settings, report):
        if settings.get("my.key") == "bad":
            report.add(self._error("my.key must not be 'bad'"))

checker = HealthChecker.default().add(MyCheck())
```

### Subscribe to Audit Events

```python
from core.audit import get_audit_log, AuditFilter, AuditLevel

log = get_audit_log()
errors = log.errors()                           # all ERROR entries
recent = log.last_n(10, AuditFilter.errors_and_warnings())
log.export_markdown()                           # Markdown table
```

### Use Pipeline v11 Stages

```python
from core.pipeline import ReduceStage, BranchStage, CacheStage, AuditStage

# Count integer-valued settings
count_stage = ReduceStage(
    lambda acc, k, v: acc + (1 if isinstance(v, int) else 0), 0, "int_count"
)

# Conditional hardening
harden_stage = BranchStage(
    predicate    = lambda p: p.meta.get("profile") == "PARANOID",
    true_branch  = harden_pipeline,
)

# Memoize expensive computation
cached = CacheStage(TransformStage(expensive_fn, "slow"), "fast-cache")

# Combine two stages
combined = LogStage("pre") + ValidateStage({...})
```

---

## Testing Strategy

```
tests/
  test_architecture.py    ← Layer / Stack / Orchestrator integration
  test_incremental.py     ← ConfigDiffer, IncrementalApplier, SnapshotStore
  test_extensions.py      ← Context, strategies, host policies
  test_health.py          ← All 18 health checks
  test_v10.py             ← v10 fixes (LayerStack._layers, etc.)
  test_v11.py             ← v11 additions (AuditLog, SessionLayer, pipeline)  ← v11
```

### Test isolation

- `reset_audit_log()` returns a fresh AuditLog for tests.
- `reset_metrics_collector()` returns a fresh MetricsCollector for tests.
- `EventBus.unsubscribe_all()` clears all subscribers.
- `SnapshotStore.clear()` resets snapshot history.
- `HealthChecker.with_checks(...)` composes targeted check sets.

---

## Metrics System

`core/metrics.py` — v12

Previously, `orchestrator.py` owned a bare `_last_metrics: Dict[str, float]` dict and called `router.emit_metrics(...)` inline. That scattered telemetry across orchestration logic, violating SRP.

v12 extracts telemetry into a dedicated, composable module:

```
MetricsSample   — immutable frozen dataclass
  phase         : str    — "build" | "apply" | "reload" | "host_policies"
  duration_ms   : float  — wall-clock duration
  key_count     : int    — keys processed
  timestamp     : UTC datetime
  meta          : Dict[str, Any]  — extra context

PhaseTimer      — context manager for wall-clock timing
  with timer:
      ...work...
  ms = timer.elapsed_ms

MetricsCollector — thread-safe ring buffer (default capacity=128)
  emit(phase, duration_ms, key_count, **meta) → MetricsSample
  get(phase)            → Optional[MetricsSample]   latest for phase
  last_n(n)             → List[MetricsSample]
  iter_phase(phase)     → Iterator[MetricsSample]
  all_phases()          → List[str]  (order of first occurrence)
  totals_by_phase()     → Dict[str, float]
  summary(last_n)       → str
  on_emit(callback)     → self  (fluent chaining)
  clear()
```

### Orchestrator integration

```python
# orchestrator.__init__:
self._metrics = MetricsCollector(capacity=64)
self._metrics.on_emit(
    lambda ph, ms, n: self._router.emit_metrics(phase=ph, duration_ms=ms, key_count=n)
)

# In build():
self._emit_metrics("build", duration_ms, key_count=n_sets, layer_count=len(self._resolved))
```

The `on_emit` callback fires `router.emit_metrics` so that all existing `MetricsEvent` subscribers continue to work. The `MetricsCollector` also accumulates samples locally for introspection.

### Query via QueryBus

```python
# v12: GetMetricsSummaryQuery
summary = router.ask(GetMetricsSummaryQuery())
# → "Metrics (last 8 samples):\n  [14:32:01] build  2.3ms  keys=47\n  ..."
```

### Zero-import policy

`core/metrics.py` does **not** import from any other project module. All coupling to `MessageRouter` happens through the injected callback. This makes `MetricsCollector` independently testable.

### Pattern

Memento (MetricsSample) + Strategy (emit callback) + Context Manager (PhaseTimer).

---

## Changelog

### v12 (current)

**New: `core/metrics.py`**

Dedicated metrics/telemetry module. Extracts `_last_metrics` dict from `ConfigOrchestrator` into `MetricsCollector`, satisfying SRP.

- `MetricsSample` — immutable frozen dataclass with timestamp + meta
- `PhaseTimer` — context manager: `with PhaseTimer() as t: ...`; `t.elapsed_ms`
- `MetricsCollector` — thread-safe ring buffer; `emit()`, `get()`, `last_n()`, `iter_phase()`, `totals_by_phase()`, `summary()`, `on_emit(callback)`
- `metrics_time()` — module-level convenience context manager
- `get_metrics_collector()` / `reset_metrics_collector()` — thread-safe singleton

**Updated: `core/pipeline.py` (v12)**

Three new pipeline stages:

| Stage            | Purpose                                                              |
| ---------------- | -------------------------------------------------------------------- |
| `TeeStage`       | Fan-out: run observer stage, main packet continues unchanged         |
| `RetryStage`     | Retry wrapper: up to `max_retries` attempts; warnings recorded       |
| `CompositeStage` | Wrap a sub-pipeline as a single named stage for cleaner `describe()` |

**Updated: `orchestrator.py` (v12)**

- `MetricsCollector` wired in `__init__`; `_last_metrics` dict removed
- `_emit_metrics()` private helper routes through collector
- `audit_trail(last_n)` method: formatted AuditLog output
- `metrics_summary(last_n)` method: formatted MetricsSample table
- `_handle_get_metrics_summary()`: QueryBus handler for `GetMetricsSummaryQuery`
- `summary()` updated to v12: includes session + metrics + audit sections
- `_on_state_transition()` now records FSM transitions to AuditLog
- FSM audit entries for every `IDLE→LOADING→…→ACTIVE` transition

**Updated: `core/__init__.py` (v12)**

New exports: `TeeStage`, `RetryStage`, `CompositeStage`, `MetricsSample`, `MetricsCollector`, `PhaseTimer`, `get_metrics_collector`, `reset_metrics_collector`, `metrics_time`, all audit symbols.

**New: `tests/test_v12.py`**

56 new tests covering all v12 additions.

**Total test count: ~315 (was ~259)**

---

### v11 (previous)

**New: `core/audit.py`**

- `AuditLevel` enum: DEBUG / INFO / WARN / ERROR
- `AuditEntry` frozen dataclass with `ts`, `level`, `component`, `message`, `meta`, `seq`
- `AuditLog` thread-safe ring buffer (default cap=512): `record()`, `query()`, `last_n()`, `errors()`, `export_*()`, `summary()`
- `AuditFilter` composable predicate: `level_min`, `level_max`, `component`, `message_contains`, `since_seq`
- Global singleton: `get_audit_log()` / `reset_audit_log()`
- Module helpers: `audit_debug()`, `audit_info()`, `audit_warn()`, `audit_error()`

**New: `layers/session.py`** (priority=55)

- `SessionMode` enum: AUTO / DAY / EVENING / NIGHT / FOCUS / COMMUTE / PRESENT
- `SessionSpec` frozen dataclass: `settings_delta`, `description`, `zoom_hint`
- `_SESSION_TABLE` data-driven spec map
- `_resolve_active_session()`: env var → file → auto-detect from time
- `SessionLayer`: `_settings()`, `_keybindings()` (`,S` prefix), `describe()`, `available_sessions()`

**New: `scripts/session_switch.py`**

- Runtime session switching userscript (mirrors `context_switch.py`)

**New: `scripts/diagnostics.py`**

- CLI tool: `layers`, `health`, `audit`, `contexts`, `sessions`, `themes`, `keybindings`, `summary`
- `--format text|json|markdown`, `--out FILE`, `--context`, `--session`, `--theme`
- Exit code 0=clean, 1=health errors, 2=import error

**Enhanced: `core/pipeline.py`**

- `ReduceStage`: fold (k,v) pairs; result in `packet.meta`
- `BranchStage`: conditional routing to true/false sub-pipelines
- `CacheStage`: memoize inner stage; SHA-1 content hash; `invalidate()`
- `AuditStage`: zero-cost audit recording at pipeline passage points
- `Pipeline.fork()`: independent copy
- `Pipeline.describe()`: human-readable stage summary
- `PipeStage.__add__(other) → Pipeline`: 2-stage composition sugar
- `ConfigPacket.with_errors(msgs)`: bulk-add errors (no-op if empty)
- `ConfigPacket.with_warnings(msgs)`: bulk-add warnings
- `field(default_factory=dict[str,Any])` → `field(default_factory=dict)` (Pyright strict fix)

**Enhanced: `config.py`**

- `ACTIVE_SESSION` configuration flag
- `LAYERS["session"] = True` (default enabled)
- `SessionLayer` registered in `_build_orchestrator()`
- Audit log queried after apply; warnings logged if present

**New: `tests/test_v11.py`**

- 40+ tests covering all v11 additions

### v10

- `core/types.py` (zero-dep primitives)
- `LayerStack._layers` property (fix for `GetLayerNamesQuery`)
- `core/__init__.py` full exports
- `conftest.py` for pytest discovery

### v9

- Incremental hot-reload (IncrementalApplier, SnapshotStore)
- Event system v2: ConfigReloadedEvent, SnapshotTakenEvent, PolicyDeniedEvent, MetricsEvent
- Health checks v2: 3 new checks (SearchEngineCountCheck, ProxySchemeDetailCheck, DownloadPromptCheck)
- QueryBus introspection: GetSnapshotQuery, GetLayerDiffQuery, GetLayerNamesQuery
