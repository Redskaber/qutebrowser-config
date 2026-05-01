# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**131 tests · 6 layers · 7 core modules · 4 strategy modules · 4 policy modules · 8 extended themes · NixOS-ready**

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Design Principles](#design-principles)
4. [Module Reference](#module-reference)
5. [Configuration Guide](#configuration-guide)
6. [Keybindings Reference](#keybindings-reference)
7. [Themes](#themes)
8. [Privacy Profiles](#privacy-profiles)
9. [Userscripts](#userscripts)
10. [Extending the Architecture](#extending-the-architecture)
11. [Testing](#testing)
12. [Troubleshooting](#troubleshooting)
13. [Changelog](#changelog)

---

## Quick Start

### Standard (any Linux)

```bash
git clone <repo> ~/.config/qutebrowser
cd ~/.config/qutebrowser
./scripts/install.sh --backup
```

For live development (changes take effect on `:config-source`):

```bash
./scripts/install.sh --link
```

### NixOS / home-manager

```nix
imports = [ /path/to/qutebrowser-config/nix/qutebrowser.nix ];
```

### Reload in qutebrowser

```
:config-source
```

or press `,r` (default leader key binding).

---

## Architecture Overview

```
config.py  ← qutebrowser loads ONLY this file
    │
    └── ConfigOrchestrator          (composition root)
          │
          ├── LayerStack ─────────────────── priority-ordered merge pipeline
          │     ├── BaseLayer        [p=10]  foundational defaults
          │     ├── PrivacyLayer     [p=20]  security & tracking protection
          │     ├── AppearanceLayer  [p=30]  theme, fonts, colors
          │     ├── BehaviorLayer    [p=40]  UX, keybindings, per-host rules
          │     ├── PerformanceLayer [p=50]  cache & rendering tuning
          │     └── UserLayer        [p=90]  personal overrides (highest)
          │
          ├── ConfigStateMachine ─────────── lifecycle state tracking
          │     IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
          │              ↘              ↘           ↘
          │             ERROR          ERROR       ERROR
          │               └──── RELOADING ─────────┘
          │
          ├── MessageRouter ──────────────── inter-module communication
          │     ├── EventBus   (pub/sub, zero coupling)
          │     ├── CommandBus (CQRS commands, exactly-one handler)
          │     └── QueryBus   (CQRS queries, exactly-one handler)
          │
          ├── LifecycleManager ───────────── ordered hook execution
          │     PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY
          │     PRE_RELOAD → POST_RELOAD → ON_ERROR → ON_TEARDOWN
          │
          ├── HostPolicyRegistry ─────────── structured per-host rules
          │     categories: dev | login | social | media | general
          │
          └── IncrementalApplier ─────────── delta-only hot reload
                SnapshotStore → ConfigDiffer → apply changed keys only
```

### Data Flow

```
qutebrowser loads config.py
        │
        ▼
_build_orchestrator()
  ├── HostPolicyRegistry   ← structured per-host rules (policies/host.py)
  ├── MessageRouter / LifecycleManager / ConfigStateMachine
  └── LayerStack           ← layers registered by priority
        │
        ▼
orchestrator.build()
  ├── FSM: IDLE → LOADING
  ├── lifecycle: PRE_INIT hooks
  ├── LayerStack.resolve():
  │     for each layer (priority order):
  │       raw   = layer.build()            ← pure: {settings, keybindings, aliases}
  │       errs  = layer.validate(raw)      ← pure: [] or ["error"]
  │       pkt   = ConfigPacket(raw, errs)
  │       pkt   = layer.pipeline().run(pkt)   ← optional per-layer transform
  │       merged = deep_merge(merged, pkt.data)
  ├── FSM: LOADING → VALIDATING → APPLYING
  └── lifecycle: POST_INIT hooks
        │
        ▼
orchestrator.apply(ConfigApplier)
  ├── lifecycle: PRE_APPLY
  ├── applier.apply_settings(merged["settings"])
  │     └── PolicyChain.evaluate(key, value) per key  [optional gate]
  ├── applier.apply_keybindings(merged["keybindings"])
  ├── applier.apply_aliases(merged["aliases"])
  ├── emit LayerAppliedEvent per layer
  ├── FSM: → ACTIVE (or ERROR)
  └── lifecycle: POST_APPLY
        │
        ▼
orchestrator.apply_host_policies(applier)
  ├── HostPolicyRegistry.active() → config.set(k, v, pattern=…)   [structured]
  └── BehaviorLayer.host_policies() → config.set(k, v, pattern=…) [legacy/escape]
```

---

## Design Principles

| Principle                 | Implementation                                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------------- |
| **Dependency Inversion**  | Layers depend on `LayerProtocol`; orchestrator depends on abstractions. No layer imports another. |
| **Single Responsibility** | `pipeline.py` transforms data, `state.py` tracks FSM, `protocol.py` routes messages.              |
| **Open/Closed**           | New layers, stages, strategies, policies, themes register without modifying existing code.        |
| **Layered Architecture**  | Strict priority ordering; higher layers override lower; no circular dependencies.                 |
| **Pipeline / Data Flow**  | Config flows as `ConfigPacket` through composable `PipeStage` chains.                             |
| **State Machine**         | Lifecycle is explicit — no implicit state mutation; transitions are data-driven.                  |
| **Strategy Pattern**      | Privacy profiles, performance profiles, merge algorithms, search engines are interchangeable.     |
| **Policy Chain**          | Validation / gating rules (JS, cookies, WebRTC) compose via Chain of Responsibility.              |
| **Event-Driven / CQRS**   | Cross-module communication via typed events — never direct imports between top-level modules.     |
| **Incremental/Delta**     | Hot-reload computes and applies only changed keys, not the full config.                           |
| **Data-Driven**           | Per-host overrides, search engines, color schemes — expressed as data, not code.                  |

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

### `layers/`

| Layer            | Priority | Description                                                     |
| ---------------- | -------- | --------------------------------------------------------------- |
| `base.py`        | 10       | Foundational defaults; applied first; overridable by all        |
| `privacy.py`     | 20       | WebRTC, cookies, HTTPS, adblock, fingerprinting                 |
| `appearance.py`  | 30       | Themes, fonts, colors                                           |
| `behavior.py`    | 40       | UX, Vim keybindings, per-host policies                          |
| `performance.py` | 50       | Cache, rendering, DNS prefetch                                  |
| `user.py`        | 90       | Personal overrides; driven by `config.py` (never edit directly) |

### `strategies/`

| Module        | Responsibility                                                          |
| ------------- | ----------------------------------------------------------------------- |
| `merge.py`    | LastWins / FirstWins / DeepMerge / ProfileAware config merge algorithms |
| `profile.py`  | `UnifiedProfile` — single knob → (privacy, performance) resolution      |
| `search.py`   | Named search engine sets: base, dev, privacy, academia, chinese, full   |
| `download.py` | Download dispatcher auto-detection: handlr → rifle → xdg-open → none    |

### `policies/`

| Module        | Responsibility                                                             |
| ------------- | -------------------------------------------------------------------------- |
| `content.py`  | JS / Cookie / Autoplay / Canvas / LocalStorage / WebRTC per-profile policy |
| `network.py`  | DNS prefetch / Referrer / Proxy / HTTPS enforcement                        |
| `security.py` | Geolocation / MediaCapture / Notifications / Clipboard / MixedContent      |
| `host.py`     | `HostRule` + `HostPolicyRegistry` — structured per-domain exceptions       |

### `themes/`

| Module        | Responsibility                                                                          |
| ------------- | --------------------------------------------------------------------------------------- |
| `extended.py` | 8 extra color schemes: nord, dracula, solarized-\*, one-dark, everforest, modus-vivendi |

### `keybindings/`

| Module       | Responsibility                                                                 |
| ------------ | ------------------------------------------------------------------------------ |
| `catalog.py` | `KeybindingCatalog` — query, conflict detection, Markdown reference generation |

### `scripts/` (userscripts)

| Script           | Binding       | Description                                       |
| ---------------- | ------------- | ------------------------------------------------- |
| `readability.py` | `,R`          | Reader mode via Mozilla Readability               |
| `password.py`    | `,p` / `,P`   | pass integration (fill / OTP)                     |
| `open_with.py`   | `,o` / `,m`   | Open URL with external app (mpv, zathura, feh, …) |
| `search_sel.py`  | `,/` / `,sg`  | Search selected text in any configured engine     |
| `tab_restore.py` | `,Ss` / `,Sr` | Named session save/restore (plain URL lists)      |

---

## Configuration Guide

**All user-facing options are in `config.py`** — there are two sections:

### CONFIGURATION SECTION (top-level choices)

```python
THEME              = "catppuccin-mocha"          # visual theme
PRIVACY_PROFILE    = PrivacyProfile.STANDARD     # STANDARD | HARDENED | PARANOID
PERFORMANCE_PROFILE= PerformanceProfile.BALANCED # BALANCED | HIGH | LOW | LAPTOP
LEADER_KEY         = ","                         # prefix for multi-key bindings
LAYERS             = {"base": True, ..., "user": True}

HOST_POLICY_LOGIN  = True   # Google/GitHub login cookies
HOST_POLICY_SOCIAL = True   # Discord, Notion, Bilibili
HOST_POLICY_MEDIA  = True   # YouTube, Twitch (autoplay blocked)
```

### USER PREFERENCE SECTION (personal overrides)

```python
USER_EDITOR       = ["kitty", "-e", "nvim", "{}"]   # external editor
USER_START_PAGES  = ["https://www.bilibili.com"]     # start / new-tab page
USER_ZOOM         = None                             # default zoom, e.g. "110%"
USER_SPELLCHECK   = None                             # e.g. ["en-US", "zh-CN"]
USER_SEARCH_ENGINES = None                           # extra search shortcuts
USER_EXTRA_SETTINGS  = {}                            # any qutebrowser key
USER_EXTRA_BINDINGS  = [...]                         # (key, command, mode) tuples
USER_EXTRA_ALIASES   = {}                            # :alias_name = command
```

You **never** need to edit `layers/user.py` — it is a data receiver wired by `config.py`.

---

## Keybindings Reference

### Normal Mode — Core

| Key          | Action                       |
| ------------ | ---------------------------- |
| `f` / `F`    | Hint links / open in new tab |
| `;d` / `;y`  | Hint: download / yank link   |
| `;r`         | Rapid hint: open many tabs   |
| `J` / `K`    | Prev / next tab              |
| `H` / `L`    | Back / forward               |
| `d` / `u`    | Close tab / undo close       |
| `th` / `tl`  | Move tab left / right        |
| `tp` / `tm`  | Pin / mute tab               |
| `gg` / `G`   | Scroll top / bottom          |
| `<ctrl-d/u>` | Half-page down / up          |
| `<alt-1..9>` | Jump to tab 1–9              |
| `yy` / `yt`  | Yank URL / title             |
| `m` / `'`    | Save / load quickmark        |
| `v`          | Enter caret mode             |

### Leader Key (`,` by default)

| Key    | Action                                     |
| ------ | ------------------------------------------ |
| `,r`   | Reload config (`:config-source`)           |
| `,e`   | Edit config (`:config-edit`)               |
| `,j`   | Toggle JavaScript                          |
| `,i`   | Toggle images                              |
| `,c`   | Cycle cookie policy                        |
| `,s`   | Force HTTPS reload                         |
| `,p`   | Open private tab                           |
| `,q`   | Quit / `,Q` quit + save session            |
| `,x`   | Close tab / `,X` undo                      |
| `,y/Y` | Yank URL / to primary                      |
| `,o`   | Open URL with best external app            |
| `,m`   | Open URL in mpv                            |
| `,R`   | Reader mode (readability)                  |
| `,/`   | Search selection (default engine, new tab) |
| `,sg`  | Search selection in Google                 |
| `,sw`  | Search selection in Wikipedia              |
| `,lm`  | Copy as Markdown link `[title](url)`       |
| `gx`   | Open clipboard URL in new tab              |
| `;m`   | Hint: open link in mpv                     |

For the full generated reference with all modes and conflict report:

```bash
python3 -c "
from keybindings.catalog import KeybindingCatalog
from layers.base import BaseLayer
from layers.behavior import BehaviorLayer
from layers.privacy import PrivacyLayer, PrivacyProfile
from layers.user import UserLayer
catalog = KeybindingCatalog.from_layers([
    BaseLayer(), BehaviorLayer(), PrivacyLayer(), UserLayer()
])
print(catalog.reference_all())
print(catalog.conflict_report())
"
```

---

## Themes

### Built-in

| Name               | Style            |
| ------------------ | ---------------- |
| `catppuccin-mocha` | Dark, pastel     |
| `catppuccin-latte` | Light, pastel    |
| `gruvbox-dark`     | Dark, retro warm |
| `tokyo-night`      | Dark, cool blue  |
| `rose-pine`        | Dark, rosewood   |

### Extended (`themes/extended.py`)

| Name              | Style                       |
| ----------------- | --------------------------- |
| `nord`            | Dark, arctic blue           |
| `dracula`         | Dark, purple                |
| `solarized-dark`  | Dark, precision engineered  |
| `solarized-light` | Light, precision engineered |
| `one-dark`        | Dark, Atom-inspired         |
| `everforest-dark` | Dark, nature green          |
| `gruvbox-light`   | Light, retro warm           |
| `modus-vivendi`   | Dark, WCAG AAA accessible   |

Set in `config.py`:

```python
THEME = "nord"
```

### Adding a Custom Theme

```python
# themes/extended.py — add to EXTENDED_THEMES dict:
"my-theme": ColorScheme(
    bg="#1a1b26", bg_alt="#16161e", bg_surface="#24283b",
    fg="#a9b1d6", fg_dim="#565f89", fg_strong="#c0caf5",
    accent="#7aa2f7", accent2="#bb9af7",
    success="#9ece6a", warning="#e0af68", error="#f7768e", info="#7dcfff",
    hint_bg="#1a1b26", hint_fg="#f7768e", hint_border="#7aa2f7",
    select_bg="#283457", select_fg="#c0caf5",
    font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
),
```

---

## Privacy Profiles

| Profile    | Description                                                                                      |
| ---------- | ------------------------------------------------------------------------------------------------ |
| `STANDARD` | Sensible defaults: adblock + EasyList, WebRTC restricted, same-domain referer. Minimal breakage. |
| `HARDENED` | No cookies (default), no local storage, no referer headers, TLS errors blocked.                  |
| `PARANOID` | JS disabled, images disabled, all cookies blocked, Tor proxy (`socks://localhost:9050`).         |

Per-host exceptions for HARDENED / PARANOID: configure `HOST_POLICY_*` flags in `config.py`,
or add custom rules in `policies/host.py`.

---

## Userscripts

### `open_with.py` — Open with External App

Auto-detects the best application based on URL type:

| URL type     | App tried (in order)      |
| ------------ | ------------------------- |
| Video/stream | mpv → vlc → celluloid     |
| Audio        | mpv → vlc                 |
| Image        | imv → feh → eog           |
| PDF          | zathura → evince → okular |
| Fallback     | xdg-open                  |

Bindings: `,o` (auto), `,m` (force mpv), `;m` (hint link → mpv)

### `search_sel.py` — Search Selection

Select text in caret mode (`v`), then:

- `,/` → search in default engine (new tab)
- `,sg` → search in Google
- `,sw` → search in Wikipedia

### `readability.py` — Reader Mode

Strips page chrome, renders article as clean HTML with Catppuccin styling.
Requires: `pip install readability-lxml`
Binding: `,R`

### `password.py` — pass Integration

Fills login forms from `pass` entries. Wayland-native (`wl-copy`), X11 fallback.
Bindings: `,p` (fill) · `,P` (OTP)

### `tab_restore.py` — Named Sessions

Saves / restores named tab sessions as plain URL lists.
Bindings (uncomment in `config.py`):

- `,Ss work` → save current tab(s) as session "work"
- `,Sr work` → restore session "work"
- `,Sl` → list all saved sessions

---

## Extending the Architecture

See [docs/EXTENDING.md](docs/EXTENDING.md) for the full guide.

### Add a Layer

```python
# layers/myfeature.py
from core.layer import BaseConfigLayer

class MyFeatureLayer(BaseConfigLayer):
    name = "myfeature"
    priority = 45          # between behavior(40) and performance(50)

    def _settings(self): return {"some.key": "value"}
    def _keybindings(self): return [(f"{self._leader}x", "some-command", "normal")]
```

Register in `config.py` LAYERS dict + `_build_orchestrator()`.

### Add a Theme

Add a `ColorScheme` entry to `themes/extended.py` → `EXTENDED_THEMES`, then set `THEME = "your-name"`.

### Add a Per-Host Exception

```python
# In config.py USER PREFERENCE SECTION:
# Or directly in policies/host.py for permanent rules.
```

### Add a Userscript Binding

```python
USER_EXTRA_BINDINGS = [
    (",u", "spawn --userscript my_script.py", "normal"),
]
```

---

## Testing

```bash
# Core architecture (67 tests)
python3 tests/test_architecture.py

# Incremental + lifecycle (25 tests)
python3 tests/test_incremental.py

# Extension modules (64 tests)
python3 tests/test_extensions.py

# All with pytest
pip install pytest && pytest tests/ -v

# Syntax check everything
python3 -m py_compile config.py orchestrator.py \
  core/*.py layers/*.py strategies/*.py policies/*.py themes/*.py keybindings/*.py
```

Expected: **156 tests, 0 failures**

---

## Project Structure

```
qutebrowser-config/
│
├── config.py               ← entry point (edit CONFIGURATION + USER PREFERENCE sections)
├── orchestrator.py         ← composition root; wires all modules
│
├── core/                   ← architecture (stable; rarely modified)
│   ├── pipeline.py         ← ConfigPacket + PipeStage + Pipeline
│   ├── state.py            ← ConfigStateMachine + FSM transition table
│   ├── lifecycle.py        ← LifecycleManager + hooks
│   ├── protocol.py         ← MessageRouter (EventBus + CommandBus + QueryBus)
│   ├── layer.py            ← LayerProtocol + LayerStack + BaseConfigLayer
│   ├── strategy.py         ← Strategy + Policy + Registry + PolicyChain
│   └── incremental.py      ← ConfigSnapshot + ConfigDiffer + IncrementalApplier
│
├── layers/                 ← configuration layers (extend here)
│   ├── base.py             [p=10]  foundational defaults
│   ├── privacy.py          [p=20]  blocking, cookies, WebRTC
│   ├── appearance.py       [p=30]  themes, fonts, colors
│   ├── behavior.py         [p=40]  keybindings, per-host overrides
│   ├── performance.py      [p=50]  cache, rendering
│   └── user.py             [p=90]  personal overrides (driven by config.py)
│
├── strategies/             ← pluggable algorithms
│   ├── merge.py            ← LastWins / FirstWins / DeepMerge / ProfileAware
│   ├── profile.py          ← UnifiedProfile → (privacy, perf) resolution
│   ├── search.py           ← named search engine sets
│   └── download.py         ← download dispatcher auto-selection
│
├── policies/               ← declarative policy rules
│   ├── content.py          ← JS, cookies, autoplay, canvas, WebRTC
│   ├── network.py          ← DNS, referrer, proxy, HTTPS
│   ├── security.py         ← geolocation, media, clipboard, mixed-content
│   └── host.py             ← HostRule + HostPolicyRegistry
│
├── themes/                 ← color scheme extensions
│   └── extended.py         ← 8 extra themes
│
├── keybindings/            ← keybinding tooling
│   └── catalog.py          ← query, conflict detection, reference generation
│
├── docs/                   ← documentation
│   ├── ARCHITECTURE.md     ← deep architecture reference
│   ├── EXTENDING.md        ← extension guide for layer / policy / theme authors
│   └── KEYBINDINGS.md      ← full keybinding reference (auto-generatable)
│
├── scripts/                ← userscripts
│   ├── install.sh          ← deployment script
│   ├── readability.py      ← reader mode
│   ├── password.py         ← pass integration
│   ├── open_with.py        ← open URL with external app (mpv, zathura, …)
│   ├── search_sel.py       ← search selected text
│   └── tab_restore.py      ← named session save/restore
│
└── tests/
    ├── test_architecture.py   ← 67 core + layer tests
    ├── test_incremental.py    ← 25 incremental + lifecycle tests
    └── test_extensions.py     ← 64 strategy + policy + theme + catalog tests
```

---

## Troubleshooting

### `Error while loading config.py` in qutebrowser log

This is qutebrowser's own message when any `config.set()` call fails.
Check `:messages` in qutebrowser, or run:

```bash
python3 -m py_compile config.py && echo "syntax ok"
```

### Keybinding not working

1. Check for conflicts: `python3 -c "from keybindings.catalog import ...; print(catalog.conflict_report())"`
2. Ensure the binding mode is correct (`"normal"`, `"insert"`, `"command"`, …)
3. Run `:bind` in qutebrowser to see all active bindings

### Theme not found

Ensure `themes/extended.py` is deployed and `themes/__init__.py` exists.
Check that `register_all_themes()` is called before `AppearanceLayer` is instantiated.

### Privacy keybindings use wrong leader key

Ensure `PrivacyLayer` is constructed with `leader=LEADER_KEY` in `_build_orchestrator()`.

### FSM `no transition` WARNING

This was a v1 bug (spurious `APPLY_START` event). Fixed in v2+.
If you see it in v3, a custom lifecycle hook is sending an unexpected event.

---

## Changelog

### v3 (current)

**New modules:**

- `strategies/` — merge, profile (UnifiedProfile), search engine sets, download dispatcher
- `policies/` — content, network, security, host (HostPolicyRegistry)
- `themes/extended.py` — 8 additional color schemes
- `keybindings/catalog.py` — query, conflict detection, reference generation
- `scripts/open_with.py` — open URL with best external app
- `scripts/search_sel.py` — search selected text
- `scripts/tab_restore.py` — named session save/restore

**Architectural changes:**

- `UserLayer` is now parameter-injected; users never edit `layers/user.py`
- `config.py` exposes full USER PREFERENCE SECTION (8 knobs)
- `ConfigOrchestrator` integrates `HostPolicyRegistry` alongside BehaviorLayer
- `ConfigApplier.apply_settings()` accepts optional `PolicyChain` for per-key gating
- `install.sh` updated to deploy all new package directories
- 64 new tests (total: 156)

### v2

- FSM spurious APPLY_START WARNING fixed
- Dead duplicate code in `state.py` removed
- `PrivacyLayer` leader-key parameterisation
- `ValidateStage` fixed to inspect `packet.data["settings"]` correctly
- `orchestrator.summary()` logs actual setting counts
