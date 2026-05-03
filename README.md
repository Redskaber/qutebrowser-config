# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**385+ tests · 8 layers · 10 core modules · 4 strategy modules · 4 policy modules · 18+ themes · NixOS-ready**

---

## Quick Start

```bash
git clone <repo> ~/.config/qutebrowser
cd ~/.config/qutebrowser
./scripts/install.sh --backup
# Reload: :config-source  or  ,r
```

For live development:

```bash
./scripts/install.sh --link
```

---

## Architecture Overview

```
config.py  ← qutebrowser loads ONLY this file
    │
    ├── QutebrowserApplier         concrete bridge → qutebrowser config/c API  ← v12.1
    │
    └── ConfigOrchestrator          (composition root)
          ├── LayerStack             priority-ordered merge pipeline
          │     ├── BaseLayer        [p=10]  foundational defaults
          │     ├── PrivacyLayer     [p=20]  security & tracking protection
          │     ├── AppearanceLayer  [p=30]  theme, fonts, colors
          │     ├── BehaviorLayer    [p=40]  UX, keybindings, per-host rules
          │     ├── ContextLayer     [p=45]  situational mode (work/research/media/dev/writing/gaming)
          │     ├── PerformanceLayer [p=50]  cache & rendering tuning
          │     ├── SessionLayer     [p=55]  time-aware mode (day/evening/night/focus/commute/present)
          │     ├── ComposeLayer     [p=60+] named layer bundles (any children)  ← v13
          │     └── UserLayer        [p=90]  personal overrides (highest)
          ├── ConfigStateMachine     IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
          ├── MessageRouter          EventBus + CommandBus + QueryBus
          │     └── EventFilter      middleware chain (log/dedupe/throttle/filter)  ← v13
          ├── LifecycleManager       PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY → PRE_RELOAD → POST_RELOAD
          ├── HostPolicyRegistry     per-host config.set(…, pattern=…) rules
          ├── HealthChecker          post-apply validation (21 built-in checks)
          ├── ConfigValidator        schema validation at build time  ← v13
          ├── IncrementalApplier     delta-only hot reload (wired into reload())
          ├── LayerHotSwap           surgical layer replacement (diff-only apply)  ← v13
          └── AuditLog               ring-buffer audit trail (capacity=512)
```

---

## Design Principles

| Principle                   | Implementation                                                                  |
| --------------------------- | ------------------------------------------------------------------------------- |
| **Dependency Inversion**    | Layers depend on `LayerProtocol`; orchestrator depends on abstractions          |
| **Single Responsibility**   | `pipeline.py` transforms, `state.py` tracks FSM, `protocol.py` routes           |
| **Open/Closed**             | New layers/stages/strategies/policies register without modifying existing code  |
| **Layered Architecture**    | Strict priority; higher layers override lower; no circular deps                 |
| **Pipeline / Data Flow**    | Config flows as `ConfigPacket` through composable `PipeStage` chains            |
| **State Machine**           | Lifecycle is explicit; transitions are data-driven                              |
| **Strategy Pattern**        | Privacy, performance, merge, search engines are interchangeable                 |
| **Policy Chain**            | Validation rules compose via Chain of Responsibility                            |
| **Event-Driven / CQRS**     | Cross-module via typed events — never direct imports between modules            |
| **Incremental/Delta**       | Hot-reload applies only changed keys                                            |
| **Data-Driven**             | Host rules, search engines, color schemes, contexts, sessions are data not code |
| **Health Checks**           | Post-apply validation catches misconfiguration before it silently fails         |
| **Schema Validation** ← v13 | Structural validation (type, range, pattern) separated from semantic checks     |
| **Composable Layers** ← v13 | `ComposeLayer` bundles N layers into one named unit                             |
| **Event Middleware** ← v13  | `EventFilter` adds log/dedupe/throttle without modifying EventBus               |
| **Surgical Hot-Swap** ← v13 | `LayerHotSwap` replaces one layer and applies only the diff                     |
| **Observable**              | Every phase emits MetricsEvent; reload emits ConfigReloadedEvent                |
| **Audit Trail** ← v11       | Structured ring-buffer log of all config lifecycle events                       |

---

## New in v13

### ComposeLayer — bundle layers into named units

```python
from core.compose import compose
from layers.context import ContextLayer
from layers.session import SessionLayer

# Bundle context + session into one priority slot
dev_focus = compose("dev_focus", ContextLayer("dev"), SessionLayer("focus"), priority=57)
stack.register(dev_focus)
```

### EventFilter — middleware for the EventBus

```python
from core.event_filter import EventFilter, LoggingMiddleware, DedupeMiddleware

router.events = (
    EventFilter(router.events)
    .use(LoggingMiddleware())
    .use(DedupeMiddleware(ttl=0.1))
)
```

### LayerHotSwap — surgical layer replacement

```python
from core.hot_swap import LayerHotSwap

hs = LayerHotSwap(stack, apply_fn=lambda k, v: applier.apply_settings({k: v}))
result = hs.swap("context", ContextLayer("research"))
# Only changed keys applied — no full :config-source needed
```

