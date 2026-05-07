#!/usr/bin/env python3
"""
scripts/diagnostics.py
=======================
Configuration Diagnostics CLI Tool  (v15)

A self-contained inspection utility that imports the config architecture
without starting qutebrowser.  Useful for CI, debugging, and documentation.

Usage::

    python3 scripts/diagnostics.py [command] [options]

Commands:
    layers          Print layer stack summary (priorities, enabled status)
    health          Run all health checks against resolved config
    audit           Show audit log (errors/warnings)
    contexts        List all available contexts with their engine counts
    sessions        List all available session modes with their delta keys
    network         List all available network modes and active mode  [v15]
    themes          List all registered themes
    keybindings     Print keybinding reference table (all modes)
    diff            Print diff between two config snapshots
    summary         Full diagnostic report (default if no command given)

Options::

    --context   CONTEXT   Activate a context before inspecting
    --session   SESSION   Activate a session before inspecting
    --network   NETWORK   Activate a network mode before inspecting  [v15]
    --theme     THEME     Theme to use
    --leader    KEY       Leader key (default: ,)
    --format    FORMAT    Output format: text (default) | json | markdown
    --out       FILE      Write output to FILE (default: stdout)
    --verbose             Include DEBUG-level audit entries

Exit codes:
    0  — success (no health errors)
    1  — health errors found
    2  — usage / import error

This script intentionally does NOT import config.py (which tries to call
qutebrowser's config API).  It imports the architecture modules directly.

v15 changes:
  - Added cmd_network(): lists all NetworkMode entries with proxy/DNS/description.
    Shows which mode is active given --network flag.
  - cmd_layers(): registers NetworkLayer between privacy and appearance.
  - cmd_summary(): includes cmd_network() in report.
  - build_parser(): --network option added; "network" added to command choices.
  - All diagnostics updated to "v15" version label.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import Any, Dict, List


# ── Path setup ────────────────────────────────────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)
# Also try same-dir (flat layout — project root IS scripts dir)
if _here not in sys.path:
    sys.path.insert(0, _here)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _header(title: str, width: int = 62) -> str:
    bar = "─" * width
    return f"\n{bar}\n  {title}\n{bar}"


def _import_error(what: str, exc: Exception) -> str:
    return f"[ERROR] Could not import {what}: {exc}"


# ─────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────

def cmd_layers(args: argparse.Namespace) -> int:
    try:
        from core.layer          import LayerStack
        from layers.base         import BaseLayer
        from layers.privacy      import PrivacyLayer, PrivacyProfile
        from layers.network      import NetworkLayer  # v15: NetworkLayer (p=27)
        from layers.appearance   import AppearanceLayer
        from layers.behavior     import BehaviorLayer
        from layers.context      import ContextLayer
        from layers.performance  import PerformanceLayer
        from layers.session      import SessionLayer
        from layers.user         import UserLayer
        from themes.extended     import register_all_themes
    except ImportError as exc:
        print(_import_error("layers", exc))
        return 2

    register_all_themes()

    stack = LayerStack()
    stack.register(BaseLayer())
    stack.register(PrivacyLayer(PrivacyProfile.STANDARD, leader=args.leader))
    stack.register(NetworkLayer(mode=args.network, leader=args.leader))
    stack.register(AppearanceLayer(theme=args.theme))
    stack.register(BehaviorLayer(leader=args.leader))
    stack.register(ContextLayer(context=args.context, leader=args.leader))
    stack.register(PerformanceLayer())
    stack.register(SessionLayer(session=args.session, leader=args.leader))
    stack.register(UserLayer(leader=args.leader))

    print(_header("Layer Stack  (v15)"))
    print(stack.summary())
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    try:
        from core.layer          import LayerStack
        from core.health         import HealthChecker
        from layers.base         import BaseLayer
        from layers.privacy      import PrivacyLayer, PrivacyProfile
        from layers.network      import NetworkLayer
        from layers.appearance   import AppearanceLayer
        from layers.behavior     import BehaviorLayer
        from layers.context      import ContextLayer
        from layers.performance  import PerformanceLayer
        from layers.session      import SessionLayer
        from layers.user         import UserLayer
        from themes.extended     import register_all_themes
    except ImportError as exc:
        print(_import_error("health", exc))
        return 2

    register_all_themes()

    stack = LayerStack()
    stack.register(BaseLayer())
    stack.register(PrivacyLayer(PrivacyProfile.STANDARD, leader=args.leader))
    stack.register(NetworkLayer(mode=args.network, leader=args.leader))
    stack.register(AppearanceLayer(theme=args.theme))
    stack.register(BehaviorLayer(leader=args.leader))
    stack.register(ContextLayer(context=args.context, leader=args.leader))
    stack.register(PerformanceLayer())
    stack.register(SessionLayer(session=args.session, leader=args.leader))
    stack.register(UserLayer(leader=args.leader))
    stack.resolve()

    settings: Dict[str, Any] = stack.merged.get("settings", {})
    report = HealthChecker.default().check(settings)

    print(_header("Health Check Report"))
    print(report.summary())

    if report.errors:
        print("\nErrors:")
        for e in report.errors:
            print(f"  ✗ [{e.check}] {e.message}")

    if report.warnings:
        print("\nWarnings:")
        for w in report.warnings:
            print(f"  ⚠ [{w.check}] {w.message}")

    if report.infos:
        print("\nInfo:")
        for i in report.infos:
            print(f"  · [{i.check}] {i.message}")

    if report.ok:
        print("\n✓ All health checks passed.")
        return 0
    else:
        print(f"\n✗ {len(report.errors)} error(s) found.")
        return 1


def cmd_audit(args: argparse.Namespace) -> int:
    try:
        from core.audit import get_audit_log, AuditFilter, AuditLevel
    except ImportError as exc:
        print(_import_error("audit", exc))
        return 2

    log = get_audit_log()
    flt = None if args.verbose else AuditFilter(level_min=AuditLevel.INFO)

    print(_header("Audit Log"))
    if args.format == "json":
        print(log.export_json(flt))
    elif args.format == "markdown":
        print(log.export_markdown(flt))
    else:
        text = log.export_text(flt)
        if text:
            print(text)
        else:
            print("  (no entries yet — run a full config load first)")

    print(f"\n{log.summary(last_n=0).splitlines()[0]}")
    return 0


def cmd_contexts(args: argparse.Namespace) -> int:
    try:
        from layers.context import _CONTEXT_TABLE, ContextMode  # type: ignore
    except ImportError as exc:
        print(_import_error("context", exc))
        return 2

    print(_header("Available Contexts"))
    print(f"{'Mode':<12} {'Engines':>7}  Description")
    print("─" * 62)
    for mode in ContextMode:
        spec = _CONTEXT_TABLE.get(mode)
        if spec is None:
            continue
        n_engines  = len(spec.search_engines)
        n_settings = len(spec.settings_delta)
        print(
            f"  {mode.value:<10} {n_engines:>4} eng  {n_settings:>2} settings Δ"
            f"  {spec.description}"
        )

    print(f"\nActive (with current flags): {args.context or 'auto'}")
    return 0


def cmd_sessions(args: argparse.Namespace) -> int:
    try:
        from layers.session import _SESSION_TABLE, SessionMode  # type: ignore
    except ImportError as exc:
        print(_import_error("session", exc))
        return 2

    print(_header("Available Session Modes  (v11)"))
    print(f"{'Mode':<12} {'Δ keys':>6}  Zoom   Description")
    print("─" * 62)
    for mode in SessionMode:
        spec = _SESSION_TABLE.get(mode)
        if spec is None:
            continue
        n_keys = len(spec.settings_delta)
        print(
            f"  {mode.value:<10} {n_keys:>5}  {spec.zoom_hint:<6}  {spec.description}"
        )

    print(f"\nActive (with current flags): {args.session or 'auto'}")
    return 0


def cmd_network(args: argparse.Namespace) -> int:
    """
    List all network modes with their proxy, DNS, referer, TLS settings.
    Indicates which mode is active given --network flag.

    Added in v15.
    """
    try:
        from layers.network import (  # type: ignore
            _NETWORK_TABLE, NetworkMode, _resolve_active_mode, # type: ignore[private]
        )
    except ImportError as exc:
        print(_import_error("network layer", exc))
        return 2

    network_arg = getattr(args, "network", None)
    active_mode = _resolve_active_mode(network_arg)

    print(_header("Available Network Modes  (v14/v15)"))
    print(f"{'Mode':<10} {'Proxy':<36} {'DNS':>5}  {'Referer':<15} {'TLS':<14}")
    print("─" * 90)

    for mode in NetworkMode:
        spec = _NETWORK_TABLE.get(mode)
        if spec is None:
            continue
        marker = " ← active" if mode == active_mode else ""
        dns_str = "on " if spec.dns_prefetch else "off"
        print(
            f"  {mode.value:<8} {spec.proxy:<36} {dns_str:>5}  "
            f"{spec.referer:<15} {spec.tls_errors:<14}{marker}"
        )

    print("\n  Mode resolution order: --network flag → QUTE_NETWORK env")
    print("  → ~/.config/qutebrowser/.network file → 'system' fallback")
    print(f"\nActive (with current flags): {active_mode.value}")
    print(f"  proxy   = {_NETWORK_TABLE[active_mode].proxy}")
    print(f"  dns     = {'on' if _NETWORK_TABLE[active_mode].dns_prefetch else 'off'}")
    print(f"  referer = {_NETWORK_TABLE[active_mode].referer}")
    print(f"  tls     = {_NETWORK_TABLE[active_mode].tls_errors}")
    print(f"  info    = {_NETWORK_TABLE[active_mode].description}")
    print("\nKeyboard shortcuts:  ,Nn (direct)  ,Ns (system)  ,N5 (socks5)")
    print("                     ,Nh (http)    ,Nt (tor)      ,Ni (show current)")
    return 0


def cmd_themes(args: argparse.Namespace) -> int:
    try:
        from themes.extended import register_all_themes, list_themes
    except ImportError as exc:
        print(_import_error("themes", exc))
        return 2

    register_all_themes()
    names = list_themes()

    print(_header(f"Available Themes ({len(names)} total)"))
    for name in names:
        marker = " ← active" if name == args.theme else ""
        print(f"  {name}{marker}")
    return 0


def cmd_keybindings(args: argparse.Namespace) -> int:
    try:
        from core.layer          import LayerProtocol
        from keybindings.catalog import KeybindingCatalog
        from layers.base         import BaseLayer
        from layers.privacy      import PrivacyLayer, PrivacyProfile
        from layers.network      import NetworkLayer  # NetworkLayer (v15)
        from layers.behavior     import BehaviorLayer
        from layers.context      import ContextLayer
        from layers.user         import UserLayer
    except ImportError as exc:
        print(_import_error("keybindings", exc))
        return 2

    active_layers: List[LayerProtocol] = [
        BaseLayer(),
        PrivacyLayer(PrivacyProfile.STANDARD, leader=args.leader),
        NetworkLayer(mode=args.network, leader=args.leader),
        BehaviorLayer(leader=args.leader),
        ContextLayer(context=args.context, leader=args.leader),
        UserLayer(leader=args.leader),
    ]
    catalog = KeybindingCatalog.from_layers(active_layers)

    print(_header("Keybinding Reference"))

    if args.format == "markdown":
        print(catalog.reference_all())
    else:
        for mode in catalog.modes():
            entries = catalog.by_mode(mode)
            print(f"\n[{mode.capitalize()} mode — {len(entries)} bindings]")
            for e in entries:
                print(f"  {e.key:<18} {e.command:<45} ({e.layer})")

    conflict_report = catalog.conflict_report()
    if "Conflict" in conflict_report:
        print(_header("Conflicts"))
        print(conflict_report)

    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """
    Show diff between two config snapshots.

    Usage::

        python3 diagnostics.py diff --label-a pre-reload --label-b post-reload
    """
    try:
        from core.incremental import SnapshotStore, ConfigDiffer
    except ImportError as exc:
        print(_import_error("incremental", exc))
        return 2

    store = SnapshotStore(max_history=20)
    snapshots = store.snapshots

    label_a = getattr(args, "label_a", None) or "pre-reload"
    label_b = getattr(args, "label_b", None) or "post-reload"

    snap_a = snap_b = None
    for snap in snapshots:
        if snap.label == label_a:
            snap_a = snap
        if snap.label == label_b:
            snap_b = snap

    if snap_a is None or snap_b is None:
        print(f"[diff] Snapshots not found: {label_a!r} → {label_b!r}")
        print("  Snapshots are recorded automatically during hot-reload cycles.")
        print("  Run a reload first, then inspect the diff.")
        print(f"  Available: {[s.label for s in snapshots]}")
        return 1

    changes = ConfigDiffer.diff(snap_a, snap_b)
    print(_header(f"Config Diff  {label_a!r} → {label_b!r}"))
    if not changes:
        print("  (no differences)")
    else:
        for c in changes:
            print(f"  [{c.kind.name:<8}]  {c.key}")
            if c.kind.name == "CHANGED":
                print(f"             {c.old_value!r} → {c.new_value!r}")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    """Full diagnostic report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"# qutebrowser Config Diagnostics  [{now}]")
    network_arg = getattr(args, "network", None)
    print(
        f"# theme={args.theme}  context={args.context or 'auto'}  "
        f"session={args.session or 'auto'}  "
        f"network={network_arg or 'auto'}  leader={args.leader!r}"
    )
    print()

    rc_layers   = cmd_layers(args)
    rc_health   = cmd_health(args)
    rc_contexts = cmd_contexts(args)
    rc_sessions = cmd_sessions(args)
    rc_network  = cmd_network(args)   # v15
    rc_themes   = cmd_themes(args)

    return max(rc_layers, rc_health, rc_contexts, rc_sessions, rc_network, rc_themes)


