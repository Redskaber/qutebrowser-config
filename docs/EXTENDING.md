# Extending the Configuration (v11)

This guide covers every extension point in the architecture.
Read [ARCHITECTURE.md](ARCHITECTURE.md) first.

---

## Adding a New Layer

Layers are the primary extension mechanism.

```python
# layers/workspace.py
"""
layers/workspace.py  —  Workspace Layer  (priority 60)
"""
from __future__ import annotations
from typing import Any, Dict, List
from core.layer import BaseConfigLayer, ConfigDict
from core.types import Keybind


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
                },
            }
        return {}

    def _keybindings(self) -> List[Keybind]:
        L = self._leader
        if self._workspace == "work":
            return [(f"{L}J", "open https://jira.mycompany.com", "normal")]
        return []
```

Register in `config.py`:

```python
from layers.workspace import WorkspaceLayer

# In _build_orchestrator():
if LAYERS.get("workspace"):
    stack.register(WorkspaceLayer(leader=LEADER_KEY, workspace="work"))

LAYERS: dict[str, bool] = {
    ...,
    "workspace": True,
}
```

**Rules for layer authors:**

- `build()` must be **pure** — no `config.set()`, no I/O.
- Never import from another `layers/*` module.
- Always honour the `leader` parameter.
- Priority 60–80 is the recommended range for custom layers.

---

## Adding a Session Mode (v11)

A session mode is a time/situation spec that adjusts zoom, fonts, and chrome.

```python
# In layers/session.py — extend _SESSION_TABLE:

# 1. Add to SessionMode enum:
class SessionMode(str, Enum):
    ...
    READING = "reading"   # new

# 2. Add a SessionSpec to _SESSION_TABLE:
_SESSION_TABLE[SessionMode.READING] = SessionSpec(
    mode        = SessionMode.READING,
    description = "Reading — large font, distraction-free",
    settings_delta = {
        "content.autoplay":              False,
        "content.notifications.enabled": False,
        "statusbar.show":                "in-mode",
        "tabs.show":                     "multiple",
        "fonts.web.size.default":        22,
        "zoom.default":                  "115%",
    },
    zoom_hint = "115%",
)

# 3. Add keybinding in _keybindings():
#    (f"{L}Sr", "spawn --userscript session_switch.py reading", "normal"),

# 4. Add to session_switch.py VALID_SESSIONS:
VALID_SESSIONS = {..., "reading"}
```

---

## Adding a Context Mode

Add a `ContextSpec(…)` to `_CONTEXT_TABLE` in `layers/context.py`:

```python
ContextMode.SCIENCE: ContextSpec(
    mode        = ContextMode.SCIENCE,
    description = "Science — arXiv, PubMed, NCBI, element searches",
    search_engines = {
        "DEFAULT": "https://pubmed.ncbi.nlm.nih.gov/?term={}",
        "arxiv":   "https://arxiv.org/search/?searchtype=all&query={}",
        "ncbi":    "https://www.ncbi.nlm.nih.gov/search/research-articles/?term={}",
        "elem":    "https://ptable.com/#Properties/{}",
    },
    settings_delta = {
        "content.autoplay":              False,
        "content.notifications.enabled": False,
    },
),
```

Also add to `ContextMode` enum and register the `,Cs` keybinding.

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

Then in `config.py`: `THEME = "my-theme"`.

---

## Adding a Pipeline Stage (v11)

### Simple transform

```python
from core.pipeline import TransformStage

# Prefix all setting keys with a namespace (for debugging)
NamespacePrefixStage = TransformStage(
    fn    = lambda d: {f"ns:{k}": v for k, v in d.items()},
    label = "namespace-prefix",
)
```

### Reduce stage (aggregate)

```python
from core.pipeline import ReduceStage

# Count bool-valued settings
BoolCountStage = ReduceStage(
    reducer    = lambda acc, k, v: acc + (1 if isinstance(v, bool) else 0),
    initial    = 0,
    result_key = "bool_key_count",
    label      = "bool-counter",
)
```

### Branch stage (conditional)

```python
from core.pipeline import BranchStage, Pipeline, TransformStage

# Only apply hardening transform in PARANOID mode
harden_pipeline = Pipeline("harden").pipe(
    TransformStage(lambda d: {**d, "content.javascript.enabled": False}, "js-off")
)

HardenBranchStage = BranchStage(
    predicate    = lambda p: p.meta.get("privacy_profile") == "PARANOID",
    true_branch  = harden_pipeline,
    false_branch = None,  # pass-through otherwise
    label        = "paranoid-harden",
)
```

