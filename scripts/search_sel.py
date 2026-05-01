#!/usr/bin/env python3
"""
scripts/search_sel.py
=====================
Userscript: Search Selected Text

Opens the current text selection in a search engine.
Supports multiple search targets via --engine argument.

Usage (add to USER_EXTRA_BINDINGS or BehaviorLayer):
    (",/",  "spawn --userscript search_sel.py",              "normal")
    (",//", "spawn --userscript search_sel.py --engine ddg", "normal")
    (",g",  "spawn --userscript search_sel.py --engine g",   "normal")
    (",G",  "spawn --userscript search_sel.py --engine gh",  "normal")

Environment (injected by qutebrowser):
    QUTE_SELECTED_TEXT  — the selected text
    QUTE_FIFO           — path to qutebrowser FIFO

In caret mode, the selection is available after `y` or directly.
In normal mode, this works on the primary selection (middle-click clipboard).

Engine shortcuts match qutebrowser's url.searchengines:
    DEFAULT  → Brave Search (default)
    g        → Google
    ddg      → DuckDuckGo
    gh       → GitHub search
    w        → Wikipedia
    yt       → YouTube
    nix      → NixOS packages
    mdn      → MDN
"""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import quote_plus

QUTE_FIFO          = os.environ.get("QUTE_FIFO", "")
QUTE_SELECTED_TEXT = os.environ.get("QUTE_SELECTED_TEXT", "").strip()
QUTE_URL           = os.environ.get("QUTE_URL", "")


# ─────────────────────────────────────────────
# Engine URL Map
# ─────────────────────────────────────────────
# These should match url.searchengines in config.py / BaseLayer.
# Duplicated here so the script is self-contained.
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


def send(cmd: str) -> None:
    if QUTE_FIFO:
        with open(QUTE_FIFO, "w") as f:
            f.write(cmd + "\n")


def error(msg: str) -> None:
    send(f"message-error '[search-sel] {msg}'")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search selected text.")
    parser.add_argument(
        "--engine", "-e", default="DEFAULT",
        help="Engine shortcut (DEFAULT, g, ddg, gh, w, yt, …)"
    )
    parser.add_argument(
        "--tab", "-t", action="store_true",
        help="Open in new tab (default: current tab)"
    )
    args = parser.parse_args()

    text = QUTE_SELECTED_TEXT
    if not text:
        # Fallback: try QUTE_FIFO-based selection query isn't available;
        # instruct user how to use caret mode selection
        error("No text selected. Use caret mode (v) to select text first.")
        return

    engine_key = args.engine
    if engine_key not in ENGINES:
        # Try case-insensitive lookup
        lower = {k.lower(): v for k, v in ENGINES.items()}
        if engine_key.lower() in lower:
            url_template = lower[engine_key.lower()]
        else:
            engine_key = "DEFAULT"
            url_template = ENGINES["DEFAULT"]
    else:
        url_template = ENGINES[engine_key]

    search_url = url_template.replace("{}", quote_plus(text))

    open_cmd = "open -t" if args.tab else "open"
    send(f"{open_cmd} {search_url}")
    send(f"message-info '[search-sel] {engine_key}: {text[:40]}'")


if __name__ == "__main__":
    main()