# ─────────────────────────────────────────────
# Argument Parser
# ─────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="diagnostics.py",
        description="qutebrowser config diagnostics (v15)",
    )
    p.add_argument(
        "command", nargs="?", default="summary",
        choices=[
            "layers", "health", "audit", "contexts",
            "sessions", "network", "themes", "keybindings", "diff", "summary",
        ],
        help="diagnostic command (default: summary)",
    )
    p.add_argument("--context",  default=None, help="active context name")
    p.add_argument("--session",  default=None, help="active session name")
    p.add_argument("--network",  default=None,
                   help="active network mode (direct|system|socks5|http|tor|offline)")
    p.add_argument("--theme",    default="glass", help="theme name (default: glass)")
    p.add_argument("--leader",   default=",",     help="leader key (default: ,)")
    p.add_argument("--format",   default="text",  choices=["text", "json", "markdown"])
    p.add_argument("--out",      default=None,    help="output file (default: stdout)")
    p.add_argument("--verbose",  action="store_true", help="include DEBUG audit entries")
    # diff subcommand options
    p.add_argument("--label-a",  default="pre-reload",
                   help="diff: first snapshot label (default: pre-reload)")
    p.add_argument("--label-b",  default="post-reload",
                   help="diff: second snapshot label (default: post-reload)")
    return p


def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    _orig_stdout = sys.stdout
    if args.out:
        try:
            sys.stdout = open(args.out, "w")
        except OSError as exc:
            print(f"[ERROR] Cannot open output file {args.out!r}: {exc}", file=sys.stderr)
            return 2

    try:
        dispatch = {
            "layers":      cmd_layers,
            "health":      cmd_health,
            "audit":       cmd_audit,
            "contexts":    cmd_contexts,
            "sessions":    cmd_sessions,
            "network":     cmd_network,     # v15
            "themes":      cmd_themes,
            "keybindings": cmd_keybindings,
            "diff":        cmd_diff,
            "summary":     cmd_summary,
        }
        fn = dispatch.get(args.command, cmd_summary)
        return fn(args)
    finally:
        if args.out:
            sys.stdout.close()
            sys.stdout = _orig_stdout


if __name__ == "__main__":
    sys.exit(main())