### Cache stage (memoize)

```python
from core.pipeline import CacheStage, TransformStage

# Cache an expensive transform across hot-reloads
cached_stage = CacheStage(
    inner = TransformStage(expensive_fn, "slow"),
    label = "slow-cache",
)
# Reset on manual config change:
cached_stage.invalidate()
```

### Compose stages with `+`

```python
from core.pipeline import LogStage, ValidateStage

# Two-stage mini-pipeline:
combined = LogStage("pre") + ValidateStage({"content.blocking.enabled": lambda v: isinstance(v, bool)})
result = combined.run(packet)
```

---

## Using the Audit System (v11)

### Record from any component

```python
from core.audit import audit_info, audit_warn, audit_error, get_audit_log

# In a lifecycle hook:
audit_info("my-hook", "POST_APPLY hook ran", key_count=87)

# In a custom health check:
if bad_condition:
    audit_warn("my-check", "suspicious value detected", key="content.proxy", val=v)
```

### Query the log

```python
from core.audit import get_audit_log, AuditFilter, AuditLevel

log = get_audit_log()

# All entries
all_entries = log.query()

# Only WARN and above
issues = log.query(AuditFilter.errors_and_warnings())

# Only orchestrator entries since seq=50
recent = log.query(AuditFilter(component="orchestrator", since_seq=50))

# Last 10 entries
last10 = log.last_n(10)

# Export
print(log.export_text())
print(log.export_json())
print(log.export_markdown())
```

### Add an AuditStage to a pipeline

```python
from core.pipeline import Pipeline, AuditStage, ValidateStage

Pipeline("privacy")
.pipe(AuditStage("pre", component="privacy"))
.pipe(ValidateStage({...}))
.pipe(AuditStage("post", component="privacy"))
```

---

## Adding a Per-Host Rule

Add a `HostRule(…)` to the appropriate list in `policies/host.py`:

```python
HostRule(
    pattern     = "*.mycompany.com",
    settings    = {
        "content.javascript.enabled": True,
        "content.cookies.accept":     "all",
    },
    description = "Corporate intranet — JS + cookies required",
    category    = "work",
    enabled     = True,
)
```

---

## Adding a Lifecycle Hook

```python
from core.lifecycle import LifecycleHook

@lifecycle.decorator(LifecycleHook.POST_APPLY, priority=50)
def _on_config_applied() -> None:
    # emit a custom event, write a timestamp file, etc.
    pass

_ = _on_config_applied  # suppress Pyright reportUnusedFunction
```

Available hooks (in order):

```
PRE_INIT → POST_INIT → PRE_APPLY → POST_APPLY
PRE_RELOAD → POST_RELOAD → ON_ERROR → ON_TEARDOWN
```

---

## Overriding Fonts (v8+)

Use the `USER_FONT_*` variables in `config.py`:

```python
USER_FONT_FAMILY  = "Iosevka Term"   # or None
USER_FONT_SIZE    = "10pt"           # UI chrome (Qt string)
USER_FONT_SIZE_WEB = "16px"          # web content (int pixels)
```

**Note (v11):** `SessionLayer` (p=55) also sets `fonts.web.size.default` for evening/night/present modes.
`UserLayer` (p=90) always wins — `USER_FONT_SIZE_WEB` overrides session values.

---

## Adding a Search Strategy

```python
# strategies/search.py — add to build_search_registry():

class AcademiaSearchStrategy(Strategy[SearchEngineMap]):
    name = "academia"
    def apply(self, context: ConfigDict) -> SearchEngineMap:
        return {**_BASE_ENGINES, **_ACADEMIA_EXTRAS}

registry.register(AcademiaSearchStrategy())
```

---

## Adding a Health Check

```python
from core.health import HealthCheck, HealthIssue, Severity

class MyCheck(HealthCheck):
    @property
    def name(self) -> str:
        return "my_check"

    def run(self, settings: dict, report: HealthReport) -> None:
        if settings.get("my.key") == "bad":
            report.add(self._error("my.key must not be 'bad'"))

# Inject for one run:
checker = HealthChecker.default().add(MyCheck())

# Or compose a targeted checker:
checker = HealthChecker.with_checks(MyCheck())
```

---

## Adding a Policy

