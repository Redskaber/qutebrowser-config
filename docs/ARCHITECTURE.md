# Architecture Reference

> qutebrowser-config v5 — principled, layered, extensible

---

## Layer Priority Map

```
Priority  Layer           Responsibility
────────────────────────────────────────────────────────────
  10      BaseLayer       Foundational defaults (search engines, hints,
                          tabs, statusbar, session, zoom, aliases)
  20      PrivacyLayer    WebRTC, fingerprinting, cookies, HTTPS,
                          content blocking (STANDARD/HARDENED/PARANOID)
  30      AppearanceLayer Theme rendering: ColorScheme → qutebrowser keys
                          18 built-in themes; font, color, hint overrides
  40      BehaviorLayer   UX keybindings (Vim-style), per-host rules,
                          quickmarks, hints, download, caret mode
  45      ContextLayer    Situational mode: work / research / media / dev
          [NEW v5]        Search engine delta + settings delta per mode
  50      PerformanceLayer Cache tuning, DNS prefetch, rendering (4 profiles)
  90      UserLayer       Personal overrides injected from config.py
                          (editor, start_pages, zoom, search, bindings, aliases)
────────────────────────────────────────────────────────────
```

Higher priority overwrites lower for the same key (except keybindings,
which accumulate across all layers).

---

## Data Flow

```
config.py
  │  reads: THEME, PRIVACY_PROFILE, PERFORMANCE_PROFILE, ACTIVE_CONTEXT, USER_*
  │
  ▼
_build_orchestrator()
  │
  ├─ LayerStack.register(layer)  ← 7 layers sorted by priority
  │
  ▼
ConfigOrchestrator.build()
  │
  ├─ FSM: IDLE → LOADING
  ├─ LifecycleManager.run(PRE_INIT)
  ├─ LayerStack.resolve()
  │     for each layer (priority order):
  │       1. layer.build()          → ConfigDict (pure, no side effects)
  │       2. layer.validate(data)   → List[str] errors
  │       3. ConfigPacket(data)     → data unit
  │       4. layer.pipeline().run() → optional post-process
  │       5. _deep_merge(accumulated, packet.data)
  │
  ├─ FSM: LOADING → VALIDATING → APPLYING
  ├─ LifecycleManager.run(POST_INIT)
  │
  ▼
ConfigOrchestrator.apply(applier)
  │
  ├─ LifecycleManager.run(PRE_APPLY)
  ├─ PolicyChain.evaluate(key, value) per setting → ALLOW/MODIFY/DENY/WARN
  ├─ ConfigApplier.apply_settings(merged_settings)
  │     config.set(key, value)  for each key
  ├─ ConfigApplier.apply_keybindings(all_bindings)
  │     config.bind(key, cmd, mode=mode)
  ├─ ConfigApplier.apply_aliases(aliases)
  │     c.aliases[alias] = cmd
  ├─ MessageRouter.emit(LayerAppliedEvent) per layer
  ├─ HealthChecker.default().check(settings)  ← 9 checks
  ├─ FSM: APPLYING → ACTIVE
  ├─ LifecycleManager.run(POST_APPLY)
  │
  ▼
ConfigOrchestrator.apply_host_policies(applier)
  │
  ├─ HostPolicyRegistry.active() → per-pattern rules
  │     config.set(key, value, pattern=...)
  └─ BehaviorLayer.host_policies() → legacy rules
```

---

## Merge Semantics

The `LayerStack._deep_merge()` function controls how layers combine:

| Value Type | Key Context           | Merge Rule                |
| ---------- | --------------------- | ------------------------- |
| `dict`     | any                   | recursive deep-merge      |
| `list`     | `"keybindings"` (top) | **accumulate** (extend)   |
| `list`     | anything else         | **replace** (higher wins) |
| scalar     | any                   | **replace** (higher wins) |

**Keybindings accumulate** because every layer contributes its own subset;
qutebrowser merges them on top of its built-in defaults.

**Settings replace** because they are point values; the highest-priority
layer's value wins outright.

**Search engines** (`url.searchengines`) are a `dict` inside `settings`,
so they deep-merge by key. This means ContextLayer and UserLayer can add
_individual_ engine entries without replacing the whole map.

---

