# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**153 tests · 6 layers · 8 core modules · 4 strategy modules · 4 policy modules · 18 themes · NixOS-ready**

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
          │     ├── PerformanceLayer [p=50]  cache & rendering tuning
          │     └── UserLayer        [p=90]  personal overrides (highest)
          ├── ConfigStateMachine     IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
          ├── MessageRouter          EventBus + CommandBus + QueryBus
          ├── LifecycleManager       PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY
          ├── HostPolicyRegistry     per-host config.set(…, pattern=…) rules
          ├── HealthChecker          post-apply validation (6 built-in checks)
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
| **Data-Driven**           | Host rules, search engines, color schemes are data not code                    |
| **Health Checks**         | Post-apply validation catches misconfiguration before it silently fails        |

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
| `health.py`      | `HealthChecker` + built-in checks — post-apply config validation  |

### `layers/`

| Layer            | Priority | Description                              |
| ---------------- | -------- | ---------------------------------------- |
| `base.py`        | 10       | Foundational defaults; applied first     |
| `privacy.py`     | 20       | WebRTC, cookies, HTTPS, adblock          |
| `appearance.py`  | 30       | Themes, fonts, colors                    |
| `behavior.py`    | 40       | UX, Vim keybindings, per-host overrides  |
| `performance.py` | 50       | Cache, rendering, DNS prefetch           |
| `user.py`        | 90       | Personal overrides (driven by config.py) |

---

## Configuration Guide

Edit only the `CONFIGURATION SECTION` and `USER PREFERENCE SECTION` in `config.py`:

```python
# ── Theme (17 options) ────────────────────────────────────────────────────────
THEME = "catppuccin-mocha"

# ── Privacy profile ───────────────────────────────────────────────────────────
PRIVACY_PROFILE = PrivacyProfile.STANDARD   # STANDARD | HARDENED | PARANOID

# ── Performance profile ───────────────────────────────────────────────────────
PERFORMANCE_PROFILE = PerformanceProfile.BALANCED  # BALANCED | HIGH | LOW | LAPTOP

# ── Leader key ────────────────────────────────────────────────────────────────
LEADER_KEY = ","

# ── Per-host policy categories ────────────────────────────────────────────────
HOST_POLICY_LOGIN  = True   # Google, GitHub, GitLab
HOST_POLICY_SOCIAL = True   # Discord, Notion, Bilibili
HOST_POLICY_MEDIA  = True   # YouTube, Twitch

# ── Personal overrides ────────────────────────────────────────────────────────
USER_EDITOR       = ["kitty", "-e", "nvim", "{}"]
USER_START_PAGES  = ["https://www.bilibili.com"]
USER_ZOOM         = None          # e.g. "110%"
USER_SPELLCHECK   = None          # e.g. ["en-US"]
USER_SEARCH_ENGINES = None        # replaces url.searchengines
USER_EXTRA_SETTINGS = {}          # escape hatch for any qutebrowser setting
USER_EXTRA_BINDINGS = [...]       # (key, command, mode) tuples
USER_EXTRA_ALIASES  = {}          # {name: command}
```

---

## Themes

### Built-in (5)

`catppuccin-mocha` · `catppuccin-latte` · `gruvbox-dark` · `tokyo-night` · `rose-pine`

### Extended (13)

`nord` · `dracula` · `solarized-dark` · `solarized-light` · `one-dark` · `everforest-dark`
`gruvbox-light` · `modus-vivendi` · `catppuccin-macchiato` · `catppuccin-frappe` · `kanagawa` · `palenight`
`glass`

| Theme   | Aesthetic                                                                                                                                                                                      |
| ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `glass` | Modern · minimal · premium — deep cold substrate (`#0d0f14`), frosted-glass panel (`#161b26`), ice-blue accent (`#7ab8f5`), soft-violet secondary (`#9d8fe8`). Desaturated semantics. No neon. |

Set `THEME = "glass"` in `config.py`. Add your own to `themes/extended.py`.

---

## Privacy Profiles

| Profile    | Description                                      | Breakage |
| ---------- | ------------------------------------------------ | -------- |
| `STANDARD` | Adblock, no 3rd-party cookies, WebRTC restricted | minimal  |
| `HARDENED` | No cookies, no local storage, strict TLS         | moderate |
| `PARANOID` | No JS, no images, Tor proxy, all cookies off     | severe   |

---

## Key Bindings (selected)

