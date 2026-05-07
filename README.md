# qutebrowser-config

> A principled, layered qutebrowser configuration — built like software, not a script.

**450+ tests · 9 layers · 10 core modules · 4 strategy modules · 4 policy modules · 18+ themes · NixOS-ready**

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
    ├── QutebrowserApplier         concrete bridge → qutebrowser config/c API  ← v12
    │
    └── ConfigOrchestrator          (composition root)
          ├── LayerStack             priority-ordered merge pipeline
          │     ├── BaseLayer        [p=10]  foundational defaults
          │     ├── PrivacyLayer     [p=20]  security & tracking protection
          │     ├── NetworkLayer     [p=27]  proxy/DNS/TLS configuration    ← v14/v15
          │     ├── AppearanceLayer  [p=30]  theme, fonts, colors
          │     ├── BehaviorLayer    [p=40]  UX, keybindings, per-host rules
          │     ├── ContextLayer     [p=45]  situational mode (work/research/media/dev/…)
          │     ├── PerformanceLayer [p=50]  cache & rendering tuning
          │     ├── SessionLayer     [p=55]  time-aware mode (day/evening/night/focus/…)
          │     ├── ComposeLayer     [p=60+] named layer bundles (any children)  ← v13
          │     └── UserLayer        [p=90]  personal overrides (highest)
          ├── ConfigStateMachine     IDLE → LOADING → VALIDATING → APPLYING → ACTIVE
          ├── MessageRouter          EventBus + CommandBus + QueryBus
          │     └── EventFilter      middleware chain (log/dedupe/throttle/filter)  ← v13
          ├── LifecycleManager       PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY → …
          ├── HostPolicyRegistry     per-host config.set(…, pattern=…) rules
          ├── HealthChecker          post-apply validation (21 built-in checks)
          ├── ConfigValidator        schema validation at build time  ← v13
          ├── IncrementalApplier     delta-only hot reload (wired into reload())
          ├── LayerHotSwap           surgical layer replacement (diff-only apply)  ← v13
          │     └── _WrappedHotSwap  orchestrator-level wrapper (events + audit)  ← v15
          └── AuditLog               ring-buffer audit trail (capacity=512)
```

---

## Quick Configuration Reference

Edit **only** the `CONFIGURATION SECTION` and `USER PREFERENCE SECTION` at the top of `config.py`:

| Variable               | Type       | Default    | Description                       |
| ---------------------- | ---------- | ---------- | --------------------------------- |
| `THEME`                | str        | `"glass"`  | Active color theme                |
| `PRIVACY_PROFILE`      | enum       | `STANDARD` | Privacy hardening level           |
| `PERFORMANCE_PROFILE`  | enum       | `BALANCED` | Cache/rendering tuning            |
| `LEADER_KEY`           | str        | `","`      | Multi-key binding prefix          |
| `ACTIVE_CONTEXT`       | str\|None  | `None`     | Situational browser mode          |
| `ACTIVE_SESSION`       | str\|None  | `None`     | Time-aware session                |
| `NETWORK_MODE`         | str\|None  | `None`     | Proxy/DNS mode ← **v14**          |
| `USER_DARK_MODE`       | str\|None  | `None`     | Web dark mode algorithm ← **v14** |
| `USER_PDF_VIEWER`      | bool\|None | `None`     | PDF.js enable/disable ← **v14**   |
| `USER_NEW_TAB_PAGE`    | str\|None  | `None`     | New tab URL ← **v14**             |
| `USER_TAB_BAR_PADDING` | dict\|None | `None`     | Tab bar padding ← **v14**         |

---

## New in v16

### Bug fix — `_WrappedHotSwap` now propagates change count

**Before v16**, `_last_hot_swap_result["changes"]` was always an empty list and
`HotSwapCompletedEvent.changes` was always `[]`, even when keys actually changed.
The lambda passed to `_execute()` was calling `LayerHotSwap.swap()` but discarding
its `HotSwapResult` return value.

**After v16**, the `HotSwapResult` is captured and its `.changes` (int) and
`.errors` are forwarded to the event and stored result:

```python
# From :py after a hot-swap:
status = router.ask(GetHotSwapStatusQuery())
# → {"operation": "swap", "layer_name": "network", "ok": True,
#    "changes": 3, "errors": [], "duration_ms": 0.4}
#                  ^^^^ now correctly populated
```

### Bug fix — accurate `old_session` / `old_mode` in protocol events

**Before v16**, `SessionChangedEvent.old_session` and
`NetworkModeChangedEvent.old_mode` were always `"unknown"`, even after the first
hot-swap that transitioned from a real mode.

**After v16**, the orchestrator tracks `_active_session` and
`_active_network_mode` and emits the actual previous value:

```python
# Startup:  old_session="unknown"  → new_session="evening"
# Hot-swap: old_session="evening"  → new_session="night"   ← now correct
```

### Improvement — `deep_merge` public API in `core/pipeline.py`

`_deep_merge` is now exposed as the public `deep_merge` function and included in
`__all__`. External code that was using `# type: ignore[private]` to import
`_deep_merge` should switch to `deep_merge`.

