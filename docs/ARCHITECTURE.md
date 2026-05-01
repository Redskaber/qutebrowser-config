# Architecture Deep-Dive

> For the quick-start and high-level overview, see [README.md](README.md).
> This document targets contributors and layer authors.
>
> **Single source of truth** — `ARCHITECTURE_v6_patch.md` has been merged
> into this file and can be deleted.

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
13. [Changelog](#changelog)

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
                 ContextSwitchedEvent, HealthReportReadyEvent  [v5+]
  strategy.py    Strategy, StrategyRegistry, Policy, PolicyChain, PolicyDecision
                 ReadOnlyPolicy, TypeEnforcePolicy, RangePolicy, AllowlistPolicy
                 MergeStrategy.*
  incremental.py SnapshotStore, IncrementalApplier
  health.py      HealthCheck, HealthChecker, HealthReport, HealthIssue, Severity

layers/
  base.py        BaseLayer           [priority=10]
  privacy.py     PrivacyLayer        [priority=20]   PrivacyProfile
  appearance.py  AppearanceLayer     [priority=30]   ColorScheme, THEMES
  behavior.py    BehaviorLayer       [priority=40]   HostPolicy
  context.py     ContextLayer        [priority=45]   ContextMode, ContextSpec  [v5+]
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
  host.py        HostRule, HostPolicyRegistry, ALWAYS/DEV/LOGIN/SOCIAL/MEDIA rules

themes/
  extended.py    nord, dracula, solarized-*, one-dark, everforest-dark, …

keybindings/
  catalog.py     KeybindingCatalog, KeybindingEntry (query + conflict detection)

scripts/
  install.sh          deployment script
  context_switch.py   runtime context switching (6 modes)
  gen_keybindings.py  auto-generates KEYBINDINGS.md
  readability.py      userscript: reader mode
  password.py         userscript: pass integration
  open_with.py        userscript: open with external app
  search_sel.py       userscript: search selected text
  tab_restore.py      userscript: save/restore tab sessions

tests/
  test_architecture.py  unit tests covering all core modules
  test_incremental.py   incremental apply + snapshot tests
  test_health.py        health check tests (12 checks)
  test_extensions.py    extension/layer tests
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

| Priority | Layer       | Notes                                          |
| -------- | ----------- | ---------------------------------------------- |
| 10       | base        | Foundational defaults; lowest priority         |
| 20       | privacy     | Overrides base security stance                 |
| 30       | appearance  | Theme, colors, fonts                           |
| 40       | behavior    | UX patterns, keybindings, non-dev host rules   |
| 45       | context     | Situational mode delta (work/research/dev/…)   |
| 50       | performance | Cache, rendering, resource limits              |
| 60–80    | *(reserved)*| User-added layers without touching existing    |
| 90       | user        | Personal overrides; highest priority; wins all |

**Keybindings accumulate** across all layers (each layer's bindings are merged
additively).  **All other settings replace** — the highest-priority layer wins.

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

Custom stages plug in via `layer.pipeline()`:

```python
def pipeline(self) -> Pipeline:
    return (
        Pipeline("mylayer")
        .pipe(LogStage("pre"))
        .pipe(ValidateStage({"my.key": lambda v: isinstance(v, bool)}))
        .pipe(LogStage("post"))
    )
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

Three buses, one router — no direct cross-module imports:

```
EventBus   — fire-and-forget; zero or many subscribers
  LayerAppliedEvent(layer_name, key_count)
  ConfigErrorEvent(error_msg, layer_name)
  ThemeChangedEvent(theme_name)
  BindingRegisteredEvent(key, command, mode)
  ContextSwitchedEvent(old_context, new_context)   [v5+]
  HealthReportReadyEvent(ok, error_count, …)       [v5+]

CommandBus — imperative; exactly one handler; may fail
  ApplyLayerCommand(layer_name, priority)
  ReloadConfigCommand(reason)
  SetOptionCommand(key, value)

QueryBus   — request/response; exactly one handler; returns value
  GetMergedConfigQuery()      → Dict[str, Any]
  GetLayerQuery(name)         → Optional[LayerProtocol]
  GetHealthReportQuery()      → Optional[HealthReport]  [v5+]
```

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

Policy chains run *after* `LayerStack.resolve()` and *before*
`ConfigApplier.apply_settings()`. This means even a UserLayer (priority=90)
override can be blocked by a PARANOID policy.

---

## Host Policy System

Per-host overrides are managed via two complementary sources:

```
Source 1 — HostPolicyRegistry (policies/host.py)
  ALWAYS_RULES  → file://* (local HTML)          [always loaded]
  DEV_RULES     → localhost, 127.0.0.1, [::1], *.local  [HOST_POLICY_DEV]
  LOGIN_RULES   → *.google.com, accounts.google.com, *.github.com, *.gitlab.com
  SOCIAL_RULES  → discord.com, *.notion.so, bilibili.com
  MEDIA_RULES   → youtube.com, *.twitch.tv

Source 2 — BehaviorLayer.host_policies() (layers/behavior.py)
  login/social rules as lightweight fallback
  ⚠ Dev/localhost rules removed from BehaviorLayer in v7 (deduplication fix)

Orchestrator applies Source 1 first, then Source 2 for patterns not already
covered by Source 1 — no double application.
```

Controlled in `config.py`:

```python
HOST_POLICY_DEV    = True   # localhost / 127.0.0.1 / [::1] / *.local
HOST_POLICY_LOGIN  = True   # Google, GitHub, GitLab
HOST_POLICY_SOCIAL = True   # Discord, Notion, Bilibili
HOST_POLICY_MEDIA  = True   # YouTube, Twitch
```

---

## Health Check System

`HealthChecker.default()` runs **12 checks** after `apply()`:

| Check                   | Key                                    | Severity |
| ----------------------- | -------------------------------------- | -------- |
| `BlockingEnabledCheck`  | `content.blocking.enabled`             | WARNING  |
| `BlockingListCheck`     | `content.blocking.adblock.lists`       | WARNING  |
| `SearchEngineDefault`   | `url.searchengines["DEFAULT"]`         | ERROR    |
| `SearchEngineUrl`       | All engine URL templates               | ERROR    |
| `WebRTCPolicyCheck`     | `content.webrtc_ip_handling_policy`    | WARNING  |
| `CookieAcceptCheck`     | `content.cookies.accept`               | WARNING  |
| `StartPageCheck`        | `url.start_pages`                      | WARNING  |
| `EditorCommandCheck`    | `editor.command` (list + `{}`)         | ERROR    |
| `DownloadDirCheck`      | `downloads.location.directory`         | WARNING  |
| `TabTitleFormatCheck`   | `tabs.title.format`                    | INFO     |
| `ProxySchemeCheck`      | `content.proxy`                        | ERROR    |
| `ZoomDefaultCheck`      | `zoom.default`                         | ERROR/W  |

Health issues appear in qutebrowser's message bar and the log.

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

| Mode     | Key     | Description                                    |
| -------- | ------- | ---------------------------------------------- |
| default  | `,C0`   | Base settings, no overrides                    |
| work     | `,Cw`   | Corporate tools, Google default engine         |
| research | `,Cr`   | arXiv, Scholar, Wikipedia, Brave engine        |
| media    | `,Cm`   | YouTube, Bilibili, Twitch; autoplay ON         |
| dev      | `,Cd`   | GitHub, MDN, DevDocs, npm, crates.io           |
| writing  | `,Cwt`  | Dict, thesaurus, grammar; minimal UI           |

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
           ├─ build_default_host_registry(
           │      include_dev    = HOST_POLICY_DEV,   ← v7: was missing
           │      include_login  = HOST_POLICY_LOGIN,
           │      include_social = HOST_POLICY_SOCIAL,
           │      include_media  = HOST_POLICY_MEDIA,
           │  )
           └─ LayerStack()
                 ├─ register(BaseLayer())           [p=10]
                 ├─ register(PrivacyLayer())         [p=20]
                 ├─ register(AppearanceLayer())      [p=30]
                 ├─ register(BehaviorLayer())        [p=40]
                 ├─ register(ContextLayer())         [p=45]  ← if LAYERS["context"]
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
    ├─ HealthChecker.default().check(settings) → HealthReport
    ├─ router.emit_health(...)
    ├─ fsm.send(APPLY_DONE) → APPLYING→ACTIVE
    └─ lifecycle.run(POST_APPLY)

orchestrator.apply_host_policies(applier)
    ├─ for rule in HostPolicyRegistry.active():
    │     config.set(k, v, pattern=rule.pattern)
    │     registry_patterns.add(rule.pattern)
    └─ for policy in BehaviorLayer.host_policies():
          if policy.pattern NOT in registry_patterns:
            config.set(k, v, pattern=policy.pattern)
          # ← v7: skip duplicates to avoid double-application
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
Violations of these invariants are bugs.

---

## Extension Points

| What to add             | Where                        | Register in                     |
| ----------------------- | ---------------------------- | ------------------------------- |
| New configuration layer | `layers/myfeature.py`        | `config.py` LAYERS dict         |
| New theme               | `themes/extended.py`         | auto via import                 |
| New merge algorithm     | `strategies/merge.py`        | `build_merge_registry()`        |
| New search engine set   | `strategies/search.py`       | `build_search_registry()`       |
| New privacy policy rule | `policies/content.py`        | `build_content_policy_chain()`  |
| New host exception      | `policies/host.py`           | `build_default_host_registry()` |
| New pipeline stage      | `core/pipeline.py` or inline | `layer.pipeline()`              |
| New lifecycle hook      | `config.py` wiring section   | `@lifecycle.on(phase)`          |
| New FSM event           | `core/state.py` TRANSITIONS  | declare + send()                |
| New context mode        | `layers/context.py`          | `_CONTEXT_TABLE`                |
| New health check        | `core/health.py`             | `HealthChecker.default()`       |

---

## Testing Strategy

Tests are **pure Python** — no qutebrowser process required.
All layer `build()` methods are tested in isolation.

```
tests/
  test_architecture.py   unit tests covering all core modules
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

  test_incremental.py    incremental apply + snapshot tests
    ├── SnapshotStore        record, retrieve, max_history
    ├── IncrementalApplier   delta compute, apply, error handling
    └── integration          full load→record→reload→delta cycle

  test_health.py         health check tests
    ├── all 12 built-in checks
    └── HealthChecker.default()

  test_extensions.py     extension/layer tests
```

Run all tests:

```bash
pytest tests/ -v
# or
python3 -m pytest tests/ -v
```

---

## Changelog

### v7 (current)

**Bug fixes:**

| File | Bug | Fix |
|------|-----|-----|
| `config.py` | `HOST_POLICY_DEV` flag declared but never passed to `build_default_host_registry` — dev rules always applied regardless of the flag | Passed `include_dev=HOST_POLICY_DEV` to factory |
| `policies/host.py` | `build_default_host_registry` had no `include_dev` parameter | Added `include_dev: bool = True` parameter + `DEV_RULES` list |
| `policies/host.py` | `ALWAYS_RULES` contained dev/localhost rules that were *also* in `BehaviorLayer.host_policies()` — silent double-application of same `config.set()` calls | Moved localhost rules to `DEV_RULES`; `ALWAYS_RULES` only contains `file://*` |
| `layers/behavior.py` | `host_policies()` included dev/localhost rules, duplicating `HostPolicyRegistry.DEV_RULES` | Removed localhost/127.0.0.1 entries; added docstring explaining ownership |
| `orchestrator.py` | Both `HostPolicyRegistry` and `BehaviorLayer.host_policies()` applied without deduplication | `apply_host_policies` now tracks registry patterns and skips BehaviorLayer duplicates |
| `orchestrator.py` | Version string said `v5` despite being shipped as part of v6/v7 | Bumped to `v7` |
| `core/pipeline.py` | `ConfigPacket` field `default_factory` args used generic aliases (`ConfigDict`, `dict[str,Any]`, `list[str]`) which are not callable — Pyright strict error | Changed to bare `dict` and `list` |

**Improvements:**

- `policies/host.py`: Added `DEV_RULES` (`[::1]` IPv6 loopback + `*.local` mDNS)
- `policies/host.py`: `HostPolicyRegistry.summary()` now shows enabled/total counts
- `policies/host.py`: `HostPolicyRegistry.active()` return type is now a proper `Iterator[HostRule]` generator method (not a generator expression without annotation)
- `layers/user.py`: `search_engines_merge` branches documented clearly (both branches are valid, distinction is about what the caller provides, not code-path difference)
- `ARCHITECTURE.md`: Merged `ARCHITECTURE_v6_patch.md` — single source of truth for all version history

### v6 (merged from ARCHITECTURE_v6_patch.md)

**Bug fixes:**

| File | Bug | Fix |
|------|-----|-----|
| `layers/base.py` | `downloads.prevent_mixed_content` is not a valid qutebrowser setting | Removed |
| `layers/context.py` | `_resolve_active_mode` never read the `.context` file written by `context_switch.py` | Reads via `_read_context_file(_default_context_file())` at priority 3 |
| `config.py` | `USER_PROXY: str` — type mismatch with `UserLayer._validate_proxy(Optional[str])` | Changed to `Optional[str]` |

**New features:**
- Health checks: `ProxySchemeCheck`, `ZoomDefaultCheck`, `BlockingListCheck` (12 total)
- Context: `WRITING` mode (`,Cwt`)
- Behavior: zoom keybindings (`zi`/`zo`/`z0`/`zz`), `<ctrl-tab>`, `gf`/`wf`, `tc`, `,b`, `<ctrl-y>` in prompt
- Performance: `content.webgl` per profile, `qt.chromium.low_end_device_mode` for LOW, software rendering for LAPTOP
- Base: `tabs.indicator.*`, `tabs.favicons.scale`, `tabs.title.alignment`, `completion.cmd_history_max_items`

### v5

- `ContextSwitchedEvent`, `HealthReportReadyEvent` events
- `GetHealthReportQuery`, `GetMergedConfigQuery` queries
- `ContextLayer` [priority=45] with 5 modes
- `HealthChecker` system (9 checks)
- `MessageRouter.emit_health()` helper
