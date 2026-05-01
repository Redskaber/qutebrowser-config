# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**67 tests · 6 layers · 7 core modules · NixOS-ready**

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
9. [Extending the Architecture](#extending-the-architecture)
10. [Testing](#testing)
11. [Troubleshooting](#troubleshooting)
12. [Changelog / Fixes](#changelog--fixes)

---

## Quick Start

### Standard (any Linux)

```bash
git clone <repo> ~/.config/qutebrowser
cd ~/.config/qutebrowser

# Deploy (copies to ~/.config/qutebrowser/)
./scripts/install.sh --backup

# Or symlink for live development (changes take effect on :config-source)
./scripts/install.sh --link
```

### NixOS / home-manager

```nix
# In your home.nix or flake.nix:
imports = [ /path/to/qutebrowser-config/nix/qutebrowser.nix ];
```

Then run `home-manager switch`.

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
          │               └──── RELOAD ────────────┘
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
          └── IncrementalApplier ─────────── delta-only hot reload
                SnapshotStore → ConfigDiffer → apply changed keys only
```

### Data Flow

```
qutebrowser loads config.py
        │
        ▼
_build_orchestrator()
  ├── create MessageRouter, LifecycleManager, ConfigStateMachine
  └── register layers into LayerStack (sorted by priority)
        │
        ▼
orchestrator.build()
  ├── FSM: IDLE → LOADING
  ├── lifecycle: PRE_INIT hooks
  ├── LayerStack.resolve():
  │     for each layer (priority order):
  │       raw  = layer.build()          ← pure: {settings, keybindings, aliases}
  │       errs = layer.validate(raw)    ← pure: [] or ["error msg"]
  │       pkt  = ConfigPacket(raw, errs)
  │       pkt  = layer.pipeline().run(pkt)   ← optional per-layer pipeline
  │       merged = deep_merge(merged, pkt.data)
  ├── FSM: LOADING → VALIDATING → APPLYING
  └── lifecycle: POST_INIT hooks
        │
        ▼
orchestrator.apply(ConfigApplier)
  ├── lifecycle: PRE_APPLY
  ├── applier.apply_settings(merged["settings"])
  ├── applier.apply_keybindings(merged["keybindings"])
  ├── applier.apply_aliases(merged["aliases"])
  ├── emit LayerAppliedEvent per layer
  ├── FSM: → ACTIVE (or ERROR)
  └── lifecycle: POST_APPLY
        │
        ▼
orchestrator.apply_host_policies(applier)
  └── BehaviorLayer.host_policies() → per-host config.set(key, val, pattern=…)
```

---

## Design Principles

| Principle                 | Implementation                                                                                    |
| ------------------------- | ------------------------------------------------------------------------------------------------- |
| **Dependency Inversion**  | Layers depend on `LayerProtocol`; orchestrator depends on abstractions. No layer imports another. |
| **Single Responsibility** | `pipeline.py` transforms data, `state.py` tracks FSM, `protocol.py` routes messages.              |
| **Open/Closed**           | New layers, stages, strategies, and policies register without modifying existing code.            |
| **Layered Architecture**  | Strict priority ordering; higher layers override lower; no circular dependencies.                 |
| **Pipeline / Data Flow**  | Config flows as `ConfigPacket` through composable `PipeStage` chains.                             |
| **State Machine**         | Lifecycle is explicit — no implicit state mutation; transitions are data-driven.                  |
| **Strategy Pattern**      | Privacy profiles, performance profiles, and merge algorithms are interchangeable.                 |
| **Policy Chain**          | Validation rules (read-only, type, range) compose via Chain of Responsibility.                    |
| **Event-Driven / CQRS**   | Cross-module communication via typed events and commands — never direct imports.                  |
| **Incremental/Delta**     | Hot-reload computes and applies only changed keys, not the full config.                           |
| **Data-Driven**           | Per-host overrides, search engines, color schemes — expressed as data, not code.                  |
| **Memento**               | `SnapshotStore` maintains bounded history of config states for rollback and diff.                 |

---

## Module Reference

### `core/`

| Module           | Responsibility                                                           |
| ---------------- | ------------------------------------------------------------------------ |
| `state.py`       | `ConfigStateMachine` — FSM with data-driven transition table             |
| `pipeline.py`    | `ConfigPacket` + `PipeStage` + `Pipeline` — composable transforms        |
| `lifecycle.py`   | `LifecycleManager` — ordered hook execution (PRE/POST_INIT/APPLY/RELOAD) |
| `protocol.py`    | `MessageRouter` — `EventBus` + `CommandBus` + `QueryBus`                 |
| `layer.py`       | `LayerProtocol` + `LayerStack` + `BaseConfigLayer`                       |
| `strategy.py`    | `Strategy` + `Policy` + `PolicyChain` + registry                         |
| `incremental.py` | `ConfigSnapshot` + `ConfigDiffer` + `IncrementalApplier`                 |

### `layers/`

| Layer            | Priority | Description                                              |
| ---------------- | -------- | -------------------------------------------------------- |
| `base.py`        | 10       | Foundational defaults; applied first; overridable by all |
| `privacy.py`     | 20       | WebRTC, cookies, HTTPS, adblock, fingerprinting          |
| `appearance.py`  | 30       | Themes, fonts, colors                                    |
| `behavior.py`    | 40       | UX, Vim keybindings, per-host policies                   |
| `performance.py` | 50       | Cache, rendering, DNS prefetch                           |
| `user.py`        | 90       | Personal one-off overrides; highest priority             |

---

## Configuration Guide

All user-facing options are in the **CONFIGURATION SECTION** at the top of `config.py`:

```python
# ── Theme ──────────────────────────────────────────────────────────────────
# Options: catppuccin-mocha | catppuccin-latte | gruvbox-dark | tokyo-night | rose-pine
THEME = "catppuccin-mocha"

# ── Privacy ────────────────────────────────────────────────────────────────
# Options: PrivacyProfile.STANDARD | HARDENED | PARANOID
PRIVACY_PROFILE = PrivacyProfile.STANDARD

# ── Performance ────────────────────────────────────────────────────────────
# Options: PerformanceProfile.BALANCED | HIGH | LOW | LAPTOP
PERFORMANCE_PROFILE = PerformanceProfile.BALANCED

# ── Leader key ─────────────────────────────────────────────────────────────
LEADER_KEY = ","

# ── Layer enable/disable ───────────────────────────────────────────────────
LAYERS = {
    "base":        True,
    "privacy":     True,
    "appearance":  True,
    "behavior":    True,
    "performance": True,
    "user":        True,
}
```

### Adding Personal Settings

Edit `layers/user.py` — it has the highest priority (90) and wins over everything:

```python
def _settings(self) -> ConfigDict:
    return {
        "editor.command": ["kitty", "-e", "nvim", "{}"],
        "zoom.default": "110%",
        "url.start_pages": ["https://start.duckduckgo.com"],
    }

def _keybindings(self):
    L = self._leader  # respects config.py LEADER_KEY
    return [
        ("gx", "open -t -- {clipboard}", "normal"),
        (f"{L}M", "yank inline [{title}]({url})", "normal"),
    ]
```

---

## Keybindings Reference

### Normal Mode — Navigation

| Key          | Action                     |
| ------------ | -------------------------- |
| `f`          | Open hint (follow link)    |
| `F`          | Open hint in new tab       |
| `;d`         | Hint: download link        |
| `;y`         | Hint: yank link            |
| `;r`         | Rapid hint: open many tabs |
| `J` / `K`    | Prev / next tab            |
| `H` / `L`    | Back / forward             |
| `d`          | Close tab                  |
| `u`          | Undo close tab             |
| `th` / `tl`  | Move tab left / right      |
| `tp`         | Pin tab                    |
| `tm`         | Mute tab                   |
| `gg` / `G`   | Scroll to top / bottom     |
| `<ctrl-d/u>` | Half-page down / up        |
| `yy`         | Yank URL                   |
| `yt`         | Yank title                 |
| `m`          | Save quickmark             |
| `'`          | Load quickmark             |
| `v`          | Enter caret mode           |
| `<alt-1..9>` | Jump to tab 1–9            |

### Leader Key (`,` by default)

| Key         | Action                                          |
| ----------- | ----------------------------------------------- |
| `,r`        | Reload config (`:config-source`)                |
| `,e`        | Edit config (`:config-edit`)                    |
| `,j`        | Toggle JavaScript                               |
| `,i`        | Toggle images                                   |
| `,c`        | Cycle cookie policy (all → no-3rdparty → never) |
| `,s`        | Force HTTPS reload                              |
| `,p`        | Open private tab                                |
| `,y` / `,Y` | Yank URL / yank to primary                      |
| `,x`        | Close tab                                       |
| `,X`        | Undo close                                      |
| `,q`        | Quit                                            |
| `,Q`        | Quit and save session                           |

### Search Engines

| Prefix    | Engine         |
| --------- | -------------- |
| (default) | Brave Search   |
| `g`       | Google         |
| `gh`      | GitHub         |
| `yt`      | YouTube        |
| `w`       | Wikipedia      |
| `ddg`     | DuckDuckGo     |
| `nix`     | NixOS packages |
| `crates`  | crates.io      |
| `pypi`    | PyPI           |
| `mdn`     | MDN Web Docs   |

Usage: `o ddg qutebrowser config`

---

## Themes

| Name               | Style                               |
| ------------------ | ----------------------------------- |
| `catppuccin-mocha` | Dark, pastel — Catppuccin (default) |
| `catppuccin-latte` | Light, pastel — Catppuccin          |
| `gruvbox-dark`     | Dark, retro warm                    |
| `tokyo-night`      | Dark, cool blue/purple              |
| `rose-pine`        | Dark, muted rose                    |

### Adding a Custom Theme

```python
# In layers/appearance.py, add to THEMES dict:
THEMES["my-theme"] = ColorScheme(
    bg="#...", bg_alt="#...", bg_surface="#...",
    fg="#...", fg_dim="#...", fg_strong="#...",
    accent="#...", accent2="#...",
    success="#...", warning="#...", error="#...", info="#...",
    hint_bg="#...", hint_fg="#...", hint_border="#...",
    select_bg="#...", select_fg="#...",
    font_mono="JetBrainsMono Nerd Font",
    font_sans="Noto Sans",
)
```

Then set `THEME = "my-theme"` in `config.py`.

---

## Privacy Profiles

| Profile    | Description                                                                             |
| ---------- | --------------------------------------------------------------------------------------- |
| `STANDARD` | Block 3rd-party cookies, WebRTC leak prevention, adblock. Minimal breakage.             |
| `HARDENED` | No cookies, no local storage, no referer headers. Some sites will break.                |
| `PARANOID` | JS disabled, images disabled, all cookies blocked, routes through Tor. Expect breakage. |

Per-host exceptions for HARDENED / PARANOID belong in `BehaviorLayer.host_policies()`.

---

## Extending the Architecture

### Adding a New Layer

```python
# layers/myfeature.py
from core.layer import BaseConfigLayer

class MyFeatureLayer(BaseConfigLayer):
    name = "myfeature"
    priority = 45          # between behavior(40) and performance(50)
    description = "My custom feature"

    def __init__(self, leader: str = ",") -> None:
        self._leader = leader

    def _settings(self) -> dict:
        return {
            "some.qutebrowser.key": "value",
        }

    def _keybindings(self) -> list:
        L = self._leader
        return [
            (f"{L}x", "some-command", "normal"),
        ]
```

Register in `config.py`:

```python
from layers.myfeature import MyFeatureLayer
# ...
stack.register(MyFeatureLayer(leader=LEADER_KEY))
```

### Adding a Per-Host Policy

```python
# In layers/behavior.py → host_policies():
HostPolicy(
    pattern="*.mysite.com",
    settings={
        "content.javascript.enabled": True,
        "content.cookies.accept": "all",
    },
    description="mysite needs JS and cookies",
),
```

### Adding a Pipeline Stage

```python
from core.pipeline import PipeStage, ConfigPacket

class ExpandEnvVarsStage(PipeStage):
    name = "expand_env"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        import os
        settings = packet.data.get("settings", {})
        expanded = {
            k: os.path.expandvars(v) if isinstance(v, str) else v
            for k, v in settings.items()
        }
        return packet.replace_data({**packet.data, "settings": expanded})
```

### Implementing Incremental Hot-Reload

```python
from core.incremental import IncrementalApplier, SnapshotStore

store   = SnapshotStore(max_history=10)
applier = IncrementalApplier(store)

# First load
applier.record(merged_settings, label="v1")

# On reload — only changed keys are applied
applier.record(new_merged_settings, label="v2")
delta = applier.compute_delta()
errors = applier.apply_delta(delta, apply_fn=config.set)
```

---

## Testing

```bash
# Run architecture tests (42 tests)
python3 tests/test_architecture.py

# Run incremental + lifecycle tests (25 tests)
python3 tests/test_incremental.py

# Run all with pytest
pip install pytest
pytest tests/ -v

# Syntax-check all modules
python3 -m py_compile config.py orchestrator.py core/*.py layers/*.py
```

Expected: **67 tests, 0 failures**

---

## Userscripts

### Readability (Reader Mode)

- **Binding**: `,R`
- Extracts article content using Mozilla's Readability algorithm
- Renders clean HTML with Catppuccin styling
- Requires: `pip install readability-lxml`

### Pass (Password Manager)

- **Binding**: `,p` fill · `,P` OTP
- Integrates with [`pass`](https://passwordstore.org)
- Wayland-native (`wl-copy`) with X11 fallback (`xclip`)

---

## Troubleshooting

### `Error while loading config.py` in qutebrowser log

This is qutebrowser's own error message printed when any `config.set()` call
fails. The most common causes:

1. **Invalid setting key for your qutebrowser version** — check
   [qutebrowser settings reference](https://qutebrowser.org/doc/help/settings.html).
2. **Type mismatch** — e.g. passing a Python `None` where qutebrowser expects
   a specific string enum value.
3. **Adblock package not installed** — `content.blocking.method = "both"` requires
   `pip install qutebrowser[adblock]` or the NixOS `adblock` extra.

Enable debug logging to see the exact failing key:

```
qutebrowser --debug 2>&1 | grep -i error
```

### FSM warning: `no transition from APPLYING on APPLY_START`

This was a bug in the original code — fixed. The spurious `APPLY_START` send
inside `apply()` has been removed. The FSM enters APPLYING state at the end
of `build()` (via `VALIDATE_DONE`); `apply()` drives it to ACTIVE or ERROR.

### `Merged keys: 3` in log looks too small

The number refers to top-level _categories_ in the merged config dict:
`settings`, `keybindings`, and `aliases`. The fixed orchestrator now logs
the actual counts:

```
build() complete: 6 layers  settings=180  bindings=75  aliases=4
```

### Privacy keybindings use wrong leader key

Fixed — `PrivacyLayer` now accepts a `leader` parameter and all bindings use
`self._leader` instead of a hard-coded `","`.

---

## Project Structure

```
qutebrowser-config/
│
├── config.py               ← qutebrowser entry point (edit CONFIGURATION SECTION)
├── orchestrator.py         ← composition root; wires all modules
│
├── core/                   ← architecture modules (stable)
│   ├── __init__.py         ← public API surface
│   ├── pipeline.py         ← ConfigPacket + PipeStage + Pipeline
│   ├── state.py            ← ConfigStateMachine + FSM transition table
│   ├── lifecycle.py        ← LifecycleManager + hooks
│   ├── protocol.py         ← MessageRouter (EventBus + CommandBus + QueryBus)
│   ├── layer.py            ← LayerProtocol + LayerStack + BaseConfigLayer
│   ├── strategy.py         ← Strategy + Policy + Registry + PolicyChain
│   └── incremental.py      ← ConfigSnapshot + ConfigDiffer + IncrementalApplier
│
├── layers/                 ← configuration layers (frequently extended)
│   ├── __init__.py
│   ├── base.py             ← BaseLayer: foundational defaults         [p=10]
│   ├── privacy.py          ← PrivacyLayer: blocking, cookies, WebRTC  [p=20]
│   ├── appearance.py       ← AppearanceLayer: themes, fonts, colors   [p=30]
│   ├── behavior.py         ← BehaviorLayer: keybindings, per-host     [p=40]
│   ├── performance.py      ← PerformanceLayer: cache, rendering        [p=50]
│   └── user.py             ← UserLayer: personal overrides             [p=90]
│
├── scripts/                ← qutebrowser userscripts
│   ├── readability.py      ← reader mode (requires readability-lxml)
│   ├── password.py         ← pass integration (Wayland + X11)
│   └── install.sh          ← deploy script
│
├── nix/
│   └── qutebrowser.nix     ← home-manager module
│
└── tests/
    ├── test_architecture.py   ← 42 core + layer tests
    └── test_incremental.py    ← 25 incremental + lifecycle tests
```

---

## Changelog / Fixes

### v2 (current)

**Bug fixes:**

1. **FSM spurious WARNING** — Removed `fsm.send(ConfigEvent.APPLY_START)` from
   `orchestrator.apply()`. There was no `(APPLYING, APPLY_START)` transition
   defined, so this always emitted `"no transition: APPLYING + APPLY_START"`.
   The FSM correctly enters APPLYING state during `build()`.

2. **Dead duplicate code in `state.py`** — `LifecycleHook` and `LifecycleManager`
   were fully duplicated from `lifecycle.py` (with identical content). The
   duplicates in `state.py` have been removed. All imports now come from
   `core.lifecycle` (where they always should have been).

3. **`TransformStage` key accumulation bug** — `process()` called `packet.with_data(new_data)`
   which _merges_ the new data on top of old data. For transforms that rename
   or restructure keys this left the old keys present alongside the new ones.
   Fixed: `TransformStage` now calls `packet.replace_data(new_data)` which
   replaces the data dict entirely. A new `ConfigPacket.replace_data()` method
   was added alongside the existing `with_data()`.

4. **`PrivacyLayer` hard-coded leader key** — All keybindings used the literal
   string `","` instead of the configured leader key. Fixed: `PrivacyLayer`
   now accepts a `leader` parameter and `config.py` passes `LEADER_KEY` to it.

5. **`ValidateStage` never matched keys** — The privacy pipeline's `ValidateStage`
   looked for `content.blocking.enabled` directly in `packet.data`, but layers
   produce nested data `{"settings": {"content.blocking.enabled": …}}`. Fixed:
   `ValidateStage` now inspects both `packet.data` and `packet.data["settings"]`.

6. **Invalid color values** — `colors.downloads.system.fg/bg` were set to the
   string `"rgb"`, which is not a valid qutebrowser color value and caused
   `"Error while loading config.py"`. These keys are not user-configurable
   (they are internal gradient descriptors); the assignments have been removed.

7. **`UserLayer` missing `leader` param** — Added for consistency with
   `BehaviorLayer` and `PrivacyLayer`.

8. **Missing `core/__init__.py` and `layers/__init__.py`** — Added proper
   package init files so `from core.X import Y` works correctly when
   `core/` and `layers/` are subdirectories.

9. **`config.py` not registering `UserLayer`** — Added `UserLayer` registration.

10. **FSM: added `(IDLE, RELOAD) → LOADING` convenience transition** — Allows
    hot-reload to be triggered from IDLE state (useful in tests and manual flows).

**Improvements:**

- `orchestrator.summary()` now reports `settings=N  bindings=N  aliases=N`
  instead of the misleading `Merged keys: 3`.
- `LayerAppliedEvent.key_count` now reports the number of settings keys rather
  than the number of top-level categories in the packet.
- All docstrings updated to reflect the corrected behaviour.

---

## Environment

Tested on:

- qutebrowser 3.6.3
- Qt 6.10.2 / QtWebEngine 6.10.2 (Chromium 134)
- PyQt6 6.9.0
- Python 3.13.12
- NixOS 25.11 (Xantusia)
- Wayland / Hyprland