| Key       | Command                | Layer    |
| --------- | ---------------------- | -------- |
| `J` / `K` | prev / next tab        | behavior |
| `H` / `L` | back / forward         | behavior |
| `f` / `F` | hint / hint all tab    | behavior |
| `,r`      | reload config          | behavior |
| `,j`      | toggle JavaScript      | privacy  |
| `,i`      | toggle images          | privacy  |
| `,o`      | open with external app | user     |
| `,m`      | open with mpv          | user     |
| `,R`      | reader mode            | user     |
| `gx`      | open clipboard URL     | user     |

Full reference: run `python3 scripts/gen_keybindings.py` → `docs/KEYBINDINGS.md`

---

## Userscripts

| Script               | Binding | Description                         |
| -------------------- | ------- | ----------------------------------- |
| `open_with.py`       | `,o`    | Open URL with best external app     |
| `readability.py`     | `,R`    | Reader mode                         |
| `search_sel.py`      | `,/`    | Search selection in new tab         |
| `password.py`        | `,p`    | pass integration                    |
| `tab_restore.py`     | —       | Named session save/restore          |
| `gen_keybindings.py` | —       | Auto-generate `docs/KEYBINDINGS.md` |

---

## Testing

```bash
python3 tests/test_architecture.py   # 42 tests
python3 tests/test_incremental.py    # 25 tests
python3 tests/test_extensions.py     # 64 tests
python3 tests/test_health.py         # 22 tests  (NEW v4)
# Total: 153 tests, 0 failures

# Syntax check
python3 -m py_compile config.py orchestrator.py \
  core/*.py layers/*.py strategies/*.py policies/*.py themes/*.py \
  keybindings/*.py scripts/gen_keybindings.py
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
│   └── health.py           ← HealthChecker  [NEW v4]
│
├── layers/                 ← extend here
│   ├── base.py  [p=10] · privacy.py [p=20] · appearance.py [p=30]
│   ├── behavior.py [p=40] · performance.py [p=50] · user.py [p=90]
│
├── strategies/  merge.py · profile.py · search.py · download.py
├── policies/    content.py · network.py · security.py · host.py
├── themes/      extended.py  (13 extra themes)
├── keybindings/ catalog.py   (query + conflict detection)
│
├── scripts/
│   ├── install.sh          ← deployment
│   ├── gen_keybindings.py  ← auto-gen KEYBINDINGS.md  [NEW v4]
│   ├── open_with.py · readability.py · password.py
│   ├── search_sel.py · tab_restore.py
│
├── tests/
│   ├── test_architecture.py (42) · test_incremental.py (25)
│   ├── test_extensions.py (64)  · test_health.py (22)
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

### Add a Health Check

Subclass `HealthCheck` in `core/health.py`, then `.add(MyCheck())` to `HealthChecker.default()`.

---

## Troubleshooting

**`Error while loading config.py`** → `python3 -m py_compile config.py`

**Keybinding not working** → `python3 scripts/gen_keybindings.py --stdout` to inspect conflicts

**Theme not found** → ensure `themes/extended.py` is deployed + `register_all_themes()` called

**Health warnings in log** → informational only; config still applied. Review the flagged setting.

**FSM `no transition` WARNING** → a lifecycle hook is sending an unexpected event; check `@lifecycle.decorator(…)` registrations.

---

## Changelog

### v4 (current)

- **New**: `core/health.py` — `HealthChecker` + 6 built-in checks integrated into `orchestrator.apply()`
- **New**: `scripts/gen_keybindings.py` — auto-generates `docs/KEYBINDINGS.md`
- **Fix**: `appearance.py` — `_font_settings()` now uses `ColorScheme.font_size_ui` (was hard-coded `"10pt"`)
- **Fix**: `behavior.py` — removed invalid `downloads.open_dispatcher: None`
- **Fix**: `privacy.py` — updated Chrome UA version (134→124)
- **New themes**: `catppuccin-macchiato`, `catppuccin-frappe`, `kanagawa`, `palenight`, `glass` (18 total)
  - `glass`: modern · minimal · premium frosted-glass aesthetic; deep cold substrate + ice-blue accent
- **New bindings**: prompt mode, hint escape, window management (`,n`, `,N`)
- **New engines**: `npm`, `dh` (Docker Hub), `tf` (Terraform) in dev search set
- **22 new tests** (total: **153**)

### v3

- `strategies/` — merge, profile, search, download
- `policies/` — content, network, security, host
- 8 extended themes · keybinding catalog · 3 userscripts
- 64 new tests (total: 131)

### v2

- FSM spurious `APPLY_START` WARNING fixed
- `PrivacyLayer` leader-key parameterisation
- `ValidateStage` fixed to inspect nested `packet.data["settings"]`
