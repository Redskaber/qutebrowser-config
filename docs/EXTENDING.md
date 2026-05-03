# Extending the Configuration (v13)

This guide covers every extension point in the architecture.
Read [ARCHITECTURE.md](ARCHITECTURE.md) first for design context.

---

## Table of Contents

1. [Adding a New Layer](#adding-a-new-layer)
2. [Using ComposeLayer](#using-composelayer) ← v13
3. [Adding a Session Mode](#adding-a-session-mode)
4. [Adding a Context Mode](#adding-a-context-mode)
5. [Adding a Theme](#adding-a-theme)
6. [Adding a Per-Host Rule](#adding-a-per-host-rule)
7. [Adding a Health Check](#adding-a-health-check)
8. [Adding a Policy](#adding-a-policy)
9. [Adding a Lifecycle Hook](#adding-a-lifecycle-hook)
10. [Adding a Pipeline Stage](#adding-a-pipeline-stage)
11. [Using Pipeline v12 Stages](#using-pipeline-v12-stages)
12. [Adding an Event Middleware](#adding-an-event-middleware) ← v13
13. [Using LayerHotSwap](#using-layerhotswap) ← v13
14. [Using ConfigValidator](#using-configvalidator) ← v13
15. [Using the Audit System](#using-the-audit-system)
16. [Using the Metrics System](#using-the-metrics-system)
17. [Adding a Search Strategy](#adding-a-search-strategy)
18. [Overriding Fonts](#overriding-fonts)
19. [CLI Diagnostics Reference](#cli-diagnostics-reference)

---

## Adding a New Layer

Layers are the primary extension mechanism.

```python
# layers/workspace.py
"""
layers/workspace.py  —  Workspace Layer  (priority 60)
"""
from __future__ import annotations
from typing import Dict, List
from core.layer import BaseConfigLayer
from core.types import ConfigDict, Keybind


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

Register in `config.py` `_build_orchestrator()`:

```python
from layers.workspace import WorkspaceLayer

# In _build_orchestrator():
if LAYERS.get("workspace"):
    stack.register(WorkspaceLayer(leader=LEADER_KEY, workspace="work"))

# In the LAYERS dict:
LAYERS: dict[str, bool] = {
    ...,
    "workspace": True,
}
```

**Rules for layer authors:**

- `build()` must be **pure** — no `config.set()`, no I/O, no side effects
- Never import from another `layers/*` module
- Always accept and honour the `leader` parameter
- Priority 60–80 is the recommended range for custom layers
- Use `_settings()` / `_keybindings()` / `_aliases()` — do not override `build()` directly

---

## Using ComposeLayer

`core/compose.py` ← v13

Bundle multiple layers into one named priority slot.

```python
from core.compose import ComposeLayer, compose
from layers.context import ContextLayer
from layers.session import SessionLayer

# Option 1: factory shorthand (recommended)
dev_focus = compose(
    "dev_focus",
    ContextLayer("dev"),
    SessionLayer("focus"),
    priority    = 57,
    description = "Dev context in focus mode",
)

# Option 2: fluent builder
work_day = (
    ComposeLayer("work_day", priority=57)
    .add(ContextLayer("work"))
    .add(SessionLayer("day"))
)

# Option 3: constructor
bundle = ComposeLayer(
    "bundle", priority=57,
    children=[ContextLayer("media"), SessionLayer("evening")],
)

# Register in _build_orchestrator():
stack.register(dev_focus)
```

**Nesting** — a `ComposeLayer` can itself be a child of another `ComposeLayer`:

```python
inner = compose("inner", LayerA(), LayerB(), priority=20)
outer = ComposeLayer("outer", priority=60).add(inner)
```

**Hot-swapping** — `ComposeLayer` implements `LayerProtocol` fully, so it can be replaced at runtime with `LayerHotSwap`:

```python
hs.swap("dev_focus", compose("dev_focus", ContextLayer("research"), SessionLayer("focus"), priority=57))
```

**Rules:**

- Duplicate child names raise `LayerCompositionError`
- A child may not share the name of its parent
- Child `build()` exceptions are caught and logged; that child is skipped silently

---

## Adding a Session Mode

A session mode is a time/situation spec that adjusts zoom, fonts, and chrome.

```python
# In layers/session.py:

# 1. Extend the SessionMode enum:
class SessionMode(str, Enum):
    ...
    READING = "reading"

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

# 3. Add a keybinding in SessionLayer._keybindings():
#    (f"{L}Sr", "spawn --userscript session_switch.py reading", "normal"),

# 4. Add to scripts/session_switch.py VALID_SESSIONS:
VALID_SESSIONS = {..., "reading"}
```

---

## Adding a Context Mode

A context mode overrides search engines and behavioral settings for a named situation.

```python
# In layers/context.py:

# 1. Extend the ContextMode enum:
class ContextMode(str, Enum):
    ...
    SCIENCE = "science"

# 2. Add a ContextSpec to _CONTEXT_TABLE:
_CONTEXT_TABLE[ContextMode.SCIENCE] = ContextSpec(
    mode        = ContextMode.SCIENCE,
    description = "Science — arXiv, PubMed, NCBI, periodic table",
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
    bindings_extra = [],
)

# 3. Add a keybinding in ContextLayer._keybindings():
#    (f"{L}Cs", "spawn --userscript context_switch.py science", "normal"),
```

---

## Adding a Theme

```python
# In themes/extended.py — add to EXTENDED_THEMES:

"my-theme": ColorScheme(
    bg         = "#1a1b26",
    bg_alt     = "#16161e",
    bg_surface = "#24283b",
    fg         = "#a9b1d6",
    fg_dim     = "#565f89",
    fg_strong  = "#c0caf5",
    accent     = "#7aa2f7",
    accent2    = "#bb9af7",
    success    = "#9ece6a",
    warning    = "#e0af68",
    error      = "#f7768e",
    info       = "#7dcfff",
    hint_bg    = "#1a1b26",
    hint_fg    = "#f7768e",
    hint_border= "#7aa2f7",
    select_bg  = "#283457",
    select_fg  = "#c0caf5",
    font_mono  = "JetBrainsMono Nerd Font",
    font_sans  = "Noto Sans",
    font_size_ui  = "10pt",
    font_size_web = "16px",
),
```

Then in `config.py`: `THEME = "my-theme"`.

---

## Adding a Per-Host Rule

Add a `HostRule(…)` to the appropriate category list in `policies/host.py`:

```python
HostRule(
    pattern     = "*.mycompany.com",
    settings    = {
        "content.javascript.enabled": True,
        "content.cookies.accept":     "all",
        "content.images":             True,
    },
    description = "Corporate intranet — JS, cookies, and images required",
    category    = "work",
    enabled     = True,
)
```

Available categories: `"login"`, `"social"`, `"media"`, `"dev"` (controlled by `HOST_POLICY_*` flags in `config.py`).

---

## Adding a Health Check

Health checks validate the fully-merged config at apply time (semantic checks — see `ConfigValidator` for build-time structural checks).

```python
from core.health import HealthCheck, HealthReport
from core.types import ConfigDict

class MyCheck(HealthCheck):
    @property
    def name(self) -> str:
        return "my_check"

    def run(self, settings: ConfigDict, report: HealthReport) -> None:
        value = settings.get("my.key")
        if value is None:
            return   # not set — skip
        if value == "bad_value":
            report.add(self._error(
                "my.key must not be 'bad_value' — use 'good_value' instead"
            ))
        elif value == "suboptimal":
            report.add(self._warning("my.key: consider using 'good_value'"))
        elif value == "ok_but_unusual":
            report.add(self._info("my.key is set to an unusual value"))
```

Inject into the default checker or compose a targeted one:

```python
# Add to default checker (one run):
report = HealthChecker.default().check(settings)   # MyCheck not included by default

# Compose a targeted checker for your layer:
checker = HealthChecker.with_checks(MyCheck(), AnotherCheck())
report  = checker.check(settings)

# Or extend the default:
checker = HealthChecker(
    checks=HealthChecker.default()._checks + [MyCheck()]
)
```

---

## Adding a Policy

Policies run on every key during `apply_settings()`. A DENY policy skips the key and emits `PolicyDeniedEvent`.

```python
from core.strategy import Policy, PolicyDecision, PolicyAction

class EnforceBlockingPolicy(Policy):
    """Prevent anyone from disabling ad blocking."""
    name     = "enforce_blocking"
    priority = 10   # run early

    def evaluate(self, key: str, value: object, context: dict) -> PolicyDecision | None:
        if key == "content.blocking.enabled" and value is False:
            return PolicyDecision(
                action         = PolicyAction.DENY,
                reason         = "content blocking cannot be disabled by config",
                modified_value = None,
            )
        return None   # pass through
```

Register in `_build_orchestrator()`:

```python
from core.strategy import PolicyChain

policy = PolicyChain()
policy.add(EnforceBlockingPolicy())
# Pass to ConfigOrchestrator constructor as policy_chain=policy
```

---

## Adding a Lifecycle Hook

```python
from core.lifecycle import LifecycleHook

@lifecycle.decorator(LifecycleHook.POST_APPLY, priority=50)
def _on_config_applied() -> None:
    from core.audit import audit_info
    audit_info("my-hook", "POST_APPLY hook ran")

_ = _on_config_applied   # suppress Pyright reportUnusedFunction
```

Available hooks (in execution order):

```
PRE_INIT  → POST_INIT → PRE_APPLY → POST_APPLY
PRE_RELOAD → POST_RELOAD → ON_ERROR → ON_TEARDOWN
```

---

## Adding a Pipeline Stage

```python
from core.pipeline import PipeStage, ConfigPacket
from typing import override

class StripDebugKeysStage(PipeStage):
    """Remove all keys starting with 'debug.' from the packet."""

    @property
    def name(self) -> str:
        return "strip-debug-keys"

    def process(self, packet: ConfigPacket) -> ConfigPacket:
        clean = {k: v for k, v in packet.data.items()
                 if not k.startswith("debug.")}
        return ConfigPacket(
            source   = packet.source,
            data     = clean,
            errors   = packet.errors,
            warnings = packet.warnings,
            meta     = packet.meta,
        )
```

Use in a layer's `pipeline()`:

```python
class MyLayer(BaseConfigLayer):
    ...
    def pipeline(self) -> Pipeline:
        return Pipeline("my-layer").pipe(StripDebugKeysStage())
```

---

## Using Pipeline v12 Stages

### TeeStage — probe without mutating

```python
from core.pipeline import TeeStage, Pipeline, AuditStage, MergeStage

# Insert an audit probe mid-pipeline; main packet continues unchanged
pipeline = (
    Pipeline("with-probe")
    .pipe(MergeStage({"init_key": "value"}))
    .pipe(TeeStage(AuditStage("mid-point"), label="mid-audit"))
    .pipe(MergeStage({"final_key": "value"}))
)
```

Observer exceptions are caught and logged; the main packet always continues.

### RetryStage — resilient idempotent stages

```python
from core.pipeline import RetryStage, TransformStage

def fetch_remote_config(data: dict) -> dict:
    # may raise on transient network failures
    response = requests.get("https://config.example.com/delta")
    return {**data, **response.json()}

stage = RetryStage(
    TransformStage(fetch_remote_config, "remote-config"),
    max_retries = 3,
    delay_s     = 0.05,    # 50ms between retries
    label       = "remote-fetch",
)
```

Only use with **idempotent** stages. Each failure appends a warning to the packet.

### CompositeStage — reusable pipeline fragments

```python
from core.pipeline import CompositeStage, Pipeline, ValidateStage, FilterStage

# Define a reusable fragment
privacy_pipeline = (
    Pipeline("privacy-checks")
    .pipe(ValidateStage({
        "content.javascript.enabled": lambda v: isinstance(v, bool),
    }))
    .pipe(FilterStage(lambda k, v: not k.startswith("debug.")))
)

# Embed as a single stage in a larger pipeline
main = (
    Pipeline("main")
    .pipe(CompositeStage(privacy_pipeline, label="privacy"))
    .pipe(MergeStage({"hardened": True}))
)
```

### ReduceStage — aggregate values

```python
from core.pipeline import ReduceStage

# Count boolean-valued settings; result stored in packet.meta["bool_count"]
BoolCountStage = ReduceStage(
    reducer    = lambda acc, k, v: acc + (1 if isinstance(v, bool) else 0),
    initial    = 0,
    result_key = "bool_count",
    label      = "bool-counter",
)
```

### BranchStage — conditional routing

```python
from core.pipeline import BranchStage, Pipeline, TransformStage

harden_pipeline = Pipeline("harden").pipe(
    TransformStage(
        lambda d: {**d, "content.javascript.enabled": False},
        "js-off",
    )
)

HardenBranchStage = BranchStage(
    predicate    = lambda p: p.meta.get("privacy_profile") == "PARANOID",
    true_branch  = harden_pipeline,
    false_branch = None,   # pass-through otherwise
    label        = "paranoid-harden",
)
```

### CacheStage — memoize expensive stages

```python
from core.pipeline import CacheStage, TransformStage

cached_stage = CacheStage(
    inner = TransformStage(expensive_fn, "slow"),
    label = "slow-cache",
)

# Invalidate on manual config change:
cached_stage.invalidate()
```

### Compose stages with `+`

```python
from core.pipeline import LogStage, ValidateStage

combined = LogStage("pre") + ValidateStage({
    "content.blocking.enabled": lambda v: isinstance(v, bool),
})
result = combined.run(packet)
```

---

## Adding an Event Middleware

`core/event_filter.py` ← v13

### Wrap the router's event bus

```python
from core.event_filter import (
    EventFilter, LoggingMiddleware, DedupeMiddleware,
    ThrottleMiddleware, AuditMiddleware, CountingMiddleware,
)
from core.protocol import MetricsEvent

# In _build_orchestrator(), after router = MessageRouter():
router.events = (
    EventFilter(router.events)
    .use(AuditMiddleware())                           # all events → AuditLog
    .use(LoggingMiddleware())                         # all events → DEBUG log
    .use(DedupeMiddleware(ttl=0.1))                  # suppress rapid dupes
    .use(ThrottleMiddleware(10.0, MetricsEvent))      # max 10 MetricsEvents/s
)
```

### Write custom middleware

```python
from core.event_filter import Middleware
from core.protocol import Event, ConfigErrorEvent
import requests

class AlertMiddleware(Middleware):
    """POST to a webhook on every ConfigErrorEvent."""

    def __call__(self, event: Event, next_fn) -> int:
        if isinstance(event, ConfigErrorEvent):
            try:
                requests.post(
                    "https://hooks.example.com/alerts",
                    json={"text": f"qutebrowser error: {event.error_msg}"},
                    timeout=1.0,
                )
            except Exception:
                pass   # never block the main pipeline
        return next_fn(event)

router.events = EventFilter(router.events).use(AlertMiddleware())
```

### Use CountingMiddleware for testing

```python
from core.event_filter import EventFilter, CountingMiddleware
from core.protocol import EventBus, MetricsEvent

bus     = EventBus()
counter = CountingMiddleware()
flt     = EventFilter(bus).use(counter)

flt.publish(MetricsEvent(phase="build", duration_ms=1.0, key_count=10))

assert counter.count("MetricsEvent") == 1
assert counter.total() == 1
counter.reset()
```

---

## Using LayerHotSwap

`core/hot_swap.py` ← v13

Surgical layer replacement — applies only the diff; no `:config-source` reload.

### Basic usage

```python
from core.hot_swap import LayerHotSwap
from layers.context import ContextLayer

# Construct the hot-swap engine (once, e.g. inside orchestrator)
hs = LayerHotSwap(
    stack    = orchestrator._stack,
    apply_fn = lambda k, v: applier.apply_settings({k: v}),
    router   = router,   # optional, enables LayerSwappedEvent
)

# Swap context to "research" (only changed keys applied)
result = hs.swap("context", ContextLayer("research"))
print(f"Swapped: {result.changes} changes in {result.duration_ms:.1f}ms")

# Remove a layer temporarily (e.g. for debugging)
result = hs.remove("session")

# Insert a new layer at runtime
result = hs.insert(MyNewLayer())
```

### Inspecting the result

```python
result.ok           # bool  — True if no apply errors
result.changes      # int   — keys written
result.errors       # List[str] — apply error messages
result.duration_ms  # float — wall-clock time
result.operation    # "swap" | "remove" | "insert"
result.layer_name   # name of affected layer
str(result)         # "HotSwap[swap:context] changes=3 OK 0.4ms"
```

### Listening for swap events

```python
from core.hot_swap_events import LayerSwappedEvent

router.events.subscribe(LayerSwappedEvent, lambda e: logger.info(
    "Swapped %s (%s): %d changes, %d errors",
    e.layer_name, e.operation, e.changes, e.errors,
))
```

### Context/session switching without :config-source

Rather than writing to a file and calling `:config-source` (full reload), a future version of `context_switch.py` / `session_switch.py` can call `LayerHotSwap.swap()` for sub-millisecond in-process switching:

```python
# In a userscript or keybinding handler:
hs.swap("context", ContextLayer(new_context))
# Only the delta is applied — ~0.5ms typical
```

---

## Using ConfigValidator

`core/validator.py` ← v13

Declarative schema validation at build time (structural checks; contrast with `health.py` semantic checks at apply time).

### Validate a layer's settings

```python
from core.validator import ConfigValidator, FieldSpec, COMMON_SCHEMA

class MyLayer(BaseConfigLayer):
    name     = "my_layer"
    priority = 60

    def _settings(self) -> ConfigDict:
        return {
            "zoom.default":               "110%",
            "content.javascript.enabled": True,
            "my_custom.setting":          "option_a",
        }

    def validate(self, data: ConfigDict) -> list[str]:
        schema = {
            **COMMON_SCHEMA,   # reuse standard constraints
            "my_custom.setting": FieldSpec(
                type_    = str,
                choices  = {"option_a", "option_b", "option_c"},
                required = True,
            ),
        }
        result = ConfigValidator(schema).validate(data.get("settings", {}))
        return result.errors   # only errors block apply; warnings are informational
```

### FieldSpec reference

```python
FieldSpec(
    type_    = str,              # Python type or (str, int) tuple
    required = True,             # key must be present
    choices  = {"a", "b", "c"}, # value must be one of these
    min_     = 0,                # numeric lower bound
    max_     = 200,              # numeric upper bound
    pattern  = r"^\d+%$",        # regex (re.search)
    custom   = lambda v: None,   # callable: None=pass, str=error message
    description = "e.g. '100%'",
)
```

### Register in the global SchemaRegistry

```python
from core.validator import get_schema_registry, FieldSpec

# Call once at module load time (e.g. in your layer's module-level code):
reg = get_schema_registry()
reg.register("my_layer_schema", {
    "my_custom.setting": FieldSpec(type_=str, choices={"a", "b", "c"}),
    "my_count":          FieldSpec(type_=int, min_=0, max_=100),
})

# Later, validate everything at once:
all_settings = stack.merged.get("settings", {})
result = reg.validate_all(all_settings)
if not result.ok:
    for err in result.errors:
        logger.error("[Schema] %s", err)
```

### Extend an existing schema

```python
reg.extend("common", {
    "my_extra_key": FieldSpec(type_=bool),
})
```

---

## Using the Audit System

`core/audit.py` ← v11

### Record from any component

```python
from core.audit import audit_info, audit_warn, audit_error, get_audit_log

# In a lifecycle hook:
audit_info("my-hook", "POST_APPLY ran", key_count=87)

# In a custom health check:
if bad_condition:
    audit_warn("my-check", "suspicious proxy value",
               key="content.proxy", val=str(v))

# In error handling:
audit_error("my-layer", "build() raised an exception", exc=str(exc))
```

### Query the log

```python
from core.audit import get_audit_log, AuditFilter, AuditLevel

log = get_audit_log()

# All entries since startup
all_entries = log.query()

# Only WARN and above
issues = log.query(AuditFilter.errors_and_warnings())

# Only a specific component since seq=50
recent = log.query(AuditFilter(component="orchestrator", since_seq=50))

# Last 10 entries
last10 = log.last_n(10)

# Export
print(log.export_text())
print(log.export_json())
print(log.export_markdown())
print(log.summary(last_n=20))
```

### Add an AuditStage to a pipeline

```python
from core.pipeline import Pipeline, AuditStage, ValidateStage

Pipeline("privacy-pipeline")
    .pipe(AuditStage("pre",  component="privacy-pipeline"))
    .pipe(ValidateStage({"content.javascript.enabled": lambda v: isinstance(v, bool)}))
    .pipe(AuditStage("post", component="privacy-pipeline"))
```

---

## Using the Metrics System

`core/metrics.py` ← v12

### Standalone usage

```python
from core.metrics import MetricsCollector, PhaseTimer, metrics_time

collector = MetricsCollector(capacity=64)

# Time a block with the convenience context manager
with metrics_time() as t:
    ...expensive work...
collector.emit("my_phase", t.elapsed_ms, key_count=42)

# Or with explicit PhaseTimer
timer = PhaseTimer()
with timer:
    ...
collector.emit("another_phase", timer.elapsed_ms)

# Query
sample = collector.get("my_phase")      # latest MetricsSample for phase
last5  = collector.last_n(5)            # List[MetricsSample]
totals = collector.totals_by_phase()    # Dict[str, float] cumulative ms
print(collector.summary())              # formatted table
```

### Wire to MessageRouter

```python
collector.on_emit(
    lambda ph, ms, n: router.emit_metrics(phase=ph, duration_ms=ms, key_count=n)
)
```

Every `collector.emit()` call fires `MetricsEvent` to all existing subscribers.

### Access orchestrator metrics

```python
# Direct method (v12):
print(orchestrator.metrics_summary(last_n=10))

# Via QueryBus:
summary = router.ask(GetMetricsSummaryQuery(last_n=10))
```

### Module-level singleton

```python
from core.metrics import get_metrics_collector, reset_metrics_collector

c = get_metrics_collector()   # shared global
c = reset_metrics_collector() # fresh instance (for tests)
```

---

## Adding a Search Strategy

```python
# In strategies/search.py — extend build_search_registry():

class AcademiaSearchStrategy(Strategy[SearchEngineMap]):
    name = "academia"

    def apply(self, context: ConfigDict) -> SearchEngineMap:
        return {
            **_BASE_ENGINES,
            "DEFAULT": "https://scholar.google.com/scholar?q={}",
            "arxiv":   "https://arxiv.org/search/?searchtype=all&query={}",
            "pubmed":  "https://pubmed.ncbi.nlm.nih.gov/?term={}",
        }

# In build_search_registry():
registry.register(AcademiaSearchStrategy())
```

---

## Overriding Fonts

Use the `USER_FONT_*` variables in `config.py` — no need to edit any layer file:

```python
USER_FONT_FAMILY   = "Iosevka Term"    # fonts.default_family  (or None)
USER_FONT_SIZE     = "10pt"            # fonts.default_size    (UI chrome, Qt string)
USER_FONT_SIZE_WEB = "16px"            # fonts.web.size.default (web content, px)
```

**v11 note:** `SessionLayer` (p=55) also sets `fonts.web.size.default` for evening/night/present modes. `UserLayer` (p=90) always wins — `USER_FONT_SIZE_WEB` overrides session values.

---

## CLI Diagnostics Reference

`scripts/diagnostics.py` ← v11

```bash
# Full diagnostic report (default command)
python3 scripts/diagnostics.py

# Individual commands
python3 scripts/diagnostics.py layers        # layer stack with priorities
python3 scripts/diagnostics.py health        # run all 21 health checks
python3 scripts/diagnostics.py audit         # audit log (INFO and above)
python3 scripts/diagnostics.py audit --verbose  # include DEBUG entries
python3 scripts/diagnostics.py contexts      # context table with engine counts
python3 scripts/diagnostics.py sessions      # session table with delta keys
python3 scripts/diagnostics.py themes        # all registered themes
python3 scripts/diagnostics.py keybindings   # full keybinding reference

# Options
--context   CONTEXT   activate a context before inspecting
--session   SESSION   activate a session before inspecting
--theme     THEME     theme name (default: glass)
--leader    KEY       leader key (default: ,)
--format    FORMAT    text (default) | json | markdown
--out       FILE      write output to FILE instead of stdout
--verbose             include DEBUG-level audit entries

# Exit codes
0  — success, no health errors
1  — health errors found
2  — usage / import error

# Examples
python3 scripts/diagnostics.py health --format markdown --out health.md
python3 scripts/diagnostics.py summary --context dev --session focus
python3 scripts/diagnostics.py keybindings --format markdown --out KEYBINDINGS.md
```

---

## Full Extension Checklist

When adding a **layer**:

- [ ] Create `layers/<name>.py` implementing `BaseConfigLayer`
- [ ] Add to `LAYERS` dict in `config.py`
- [ ] Register in `_build_orchestrator()` with priority 60–80
- [ ] Add tests in `tests/test_v13.py` or a new file
- [ ] Update `KEYBINDINGS.md` if new bindings are added

When adding a **ComposeLayer** ← v13:

- [ ] Import `compose` from `core.compose`
- [ ] Register in `_build_orchestrator()` after the constituent layers
- [ ] Consider priority relative to context (p=45) and session (p=55)

When adding a **session mode**:

- [ ] Extend `SessionMode` enum
- [ ] Add `SessionSpec` to `_SESSION_TABLE`
- [ ] Add `,S<key>` keybinding in `_keybindings()`
- [ ] Add to `VALID_SESSIONS` in `scripts/session_switch.py`

When adding a **context mode**:

- [ ] Extend `ContextMode` enum
- [ ] Add `ContextSpec` to `_CONTEXT_TABLE`
- [ ] Add `,C<key>` keybinding in `_keybindings()`

When adding a **health check**:

- [ ] Subclass `HealthCheck`, implement `run(settings, report)`
- [ ] Add to `HealthChecker.default()` checks list
- [ ] Add tests in `tests/test_health.py`
- [ ] Document in `ARCHITECTURE.md` §Health Check System

When adding **event middleware** ← v13:

- [ ] Subclass `Middleware`, implement `__call__(event, next_fn)`
- [ ] Wire into `router.events = EventFilter(router.events).use(...)`
- [ ] Test with `CountingMiddleware` to verify call counts

When adding a **schema** ← v13:

- [ ] Call `get_schema_registry().register("name", schema_dict)` in your module
- [ ] Use `FieldSpec` with precise constraints
- [ ] Test valid and invalid cases explicitly
