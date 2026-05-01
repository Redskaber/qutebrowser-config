# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**197 tests · 7 layers · 8 core modules · 4 strategy modules · 4 policy modules · 18+ themes · NixOS-ready**

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
          │     ├── ContextLayer     [p=45]  situational mode (work/research/media/dev/writing)
          │     ├── PerformanceLayer [p=50]  cache & rendering tuning
          │     └── UserLayer        [p=90]  personal overrides (highest)
          ├── ConfigStateMachine     IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
          ├── MessageRouter          EventBus + CommandBus + QueryBus
          ├── LifecycleManager       PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY
          ├── HostPolicyRegistry     per-host config.set(…, pattern=…) rules
          ├── HealthChecker          post-apply validation (12 built-in checks)
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
| **Context/Situation**     | ContextLayer switches browsing mode at runtime via keybinding                  |

---

## Context System

Switch between situational browsing modes at runtime — no restart needed.

| Key    | Context  | Purpose                                             |
| ------ | -------- | --------------------------------------------------- |
| `,Cw`  | work     | Jira, GitLab, corporate search                      |
| `,Cr`  | research | arXiv, Scholar, Wikipedia, distraction-free         |
| `,Cm`  | media    | YouTube, Bilibili, Twitch, autoplay ON              |
| `,Cd`  | dev      | GitHub, MDN, crates, npm, DevDocs                   |
| `,Cwt` | writing  | Dict, Thesaurus, Grammarly, focus mode ← **NEW v6** |
| `,C0`  | default  | Reset to base defaults                              |
| `,Ci`  | —        | Show current context + description in message bar   |

Set `ACTIVE_CONTEXT = "dev"` in config.py to permanently activate a context.
Or use the environment variable: `QUTE_CONTEXT=research qutebrowser`.
Or switch at runtime — the choice persists in `~/.config/qutebrowser/.context`.

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
│   └── health.py           ← HealthChecker (12 checks)
│
├── layers/                 ← extend here
│   ├── base.py  [p=10] · privacy.py [p=20] · appearance.py [p=30]
│   ├── behavior.py [p=40] · context.py [p=45] · performance.py [p=50]
│   └── user.py [p=90]
│
├── strategies/  merge.py · profile.py · search.py · download.py
├── policies/    content.py · network.py · security.py · host.py
├── themes/      extended.py  (18+ color schemes)
├── keybindings/ catalog.py   (query + conflict detection)
│
├── scripts/
│   ├── install.sh           ← deployment
│   ├── gen_keybindings.py   ← auto-gen KEYBINDINGS.md
│   ├── context_switch.py    ← runtime context switching (6 contexts)
│   ├── open_with.py · readability.py · password.py
│   ├── search_sel.py · tab_restore.py
│
└── tests/
    ├── test_architecture.py · test_incremental.py
    ├── test_extensions.py   · test_health.py
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
,Cw  → work        ,Cr  → research
,Cm  → media       ,Cd  → dev
,Cwt → writing     ,C0  → default
,Ci  → show current context
```

---

## Key Configuration Variables (config.py)

| Variable                    | Type                 | Purpose                                               |
| --------------------------- | -------------------- | ----------------------------------------------------- |
| `THEME`                     | `str`                | Active color scheme                                   |
| `PRIVACY_PROFILE`           | `PrivacyProfile`     | STANDARD / HARDENED / PARANOID                        |
| `PERFORMANCE_PROFILE`       | `PerformanceProfile` | BALANCED / HIGH / LOW / LAPTOP                        |
| `LEADER_KEY`                | `str`                | Multi-key binding prefix (default `,`)                |
| `ACTIVE_CONTEXT`            | `str \| None`        | Situational context (work/research/media/dev/writing) |
| `LAYERS`                    | `dict[str, bool]`    | Enable/disable individual layers                      |
| `USER_EDITOR`               | `list[str] \| None`  | Editor command for :open-editor                       |
| `USER_START_PAGES`          | `list[str] \| None`  | Browser start pages                                   |
| `USER_ZOOM`                 | `str \| None`        | Default zoom level                                    |
| `USER_PROXY`                | `Optional[str]`      | Proxy URL, or None to keep layer default              |
| `USER_GITHUB`               | `str`                | GitHub username for `:gh` alias                       |
| `USER_SEARCH_ENGINES`       | `dict \| None`       | Additional/override search engines                    |
| `USER_SEARCH_ENGINES_MERGE` | `bool`               | True=merge on top, False=replace entirely             |
| `USER_SPELLCHECK`           | `list[str] \| None`  | Spellcheck language codes                             |
| `USER_EXTRA_SETTINGS`       | `dict[str, Any]`     | Escape hatch — any qutebrowser setting                |
| `USER_EXTRA_BINDINGS`       | `list[tuple]`        | Escape hatch — additional keybindings                 |
| `USER_EXTRA_ALIASES`        | `dict[str, str]`     | Escape hatch — command aliases                        |
| `HOST_POLICY_LOGIN`         | `bool`               | Load login cookie exceptions (default True)           |
| `HOST_POLICY_SOCIAL`        | `bool`               | Load social site exceptions (default True)            |
| `HOST_POLICY_MEDIA`         | `bool`               | Load media site exceptions (default True)             |
| `HOST_POLICY_DEV`           | `bool`               | Load localhost/dev exceptions (default True)          |

---

## v6 Changelog

### Bug Fixes

- **`layers/base.py`**: Removed invalid `downloads.prevent_mixed_content` key (not a qutebrowser setting; was silently ignored)
- **`layers/context.py`**: Fixed `_resolve_active_mode` to actually read the `.context` file written by `context_switch.py` (was only checking env var and constructor param — file was written but never read)
- **`config.py`**: Fixed `USER_PROXY` type from `str` to `Optional[str]` to match `UserLayer._validate_proxy` signature

### New Features

- **`layers/context.py`**: Added `WRITING` context (focus mode, dict/thesaurus/grammar search engines)
- **`scripts/context_switch.py`**: Added `writing` as a valid context; improved confirmation messages
- **`layers/behavior.py`**: Added zoom keybindings (`zi`/`zo`/`z0`/`zz`), `<ctrl-tab>` tab cycling, `gf`/`wf` frame hints, `tc` tab-clone, prompt mode `<ctrl-y>` accept, `,b` download list, `<ctrl-shift-tab>`
- **`layers/behavior.py`**: `HostPolicy` made frozen dataclass with `category` field
- **`core/health.py`**: Added `ProxySchemeCheck` (validates proxy URL format), `ZoomDefaultCheck` (validates zoom% format), `BlockingListCheck` (warns if blocking enabled with empty filter list) — total 12 checks
- **`layers/performance.py`**: Added `content.webgl` control per profile, `qt.chromium.low_end_device_mode` for LOW profile, better laptop profile documentation
- **`layers/base.py`**: Added `tabs.indicator.width/padding`, `tabs.favicons.scale`, `tabs.title.alignment`, `tabs.min_width/max_width`, `completion.cmd_history_max_items`, `downloads.location.remember`
- **`config.py`**: Added `HOST_POLICY_DEV` flag, improved `USER_EXTRA_SETTINGS` comments with font override examples

### Documentation

- README.md: Updated test count, added WRITING context, v6 changelog
- ARCHITECTURE.md: v6 section, updated health check count to 12
- KEYBINDINGS.md: Added new v6 bindings section
