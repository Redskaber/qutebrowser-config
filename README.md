# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**315+ tests · 8 layers · 10 core modules · 4 strategy modules · 4 policy modules · 18+ themes · NixOS-ready**

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
    └── ConfigOrchestrator          (composition root)
          ├── LayerStack             priority-ordered merge pipeline
          │     ├── BaseLayer        [p=10]  foundational defaults
          │     ├── PrivacyLayer     [p=20]  security & tracking protection
          │     ├── AppearanceLayer  [p=30]  theme, fonts, colors
          │     ├── BehaviorLayer    [p=40]  UX, keybindings, per-host rules
          │     ├── ContextLayer     [p=45]  situational mode (work/research/media/dev/writing/gaming)
          │     ├── PerformanceLayer [p=50]  cache & rendering tuning
          │     ├── SessionLayer     [p=55]  time-aware mode (day/evening/night/focus/commute/present) ← v11
          │     └── UserLayer        [p=90]  personal overrides (highest)
          ├── ConfigStateMachine     IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
          ├── MessageRouter          EventBus + CommandBus + QueryBus
          ├── LifecycleManager       PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY → PRE_RELOAD → POST_RELOAD
          ├── HostPolicyRegistry     per-host config.set(…, pattern=…) rules
          ├── HealthChecker          post-apply validation (18 built-in checks)
          ├── IncrementalApplier     delta-only hot reload (wired into reload())
          └── AuditLog               ring-buffer audit trail (capacity=512)           ← v11
```

---

## Design Principles

| Principle                 | Implementation                                                                  |
| ------------------------- | ------------------------------------------------------------------------------- |
| **Dependency Inversion**  | Layers depend on `LayerProtocol`; orchestrator depends on abstractions          |
| **Single Responsibility** | `pipeline.py` transforms, `state.py` tracks FSM, `protocol.py` routes           |
| **Open/Closed**           | New layers/stages/strategies/policies register without modifying existing code  |
| **Layered Architecture**  | Strict priority; higher layers override lower; no circular deps                 |
| **Pipeline / Data Flow**  | Config flows as `ConfigPacket` through composable `PipeStage` chains            |
| **State Machine**         | Lifecycle is explicit; transitions are data-driven                              |
| **Strategy Pattern**      | Privacy, performance, merge, search engines are interchangeable                 |
| **Policy Chain**          | Validation rules compose via Chain of Responsibility                            |
| **Event-Driven / CQRS**   | Cross-module via typed events — never direct imports between modules            |
| **Incremental/Delta**     | Hot-reload applies only changed keys                                            |
| **Data-Driven**           | Host rules, search engines, color schemes, contexts, sessions are data not code |
| **Health Checks**         | Post-apply validation catches misconfiguration before it silently fails         |
| **Observable**            | Every phase emits MetricsEvent; reload emits ConfigReloadedEvent                |
| **Audit Trail** ← v11     | Structured ring-buffer log of all config lifecycle events                       |

---

## Context System

Switch between situational browsing modes at runtime — no restart needed.

| Key    | Context  | Purpose                                           |
| ------ | -------- | ------------------------------------------------- |
| `,Cw`  | work     | Jira, GitLab, corporate search                    |
| `,Cr`  | research | arXiv, Scholar, Wikipedia, distraction-free       |
| `,Cm`  | media    | YouTube, Bilibili, Twitch, autoplay ON            |
| `,Cd`  | dev      | GitHub, MDN, crates, npm, DevDocs                 |
| `,Cwt` | writing  | Dict, Thesaurus, Grammarly, focus mode            |
| `,Cg`  | gaming   | Steam, Twitch, ProtonDB, AreWeGameYet             |
| `,C0`  | default  | Reset to base defaults                            |
| `,Ci`  | —        | Show current context + description in message bar |

Set `ACTIVE_CONTEXT = "dev"` in config.py to permanently activate a context.
Or use the environment variable: `QUTE_CONTEXT=research qutebrowser`.
Or switch at runtime — the choice persists in `~/.config/qutebrowser/.context`.

---

## Session System ← v11

Time-aware configuration that adapts to the current moment — no restart needed.

| Key   | Session | When                        | Changes                              |
| ----- | ------- | --------------------------- | ------------------------------------ |
| `,Sd` | day     | 08:00–18:00 (auto)          | Standard defaults; autoplay off      |
| `,Se` | evening | 18:00–22:00 (auto)          | +5% zoom, 18px web font              |
| `,Sn` | night   | 22:00–06:00 (auto)          | 110% zoom, 20px font, minimal chrome |
| `,Sf` | focus   | Deep work (manual)          | Hide statusbar, 18px font, no notifs |
| `,Sc` | commute | Mobile / bandwidth (manual) | No images, no autoplay, 110% zoom    |
| `,Sp` | present | Screen-share (manual)       | 125% zoom, 22px font, full chrome    |
| `,S0` | auto    | Reset to time-derived       | Auto-detects from local time         |
| `,Si` | —       | —                           | Show current session in message bar  |

Set `ACTIVE_SESSION = "focus"` in config.py for a permanent session.
Or use the environment variable: `QUTE_SESSION=night qutebrowser`.
Or switch at runtime — the choice persists in `~/.config/qutebrowser/.session`.

**Session vs Context:**

- **Context** = _what_ you're browsing (search engines + per-site settings)
- **Session** = _how_ the browser behaves right now (zoom, font, chrome density)

Both systems are orthogonal and compose naturally.

---

## Audit Trail ← v11

Every config lifecycle event is recorded in a structured ring-buffer log.

```python
# Access from Python (no qutebrowser needed)
from core.audit import get_audit_log, AuditFilter, AuditLevel

