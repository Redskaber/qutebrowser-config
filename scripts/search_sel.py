#!/usr/bin/env python3
"""
scripts/search_sel.py
=====================
Userscript: Search Selected Text

Opens the current text selection in a search engine.
Supports multiple search targets via --engine argument.

Usage (add to USER_EXTRA_BINDINGS or BehaviorLayer):
    (",/",  "spawn --userscript search_sel.py --tab",           "normal")
    (",sg", "spawn --userscript search_sel.py --engine g --tab","normal")
    (",sw", "spawn --userscript search_sel.py --engine w --tab","normal")

Environment (injected by qutebrowser):
    QUTE_SELECTED_TEXT  — primary selection (X11) or caret-mode selection
    QUTE_FIFO           — path to qutebrowser command FIFO

Text resolution order:
    1. QUTE_SELECTED_TEXT  (caret selection / X11 primary)
    2. QUTE_CLIPBOARD      (Ctrl+C clipboard, --clipboard flag)
    → if both empty: show warning, exit 0 (not an error)

Exit codes:
    0  — success OR no text available (user feedback via message-warning)
    1  — script/system error (bad engine arg, unexpected exception)

Engine shortcuts match url.searchengines in config.py / BaseLayer:
    DEFAULT  → Brave Search
    g        → Google
    ddg      → DuckDuckGo
    gh       → GitHub
    w        → Wikipedia
    yt       → YouTube
    nix      → NixOS packages
    mdn      → MDN Web Docs
    crates   → crates.io
    pypi     → PyPI
    arxiv    → arXiv
    sx       → SearXNG
    bili     → Bilibili
    zhihu    → Zhihu
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import quote_plus

QUTE_FIFO          = os.environ.get("QUTE_FIFO", "")
QUTE_SELECTED_TEXT = os.environ.get("QUTE_SELECTED_TEXT", "").strip()
QUTE_CLIPBOARD     = os.environ.get("QUTE_CLIPBOARD", "").strip()
QUTE_URL           = os.environ.get("QUTE_URL", "")


# ─────────────────────────────────────────────
# Engine URL Map
# ─────────────────────────────────────────────
# Duplicated here so the script is fully self-contained.
# Keep in sync with url.searchengines in BaseLayer.
ENGINES: dict[str, str] = {
    "DEFAULT": "https://search.brave.com/search?q={}",
    "g":       "https://www.google.com/search?q={}",
    "ddg":     "https://duckduckgo.com/?q={}",
    "w":       "https://en.wikipedia.org/w/index.php?search={}",
    "yt":      "https://www.youtube.com/results?search_query={}",
    "gh":      "https://github.com/search?q={}&type=repositories",
    "nix":     "https://search.nixos.org/packages?query={}",
    "mdn":     "https://developer.mozilla.org/en-US/search?q={}",
    "crates":  "https://crates.io/search?q={}",
    "pypi":    "https://pypi.org/search/?q={}",
    "arxiv":   "https://arxiv.org/search/?searchtype=all&query={}",
    "sx":      "https://searx.be/search?q={}",
    "bili":    "https://search.bilibili.com/all?keyword={}",
    "zhihu":   "https://www.zhihu.com/search?type=content&q={}",
}


# ─────────────────────────────────────────────
# FIFO communication
# ─────────────────────────────────────────────

def send(cmd: str) -> None:
    """Write a single command line to the qutebrowser FIFO."""
    if QUTE_FIFO:
        with open(QUTE_FIFO, "w") as f:
            f.write(cmd + "\n")


def warn(msg: str) -> None:
    """User-facing warning (no text selected, etc.) — exits 0."""
    send(f"message-warning '[search-sel] {msg}'")


def fatal(msg: str) -> None:
    """Script/system error — exits 1 so qutebrowser reports it."""
    send(f"message-error '[search-sel] {msg}'")
    sys.exit(1)


# ─────────────────────────────────────────────
# Engine resolution
# ─────────────────────────────────────────────

def resolve_engine(key: str) -> tuple[str, str]:
    """
    Return (canonical_key, url_template) for the given engine shortcut.
    Falls back to DEFAULT for unknown keys (after case-insensitive retry).
    Raises SystemExit(1) only if engine map is somehow empty.
    """
    if key in ENGINES:
        return key, ENGINES[key]
    # Case-insensitive fallback
    lower_map = {k.lower(): (k, v) for k, v in ENGINES.items()}
    if key.lower() in lower_map:
        return lower_map[key.lower()]
    # Unknown key → silently fall back to DEFAULT with a hint
    send(f"message-warning '[search-sel] unknown engine {key!r}, using DEFAULT'")
    return "DEFAULT", ENGINES["DEFAULT"]


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Search selected text.")
    parser.add_argument(
        "--engine", "-e", default="DEFAULT",
        help="Engine shortcut (DEFAULT, g, ddg, gh, w, yt, …)",
    )
    parser.add_argument(
        "--tab", "-t", action="store_true",
        help="Open in new tab (default: current tab)",
    )
    parser.add_argument(
        "--clipboard", "-c", action="store_true",
        help="Use clipboard text instead of selection",
    )
    args = parser.parse_args()

    # ── Text resolution ───────────────────────────────────────────────
    # Priority: explicit --clipboard flag → QUTE_SELECTED_TEXT → QUTE_CLIPBOARD
    if args.clipboard:
        text = QUTE_CLIPBOARD
        if not text:
            warn("Clipboard is empty.")
            return
    else:
        text = QUTE_SELECTED_TEXT
        if not text:
            # Graceful fallback to clipboard
            text = QUTE_CLIPBOARD
        if not text:
            # No selection, no clipboard — inform user and exit cleanly (0)
            warn("No text selected. Select text first (caret mode: v), or use --clipboard.")
            return

    # ── Engine lookup ─────────────────────────────────────────────────
    engine_key, url_template = resolve_engine(args.engine)

    # ── Build URL and open ────────────────────────────────────────────
    search_url = url_template.replace("{}", quote_plus(text))
    open_cmd   = "open -t" if args.tab else "open"
    send(f"{open_cmd} {search_url}")
    send(f"message-info '[search-sel] {engine_key}: {text[:50]!r}'")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        fatal(f"unexpected error: {exc}")