---

## New in v15

### SessionChangedEvent — first-class session observability

`SessionChangedEvent` is now a proper protocol event (mirrors `ContextSwitchedEvent`).
Before v15, session startup only produced an audit log entry.

```python
# In config.py (already wired):
def _on_session_changed(e: Event) -> None:
    if isinstance(e, SessionChangedEvent):
        logger.info("[Session] mode=%s  source=%s", e.new_session, e.source)

router.events.subscribe(SessionChangedEvent, _on_session_changed)
```

### orchestrator.hot_swap — lazy Open/Closed wrapper

The `orchestrator.hot_swap` property returns a `_WrappedHotSwap` that adds
audit, event emission, and result storage to `LayerHotSwap` without modifying it:

```python
# Swap network layer at runtime (available via :py in qutebrowser)
from layers.network import NetworkLayer
_orchestrator.hot_swap.swap("network", NetworkLayer(mode="tor"))

# Check result
status = router.ask(GetHotSwapStatusQuery())
# → {"operation": "swap", "layer_name": "network", "ok": True, ...}
```

### GetActiveSessionQuery — new query

```python
session = router.ask(GetActiveSessionQuery())   # → "night"
```

### NetworkLayer v15 fixes

- **Bug fix:** URL overrides (`socks5_url=`, `http_url=`, `tor_url=`) no longer
  mutate the module-level `_NETWORK_TABLE`. Each instance builds its own copy.
- `active_spec` property added.
- `available_modes()` classmethod added.
- `describe()` now includes `proxy=…` value.
- `__repr__` includes mode and priority.

### diagnostics.py — network command

```bash
python3 scripts/diagnostics.py network
python3 scripts/diagnostics.py network --network tor
python3 scripts/diagnostics.py diff --label-a pre-reload --label-b post-reload
```

---

## New in v14

### NetworkLayer — declarative proxy/DNS management

A dedicated layer (priority=27) that centralises all network routing configuration:

```python
# In config.py CONFIGURATION SECTION:
NETWORK_MODE = "socks5"    # uses socks5://127.0.0.1:7897 (Clash/V2ray default)
# NETWORK_MODE = "tor"     # routes through Tor (127.0.0.1:9050)
# NETWORK_MODE = "direct"  # no proxy; direct connection
# NETWORK_MODE = "system"  # OS-level proxy (default)
```

**Runtime keybindings (`,N` prefix):**

| Key   | Mode   | Description                             |
| ----- | ------ | --------------------------------------- |
| `,Nn` | direct | No proxy; direct connection             |
| `,Ns` | system | OS-level proxy (default)                |
| `,N5` | socks5 | SOCKS5 via 127.0.0.1:7897 (Clash/Verge) |
| `,Nh` | http   | HTTP proxy via 127.0.0.1:7890           |
| `,Nt` | tor    | Tor SOCKS5 via 127.0.0.1:9050           |
| `,Ni` | —      | Show current proxy value                |

### UserLayer v14 params

| Variable               | Type       | Default | Description                                             |
| ---------------------- | ---------- | ------- | ------------------------------------------------------- |
| `USER_DARK_MODE`       | str\|None  | `None`  | `"off"` / `"simple"` / `"mediumLight"` / `"aggressive"` |
| `USER_PDF_VIEWER`      | bool\|None | `None`  | `True` = PDF.js; `False` = download                     |
| `USER_NEW_TAB_PAGE`    | str\|None  | `None`  | URL for new tab (url.default_page)                      |
| `USER_TAB_BAR_PADDING` | dict\|None | `None`  | `{"top":0,"bottom":0,"left":5,"right":5}`               |

---

## Layer Priority Table

