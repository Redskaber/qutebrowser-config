# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**177 tests · 7 layers · 8 core modules · 4 strategy modules · 4 policy modules · 18 themes · NixOS-ready**

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
          │     ├── ContextLayer     [p=45]  situational mode (work/research/media/dev)  ← NEW v5
          │     ├── PerformanceLayer [p=50]  cache & rendering tuning
          │     └── UserLayer        [p=90]  personal overrides (highest)
          ├── ConfigStateMachine     IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
          ├── MessageRouter          EventBus + CommandBus + QueryBus
          ├── LifecycleManager       PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY
          ├── HostPolicyRegistry     per-host config.set(…, pattern=…) rules
          ├── HealthChecker          post-apply validation (9 built-in checks)  ← v5: +4 checks
          └── IncrementalApplier     delta-only hot reload
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
| **Context/Situation**     | ContextLayer switches browsing mode (work/research/media/dev) via keybinding   |

---

## Context System (NEW v5)

Switch between situational browsing modes at runtime — no restart needed.

| Key   | Context  | Purpose                                     |
| ----- | -------- | ------------------------------------------- |
| `,Cw` | work     | Jira, GitLab, corporate search              |
| `,Cr` | research | arXiv, Scholar, Wikipedia, distraction-free |
| `,Cm` | media    | YouTube, Bilibili, Twitch, autoplay ON      |
| `,Cd` | dev      | GitHub, MDN, crates, npm, DevDocs           |
| `,C0` | default  | Reset to base defaults                      |
| `,Ci` | —        | Show current context in message bar         |

Set `ACTIVE_CONTEXT = "dev"` in config.py to permanently activate a context.
Or use the environment variable: `QUTE_CONTEXT=research qutebrowser`.

---

## Health Checks (v5: 9 checks)

| Check                | Severity | Detects                                         |
| -------------------- | -------- | ----------------------------------------------- |
| `blocking-enabled`   | WARNING  | content.blocking.enabled=False                  |
| `search-default`     | ERROR    | url.searchengines missing DEFAULT key           |
| `search-engine-urls` | WARNING  | Engine URL has no `{}` placeholder (NEW)        |
| `webrtc-policy`      | WARNING  | WebRTC leaking local IP                         |
| `cookie-accept`      | INFO     | Global all-cookies-accepted                     |
| `start-pages`        | WARNING  | url.start_pages is empty                        |
| `editor-command`     | ERROR    | editor.command missing `{}` placeholder (NEW)   |
| `download-dir`       | WARNING  | downloads.location.directory is /tmp (NEW)      |
| `tab-title-format`   | INFO     | tabs.title.format missing {current_title} (NEW) |

---

## Module Reference

### `core/`

| Module           | Responsibility                                                    |
| ---------------- | ----------------------------------------------------------------- |
| `state.py`       | `ConfigStateMachine` — FSM with data-driven transition table      |
| `pipeline.py`    | `ConfigPacket` + `PipeStage` + `Pipeline` — composable transforms |
| `lifecycle.py`   | `LifecycleManager` — ordered hook execution                       |
| `protocol.py`    | `MessageRouter` — `EventBus` + `CommandBus` + `QueryBus`          |
| `layer.py`       | `LayerProtocol` + `LayerStack` + `BaseConfigLayer`                |
| `strategy.py`    | `Strategy` + `Policy` + `PolicyChain` + registry infrastructure   |
| `incremental.py` | `ConfigSnapshot` + `ConfigDiffer` + `IncrementalApplier`          |
| `health.py`      | `HealthChecker` — 9 post-apply validation checks                  |

### `layers/`

| Layer            | Priority | Responsibility                                   |
| ---------------- | -------- | ------------------------------------------------ |
| `base.py`        | 10       | Foundational defaults, search engines, hints     |
| `privacy.py`     | 20       | WebRTC, cookies, HTTPS, content blocking         |
| `appearance.py`  | 30       | Theme, fonts, colors (18 built-in themes)        |
| `behavior.py`    | 40       | UX, keybindings, quickmarks, per-host overrides  |
| `context.py`     | 45       | Situational mode (work/research/media/dev) — NEW |
| `performance.py` | 50       | Cache, DNS prefetch, rendering tuning            |
| `user.py`        | 90       | Personal overrides, injected from config.py      |

### `scripts/` (userscripts)

| Script               | Key    | Purpose                             |
| -------------------- | ------ | ----------------------------------- |
| `open_with.py`       | `,o`   | Open URL with best external app     |
| `readability.py`     | `,R`   | Reader mode                         |
| `search_sel.py`      | `,/`   | Search selection in new tab         |
| `password.py`        | `,p`   | pass integration                    |
| `tab_restore.py`     | —      | Named session save/restore          |
| `context_switch.py`  | `,Cw`… | Switch browsing context — NEW       |
| `gen_keybindings.py` | —      | Auto-generate `docs/KEYBINDINGS.md` |