### ConfigValidator — declarative schema validation

```python
from core.validator import ConfigValidator, FieldSpec, COMMON_SCHEMA

validator = ConfigValidator({
    **COMMON_SCHEMA,
    "zoom.default": FieldSpec(type_=str, pattern=r"^\d+%$"),
})
result = validator.validate(settings)
if not result.ok:
    for error in result.errors:
        print(error)
```

---

## Version History

| Version | Highlights                                                                                                                                                                             |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| v13     | `ComposeLayer` (bundle N layers), `EventFilter` (middleware chain), `LayerHotSwap` (surgical diff-apply), `ConfigValidator` (declarative schema), 70 new tests                         |
| v12.1   | **BugFix**: `QutebrowserApplier(ConfigApplier)` concrete class added to `config.py` — fixes `TypeError: ConfigApplier() takes no arguments` crash on startup                           |
| v12     | `core/metrics.py` (MetricsCollector/PhaseTimer), pipeline TeeStage/RetryStage/CompositeStage, orchestrator audit_trail()/metrics_summary(), SRP: telemetry extracted from orchestrator |
| v11     | SessionLayer (p=55), AuditLog, pipeline ReduceStage/BranchStage/CacheStage/AuditStage, diagnostics.py CLI, config.py ACTIVE_SESSION                                                    |
| v10     | `core/types.py` (zero-dep primitives), `LayerStack._layers` fix, `core/__init__.py` full exports, conftest.py                                                                          |
| v9      | Incremental reload, event system v2, health checks v2, QueryBus introspection                                                                                                          |
| v8      | Extended themes (nord, dracula, glass…), SessionStore, font overrides                                                                                                                  |
| v7      | `HOST_POLICY_DEV` fix, BehaviorLayer deduplication, keybinding catalog                                                                                                                 |
| v6      | ContextLayer (work/research/media/dev/writing), context_switch.py                                                                                                                      |

---

## File Map

```
config.py                   ← entry point (edit CONFIGURATION SECTION only)
core/
  audit.py                  ← AuditLog, AuditEntry, AuditFilter, AuditLevel  [v11]
  compose.py                ← ComposeLayer, compose(), LayerCompositionError  [v13]
  event_filter.py           ← EventFilter, Middleware, built-in middleware    [v13]
  health.py                 ← 21 built-in health checks
  hot_swap.py               ← LayerHotSwap, HotSwapResult                    [v13]
  hot_swap_events.py        ← LayerSwappedEvent                              [v13]
  incremental.py            ← delta-only hot-reload
  layer.py                  ← LayerProtocol, LayerStack, BaseConfigLayer
  lifecycle.py              ← LifecycleManager, LifecycleHook enum
  metrics.py                ← MetricsCollector, MetricsSample, PhaseTimer    [v12]
  pipeline.py               ← ConfigPacket, PipeStage, Pipeline + v11+v12 stages
  protocol.py               ← EventBus, CommandBus, QueryBus, typed messages
  state.py                  ← ConfigStateMachine, TRANSITIONS table
  strategy.py               ← Policy, PolicyChain, StrategyRegistry
  types.py                  ← ConfigDict, Keybind (zero-dep primitives)
  validator.py              ← ConfigValidator, FieldSpec, SchemaRegistry     [v13]
layers/
  appearance.py  [p=30]     ← themes, fonts, colors
  base.py        [p=10]     ← foundational defaults, search engines
  behavior.py    [p=40]     ← UX, keybindings, per-host rules
  context.py     [p=45]     ← situational mode (work/research/media/dev/…)
  performance.py [p=50]     ← cache & rendering
  privacy.py     [p=20]     ← security & tracking protection
  session.py     [p=55]     ← time-aware session (day/evening/night/…)  [v11]
  user.py        [p=90]     ← personal overrides
policies/
  content.py                ← content blocking policies
  host.py                   ← per-host exception rules
  network.py                ← network policies
  security.py               ← security policies
strategies/
  download.py               ← download strategy
  merge.py                  ← merge strategies (last-wins, first-wins, deep)
  profile.py                ← UnifiedProfile (DAILY/SECURE/PARANOID/…)
  search.py                 ← search engine strategy
tests/
  test_architecture.py      ← core layer/stack/pipeline tests
  test_extensions.py        ← strategies, policies, themes, catalog tests
  test_health.py            ← health check tests
  test_incremental.py       ← incremental apply tests
  test_v10.py               ← v10 additions
  test_v11.py               ← v11 additions (audit, session, pipeline)
  test_v12.py               ← v12 additions (metrics, TeeStage, RetryStage)
  test_v13.py               ← v13 additions (compose, event_filter, hot_swap, validator)
```

---

## Running Tests

```bash
# All tests
python3 -m pytest tests/ -v

# v13 specifically
python3 tests/test_v13.py

# Quick smoke test
python3 scripts/diagnostics.py health
```
