# Extending the Configuration

This guide covers every extension point in the architecture.
You should read [ARCHITECTURE.md](ARCHITECTURE.md) first.

---

## Adding a New Layer

Layers are the primary extension mechanism. Create a new file in `layers/`.

```python
# layers/workspace.py
"""
layers/workspace.py
===================
Workspace Layer — project-specific browser environments

Priority: 60 (between performance[50] and user[90])
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple
from core.layer import BaseConfigLayer

ConfigDict = Dict[str, Any]

class WorkspaceLayer(BaseConfigLayer):
    name        = "workspace"
    priority    = 60
    description = "Project-specific search engines and keybindings"

    def __init__(self, leader: str = ",", workspace: str = "default") -> None:
        self._leader    = leader
        self._workspace = workspace

    def _settings(self) -> ConfigDict:
        if self._workspace == "work":
            return {
                "url.searchengines": {
                    "DEFAULT": "https://jira.mycompany.com/issues/?jql=text+~+{}",
                    "jira":    "https://jira.mycompany.com/issues/?jql=text+~+{}",
                    "conf":    "https://confluence.mycompany.com/dosearchsite.action?queryString={}",
                },
            }
        return {}

    def _keybindings(self) -> List[Tuple[str, str, str]]:
        L = self._leader
        if self._workspace == "work":
            return [
                (f"{L}J", "open https://jira.mycompany.com", "normal"),
            ]
        return []
```

Register in `config.py`:

```python
from layers.workspace import WorkspaceLayer

# In _build_orchestrator(), after PerformanceLayer:
if LAYERS.get("workspace"):
    stack.register(WorkspaceLayer(leader=LEADER_KEY, workspace="work"))

# Also add to LAYERS dict:
LAYERS: dict[str, bool] = {
    ...
    "workspace": True,
}
```

**Rules for layer authors:**

- `build()` must be **pure** — no `config.set()` calls, no I/O.
- Never import from another `layers/*` module.
- Always honour the `leader` parameter for keybindings.
- Priority 60–80 is reserved for user-added layers between performance and user.

---

## Adding a Theme

```python
# In themes/extended.py — add to EXTENDED_THEMES:

"my-theme": ColorScheme(
    bg="#1a1b26", bg_alt="#16161e", bg_surface="#24283b",
    fg="#a9b1d6", fg_dim="#565f89", fg_strong="#c0caf5",
    accent="#7aa2f7", accent2="#bb9af7",
    success="#9ece6a", warning="#e0af68", error="#f7768e", info="#7dcfff",
    hint_bg="#1a1b26", hint_fg="#f7768e", hint_border="#7aa2f7",
    select_bg="#283457", select_fg="#c0caf5",
    font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
    font_size_ui="10pt", font_size_web="16px",
),
```

Then in `config.py`:

```python
THEME = "my-theme"
```

---

## Adding a Context (Situational Mode)

Contexts are defined as `ContextSpec` entries in `layers/context.py`:

```python
# In layers/context.py — add to _CONTEXT_TABLE:

ContextMode.WRITING: ContextSpec(
    mode=ContextMode.WRITING,
    description="Writing mode — focus, reference tools, no media",
    search_engines={
        "DEFAULT": "https://search.brave.com/search?q={}",
        "dict":    "https://www.merriam-webster.com/dictionary/{}",
        "thes":    "https://www.thesaurus.com/browse/{}",
        "gram":    "https://www.grammarly.com/blog/?s={}",
    },
    settings_delta={
        "content.autoplay":            False,
        "content.notifications.enabled": False,
        "statusbar.show":              "in-mode",
    },
    bindings_extra=[],
),
```

Also add `WRITING = "writing"` to the `ContextMode` enum and a keybinding.

Then switch at runtime: set `ACTIVE_CONTEXT = "writing"` in `config.py` or
run `,Cw` (if you add it to the switch table in `ContextLayer._keybindings()`).

---

## Adding a Per-Host Exception

Per-host rules belong in `policies/host.py`:

```python
# policies/host.py — add to the appropriate rule set, or create a new one:

MY_RULES: List[HostRule] = [
    HostRule(
        pattern="*.mycompany.com",
        settings={
            "content.cookies.accept":     "all",
            "content.javascript.enabled": True,
        },
        description="Internal company tools need cookies + JS",
        category="work",
    ),
]
```

Register in `build_default_host_registry()` or in `config.py`:

```python
# config.py wiring section:
from policies.host import build_default_host_registry, HostRule

host_registry = build_default_host_registry()
host_registry.register(HostRule(
    pattern="*.mycompany.com",
    settings={"content.cookies.accept": "all"},
    category="work",
    description="Company intranet",
))
```

---

## Adding a Health Check

```python
# In core/health.py — add a new HealthCheck subclass:

class AutoplayCheck(HealthCheck):
    """Warn if autoplay is globally enabled (intrusive on most sites)."""
    name = "autoplay"
    description = "content.autoplay=True can be intrusive"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        if settings.get("content.autoplay", False) is True:
            report.add(HealthIssue(
                check=self.name,
                severity=Severity.INFO,
                message="content.autoplay=True — videos play automatically",
                key="content.autoplay",
            ))
```

Register it in `HealthChecker.default()`:

```python
@classmethod
def default(cls) -> "HealthChecker":
    return (
        cls()
        ...
        .add(AutoplayCheck())   # ← add here
    )
```

---

## Adding a Pipeline Stage

```python
# core/pipeline.py or inline in your layer:

from core.pipeline import PipeStage, ConfigPacket

class ExpandTildeStage(PipeStage):
    """Expand ~ in string values to the home directory."""
    name = "expand_tilde"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        import os
        settings = packet.data.get("settings", {})
        expanded = {
            k: os.path.expanduser(v) if isinstance(v, str) else v
            for k, v in settings.items()
        }
        return packet.replace_data({**packet.data, "settings": expanded})
```

Use in a layer:

```python
def pipeline(self) -> Pipeline:
    from core.pipeline import LogStage, Pipeline
    return Pipeline([LogStage(), ExpandTildeStage()])
```

---

## Adding a Search Engine Set

```python
# strategies/search.py — add a new strategy class:

class WorkSearchStrategy(Strategy[SearchEngineMap]):
    """Company-internal search."""
    name = "work"

    def apply(self, context: ConfigDict) -> SearchEngineMap:
        return {
            **_BASE_ENGINES,
            "DEFAULT": "https://jira.mycompany.com/issues/?jql=text+~+{}",
            "jira":    "https://jira.mycompany.com/issues/?jql=text+~+{}",
        }
```

Register it and use in `UserLayer` via `USER_SEARCH_ENGINES`.

---

## Adding a Lifecycle Hook

```python
# config.py wiring section:

@lifecycle.decorator(LifecycleHook.POST_APPLY, priority=100)
def _on_config_applied() -> None:
    logger.info("Config fully applied — browser is ready")
    # e.g. emit a custom event, write a timestamp file, etc.
```

---

## Adding User Keybindings (simplest path)

Just edit `USER_EXTRA_BINDINGS` in `config.py`:

```python
L = LEADER_KEY   # default ","
USER_EXTRA_BINDINGS: list[tuple[str, str, str]] = [
    (f"{L}o",  "spawn --userscript open_with.py",    "normal"),
    (f"{L}ns", "open -t https://news.ycombinator.com","normal"),
    # ... add your own
]
```

UserLayer (priority=90) ensures these win over all lower layers.
