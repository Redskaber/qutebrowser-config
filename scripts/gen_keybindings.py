#!/usr/bin/env python3
"""
scripts/gen_keybindings.py
==========================
Auto-generate KEYBINDINGS.md from the live keybinding catalog.

Usage:
    python3 scripts/gen_keybindings.py [--output docs/KEYBINDINGS.md]
    python3 scripts/gen_keybindings.py --stdout
    python3 scripts/gen_keybindings.py --context dev   # include ContextLayer bindings
    python3 scripts/gen_keybindings.py --check         # exit 1 if conflicts > 0

This script must be run from the project root (where config.py lives).
It imports all layers and builds the catalog without starting qutebrowser.

v6 changes:
  - Added writing / gaming to --context choices (were missing despite being
    valid ContextMode values since v8 of context.py).
  - _layer_summary() now shows priority=10/20/40/45/90 for all layers and
    reflects that BaseLayer no longer contributes keybindings (v12).
  - Added --check flag: exits with code 1 if any *unintentional* conflicts
    detected (i.e. same-layer conflicts only — cross-layer is expected).
  - Added _longest_match_section() to include disambiguation table in output.
  - generate_markdown() calls _longest_match_section() before conflict report.

v5 changes (retained):
  - Added ContextLayer to catalog build; --context flag; layer summary section.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from typing import List, Optional

# ── Imports ───────────────────────────────────────────────────────────────────
from core.layer          import LayerProtocol

from keybindings.catalog import KeybindingCatalog
from layers.base         import BaseLayer
from layers.behavior     import BehaviorLayer
from layers.context      import ContextLayer
from layers.privacy      import PrivacyLayer, PrivacyProfile
from layers.user         import UserLayer

# ── Path setup ────────────────────────────────────────────────────────────────
_here = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_here)
if _root not in sys.path:
    sys.path.insert(0, _root)

# All valid context choices (must stay in sync with ContextMode in context.py)
_CONTEXT_CHOICES = ["default", "work", "research", "media", "dev", "writing", "gaming"]


def build_catalog(
    leader: str = ",",
    context: Optional[str] = None,
) -> KeybindingCatalog:
    """Build the keybinding catalog from all relevant layers."""
    layers: List[LayerProtocol] = [
        BaseLayer(),
        PrivacyLayer(profile=PrivacyProfile.STANDARD, leader=leader),
        BehaviorLayer(leader=leader),
    ]

    if context is not None:
        layers.append(ContextLayer(context=context, leader=leader))

    layers.append(UserLayer(leader=leader))

    return KeybindingCatalog.from_layers(layers)


def _layer_summary(context: Optional[str]) -> str:
    """Generate a brief layer summary section."""
    layers_desc = [
        "| `base`     | 10 | Settings only — no keybindings (v12)              |",
        "| `privacy`  | 20 | `,j` `,i` `,c` `,s` privacy toggles               |",
        "| `behavior` | 40 | All normal/insert/caret/hint/cmd bindings          |",
    ]
    if context is not None:
        layers_desc.append(
            f"| `context`  | 45 | `,C*` context-switch bindings (active: `{context}`) |"
        )
    else:
        layers_desc.append(
            "| `context`  | 45 | `,C*` context-switch bindings (not loaded)         |"
        )
    layers_desc.append(
        "| `user`     | 90 | Personal overrides — always wins                   |"
    )

    return "\n".join([
        "## Layer Sources",
        "",
        "| Layer      | Pri | Responsibility                                     |",
        "| ---------- | --- | -------------------------------------------------- |",
        *layers_desc,
    ])


def _longest_match_section() -> str:
    """Generate the longest-match disambiguation table."""
    return "\n".join([
        "## Longest-Match Disambiguation",
        "",
        "When multiple bindings share a prefix, qutebrowser waits up to",
        "`input.partial_timeout` (3000 ms) for the next key:",
        "- another key arrives → the longer sequence fires",
        "- timeout expires    → the shorter sequence fires",
        "- `<Esc>` pressed    → cancel immediately",
        "",
        "| Prefix  | Short | Long | Layer |",
        "| ------- | ----- | ---- | ----- |",
        "| `,Cw`   | work context | `,Cwt` → writing context | context |",
        "| `,P`    | yank primary (new tab) | `,Pa` fill pass, `,Po` OTP | behavior |",
        "| `,s`    | HTTPS reload (privacy) | `,sn` / `,sl` session cmds | mixed |",
        "| `z`     | `zi`/`zo` zoom | `z0`/`zz` reset | behavior |",
        "| `;`     | `;;` hint | `;b` `;d` `;i` ... | behavior |",
        "| `t`     | `th`/`tl` move | `tD`/`tO` tab-only | behavior |",
        "",
    ])


def generate_markdown(
    catalog: KeybindingCatalog,
    context: Optional[str] = None,
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
        _longest_match_section(),
    ]

    for mode in modes:
        lines.append(catalog.reference_table(mode))
        lines.append("")

    # Conflicts section
    lines += [
        "## Conflicts",
        "",
        "_Cross-layer conflicts are intentional — higher-priority layers override lower ones._",
        "_Same-layer conflicts indicate a bug and should be fixed._",
        "",
        catalog.conflict_report(),
    ]

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate KEYBINDINGS.md from the live catalog",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/gen_keybindings.py
  python3 scripts/gen_keybindings.py --stdout --context dev
  python3 scripts/gen_keybindings.py --check   # CI: fail on conflicts
        """,
    )
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
        choices=_CONTEXT_CHOICES,
        help="Include ContextLayer bindings for the given context",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Exit with code 1 if any keybinding conflicts are detected",
    )
    args = parser.parse_args()

    catalog  = build_catalog(leader=args.leader, context=args.context)
    content  = generate_markdown(catalog, context=args.context)

    if args.check:
        conflicts = catalog.find_conflicts()
        if conflicts:
            print(f"✗ {len(conflicts)} keybinding conflict(s) detected:")
            for key, mode, entries in conflicts:
                print(f"  [{mode}] {key!r}: "
                      + ", ".join(f"{e.layer}[{e.priority}]" for e in entries))
            sys.exit(1)
        else:
            print("✓ No keybinding conflicts.")
        return

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