---

## Testing

```bash
python3 tests/test_architecture.py   # 42 tests
python3 tests/test_incremental.py    # 25 tests
python3 tests/test_extensions.py     # 64 tests
python3 tests/test_health.py         # 46 tests  (v5: +24 from context + new checks)
# Total: 177 tests, 0 failures

# Syntax check
python3 -m py_compile config.py orchestrator.py \
  core/*.py layers/*.py strategies/*.py policies/*.py themes/*.py \
  keybindings/*.py scripts/gen_keybindings.py scripts/context_switch.py
```

---

## Project Structure

```
qutebrowser-config/
├── config.py               ← ONLY file you edit
├── orchestrator.py         ← composition root
│
├── core/                   ← stable architecture
│   ├── pipeline.py         ← ConfigPacket + Pipeline
│   ├── state.py            ← FSM + transitions
│   ├── lifecycle.py        ← LifecycleManager
│   ├── protocol.py         ← MessageRouter (EventBus/CommandBus/QueryBus)
│   ├── layer.py            ← LayerProtocol + LayerStack
│   ├── strategy.py         ← Strategy + Policy + PolicyChain
│   ├── incremental.py      ← delta apply + snapshots
│   └── health.py           ← HealthChecker (9 checks)
│
├── layers/                 ← extend here
│   ├── base.py  [p=10] · privacy.py [p=20] · appearance.py [p=30]
│   ├── behavior.py [p=40] · context.py [p=45] · performance.py [p=50]
│   └── user.py [p=90]
│
├── strategies/  merge.py · profile.py · search.py · download.py
├── policies/    content.py · network.py · security.py · host.py
├── themes/      extended.py  (18 color schemes)
├── keybindings/ catalog.py   (query + conflict detection)
│
├── scripts/
│   ├── install.sh           ← deployment
│   ├── gen_keybindings.py   ← auto-gen KEYBINDINGS.md
│   ├── context_switch.py    ← runtime context switching  ← NEW
│   ├── open_with.py · readability.py · password.py
│   ├── search_sel.py · tab_restore.py
│
├── tests/
│   ├── test_architecture.py (42) · test_incremental.py (25)
│   ├── test_extensions.py (64)  · test_health.py (46)
│
└── docs/
    ├── ARCHITECTURE.md · EXTENDING.md · KEYBINDINGS.md
```

---

## Extending

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

### Switch Context at Runtime

```
,Cw  → work      ,Cr  → research
,Cm  → media     ,Cd  → dev
,C0  → default   ,Ci  → show current
```

Or set in `config.py`: `ACTIVE_CONTEXT = "dev"`

---

## Key Configuration Variables (config.py)

| Variable                    | Type                 | Purpose                                       |
| --------------------------- | -------------------- | --------------------------------------------- |
| `THEME`                     | `str`                | Active color scheme                           |
| `PRIVACY_PROFILE`           | `PrivacyProfile`     | STANDARD / HARDENED / PARANOID                |
| `PERFORMANCE_PROFILE`       | `PerformanceProfile` | BALANCED / HIGH / LOW / LAPTOP                |
| `LEADER_KEY`                | `str`                | Multi-key binding prefix (default `,`)        |
| `ACTIVE_CONTEXT`            | `str \| None`        | Situational context (work/research/media/dev) |
| `LAYERS`                    | `dict[str, bool]`    | Enable/disable individual layers              |
| `USER_EDITOR`               | `list[str] \| None`  | Editor command for :open-editor               |
| `USER_START_PAGES`          | `list[str] \| None`  | Browser start pages                           |
| `USER_ZOOM`                 | `str \| None`        | Default zoom level                            |
| `USER_GITHUB`               | `str`                | GitHub username for `:gh` alias               |
| `USER_SEARCH_ENGINES`       | `dict \| None`       | Additional/override search engines            |
| `USER_SEARCH_ENGINES_MERGE` | `bool`               | True=merge on top, False=replace entirely     |
| `USER_SPELLCHECK`           | `list[str] \| None`  | Spellcheck language codes                     |
| `USER_EXTRA_SETTINGS`       | `dict[str, Any]`     | Escape hatch — any qutebrowser setting        |
| `USER_EXTRA_BINDINGS`       | `list[tuple]`        | Escape hatch — additional keybindings         |
| `USER_EXTRA_ALIASES`        | `dict[str, str]`     | Escape hatch — command aliases                |
