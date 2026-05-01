#!/usr/bin/env python3
"""
scripts/gen_keybindings.py
==========================
Auto-generate KEYBINDINGS.md from the live keybinding catalog.

Usage:
    python3 scripts/gen_keybindings.py [--output docs/KEYBINDINGS.md]
    python3 scripts/gen_keybindings.py --stdout

This script must be run from the project root (where config.py lives).
It imports all layers and builds the catalog without starting qutebrowser.
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
from layers.base        import BaseLayer
from layers.behavior    import BehaviorLayer
from layers.privacy     import PrivacyLayer, PrivacyProfile
from layers.user        import UserLayer


def build_catalog() -> KeybindingCatalog:
    return KeybindingCatalog.from_layers([
        BaseLayer(),
        BehaviorLayer(leader=","),
        PrivacyLayer(profile=PrivacyProfile.STANDARD, leader=","),
        UserLayer(leader=","),
    ])


def generate_markdown(catalog: KeybindingCatalog) -> str:
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
    args = parser.parse_args()

    catalog  = build_catalog()
    content  = generate_markdown(catalog)

    if args.stdout:
        print(content)
    else:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(content)
        n = len(catalog)
        conflicts = len(catalog.find_conflicts())
        print(
            f"✓ Generated {args.output}  "
            f"({n} bindings, {conflicts} conflict(s))"
        )


if __name__ == "__main__":
    main()