## State Machine (ConfigStateMachine)

```
        START_LOAD      LOAD_DONE       VALIDATE_DONE    APPLY_DONE
IDLE ──────────→ LOADING ──────────→ VALIDATING ──────────→ APPLYING ──────────→ ACTIVE
 │                  │                    │                    │
 │                  └─ LOAD_FAILED ──→ ERROR               APPLY_FAIL ──→ ERROR
 │                                                            │
 └───────────────────── RELOAD ──────────────────────────────┘
```

Transitions are a data-driven table in `core/state.py`.
Each transition fires `on_transition` observers (used by orchestrator for logging).

---

## Communication Protocol (MessageRouter)

Three buses, one router — no direct cross-module imports:

```
EventBus   — fire-and-forget; zero or many subscribers
  LayerAppliedEvent(layer_name, key_count)
  ConfigErrorEvent(error_msg, layer_name)
  ThemeChangedEvent(theme_name)
  BindingRegisteredEvent(key, command, mode)

CommandBus — imperative; exactly one handler; may fail
  ApplyLayerCommand(layer_name, priority)
  ReloadConfigCommand(reason)
  SetOptionCommand(key, value)

QueryBus   — request/response; exactly one handler; returns value
  GetMergedConfigQuery()
  GetLayerQuery(name)
  GetHealthReportQuery()
```

---

## Context Layer (NEW v5)

`ContextLayer` [priority=45] resolves a named situational context into:

1. A **search engine delta** merged on top of base engines
2. A **settings delta** applied as overrides
3. **Context-switching keybindings** (always registered, regardless of context)

### Context Resolution Priority

```
1. ACTIVE_CONTEXT param (from config.py)      ← highest
2. QUTE_CONTEXT environment variable
3. ~/.config/qutebrowser/.context file (written by context_switch.py)
4. ContextMode.DEFAULT                        ← fallback
```

### Runtime Switching

`context_switch.py` (userscript):

1. Writes requested context to `~/.config/qutebrowser/.context`
2. Sends `:config-source` to reload
3. On next load, `ContextLayer._resolve_active_mode()` reads the file

---

## Health Check System

`HealthChecker.default()` runs 9 checks after `apply()`:

| Check Class              | Key Checked                          | Auto-fix? |
| ------------------------ | ------------------------------------ | --------- |
| BlockingEnabledCheck     | `content.blocking.enabled`           | No        |
| SearchEngineDefaultCheck | `url.searchengines["DEFAULT"]`       | No        |
| SearchEngineUrlCheck     | All engine URL templates             | No        |
| WebRTCPolicyCheck        | `content.webrtc_ip_handling_policy`  | No        |
| CookieAcceptCheck        | `content.cookies.accept`             | No        |
| StartPageCheck           | `url.start_pages`                    | No        |
| EditorCommandCheck       | `editor.command` (list + `{}` check) | No        |
| DownloadDirCheck         | `downloads.location.directory`       | No        |
| TabTitleFormatCheck      | `tabs.title.format`                  | No        |

Health issues appear in qutebrowser's message bar and the log. No
configuration is silently mis-applied; errors are visible on `:messages`.

---

## Policy Chain

`PolicyChain` wraps `PolicyAction` decisions around each `config.set()` call:

```python
ALLOW  → apply as-is
MODIFY → apply modified_value instead (e.g. GeolocationPolicy under HARDENED)
WARN   → log warning, apply as-is (e.g. ProxyPolicy under PARANOID)
DENY   → skip this key entirely (e.g. ReadOnlyPolicy)
```

Policies are composable and ordered by `priority` field.

---

## Extension Points (summary)

| What to add                | Where                        | Priority range |
| -------------------------- | ---------------------------- | -------------- |
| New theme                  | `themes/extended.py`         | —              |
| New layer                  | `layers/<name>.py`           | 60–80          |
| New context                | `layers/context.py` table    | —              |
| New per-host rule          | `policies/host.py`           | —              |
| New pipeline stage         | `core/pipeline.py` or inline | —              |
| New search engine set      | `strategies/search.py`       | —              |
| New health check           | `core/health.py`             | —              |
| New lifecycle hook         | `config.py` wiring section   | —              |
| Personal settings override | `config.py` USER\_\* section | —              |