```python
from core.strategy import Policy, PolicyDecision, PolicyAction, PolicyChain
from layers.privacy import PrivacyProfile

class ImageBlockPolicy(Policy):
    name = "image_block_policy"
    priority = 40

    def __init__(self, profile: PrivacyProfile) -> None:
        self._profile = profile

    def evaluate(self, key, value, context):
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

---

## CLI Diagnostics Reference (v11)

```bash
# Full report (default)
python3 scripts/diagnostics.py

# Individual commands
python3 scripts/diagnostics.py layers      # layer stack summary
python3 scripts/diagnostics.py health      # run all health checks
python3 scripts/diagnostics.py audit       # audit log (INFO+)
python3 scripts/diagnostics.py audit --verbose  # include DEBUG
python3 scripts/diagnostics.py contexts    # context table
python3 scripts/diagnostics.py sessions    # session table
python3 scripts/diagnostics.py themes      # available themes
python3 scripts/diagnostics.py keybindings # full reference

# Options
--context   CONTEXT   activate context for inspection
--session   SESSION   activate session for inspection
--theme     THEME     theme (default: glass)
--leader    KEY       leader key (default: ,)
--format    FORMAT    text | json | markdown
--out       FILE      write to file instead of stdout

# Example: markdown health report for CI
python3 scripts/diagnostics.py health \
    --format markdown \
    --out docs/health-report.md
```

---

## Using the Metrics System (v12)

`core/metrics.py` provides the dedicated telemetry module.

### Standalone usage

```python
from core.metrics import MetricsCollector, PhaseTimer, metrics_time

collector = MetricsCollector(capacity=64)

# Time a block with context manager
with metrics_time() as t:
    ...expensive work...
collector.emit("my_phase", t.elapsed_ms, key_count=42)

# Or with explicit PhaseTimer
timer = PhaseTimer()
with timer:
    ...
collector.emit("another_phase", timer.elapsed_ms)

# Query
sample = collector.get("my_phase")     # latest
last5  = collector.last_n(5)
totals = collector.totals_by_phase()   # cumulative ms by phase
print(collector.summary())
```

### Wiring to MessageRouter

```python
collector.on_emit(
    lambda ph, ms, n: router.emit_metrics(phase=ph, duration_ms=ms, key_count=n)
)
```

Every `collector.emit()` call now also fires `MetricsEvent` to all existing subscribers.

### Accessing orchestrator metrics

```python
# Direct call
print(orchestrator.metrics_summary(last_n=10))

# Via QueryBus
summary = router.ask(GetMetricsSummaryQuery())
```

### Module singleton

```python
from core.metrics import get_metrics_collector, reset_metrics_collector

# Global singleton (shared across code that imports it)
c = get_metrics_collector()

# Reset in tests
c = reset_metrics_collector()
```

---

## Using Pipeline v12 Stages

### TeeStage — probe without mutating

```python
from core.pipeline import TeeStage, Pipeline, AuditStage, MergeStage

# Insert an audit probe mid-pipeline without affecting data flow
pipeline = (
    Pipeline("with-probe")
    .pipe(MergeStage({"key": "value"}))
    .pipe(TeeStage(AuditStage("mid"), label="mid-audit"))
    .pipe(MergeStage({"other": "value"}))
)
```

Observer exceptions are caught and logged; the main packet always continues.

### RetryStage — resilient idempotent stages

```python
from core.pipeline import RetryStage, TransformStage

def fetch_remote_config(data: dict) -> dict:
    # may raise on transient network failures
    ...

stage = RetryStage(
    TransformStage(fetch_remote_config, "remote-config"),
    max_retries=3,
    delay_s=0.05,   # 50ms between retries
    label="remote-fetch",
)
```

Only use with **idempotent** stages. Each failure appends a warning to the packet.

### CompositeStage — reusable pipeline fragments

```python
from core.pipeline import CompositeStage, Pipeline, ValidateStage, FilterStage

# Define a reusable fragment
privacy_pipeline = (
    Pipeline("privacy-checks")
    .pipe(ValidateStage({"content.javascript.enabled": lambda v: isinstance(v, bool)}))
    .pipe(FilterStage(lambda k, v: not k.startswith("debug.")))
)

# Embed as a single stage in a larger pipeline
main = (
    Pipeline("main")
    .pipe(CompositeStage(privacy_pipeline, label="privacy"))
    .pipe(MergeStage({"hardened": True}))
)
```

`Pipeline.describe()` shows `composite:privacy` rather than all inner stage names, keeping the output readable.
