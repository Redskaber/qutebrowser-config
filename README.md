# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**259 tests · 7 layers · 8 core modules · 4 strategy modules · 4 policy modules · 18+ themes · NixOS-ready**

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
          │     └── UserLayer        [p=90]  personal overrides (highest)
          ├── ConfigStateMachine     IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
          ├── MessageRouter          EventBus + CommandBus + QueryBus
          ├── LifecycleManager       PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY → PRE_RELOAD → POST_RELOAD
          ├── HostPolicyRegistry     per-host config.set(…, pattern=…) rules
          ├── HealthChecker          post-apply validation (18 built-in checks)
          └── IncrementalApplier     delta-only hot reload (wired into reload())
```

---

## Design Principles

| Principle                 | Implementation                                                                 |
| ------------------------- | ------------------------------------------------------------------------------ |
| **Dependency Inversion**  | Layers depend on `LayerProtocol`; orchestrator depends on abstractions         |
| **Single Responsibility** | `pipeline.py` transforms, `state.py` tracks FSM, `protocol.py` routes          |
| **Open/Closed**           | New layers/stages/strategies/policies register without modifying existing code |
| **Layered Architecture**  | Strict priority; higher layers override lower; no circular deps                |
| **Pipeline / Data Flow**  | Config flows as `ConfigPacket` through composable `PipeStage` chains           |
| **State Machine**         | Lifecycle is explicit; transitions are data-driven                             |
| **Strategy Pattern**      | Privacy, performance, merge, search engines are interchangeable                |
| **Policy Chain**          | Validation rules compose via Chain of Responsibility                           |
| **Event-Driven / CQRS**   | Cross-module via typed events — never direct imports between modules           |
| **Incremental/Delta**     | Hot-reload applies only changed keys                                           |
| **Data-Driven**           | Host rules, search engines, color schemes, contexts are data not code          |
| **Health Checks**         | Post-apply validation catches misconfiguration before it silently fails        |
| **Observable**            | Every phase emits MetricsEvent; reload emits ConfigReloadedEvent               |

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

## Keybindings (v9 additions)

### Normal mode

| Key          | Action                         |
| ------------ | ------------------------------ |
| `v`          | Enter caret mode               |
| `<ctrl-v>`   | Enter passthrough (single key) |
| `<alt-1..9>` | Jump to tab position 1..9      |
| `,t`         | Open new tab                   |
| `,T`         | Clone current tab              |
| `,q`         | Close tab                      |
| `,Q`         | Close window                   |
| `,/`         | Open find bar                  |
| `,?`         | Open reverse find bar          |
| `<ctrl-d>`   | Scroll down half page          |
| `<ctrl-u>`   | Scroll up half page            |
| `<ctrl-f>`   | Scroll down full page          |
| `<ctrl-b>`   | Scroll up full page            |

### Caret mode (v9)

| Key        | Action                |
| ---------- | --------------------- |
| `H`        | Move to previous word |
| `L`        | Move to next word     |
| `V`        | Toggle line selection |
| `y` / `^C` | Yank selection        |
| `q` / Esc  | Leave caret mode      |

---

## Project Structure

```
qutebrowser-config/
├── config.py               ← ONLY file you edit
├── orchestrator.py         ← composition root
│
├── core/                   ← stable architecture
│   ├── __init__.py         ← full public API exports (v10)
│   ├── pipeline.py         ← ConfigPacket + Pipeline + FilterStage
│   ├── state.py            ← FSM + transitions
│   ├── lifecycle.py        ← LifecycleManager
│   ├── protocol.py         ← MessageRouter (EventBus/CommandBus/QueryBus)
│   ├── layer.py            ← LayerProtocol + LayerStack + _layers (v10 fix)
│   ├── strategy.py         ← Strategy + Policy + PolicyChain
│   ├── incremental.py      ← delta apply + snapshots + rollback
│   └── health.py           ← HealthChecker (21 checks)
│
├── layers/                 ← extend here
│   ├── base.py  [p=10] · privacy.py [p=20] · appearance.py [p=30]
│   ├── behavior.py [p=40] · context.py [p=45] · performance.py [p=50]
│   └── user.py [p=90]
│
├── strategies/             merge.py · profile.py · search.py · download.py
├── policies/               content.py · network.py · security.py · host.py
├── themes/                 extended.py  (18+ color schemes)
├── keybindings/            catalog.py   (query + conflict detection)
│
├── scripts/
│   ├── install.sh           ← deployment
│   ├── gen_keybindings.py   ← auto-gen KEYBINDINGS.md
│   ├── context_switch.py    ← runtime context switching (7 contexts)
│   ├── open_with.py · readability.py · password.py
│   ├── search_sel.py · tab_restore.py
│
└── tests/
    ├── conftest.py          ← sys.path setup for pytest (v10)
    ├── test_architecture.py · test_incremental.py
    ├── test_extensions.py   · test_health.py
    └── test_v10.py          ← v10 regression + feature tests
