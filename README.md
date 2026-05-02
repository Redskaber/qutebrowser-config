# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**209 tests · 7 layers · 8 core modules · 4 strategy modules · 4 policy modules · 18+ themes · NixOS-ready**

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
          ├── LifecycleManager       PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY
          ├── HostPolicyRegistry     per-host config.set(…, pattern=…) rules
          ├── HealthChecker          post-apply validation (15 built-in checks)
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
| **Context/Situation**     | ContextLayer switches browsing mode at runtime via keybinding                  |

---

## Context System

Switch between situational browsing modes at runtime — no restart needed.

| Key    | Context  | Purpose                                            |
| ------ | -------- | -------------------------------------------------- |
| `,Cw`  | work     | Jira, GitLab, corporate search                     |
| `,Cr`  | research | arXiv, Scholar, Wikipedia, distraction-free        |
| `,Cm`  | media    | YouTube, Bilibili, Twitch, autoplay ON             |
| `,Cd`  | dev      | GitHub, MDN, crates, npm, DevDocs                  |
| `,Cwt` | writing  | Dict, Thesaurus, Grammarly, focus mode             |
| `,Cg`  | gaming   | Steam, Twitch, ProtonDB, AreWeGameYet ← **NEW v8** |
| `,C0`  | default  | Reset to base defaults                             |
| `,Ci`  | —        | Show current context + description in message bar  |

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
│   └── health.py           ← HealthChecker (15 checks)
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
│   ├── context_switch.py    ← runtime context switching (7 contexts)
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
,Cwt → writing     ,Cg  → gaming  (v8)
,C0  → default     ,Ci  → show current context
```

---

## Key Configuration Variables (config.py)

| Variable                    | Type                 | Purpose                                                      |
| --------------------------- | -------------------- | ------------------------------------------------------------ |
| `THEME`                     | `str`                | Active color scheme                                          |
| `PRIVACY_PROFILE`           | `PrivacyProfile`     | STANDARD / HARDENED / PARANOID                               |
| `PERFORMANCE_PROFILE`       | `PerformanceProfile` | BALANCED / HIGH / LOW / LAPTOP                               |
| `LEADER_KEY`                | `str`                | Multi-key binding prefix (default `,`)                       |
| `ACTIVE_CONTEXT`            | `str \| None`        | Situational context (work/research/media/dev/writing/gaming) |
| `LAYERS`                    | `dict[str, bool]`    | Enable/disable individual layers                             |
| `USER_EDITOR`               | `list[str] \| None`  | Editor command for :open-editor                              |
| `USER_START_PAGES`          | `list[str] \| None`  | Browser start pages                                          |
| `USER_ZOOM`                 | `str \| None`        | Default zoom level                                           |
| `USER_FONT_FAMILY`          | `str \| None`        | Override UI font family _(v8)_                               |
| `USER_FONT_SIZE`            | `str \| None`        | Override UI font size, e.g. `"10pt"` _(v8)_                  |
| `USER_FONT_SIZE_WEB`        | `str \| None`        | Override web content font size, e.g. `"16px"` _(v8/v9)_      |
| `USER_PROXY`                | `Optional[str]`      | Proxy URL, or None to keep layer default                     |
| `USER_GITHUB`               | `str`                | GitHub username for `:gh` alias                              |
| `USER_SEARCH_ENGINES`       | `dict \| None`       | Additional/override search engines                           |
| `USER_SEARCH_ENGINES_MERGE` | `bool`               | True=merge on top, False=replace entirely                    |
| `USER_SPELLCHECK`           | `list[str] \| None`  | Spellcheck language codes                                    |
| `USER_EXTRA_SETTINGS`       | `dict[str, Any]`     | Escape hatch — any qutebrowser setting                       |
| `USER_EXTRA_BINDINGS`       | `list[tuple]`        | Escape hatch — additional keybindings                        |
| `USER_EXTRA_ALIASES`        | `dict[str, str]`     | Escape hatch — command aliases                               |
| `HOST_POLICY_LOGIN`         | `bool`               | Load login cookie exceptions (default True)                  |
| `HOST_POLICY_SOCIAL`        | `bool`               | Load social site exceptions (default True)                   |
| `HOST_POLICY_MEDIA`         | `bool`               | Load media site exceptions (default True)                    |
| `HOST_POLICY_DEV`           | `bool`               | Load localhost/dev exceptions (default True)                 |

---

## v8 / v9 Changelog

### Bug Fixes

- **`core/health.py`**: `CookieAcceptCheck` severity `WARNING`→`INFO`; `DownloadDirCheck` now catches `/tmp` subdirectories; `SearchEngineDefaultCheck` now errors when `url.searchengines` key is absent entirely
- **`layers/appearance.py`**: `fonts.web.size.default` was hardcoded to `16`; now reads `ColorScheme.font_size_web` via `_parse_px()` helper. Added `fonts.default_family` / `fonts.default_size` to font settings so UserLayer overrides work correctly
- **`layers/user.py`**: Fixed `font_size_web` parse — `str.rstrip("pt px")` stripped individual chars and would silently corrupt values like `"16px"` → `"1"`. Now uses a proper `_parse_size_to_int()` helper. Renamed `font_size_ui` → `font_size_web` for clarity
- **`layers/user.py`**: `editor=[]` now silently skipped (was writing an invalid empty list value)

### New Features

- **`core/health.py`**: 3 new checks — `FontFamilyCheck`, `SpellcheckLangCheck`, `ContentHeaderCheck` (15 total)
- **`layers/context.py`**: `GAMING` context — Steam, ProtonDB, Twitch, AreWeGameYet; `,Cg` binding
- **`layers/user.py`**: First-class `font_family`, `font_size`, `font_size_web` params
- **`config.py`**: `USER_FONT_FAMILY`, `USER_FONT_SIZE`, `USER_FONT_SIZE_WEB` variables; `HealthReportReadyEvent` subscriber
- **`orchestrator.py`**: `reload()` uses `IncrementalApplier` — only changed keys re-applied on `:config-source`

### Tests: 209 pass (was 197)
