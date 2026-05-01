# Architecture Deep-Dive

> For the quick-start and high-level overview, see [README.md](../README.md).
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
9. [Data Flow (annotated)](#data-flow-annotated)
10. [Dependency Graph](#dependency-graph)
11. [Extension Points](#extension-points)
12. [Testing Strategy](#testing-strategy)

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

The result: config is **data** flowing through **transforms**, not imperative
Python statements scattered across a file.

### Core Principles

**Dependency Inversion** — every module depends on an abstraction, not a
concrete. `LayerStack` depends on `LayerProtocol`, not `BaseLayer`.
`ConfigOrchestrator` depends on `LifecycleManager`, not specific hooks.

**Single Source of Truth** — state transitions live in `state.py::TRANSITIONS`.
Theme colors live in `ColorScheme` dataclasses. Host rules live in
`policies/host.py`. Nothing is duplicated.

**Open/Closed** — adding a layer, strategy, policy, or pipeline stage never
modifies existing code. Registration is the extension mechanism.

**Pure Build** — `layer.build()` and `layer.validate()` are pure functions.
No side effects. This makes them testable without a running browser.

**Explicit State** — the FSM (`ConfigStateMachine`) owns all lifecycle state.
No flags scattered across objects. Every transition is declared in a table.

---

## Module Map

```
config.py                     ← entry point (single file qutebrowser loads)
orchestrator.py               ← composition root; wires everything

core/
  layer.py       LayerProtocol, BaseConfigLayer, LayerStack, LayerRecord
  pipeline.py    PipeStage, Pipeline, ConfigPacket, LogStage, ValidateStage
  state.py       ConfigState, ConfigEvent, ConfigStateMachine
  lifecycle.py   LifecycleHook, LifecycleManager, LifecyclePhase
  protocol.py    MessageRouter, EventBus, CommandBus, QueryBus
                 Event, LayerAppliedEvent, ConfigErrorEvent, ThemeChangedEvent
  strategy.py    Strategy, StrategyRegistry, Policy, PolicyChain, PolicyDecision
                 ReadOnlyPolicy, TypeEnforcePolicy, RangePolicy, AllowlistPolicy
                 MergeStrategy.*
  incremental.py SnapshotStore, IncrementalApplier

layers/
  base.py        BaseLayer           [priority=10]
  privacy.py     PrivacyLayer        [priority=20]   PrivacyProfile
  appearance.py  AppearanceLayer     [priority=30]   ColorScheme, THEMES
  behavior.py    BehaviorLayer       [priority=40]   HostPolicy
  performance.py PerformanceLayer    [priority=50]   PerformanceProfile
  user.py        UserLayer           [priority=90]

strategies/
  merge.py       LastWins, FirstWins, DeepMerge, ProfileAware
  profile.py     UnifiedProfile, ProfileStrategy, ProfileResolution
  search.py      BaseSearch, DevSearch, PrivacySearch, ChineseSearch, …
  download.py    NoDispatcher, XdgOpen, Rifle, AutoDetect

policies/
  content.py     JS, Cookie, Autoplay, Canvas, LocalStorage, WebRTC policies
  network.py     DnsPrefetch, Referrer, Proxy, HttpsOnly policies
  security.py    Geolocation, MediaCapture, Notification, Clipboard, MixedContent
  host.py        HostRule, HostPolicyRegistry, built-in rule sets

themes/
  extended.py    nord, dracula, solarized-*, one-dark, everforest-dark, …

keybindings/
  catalog.py     KeybindingCatalog, KeybindingEntry (query + conflict detection)

scripts/
  install.sh     deployment script
  readability.py userscript: reader mode
  password.py    userscript: pass integration

tests/
  test_architecture.py  67 unit tests covering all core modules
  test_incremental.py   incremental apply + snapshot tests
```

---

## Layer System

```
LayerProtocol (ABC)
  ├── name: str
  ├── priority: int
  ├── description: str
  ├── build() → ConfigDict          [pure, required]
  ├── validate(data) → List[str]   [pure, optional]
  └── pipeline() → Optional[Pipeline]

BaseConfigLayer (implements LayerProtocol)
  ├── build() → calls _settings(), _keybindings(), _aliases()
  │             assembles ConfigDict{"settings":{}, "keybindings":[], "aliases":{}}
  ├── validate(data) → checks required keys present
  ├── _settings() → ConfigDict     [override in subclass]
  ├── _keybindings() → List[Tuple] [override in subclass]
  └── _aliases() → ConfigDict      [override in subclass]

LayerStack
  ├── register(layer) → ordered by priority
  ├── resolve() → Dict[name, ConfigPacket]  (runs pipeline per layer)
  └── merged → ConfigDict  (deep merge result, highest priority wins)
```

### Layer Priority Contract

| Priority | Layer       | Can override       |
| -------- | ----------- | ------------------ |
| 10       | base        | nothing            |
| 20       | privacy     | base               |
| 30       | appearance  | base, privacy      |
| 40       | behavior    | base .. appearance |
| 50       | performance | base .. behavior   |
| 90       | user        | everything         |

There is intentional space between 50 and 90 for user-added layers (60–80).

---

## Pipeline System

```
ConfigPacket
  data:   ConfigDict     ← current settings dict
  errors: List[str]      ← accumulated error strings
  meta:   Dict[str,Any]  ← arbitrary metadata for stages

PipeStage (ABC)
  name: str
  process(packet) → ConfigPacket    ← pure transform

Pipeline
  stages: List[PipeStage]
  run(packet) → ConfigPacket        ← fold: reduce over stages

Built-in stages:
  LogStage         → debug-logs packet contents; pass-through
  ValidateStage    → runs predicate(packet.data) → str; appends to errors
```

Custom stages plug in via `layer.pipeline()`:

```python
def pipeline(self) -> Pipeline:
    return Pipeline([LogStage(), MyCustomStage()])
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

The FSM is the single source of truth for "where are we in loading?".
Observer callbacks fire on every transition.

---

## Message Protocol

Three buses, zero coupling:

**EventBus** — pub/sub broadcast. `emit(event)` notifies all subscribers
of that event type. Subscribers registered with `subscribe(EventType, fn)`.

**CommandBus** — CQRS commands. Exactly one handler per command type.
Fire-and-forget with no return value.

**QueryBus** — CQRS queries. Exactly one handler per query type.
Returns a value. Used for: "what is the current theme?", "is JS enabled?".

`MessageRouter` owns all three buses and is the single injection point.

---

## Strategy & Policy System

**Strategy** — selects and applies an algorithm:

```
StrategyRegistry.apply(name, context) → T
```

Used for: merge algorithm selection, search engine set, download dispatcher.

**Policy** — gates or transforms a single key/value:

```
PolicyChain.evaluate(key, value, context) → PolicyDecision
PolicyDecision.action: ALLOW | DENY | MODIFY | WARN
```

Used for: enforcing privacy profile constraints, security hard limits.

Policy chains run _after_ LayerStack.resolve() and _before_ ConfigApplier.apply_settings().
This means even a UserLayer (priority=90) override can be blocked by a PARANOID policy.

---

## Incremental Apply

Hot-reload (`:config-source`) re-runs `config.py` from scratch.
The `IncrementalApplier` + `SnapshotStore` reduce the cost:

```
SnapshotStore.record(settings, label)  ← stores snapshot
IncrementalApplier.compute_delta()     ← diff current vs previous
IncrementalApplier.apply_delta(delta)  ← call config.set() only for changed keys
```

If no snapshot exists (first load), all keys are applied.
On reload, only changed keys are re-set — unchanged settings are skipped.

---

## Data Flow (annotated)

```
qutebrowser forks Python → loads config.py
    │
    ├─ sys.path.insert(0, config_dir)  ← makes core/, layers/ importable
    │
    └─ _build_orchestrator()
           ├─ MessageRouter()
           ├─ LifecycleManager()
           ├─ ConfigStateMachine()
           └─ LayerStack()
                 ├─ register(BaseLayer())           [p=10]
                 ├─ register(PrivacyLayer())         [p=20]
                 ├─ register(AppearanceLayer())      [p=30]
                 ├─ register(BehaviorLayer())        [p=40]
                 ├─ register(PerformanceLayer())     [p=50]
                 └─ register(UserLayer())            [p=90]

orchestrator.build()
    ├─ fsm.send(START_LOAD) → IDLE→LOADING
    ├─ lifecycle.run(PRE_INIT)
    ├─ LayerStack.resolve()
    │     for layer in sorted(priority):
    │       raw   = layer.build()           ← pure Python dict
    │       errs  = layer.validate(raw)     ← pure: [] or ["err"]
    │       pkt   = ConfigPacket(raw, errs)
    │       pkt   = layer.pipeline().run(pkt)  if pipeline
    │       merged = deep_merge(merged, pkt.data)
    ├─ fsm.send(LOAD_DONE) → LOADING→VALIDATING
    ├─ fsm.send(VALIDATE_DONE) → VALIDATING→APPLYING
    └─ lifecycle.run(POST_INIT)

orchestrator.apply(applier)
    ├─ lifecycle.run(PRE_APPLY)
    ├─ applier.apply_settings(merged["settings"])
    │     for k, v in settings.items():
    │       # policy chain evaluation (if configured)
    │       config.set(k, v)
    ├─ applier.apply_keybindings(merged["keybindings"])
    │     for key, cmd, mode in bindings:
    │       config.bind(key, cmd, mode=mode)
    ├─ applier.apply_aliases(merged["aliases"])
    │     for name, cmd in aliases.items():
    │       c.aliases[name] = cmd
    ├─ router.emit(LayerAppliedEvent(layer_name, key_count))
    ├─ fsm.send(APPLY_DONE) → APPLYING→ACTIVE
    └─ lifecycle.run(POST_APPLY)

orchestrator.apply_host_policies(applier)
    └─ BehaviorLayer.host_policies()
          for policy in policies:
            for k, v in policy.settings.items():
              config.set(k, v, pattern=policy.pattern)
```

---

## Dependency Graph

```
config.py
  → orchestrator
      → core/layer  → core/pipeline
      → core/state
      → core/lifecycle
      → core/protocol
      → core/strategy
      → core/incremental
      → layers/* → core/layer (BaseConfigLayer)
      → strategies/* → core/strategy, layers/privacy, layers/performance
      → policies/* → core/strategy, layers/privacy
      → themes/* → layers/appearance (ColorScheme, THEMES)
      → keybindings/* [optional, for docs/tests only]
```

**Invariant**: `layers/*` never imports from `layers/*`.
**Invariant**: `core/*` never imports from `layers/*` or `strategies/*`.
Violations of these invariants are bugs.

---

## Extension Points

| What to add             | Where                        | Register in                     |
| ----------------------- | ---------------------------- | ------------------------------- |
| New configuration layer | `layers/myfeature.py`        | `config.py`                     |
| New theme               | `themes/extended.py`         | auto via import                 |
| New merge algorithm     | `strategies/merge.py`        | `build_merge_registry()`        |
| New search engine set   | `strategies/search.py`       | `build_search_registry()`       |
| New privacy policy rule | `policies/content.py`        | `build_content_policy_chain()`  |
| New host exception      | `policies/host.py`           | `build_default_host_registry()` |
| New pipeline stage      | `core/pipeline.py` or inline | `layer.pipeline()`              |
| New lifecycle hook      | `config.py` wiring section   | `@lifecycle.on(phase)`          |
| New FSM event           | `core/state.py` TRANSITIONS  | declare + send()                |

---

## Testing Strategy

Tests are **pure Python** — no qutebrowser process required.
All layer `build()` methods are tested in isolation.

```
tests/
  test_architecture.py   67 tests
    ├── TestPipeline         pipeline fold, LogStage, ValidateStage
    ├── TestStateMachine     transitions, invalid transitions, observers
    ├── TestMessageRouter    EventBus, CommandBus, QueryBus
    ├── TestLifecycle        hook ordering, error isolation
    ├── TestLayerStack       priority order, merge semantics
    ├── TestBaseLayer        build, validate, keybindings
    ├── TestAppearanceLayer  all themes, color key presence
    ├── TestPrivacyLayer     all profiles, cookie/JS gating
    ├── TestFullStack        end-to-end resolve + merge
    └── TestStrategy         PolicyChain decisions

  test_incremental.py    25 tests
    ├── SnapshotStore        record, retrieve, max_history
    ├── IncrementalApplier   delta compute, apply, error handling
    └── integration          full load→record→reload→delta cycle
```

Run all tests:

```bash
pytest tests/ -v
# or
python3 tests/test_architecture.py && python3 tests/test_incremental.py
```