| Layer       | Priority | Purpose                                   |
| ----------- | -------- | ----------------------------------------- |
| base        | 10       | Foundational defaults                     |
| privacy     | 20       | Security & tracking protection            |
| **network** | **27**   | **Proxy/DNS/TLS configuration ← v14/v15** |
| appearance  | 30       | Themes, fonts, colors                     |
| behavior    | 40       | UX, keybindings                           |
| context     | 45       | Situational modes                         |
| performance | 50       | Cache, rendering                          |
| session     | 55       | Time-aware modes                          |
| compose     | 60+      | Named layer bundles                       |
| _(custom)_  | 60–80    | Recommended range for user layers         |
| user        | 90       | Personal overrides (always wins)          |

---

## Keybinding Quick Reference

| Prefix | Scope       | Bindings                                                                                                          |
| ------ | ----------- | ----------------------------------------------------------------------------------------------------------------- |
| `,C`   | Context     | `,Cw` (work) `,Cr` (research) `,Cm` (media) `,Cd` (dev) `,C0` (reset) `,Ci` (show)                                |
| `,S`   | Session     | `,Sd` (day) `,Se` (evening) `,Sn` (night) `,Sf` (focus) `,Sc` (commute) `,Sp` (present) `,S0` (auto) `,Si` (show) |
| `,N`   | **Network** | **`,Nn` (direct) `,Ns` (system) `,N5` (socks5) `,Nh` (http) `,Nt` (tor) `,Ni` (show)**                            |
| `,j`   | Privacy     | Toggle JavaScript                                                                                                 |
| `,i`   | Privacy     | Toggle content blocking                                                                                           |
| `,c`   | Privacy     | Cycle cookie policy                                                                                               |
| `,R`   | Readability | Toggle readability mode                                                                                           |
| `,p/P` | Password    | Fill password / OTP                                                                                               |
| `,r`   | Config      | Reload configuration                                                                                              |

---

## Audit Trail & Observability

```python
# From qutebrowser :py session:
_orchestrator.audit_trail(last_n=20)       # structured lifecycle log
_orchestrator.metrics_summary(last_n=10)   # timing table
_orchestrator.summary()                    # full status (v16: network + hot-swap changes)

# Via QueryBus:
router.ask(GetMergedConfigQuery())         # merged settings dict
router.ask(GetActiveNetworkQuery())        # current proxy value  ← v14/v15
router.ask(GetHotSwapStatusQuery())        # last hot-swap result ← v14/v15
router.ask(GetActiveSessionQuery())        # current session mode ← v15
```

---

## Testing

```bash
# All tests
python3 -m pytest tests/ -v

# v16 suite only
python3 -m pytest tests/test_v16.py -v

# Quick smoke
python3 scripts/diagnostics.py summary
```

**Total: 450+ tests. All run without a live qutebrowser instance.**

---

## CLI Diagnostics (v15)

```bash
python3 scripts/diagnostics.py summary                       # full report
python3 scripts/diagnostics.py layers                        # layer stack
python3 scripts/diagnostics.py health                        # health checks
python3 scripts/diagnostics.py network                       # network modes ← v15
python3 scripts/diagnostics.py network --network tor         # with active mode ← v15
python3 scripts/diagnostics.py sessions                      # session modes
python3 scripts/diagnostics.py contexts                      # context modes
python3 scripts/diagnostics.py themes                        # registered themes
python3 scripts/diagnostics.py keybindings                   # keybinding table
python3 scripts/diagnostics.py diff                          # snapshot diff ← v15
python3 scripts/diagnostics.py audit                         # audit log
```

---

## File Layout

```
config.py            ← Entry point (EDIT ONLY THIS FILE)
layers/
  base.py       [p=10]   foundational defaults
  privacy.py    [p=20]   security & tracking protection
  network.py    [p=27]   proxy/DNS/TLS  ← v14/v15
  appearance.py [p=30]   themes, fonts, colors
  behavior.py   [p=40]   UX, keybindings
  context.py    [p=45]   situational modes
  performance.py [p=50]  cache, rendering
  session.py    [p=55]   time-aware modes
  user.py       [p=90]   personal overrides (edit via config.py)
core/
  types.py layer.py pipeline.py state.py lifecycle.py
  protocol.py strategy.py health.py incremental.py
  audit.py metrics.py compose.py event_filter.py
  hot_swap.py hot_swap_events.py validator.py
policies/   host.py network.py security.py content.py
strategies/ merge.py profile.py search.py download.py
themes/     extended.py
keybindings/ catalog.py
scripts/    diagnostics.py gen_keybindings.py install.sh
```
