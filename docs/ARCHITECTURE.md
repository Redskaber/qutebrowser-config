# Architecture Deep-Dive

> For the quick-start and high-level overview, see [README.md](README.md).
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
10. [Health Check System](#health-check-system)
11. [Data Flow (annotated)](#data-flow-annotated)
12. [Dependency Graph](#dependency-graph)
13. [Extension Points](#extension-points)
14. [Testing Strategy](#testing-strategy)
15. [Changelog](#changelog)

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

**Dependency Inversion** — every module depends on an abstraction, not a concrete. `LayerStack` depends on `LayerProtocol`, not `BaseLayer`. `ConfigOrchestrator` depends on `LifecycleManager`, not specific hooks.

**Single Source of Truth** — state transitions live in `state.py::TRANSITIONS`. Theme colors live in `ColorScheme` dataclasses. Host rules live in `policies/host.py`. Nothing is duplicated.

**Open/Closed** — adding a layer, strategy, policy, or pipeline stage never modifies existing code. Registration is the extension mechanism.

**Pure Build** — `layer.build()` and `layer.validate()` are pure functions. No side effects. This makes them testable without a running browser.

**Explicit State** — the FSM (`ConfigStateMachine`) owns all lifecycle state. No flags scattered across objects. Every transition is declared in a table.

**Observable** — every meaningful phase emits events (MetricsEvent, ConfigReloadedEvent, SnapshotTakenEvent, PolicyDeniedEvent). Zero coupling between emitter and observer.

---

## Module Map

```
config.py               ← entry point (qutebrowser loads ONLY this)
orchestrator.py         ← composition root

core/
  pipeline.py           ← ConfigPacket + PipeStage + Pipeline
  state.py              ← ConfigStateMachine (FSM)
  lifecycle.py          ← LifecycleManager (hook phases)
  protocol.py           ← MessageRouter (EventBus / CommandBus / QueryBus)
  layer.py              ← LayerProtocol + LayerStack + BaseConfigLayer
  strategy.py           ← Strategy + Policy + PolicyChain
  incremental.py        ← ConfigSnapshot + ConfigDiffer + IncrementalApplier
  health.py             ← HealthCheck + HealthChecker + HealthReport

layers/
  base.py        [p=10] ← foundational defaults
  privacy.py     [p=20] ← security, tracking protection
  appearance.py  [p=30] ← theme, fonts, colors
  behavior.py    [p=40] ← UX, keybindings, per-host rules
  context.py     [p=45] ← situational mode (work/research/media/dev/writing/gaming)
  performance.py [p=50] ← cache & rendering tuning
  user.py        [p=90] ← personal overrides (highest)

strategies/
  merge.py search.py profile.py download.py

policies/
  content.py network.py security.py host.py

themes/
  extended.py           ← 18+ color schemes

keybindings/
  catalog.py            ← query + conflict detection
```

---

## Layer System

Layers are **pure** configuration providers. Each layer:

1. Declares a unique `name` and integer `priority`
2. Implements `_settings() → ConfigDict`
3. Optionally implements `_keybindings()`, `_aliases()`
4. Optionally provides a `pipeline()` for post-processing its own output

`LayerStack.resolve()` merges them in priority order (lowest first). Higher priority layers override lower-priority keys.

### Merge Semantics

- **dict values** are deep-merged (e.g. `url.searchengines`, `hints.padding`)
- **all other values** replace — the highest-priority layer wins

### Priority Table

| Layer       | Priority | Purpose                          |
| ----------- | -------- | -------------------------------- |
| base        | 10       | Foundational defaults            |
| privacy     | 20       | Security & tracking protection   |
| appearance  | 30       | Theme, fonts, colors             |
| behavior    | 40       | UX, keybindings, per-host rules  |
| context     | 45       | Situational mode overrides       |
| performance | 50       | Cache & rendering tuning         |
| user        | 90       | Personal overrides (always wins) |

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

Built-in stages:
  LogStage         → debug-logs packet contents; pass-through
  ValidateStage    → runs predicate(value) → bool; appends errors
  TransformStage   → applies an arbitrary ConfigDict → ConfigDict fn
  FilterStage      → removes keys failing a (key, value) predicate
  MergeStage       → merges a static overlay dict into packet data
```

---

## State Machine

```
States:  IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
                  ↘           ↘           ↘
                 ERROR       ERROR       ERROR
                   ↓
               RELOADING ──────────────────────┘

Events:
  START_LOAD    IDLE      → LOADING
  LOAD_DONE     LOADING   → VALIDATING
  LOAD_FAILED   LOADING   → ERROR
  VALIDATE_DONE VALIDATING→ APPLYING
  VALIDATE_FAIL VALIDATING→ ERROR
  APPLY_DONE    APPLYING  → ACTIVE
  APPLY_FAIL    APPLYING  → ERROR
  RELOAD        ACTIVE    → RELOADING
  RELOAD        ERROR     → RELOADING
  LOAD_DONE     RELOADING → VALIDATING
  RESET         *         → IDLE
```

---

## Message Protocol

Three buses, one router — no direct cross-module imports:

```
EventBus   — fire-and-forget; zero or many subscribers
  LayerAppliedEvent(layer_name, key_count)
  ConfigErrorEvent(error_msg, layer_name)
  ThemeChangedEvent(theme_name)
  BindingRegisteredEvent(key, command, mode)
  ContextSwitchedEvent(old_context, new_context)
  HealthReportReadyEvent(ok, error_count, warning_count, info_count)
  ─── v9 new ───────────────────────────────────────────────────────
  ConfigReloadedEvent(changes_count, errors_count, duration_ms)
  SnapshotTakenEvent(label, key_count, version)
  LayerConflictEvent(key, winner_layer, loser_layer)
  PolicyDeniedEvent(key, value, reason, layer_name)
  MetricsEvent(phase, duration_ms, key_count)

CommandBus — imperative; exactly one handler; may fail
  ApplyLayerCommand(layer_name, priority)
  ReloadConfigCommand(reason)
  SetOptionCommand(key, value)

QueryBus   — request/response; exactly one handler; returns value
  GetMergedConfigQuery()      → Dict[str, Any]
  GetHealthReportQuery()      → Optional[HealthReport]
  GetSnapshotQuery(label, index) → Optional[ConfigSnapshot]    ← v9
  GetLayerDiffQuery(a, b)     → List[ConfigChange]             ← v9
  GetLayerNamesQuery()        → List[str]                      ← v9
```

### v9 Event Semantics

| Event                 | When emitted                                     | Subscriber use                     |
| --------------------- | ------------------------------------------------ | ---------------------------------- |
| `ConfigReloadedEvent` | End of `orchestrator.reload()`                   | Display reload stats in status bar |
| `SnapshotTakenEvent`  | `IncrementalApplier.record()` called             | Audit trail, debug logging         |
| `LayerConflictEvent`  | Layer key override detected in `LayerStack`      | Conflict detection, tooling        |
| `PolicyDeniedEvent`   | PolicyChain returns `DENY` in `apply_settings()` | Security audit, policy debugging   |
| `MetricsEvent`        | End of build/apply/reload/host_policies phase    | Performance monitoring, profiling  |

---

## Strategy & Policy System

```
Strategy[T]
  name: str
  apply(context: ConfigDict) → T
  can_handle(context: ConfigDict) → bool  # optional guard

StrategyRegistry[T]
  register(strategy) → self
  get(name) → Strategy[T]
  apply(name, context) → T
  auto_select(context) → Optional[Strategy[T]]

Policy
  evaluate(key, value, context) → PolicyDecision
  PolicyDecision.action: ALLOW | MODIFY | DENY | WARN
  PolicyDecision.modified_value: Any   # used by MODIFY
  PolicyDecision.reason: str

PolicyChain
  policies: List[Policy]           (ordered; first DENY wins)
  evaluate(key, value, ctx) → PolicyDecision

Built-in policies:
  ReadOnlyPolicy(keys)             → DENY writes to those keys
  TypeEnforcePolicy(key, type)     → DENY wrong-type values
  RangePolicy(key, min, max)       → DENY out-of-range numbers
  AllowlistPolicy(key, values)     → DENY values not in list
```

---

## Incremental Apply

Hot-reload (`:config-source`) re-runs `config.py` from scratch. The `IncrementalApplier` + `SnapshotStore` reduce the cost:

```
SnapshotStore.record(settings, label)   ← stores snapshot (ring buffer, max 10)
ConfigDiffer.diff(old, new)             ← returns List[ConfigChange]
IncrementalApplier.compute_delta()      ← diff latest two snapshots
IncrementalApplier.apply_delta(changes, apply_fn)
                                        ← call apply_fn(k, v) only for ADDED/CHANGED
IncrementalApplier.rollback(steps, apply_fn)
                                        ← revert to snapshot N steps back  ← v9
```

### v9 apply_delta() fix

`apply_fn` type corrected to `Callable[[str, Any], List[str]]` (returns errors).
Previously typed as returning `None` — the return value from the lambda in
`orchestrator.reload()` was silently discarded. Now errors are accumulated and
returned from `apply_delta()`.

### Snapshot Query

```python
# Introspect via QueryBus:
snap = router.ask(GetSnapshotQuery(label="pre-reload"))
diff = router.ask(GetLayerDiffQuery(label_a="pre-reload", label_b="post-reload"))
```

---

## Context Layer

`ContextLayer` [priority=45] resolves a named situational context into:

1. A **search engine delta** merged on top of base engines
2. A **settings delta** applied as overrides
3. **Context-switching keybindings** (always registered)

### Context Resolution Priority

```
1. ACTIVE_CONTEXT param (config.py)               ← highest
2. QUTE_CONTEXT environment variable
3. ~/.config/qutebrowser/.context file            ← written by ,C* keybindings
4. ContextMode.DEFAULT                            ← fallback
```

### Contexts

| Mode     | Key    | Description                             |
| -------- | ------ | --------------------------------------- |
| default  | `,C0`  | Base settings, no overrides             |
| work     | `,Cw`  | Corporate tools, Google default engine  |
| research | `,Cr`  | arXiv, Scholar, Wikipedia, Brave engine |
| media    | `,Cm`  | YouTube, Bilibili, Twitch; autoplay ON  |
| dev      | `,Cd`  | GitHub, MDN, DevDocs, npm, crates.io    |
| writing  | `,Cwt` | Dict, thesaurus, grammar; minimal UI    |
| gaming   | `,Cg`  | Steam, Twitch, ProtonDB, AreWeGameYet   |

---

## Health Check System

18 built-in checks (v9):

| Check                   | Severity | What it validates                                  |
| ----------------------- | -------- | -------------------------------------------------- |
| `blocking_enabled`      | WARNING  | content.blocking.enabled should be True            |
| `blocking_lists`        | WARNING  | adblock.lists must be non-empty                    |
| `search_engine_default` | ERROR    | url.searchengines must have DEFAULT key            |
| `search_engine_urls`    | ERROR    | all engine URLs must contain `{}`                  |
| `webrtc_policy`         | WARNING  | WebRTC IP leak risk                                |
| `cookie_accept`         | INFO     | all-cookie-accept is informational                 |
| `start_pages`           | WARNING  | url.start_pages should not be empty                |
| `editor_command`        | ERROR    | editor.command must be list with `{}`              |
| `download_dir`          | WARNING  | directory should not be /tmp                       |
| `tab_title_format`      | WARNING  | should reference `{current_title}`                 |
| `proxy_scheme`          | ERROR    | proxy must start with a valid scheme               |
| `zoom_default`          | ERROR    | must end with `%`                                  |
| `font_family`           | WARNING  | must not be empty string                           |
| `spellcheck_langs`      | WARNING  | entries should look like BCP-47 tags               |
| `content_user_agent`    | WARNING  | user_agent should not be empty string              |
| `search_engine_count`   | WARNING  | >50 engines is usually a misconfiguration ← **v9** |
| `proxy_scheme_detail`   | WARNING  | socks5/http must have host:port format ← **v9**    |
| `download_prompt`       | INFO     | prompt=False with default ~/Downloads ← **v9**     |

Custom checks can be injected:

```python
checker = HealthChecker.default().add(MyCustomCheck())
# Or compose from scratch:
checker = HealthChecker.with_checks(SearchEngineDefaultCheck(), MyCheck())
```

---

## Data Flow (annotated)

```
qutebrowser forks Python → loads config.py
    │
    ├─ sys.path.insert(0, config_dir)  ← makes core/, layers/ importable
    │
    └─ _build_orchestrator()
           ├─ MessageRouter()          ← EventBus + CommandBus + QueryBus
           ├─ LifecycleManager()
           ├─ ConfigStateMachine()
           ├─ build_default_host_registry(...)
           └─ LayerStack()
                 ├─ register(BaseLayer())           [p=10]
                 ├─ register(PrivacyLayer())         [p=20]
                 ├─ register(AppearanceLayer())      [p=30]
                 ├─ register(BehaviorLayer())        [p=40]
                 ├─ register(ContextLayer())         [p=45]  ← if enabled
                 ├─ register(PerformanceLayer())     [p=50]
                 └─ register(UserLayer())            [p=90]

orchestrator.build()
    ├─ fsm.send(START_LOAD) → IDLE→LOADING
    ├─ lifecycle.run(PRE_INIT)
    ├─ LayerStack.resolve()
    │     for layer in sorted(priority):
    │       raw   = layer.build()
    │       errs  = layer.validate(raw)
    │       pkt   = ConfigPacket(raw, errs)
    │       pkt   = layer.pipeline().run(pkt)  if pipeline
    │       merged = deep_merge(merged, pkt.data)
    ├─ fsm.send(LOAD_DONE) → LOADING→VALIDATING
    ├─ fsm.send(VALIDATE_DONE) → VALIDATING→APPLYING
    ├─ lifecycle.run(POST_INIT)
    └─ router.emit_metrics("build", duration_ms, key_count)   ← v9

orchestrator.apply(applier)
    ├─ lifecycle.run(PRE_APPLY)
    ├─ applier.apply_settings(merged["settings"], policy_chain, router)
    │     for k, v in settings.items():
    │       decision = policy_chain.evaluate(k, v, {})
    │       if DENY: router.emit_policy_denied(k, v, reason)  ← v9
    │       config.set(k, applied_value)
    ├─ applier.apply_keybindings(merged["keybindings"])
    ├─ applier.apply_aliases(merged["aliases"])
    ├─ router.emit(LayerAppliedEvent(...)) per layer
    ├─ HealthChecker.default().check(settings) → HealthReport
    ├─ router.emit_health(...)
    ├─ fsm.send(APPLY_DONE) → APPLYING→ACTIVE
    ├─ lifecycle.run(POST_APPLY)
    └─ router.emit_metrics("apply", duration_ms, key_count)   ← v9

orchestrator.apply_host_policies(applier)
    ├─ for rule in HostPolicyRegistry.active():
    │     config.set(k, v, pattern=rule.pattern)
    ├─ for policy in BehaviorLayer.host_policies():
    │     if pattern NOT in registry_patterns:
    │       config.set(k, v, pattern=policy.pattern)
    └─ router.emit_metrics("host_policies", ...)              ← v9

orchestrator.reload(applier)    ← hot-reload path
    ├─ fsm.send(RELOAD) → ACTIVE→RELOADING
    ├─ lifecycle.run(PRE_RELOAD)
    ├─ incremental_applier.record(current_settings, "pre-reload")
    ├─ router.emit_snapshot("pre-reload", key_count, version) ← v9
    ├─ orchestrator.build()
    ├─ incremental_applier.record(new_settings, "post-reload")
    ├─ router.emit_snapshot("post-reload", ...)               ← v9
    ├─ changes = incremental_applier.compute_delta()
    ├─ incremental_applier.apply_delta(changes, apply_fn)
    │     apply_fn(k, v) → List[str]  (errors)               ← v9 fix
    ├─ applier.apply_keybindings(merged["keybindings"])
    ├─ applier.apply_aliases(merged["aliases"])
    ├─ orchestrator.apply_host_policies(applier)              ← v9 new
    ├─ router.emit_reload(changes_count, errors_count, ms)    ← v9
    ├─ router.emit_metrics("reload", ...)                     ← v9
    └─ lifecycle.run(POST_RELOAD)
```

---

## Dependency Graph

```
config.py
  → orchestrator
      → core/layer       → core/pipeline
      → core/state
      → core/lifecycle
      → core/protocol
      → core/strategy
      → core/health
      → core/incremental
      → layers/*         → core/layer (BaseConfigLayer)
      → strategies/*     → core/strategy, layers/privacy, layers/performance
      → policies/*       → core/strategy, layers/privacy
      → themes/*         → layers/appearance (ColorScheme, THEMES)
      → keybindings/*    [optional, for docs/tests only]
```

**Invariant**: `layers/*` never imports from `layers/*`.
**Invariant**: `core/*` never imports from `layers/*` or `strategies/*`.
Violations are bugs.

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

Register in `config.py`'s `_build_orchestrator()`.

### Add a Per-Host Rule

Add a `HostRule(…)` to the appropriate list in `policies/host.py`.

### Add a Custom Context

Add a `ContextSpec(…)` to `_CONTEXT_TABLE` in `layers/context.py`.

### Add a Health Check

```python
from core.health import HealthCheck, HealthIssue, Severity
class MyCheck(HealthCheck):
    name = "my_check"
    def check(self, config):
        if config.get("my.key") == "bad":
            return self._error("my.key must not be 'bad'")
        return None

# Inject for one run:
checker = HealthChecker.default().add(MyCheck())
# Or compose:
checker = HealthChecker.with_checks(MyCheck())
```

### Subscribe to Reload Events (v9)

```python
def _on_reload(e: Event) -> None:
    if isinstance(e, ConfigReloadedEvent):
        print(f"Reloaded: {e.changes_count} changes in {e.duration_ms:.1f}ms")

router.events.subscribe(ConfigReloadedEvent, _on_reload)
```

### Introspect Config via QueryBus (v9)

```python
# Get merged config
merged = router.ask(GetMergedConfigQuery())

# Get snapshot by label
snap = router.ask(GetSnapshotQuery(label="pre-reload"))

# Get diff between two snapshots
diff = router.ask(GetLayerDiffQuery(label_a="pre-reload", label_b="post-reload"))
for change in diff:
    print(change)

# Get registered layer names
names = router.ask(GetLayerNamesQuery())
```

---

## Testing Strategy

```
tests/
  test_architecture.py    ← Layer / Stack / Orchestrator integration
  test_incremental.py     ← ConfigDiffer, IncrementalApplier, SnapshotStore
  test_extensions.py      ← Context, strategies, host policies
  test_health.py          ← All 18 health checks
```

### Test isolation

- `EventBus.unsubscribe_all()` clears all subscribers (v9).
- `SnapshotStore.clear()` resets snapshot history.
- `CommandBus(allow_replace=True)` allows test overrides.
- `HealthChecker.with_checks(...)` composes targeted check sets.

---

## Changelog

### v10 (current)

**File/Package Layout — Breaking change (structure only)**

The project now uses the intended sub-package layout that all imports always
assumed. Files that were flat in the project root are now in the correct
sub-directory:

| Module(s)                                                                                                          | Package        |
| ------------------------------------------------------------------------------------------------------------------ | -------------- |
| `layer.py`, `lifecycle.py`, `pipeline.py`, `protocol.py`, `state.py`, `strategy.py`, `health.py`, `incremental.py` | `core/`        |
| `appearance.py`, `base.py`, `behavior.py`, `privacy.py`, `performance.py`, `context.py`, `user.py`                 | `layers/`      |
| `merge.py`, `profile.py`, `search.py`, `download.py`                                                               | `strategies/`  |
| `content.py`, `network.py`, `security.py`, `host.py`                                                               | `policies/`    |
| `extended.py`                                                                                                      | `themes/`      |
| `catalog.py`                                                                                                       | `keybindings/` |

Every sub-directory has an `__init__.py`. `config.py` and `orchestrator.py`
remain at the project root (qutebrowser's `config.py` entry-point requirement).

**core/layer.py**

- `LayerStack._layers` property added as a public alias for `_records`.
  This was needed by `orchestrator._handle_get_layer_names` which
  referenced `self._stack._layers` (non-existent attribute — was `_records`).
  The property returns the _same_ list object, O(1), no overhead.

**orchestrator.py**

- `_handle_get_layer_names`: fixed variable-shadowing bug. The old
  comprehension iterated `for layer in sorted(...)` but filtered `if rec.enabled`
  — `rec` came from an undefined outer scope. Fixed to `rec.layer.name` / `rec.enabled`
  from the same loop variable.

**core/**init**.py**

- Was empty (0 bytes). Now exports the full public API surface with `__all__`.
- Newly exported: `FilterStage`, `LayerRecord`.

**tests/**

- `tests/conftest.py` added — inserts project root onto `sys.path` so pytest
  discovers tests correctly when run from any working directory or via IDEs.
- `tests/test_v10.py` added — 38 new tests covering all v10 changes:
  package imports, `_layers` property, `GetLayerNamesQuery` end-to-end,
  `FilterStage` coverage, and `core.__all__` surface completeness.

**Total test count: 259 (was 221)**

---

### v9 (previous)

**protocol.py**

- New events: `ConfigReloadedEvent`, `SnapshotTakenEvent`, `LayerConflictEvent`, `PolicyDeniedEvent`, `MetricsEvent`
- New queries: `GetSnapshotQuery`, `GetLayerDiffQuery`, `GetLayerNamesQuery`
- `EventBus.unsubscribe_all()` for test isolation
- `CommandBus(allow_replace=True)` for test overrides
- `MessageRouter` convenience emitters: `emit_reload`, `emit_snapshot`, `emit_conflict`, `emit_policy_denied`, `emit_metrics`

**orchestrator.py**

- `build()` / `apply()` / `reload()` emit `MetricsEvent` with timing
- `reload()` now re-applies host policies (was skipped previously)
- `reload()` falls back to `self._applier` stored from `apply()`
- `apply_settings()` forwards `router` for DENY event propagation
- QueryBus handlers: `GetSnapshotQuery`, `GetLayerDiffQuery`, `GetLayerNamesQuery`
- `_handle_get_layer_names` reads `stack._layers` ordered by priority
- `summary()` includes timing metrics from last run

**incremental.py**

- `apply_delta()` `apply_fn` type corrected: `Callable[[str, Any], List[str]]` (was `None`)
- `apply_delta()` accumulates and returns errors from all `apply_fn` calls
- `IncrementalApplier.rollback(steps, apply_fn)` added
- `ConfigDiffer` promoted to top-level public class
- `SnapshotStore.snapshots` property added (was private `_snapshots`)
- `SnapshotStore.find(label)` added
- `SnapshotStore.clear()` added (test teardown)

**health.py**

- 3 new checks: `SearchEngineCountCheck`, `ProxySchemeDetailCheck`, `DownloadPromptCheck`
- `HealthReport.summary()` now categorised multi-line output
- `HealthChecker.check()` accepts `extra_checks` parameter
- `HealthChecker.with_checks(*checks)` factory method added

**behavior.py**

- Caret mode bindings: H/L word nav, V select-line, y/^C yank, q leave
- Hint mode: `<escape>` leave hint mode
- Tab position shortcuts: `<alt-1..9>`
- New tab bindings: `,t` (new tab), `,T` (clone tab), `,q` / `,Q`
- Find bar: `,/` and `,?`
- Passthrough: `<ctrl-v>` enter-mode passthrough
- Security settings: `local_content_can_access_*` hardened
- `tabs.select_on_remove`: "prev"

**base.py**

- Added: `content.pdfjs`, `content.javascript.alert/prompt`, `content.javascript.can_open_tabs_automatically`, `tabs.pinned.*`, `content.fullscreen.window`, `qt.force_software_rendering`, `messages.timeout`, `url.default_page`, `content.images`

**config.py**

- New event subscribers: `ConfigReloadedEvent`, `SnapshotTakenEvent`, `PolicyDeniedEvent`, `MetricsEvent`
- `USER_MESSAGES_TIMEOUT` parameter added
- `POST_RELOAD` lifecycle hook wired
- `USER_EXTRA_ALIASES` includes `snap` alias (v9)

### v8 (previous)

- IncrementalApplier integrated into orchestrator.reload()
- SnapshotStore(max_history=10) owned by orchestrator
- USER_FONT_FAMILY / USER_FONT_SIZE / USER_FONT_SIZE_WEB first-class params
- HealthReportReadyEvent subscriber wired in config.py
- ContextMode.GAMING added

### v7

- HOST_POLICY_DEV bug fix: flag was declared but not passed to registry factory
- apply_host_policies: BehaviorLayer deduplication vs HostPolicyRegistry
- BehaviorLayer.host_policies() removes dev/localhost rules (owned by host.py)

### v6

- ContextLayer added (priority=45); WRITING context
- \_resolve_active_mode reads .context file (was only env var + constructor)
- HealthChecker.default() 15 checks (was 12)
- AppearanceLayer: fonts.default_family/size explicitly set from ColorScheme

### v5

- ContextSwitchedEvent, HealthReportReadyEvent
- GetHealthReportQuery, GetMergedConfigQuery
- MessageRouter.emit_health() helper