log = get_audit_log()
log.summary(last_n=20)              # last 20 entries
log.errors()                        # ERROR entries only
log.query(AuditFilter.errors_and_warnings())  # WARN+ERROR
log.export_json()                   # JSON array
log.export_markdown()               # Markdown table
```

Or use the CLI:

```bash
python3 scripts/diagnostics.py audit          # text
python3 scripts/diagnostics.py audit --format markdown
```

---

## CLI Diagnostics ← v11

```bash
# Full diagnostic report
python3 scripts/diagnostics.py

# Individual commands
python3 scripts/diagnostics.py layers      # layer stack
python3 scripts/diagnostics.py health      # health checks
python3 scripts/diagnostics.py contexts    # context table
python3 scripts/diagnostics.py sessions    # session table
python3 scripts/diagnostics.py themes      # available themes
python3 scripts/diagnostics.py keybindings # full keybinding reference

# Options
python3 scripts/diagnostics.py health --context dev --theme nord
python3 scripts/diagnostics.py summary --format markdown --out report.md
```

Exit code 0 = clean; 1 = health errors found; 2 = import error.

---

## Configuration

Edit **only** the `CONFIGURATION SECTION` at the top of `config.py`:

```python
# Theme (see themes/extended.py for full list)
THEME = "glass"

# Privacy profile
PRIVACY_PROFILE = PrivacyProfile.STANDARD   # STANDARD | HARDENED | PARANOID

# Performance profile
PERFORMANCE_PROFILE = PerformanceProfile.BALANCED  # BALANCED | HIGH | LOW | LAPTOP

# Context (None = no override; resolved from env/file at runtime)
ACTIVE_CONTEXT: Optional[str] = None

# Session (None = auto-detect from local time)  ← v11
ACTIVE_SESSION: Optional[str] = None

# Layers to load (set False to disable)
LAYERS: dict[str, bool] = {
    "base": True, "privacy": True, "appearance": True,
    "behavior": True, "context": True, "performance": True,
    "session": True,   # v11
    "user": True,
}
```

---

## File Map

```
config.py                   ← entry point (edit CONFIGURATION SECTION only)
core/
  audit.py                  ← AuditLog, AuditEntry, AuditFilter, AuditLevel  [v11]
  health.py                 ← 18 built-in health checks
  incremental.py            ← delta-only hot-reload
  layer.py                  ← LayerProtocol, LayerStack, BaseConfigLayer
  lifecycle.py              ← LifecycleManager, LifecycleHook enum
  pipeline.py               ← ConfigPacket, PipeStage, Pipeline + v11 stages
  protocol.py               ← EventBus, CommandBus, QueryBus, typed messages
  state.py                  ← ConfigStateMachine, TRANSITIONS table
  strategy.py               ← Policy, PolicyChain, StrategyRegistry
  types.py                  ← ConfigDict, Keybind (zero-dep primitives)
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
  download.py               ← download dispatcher selection
  merge.py                  ← merge algorithm strategies
  profile.py                ← unified profile resolution
  search.py                 ← search engine set strategies
themes/
  extended.py               ← 14+ additional color schemes
keybindings/
  catalog.py                ← conflict detection, reference tables
scripts/
  context_switch.py         ← ,C* runtime context switching
  session_switch.py         ← ,S* runtime session switching  [v11]
  diagnostics.py            ← CLI diagnostic tool             [v11]
  gen_keybindings.py        ← auto-generate KEYBINDINGS.md
  open_with.py              ← xdg-open integration
  password.py               ← pass/bitwarden fill
  readability.py            ← reader mode
  search_sel.py             ← search selected text
  tab_restore.py            ← session tab restore
tests/
  test_architecture.py      ← layer/stack/orchestrator integration
  test_extensions.py        ← strategies, policies, themes, catalog
  test_health.py            ← all 18 health checks
  test_incremental.py       ← ConfigDiffer, IncrementalApplier
  test_v10.py               ← v10 fixes (LayerStack._layers, etc.)
  test_v11.py               ← v11 additions (audit, session, pipeline) [v11]
```

---

## Running Tests

```bash
# All tests
python3 -m pytest tests/ -v

# Specific suite
python3 tests/test_v11.py        # v11 additions
python3 tests/test_health.py     # health checks
python3 tests/test_architecture.py

# Quick smoke test
python3 scripts/diagnostics.py health
```

---

## Version History

| Version | Highlights                                                                                                                                                                             |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| v12     | `core/metrics.py` (MetricsCollector/PhaseTimer), pipeline TeeStage/RetryStage/CompositeStage, orchestrator audit_trail()/metrics_summary(), SRP: telemetry extracted from orchestrator |
| v11     | SessionLayer (p=55), AuditLog, pipeline ReduceStage/BranchStage/CacheStage/AuditStage, diagnostics.py CLI, config.py ACTIVE_SESSION                                                    |
| v10     | `core/types.py` (zero-dep primitives), `LayerStack._layers` fix, `core/__init__.py` full exports, conftest.py                                                                          |
| v9      | Incremental reload, event system v2, health checks v2, QueryBus introspection                                                                                                          |
| v8      | Extended themes (nord, dracula, glass…), SessionStore, font overrides                                                                                                                  |
| v7      | `HOST_POLICY_DEV` fix, BehaviorLayer deduplication, keybinding catalog                                                                                                                 |
| v6      | ContextLayer (work/research/media/dev/writing), context_switch.py                                                                                                                      |
