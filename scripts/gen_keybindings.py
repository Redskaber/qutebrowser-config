#!/usr/bin/env python3
"""
scripts/gen_keybindings.py
==========================
Auto-generate KEYBINDINGS.md from the live keybinding catalog.

Usage:
    python3 scripts/gen_keybindings.py [--output docs/KEYBINDINGS.md]
    python3 scripts/gen_keybindings.py --stdout
    python3 scripts/gen_keybindings.py --context dev  # include ContextLayer bindings

This script must be run from the project root (where config.py lives).
It imports all layers and builds the catalog without starting qutebrowser.

v5: Added ContextLayer to catalog build; added --context flag; added
    layer summary section to generated doc.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)

# ── Imports ───────────────────────────────────────────────────────────────────
from keybindings.catalog import KeybindingCatalog
from layers.base         import BaseLayer
from layers.behavior     import BehaviorLayer
from layers.privacy      import PrivacyLayer, PrivacyProfile
from layers.user         import UserLayer

# ContextLayer is optional (graceful fallback)
try:
    from layers.context import ContextLayer
    _CONTEXT_AVAILABLE = True
except ImportError:
    _CONTEXT_AVAILABLE = False


def build_catalog(
    leader: str = ",",
    context: str | None = None,
) -> KeybindingCatalog:
    """Build the keybinding catalog from all relevant layers."""
    layers = [
        BaseLayer(),
        PrivacyLayer(profile=PrivacyProfile.STANDARD, leader=leader),
        BehaviorLayer(leader=leader),
    ]

    if _CONTEXT_AVAILABLE and context is not None:
        layers.append(ContextLayer(context=context, leader=leader))

    layers.append(UserLayer(leader=leader))

    return KeybindingCatalog.from_layers(layers)


def _layer_summary(context: str | None) -> str:
    """Generate a brief layer summary section."""
    layers_desc = [
        "| base [p=10]        | Foundational navigation, open, yank, zoom |",
        "| privacy [p=20]     | Privacy toggle keybindings                 |",
        "| behavior [p=40]    | Vim-style UX, tabs, hints, leader bindings |",
    ]
    if _CONTEXT_AVAILABLE and context is not None:
        layers_desc.append(
            f"| context [p=45]     | Context-switch bindings (active: {context})        |"
        )
    layers_desc.append("| user [p=90]        | Personal overrides (highest priority)      |")

    return "\n".join([
        "## Layer Sources",
        "",
        "| Layer              | Responsibility                             |",
        "| ------------------ | ------------------------------------------ |",
        *layers_desc,
    ])


def generate_markdown(
    catalog: KeybindingCatalog,
    context: str | None = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Keybindings Reference",
        "",
        f"> Auto-generated on {now}.  "
        "Do not edit manually — run `python3 scripts/gen_keybindings.py` to update.",
        "",
        "## Table of Contents",
        "",
    ]

    modes = catalog.modes()
    for mode in modes:
        anchor = mode.lower().replace(" ", "-")
        lines.append(f"- [{mode.capitalize()} Mode](#{anchor}-mode-keybindings)")

    lines += [
        "- [Conflicts](#conflicts)",
        "",
        _layer_summary(context),
        "",
    ]

    for mode in modes:
        lines.append(catalog.reference_table(mode))
        lines.append("")

    # Conflicts section
    lines += [
        "## Conflicts",
        "",
        "_Conflicts are intentional — higher-priority layers override lower ones._",
        "",
        catalog.conflict_report(),
    ]

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate KEYBINDINGS.md")
    parser.add_argument(
        "--output", "-o",
        default=os.path.join(_root, "docs", "KEYBINDINGS.md"),
        help="Output file path (default: docs/KEYBINDINGS.md)",
    )
    parser.add_argument(
        "--stdout", action="store_true",
        help="Print to stdout instead of writing to file",
    )
    parser.add_argument(
        "--leader", default=",",
        help="Leader key prefix (default: ',')",
    )
    parser.add_argument(
        "--context", default=None,
        choices=["default", "work", "research", "media", "dev"],
        help="Include ContextLayer bindings for the given context",
    )
    args = parser.parse_args()

    catalog  = build_catalog(leader=args.leader, context=args.context)
    content  = generate_markdown(catalog, context=args.context)

    if args.stdout:
        print(content)
    else:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        n         = len(catalog)
        conflicts = len(catalog.find_conflicts())
        ctx_note  = f" (context={args.context})" if args.context else ""
        print(
            f"✓ Generated {args.output}  "
            f"({n} bindings, {conflicts} conflict(s)){ctx_note}"
        )


if __name__ == "__main__":
    main()
