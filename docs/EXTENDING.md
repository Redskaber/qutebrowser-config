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

Priority: 45 (between behavior[40] and performance[50])
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple
from core.layer import BaseConfigLayer, ConfigDict


class WorkspaceLayer(BaseConfigLayer):
    name        = "workspace"
    priority    = 45
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
        return {}  # default workspace: no overrides

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

# In _build_orchestrator():
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

The theme is automatically available after `register_all_themes()` is called.

---

## Adding a Per-Host Exception

Per-host rules belong in `policies/host.py`, not in `layers/behavior.py`.
The behavior layer's `host_policies()` method is the _legacy_ path; the
`HostPolicyRegistry` is the preferred structured approach.

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

Register it:

```python
def build_search_registry() -> StrategyRegistry[SearchEngineMap]:
    registry = ...
    registry.register(WorkSearchStrategy())
    return registry
```

Use in `layers/user.py`:

```python
from strategies.search import build_search_registry

def _settings(self) -> ConfigDict:
    search = build_search_registry()
    engines = search.apply("work", {})
    return {"url.searchengines": engines}
```

---

## Adding a Lifecycle Hook

```python
# config.py wiring section:

@lifecycle.on(LifecycleHook.POST_APPLY)
def _on_config_applied() -> None:
    logger.info("Config fully applied — browser is ready")
    # e.g. emit a custom event, write a timestamp file, etc.
_ = _on_config_applied  # suppress Pyright's reportUnusedFunction
```

Available hooks (in order):

```
PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY
PRE_RELOAD → POST_RELOAD → ON_ERROR → ON_TEARDOWN
```

---

## Adding a Policy

```python
# policies/content.py (or a new file):

class ImageBlockPolicy(Policy):
    """PARANOID: block image loading."""
    name = "image_block_policy"
    priority = 40

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key: str, value: Any, context: ConfigDict) -> Optional[PolicyDecision]:
        if key != "content.images":
            return None
        if self._profile == PrivacyProfile.PARANOID and value is True:
            return PolicyDecision(
                action=PolicyAction.MODIFY,
                reason="PARANOID: images disabled",
                modified_value=False,
            )
        return None
```

Add to the factory:

```python
def build_content_policy_chain(profile: PrivacyProfile) -> PolicyChain:
    chain = PolicyChain()
    ...
    chain.add(ImageBlockPolicy(profile))
    return chain
```

---

## Overriding Fonts (v8+)

The simplest way to change fonts is via the three `USER_FONT_*` variables in `config.py`. No need to touch `layers/user.py` or `extra_settings`:

```python
# config.py — USER PREFERENCE SECTION

# Font family applied to all qutebrowser UI chrome (completion, statusbar, tabs…)
USER_FONT_FAMILY  = "Iosevka Term"          # or None to keep theme default

# UI chrome font size (passed as a Qt size string like "10pt")
USER_FONT_SIZE    = "10pt"                  # or None

# Web content default font size in pixels ("16px", "18px", or plain "16")
# → maps to fonts.web.size.default (int)
USER_FONT_SIZE_WEB = "16px"                 # or None
```

These are wired via `UserLayer` at priority 90 and override whatever `AppearanceLayer` (priority 30) set from the theme's `ColorScheme`.

**Why separate `font_size` and `font_size_web`?**

| Variable             | qutebrowser key          | Unit                 | Controls                                |
| -------------------- | ------------------------ | -------------------- | --------------------------------------- |
| `USER_FONT_SIZE`     | `fonts.default_size`     | Qt string (`"10pt"`) | UI chrome (tabs, statusbar, completion) |
| `USER_FONT_SIZE_WEB` | `fonts.web.size.default` | integer (pixels)     | Default size for web page body text     |

They are independent — you can have a compact `"9pt"` UI font while keeping web pages at `18` pixels for readability.

---

## Adding a Custom Context (v8+)

Contexts live entirely in `layers/context.py` — no other file needs changing:

```python
# layers/context.py — add to ContextMode enum:
class ContextMode(str, Enum):
    ...
    FINANCE = "finance"

# Add to _CONTEXT_TABLE:
ContextMode.FINANCE: ContextSpec(
    mode=ContextMode.FINANCE,
    description="Finance mode — market data, news, portfolio tools",
    search_engines={
        "DEFAULT": "https://finance.yahoo.com/search?p={}",
        "ycharts": "https://ycharts.com/search?search[term]={}",
        "edgar":   "https://efts.sec.gov/LATEST/search-index?q={}&dateRange=custom",
        "wsj":     "https://www.wsj.com/search?query={}",
    },
    settings_delta={
        "content.autoplay":              False,
        "content.notifications.enabled": False,
        "tabs.show":                     "multiple",
    },
    bindings_extra=[],
),
```

Then add the switch binding in `_keybindings()`:

```python
(f"{L}Cf", "spawn --userscript context_switch.py finance", "normal"),
```

And register it in `scripts/context_switch.py`:

```python
VALID_CONTEXTS = {..., "finance"}
_CONTEXT_LABELS["finance"] = "Finance — market data, portfolio"
```

---

## User-Facing Config (What Users Actually Touch)

Users edit **only** the `CONFIGURATION SECTION` in `config.py`:

```python
THEME              = "catppuccin-mocha"    # any name from THEMES / extended
PRIVACY_PROFILE    = PrivacyProfile.STANDARD
PERFORMANCE_PROFILE= PerformanceProfile.BALANCED
LEADER_KEY         = ","
ACTIVE_CONTEXT     = None                  # or "work"/"dev"/"gaming"/…
LAYERS             = {"base": True, "user": True, ...}

# Font overrides (v8+)
USER_FONT_FAMILY   = "Iosevka Term"        # or None
USER_FONT_SIZE     = "10pt"                # or None
USER_FONT_SIZE_WEB = "16px"               # or None
```

And optionally the `USER PREFERENCE SECTION` for personal overrides:

```python
USER_EDITOR        = ["kitty", "-e", "nvim", "{}"]
USER_START_PAGES   = ["https://example.com"]
USER_ZOOM          = "110%"
USER_PROXY         = "socks5://127.0.0.1:7897"
USER_SEARCH_ENGINES= {"gpt": "https://chatgpt.com/?{}"}
```

Everything else — `core/`, `strategies/`, `policies/`, `themes/`, `keybindings/` —
is architecture, not configuration. Users who find themselves editing those
files are adding features, not configuring.
