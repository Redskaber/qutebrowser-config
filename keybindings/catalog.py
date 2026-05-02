"""
keybindings/catalog.py
======================
Keybinding Catalog

Aggregates all (key, command, mode) tuples from all layers into a
queryable catalog.  Provides:
  - Conflict detection: two bindings on the same key in the same mode
  - Reference table: Markdown table of bindings per mode
  - Lookup: what does key X do in mode Y?

The catalog is read-only and does not interact with qutebrowser directly.
It is consumed by documentation scripts and the test suite.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger("qute.keybindings.catalog")

LayerProtocol = Any  # avoid circular import; duck-typed


@dataclass(frozen=True)
class KeybindingEntry:
    """A single keybinding record."""
    key:      str   # e.g. "<ctrl-d>", "J", ",r"
    command:  str   # e.g. "scroll-page 0 0.5"
    mode:     str   # e.g. "normal", "insert", "command"
    layer:    str   # originating layer name, e.g. "behavior"
    priority: int   # originating layer priority


class KeybindingCatalog:
    """
    Ordered, deduplicated keybinding index.

    Conflict semantics (mirrors LayerStack priority):
      If two layers define the same (key, mode), the higher-priority
      layer wins.  The lower-priority binding is recorded as a conflict
      but not applied.
    """

    def __init__(self) -> None:
        self._entries: List[KeybindingEntry] = []

    def add(self, entry: KeybindingEntry) -> None:
        self._entries.append(entry)

    # ─── Construction ──────────────────────────────────────────────────────

    @classmethod
    def from_layers(cls, layers: List[LayerProtocol]) -> "KeybindingCatalog":
        """
        Build a catalog from a list of layer objects.
        Layers must expose a .build() → dict with "keybindings" key.
        """
        catalog = cls()

        # Sort by priority ascending (lower priority first)
        sorted_layers = sorted(layers, key=lambda l: getattr(l, "priority", 50))

        for layer in sorted_layers:
            try:
                data = layer.build()
                bindings: List[Tuple[str, str, str]] = data.get("keybindings", [])
                name     = getattr(layer, "name", "unknown")
                priority = getattr(layer, "priority", 50)

                for key, command, mode in bindings:
                    catalog.add(KeybindingEntry(
                        key=key, command=command, mode=mode,
                        layer=name, priority=priority,
                    ))
            except Exception as exc:
                logger.warning("[KeybindingCatalog] layer %r failed: %s", layer, exc)

        return catalog

    # ─── Query ─────────────────────────────────────────────────────────────

    def lookup(self, key: str, mode: str = "normal") -> Optional[KeybindingEntry]:
        """Return the highest-priority binding for (key, mode), or None."""
        matches = [e for e in self._entries if e.key == key and e.mode == mode]
        if not matches:
            return None
        return max(matches, key=lambda e: e.priority)

    def by_mode(self, mode: str) -> List[KeybindingEntry]:
        """Return all entries for a given mode, highest-priority winning on duplicates."""
        seen: Dict[str, KeybindingEntry] = {}
        for entry in self._entries:
            if entry.mode != mode:
                continue
            existing = seen.get(entry.key)
            if existing is None or entry.priority > existing.priority:
                seen[entry.key] = entry
        return sorted(seen.values(), key=lambda e: e.key)

    def by_layer(self, layer_name: str) -> List[KeybindingEntry]:
        """Return all entries from a specific layer."""
        return [e for e in self._entries if e.layer == layer_name]

    def modes(self) -> List[str]:
        """Return all distinct modes."""
        return sorted({e.mode for e in self._entries})

    def __iter__(self) -> Iterator[KeybindingEntry]:
        return iter(self._entries)

    def __len__(self) -> int:
        return len(self._entries)

    # ─── Conflict Detection ────────────────────────────────────────────────

    def find_conflicts(self) -> List[Tuple[str, str, List[KeybindingEntry]]]:
        """
        Return list of (key, mode, [conflicting entries]) where
        more than one layer defines the same (key, mode) pair.

        This is informational — conflicts are expected (higher wins).
        Useful for auditing accidental overwrites.
        """
        index: Dict[Tuple[str, str], List[KeybindingEntry]] = defaultdict(list)
        for entry in self._entries:
            index[(entry.key, entry.mode)].append(entry)

        conflicts = [
            (key, mode, entries)
            for (key, mode), entries in index.items()
            if len(entries) > 1
        ]
        return sorted(conflicts, key=lambda c: (c[1], c[0]))  # sort by mode then key

    # ─── Reference Generation ──────────────────────────────────────────────

    def reference_table(self, mode: str = "normal") -> str:
        """
        Generate a Markdown table of all active bindings for a mode.

        Example output:
          | Key       | Command              | Layer    |
          |-----------|----------------------|----------|
          | <ctrl-d>  | scroll-page 0 0.5    | base     |
          | J         | tab-prev             | behavior |
        """
        entries = self.by_mode(mode)
        if not entries:
            return f"_No bindings registered for mode '{mode}'._\n"

        lines = [
            f"### {mode.capitalize()} Mode Keybindings\n",
            "| Key | Command | Layer |",
            "|-----|---------|-------|",
        ]
        for e in entries:
            key = e.key.replace("|", "\\|")
            cmd = e.command.replace("|", "\\|")
            lines.append(f"| `{key}` | `{cmd}` | {e.layer} |")

        return "\n".join(lines) + "\n"

    def reference_all(self) -> str:
        """Generate reference tables for all modes."""
        sections: List[str] = []
        for mode in self.modes():
            sections.append(self.reference_table(mode))
        return "\n".join(sections)

    def conflict_report(self) -> str:
        """Generate a human-readable conflict report."""
        conflicts = self.find_conflicts()
        if not conflicts:
            return "✓ No keybinding conflicts detected.\n"

        lines = [f"⚠ {len(conflicts)} keybinding conflict(s):\n"]
        for key, mode, entries in conflicts:
            winner = max(entries, key=lambda e: e.priority)
            losers = [e for e in entries if e is not winner]
            loser_strs = ", ".join(f"{e.layer}[{e.priority}]" for e in losers)
            lines.append(
                f"  `{key}` [{mode}]: {winner.layer}[{winner.priority}] wins "
                f"over {loser_strs}"
            )
        return "\n".join(lines) + "\n"