```

---

## v10 What's New

### Bug Fixes

- **`core/layer.py`** — `LayerStack._layers` property added (alias for `_records`).
  The `GetLayerNamesQuery` handler in `orchestrator.py` referenced a non-existent
  `_layers` attribute; this caused a silent `AttributeError` at runtime.
- **`orchestrator.py`** — `_handle_get_layer_names` variable-shadowing bug fixed.
  The comprehension now uses `rec.layer.name` / `rec.enabled` from the same loop
  variable instead of mixing `layer` and `rec` from different scopes.

### Package Structure

The project now uses the sub-package layout all imports always required:
`core/`, `layers/`, `strategies/`, `policies/`, `themes/`, `keybindings/`.
Previously all files were flat in the root; this caused `ModuleNotFoundError`
on any system that ran tests directly. All 221 prior tests now pass cleanly,
plus 38 new v10 tests (total: **259**).

### Improved

- **`core/__init__.py`** — Exports the full public API surface with `__all__`
  (was empty). `FilterStage` and `LayerRecord` are newly exported.
- **`tests/conftest.py`** — `sys.path` inserted unconditionally; pytest now
  works from any working directory, IDE, or CI runner.
- **`tests/test_v10.py`** — 38 new tests: package imports, `_layers` property,
  `GetLayerNamesQuery` end-to-end, `FilterStage` coverage, `core.__all__` surface.

---

## v9 What's New

### Architecture

- **`protocol.py`** — 5 new events (`ConfigReloadedEvent`, `SnapshotTakenEvent`, `LayerConflictEvent`, `PolicyDeniedEvent`, `MetricsEvent`); 3 new queries (`GetSnapshotQuery`, `GetLayerDiffQuery`, `GetLayerNamesQuery`); `EventBus.unsubscribe_all()` for test isolation
- **`orchestrator.py`** — timing metrics on every phase; host policies re-applied on reload (was missing); stored applier fallback in `reload()`; `PolicyDeniedEvent` emitted on DENY; new QueryBus handlers
- **`incremental.py`** — `apply_delta()` type fix (errors returned, not discarded); `rollback(steps)` added; `ConfigDiffer` promoted to public class; `SnapshotStore.find()`, `.snapshots`, `.clear()` added
- **`health.py`** — 3 new checks; `HealthChecker.with_checks()` factory; `HealthReport.summary()` multi-line categorised output; injectable `extra_checks` in `check()`

### Layers

- **`behavior.py`** — caret mode bindings; passthrough; `<alt-1..9>` tab jumps; `,t`/`,T`/`,q`/`,Q`; `,/`/`,?` find; security settings hardened
- **`base.py`** — PDF viewer, JS alert/prompt, popup blocker, pinned tab settings, fullscreen, GPU rendering, messages timeout

### Config Surface

- `USER_MESSAGES_TIMEOUT` — control notification display time
- `POST_RELOAD` lifecycle hook exposed
- New event subscribers logged (reload stats, metrics, policy denials)

### Add a Theme

Add `ColorScheme(…)` to `themes/extended.py` → `EXTENDED_THEMES`, then set `THEME`.

### Add a Layer (example: work layer at priority 60)

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

### Subscribe to Reload Events (v9)

```python
def _on_reload(e: Event) -> None:
    if isinstance(e, ConfigReloadedEvent):
        logger.info("Reloaded: %d changes in %.1fms", e.changes_count, e.duration_ms)

router.events.subscribe(ConfigReloadedEvent, _on_reload)
```

### Introspect via QueryBus (v9)

```python
snap = router.ask(GetSnapshotQuery(label="pre-reload"))
diff = router.ask(GetLayerDiffQuery(label_a="pre-reload", label_b="post-reload"))
names = router.ask(GetLayerNamesQuery())
```
