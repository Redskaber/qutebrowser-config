#!/usr/bin/env python3
"""
scripts/readability.py
======================
Userscript: Readability / Reader Mode

Extracts main article content using Mozilla's Readability algorithm
(via a Python port) and displays it as clean HTML in qutebrowser.

Usage in config:
    config.bind(",R", "spawn --userscript readability.py", mode="normal")

Requirements:
    pip install readability-lxml

Environment (injected by qutebrowser):
    QUTE_URL         - current page URL
    QUTE_HTML        - path to temp file with page HTML
    QUTE_FIFO        - path to qutebrowser FIFO for commands
    QUTE_DATA_DIR    - qutebrowser data directory
"""

from __future__ import annotations

import os
import sys
import tempfile

QUTE_URL      = os.environ.get("QUTE_URL", "")
QUTE_HTML     = os.environ.get("QUTE_HTML", "")
QUTE_FIFO     = os.environ.get("QUTE_FIFO", "")
QUTE_DATA_DIR = os.environ.get("QUTE_DATA_DIR", "")

READABLE_CSS = """
<style>
  :root {
    --bg:   #1e1e2e;
    --fg:   #cdd6f4;
    --link: #89b4fa;
    --dim:  #6c7086;
    --font: 'Georgia', serif;
    --mono: 'JetBrainsMono Nerd Font', monospace;
    --max-width: 720px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html { font-size: 18px; }
  body {
    background: var(--bg);
    color: var(--fg);
    font-family: var(--font);
    line-height: 1.75;
    padding: 2rem 1rem;
    max-width: var(--max-width);
    margin: 0 auto;
  }
  h1, h2, h3, h4 {
    margin: 1.5em 0 0.5em;
    line-height: 1.3;
    color: #cba6f7;
  }
  h1 { font-size: 1.8rem; }
  h2 { font-size: 1.4rem; }
  p  { margin: 1em 0; }
  a  { color: var(--link); text-decoration: none; }
  a:hover { text-decoration: underline; }
  pre, code {
    font-family: var(--mono);
    font-size: 0.85em;
    background: #313244;
    border-radius: 4px;
  }
  pre  { padding: 1rem; overflow-x: auto; margin: 1em 0; }
  code { padding: 0.1em 0.3em; }
  img  { max-width: 100%; height: auto; border-radius: 4px; margin: 1em 0; }
  blockquote {
    border-left: 3px solid #89b4fa;
    padding-left: 1rem;
    color: var(--dim);
    margin: 1em 0;
  }
  #reader-meta {
    font-size: 0.8rem;
    color: var(--dim);
    margin-bottom: 2rem;
    font-family: var(--mono);
  }
</style>
"""


def send_command(cmd: str) -> None:
    if QUTE_FIFO:
        with open(QUTE_FIFO, "w") as f:
            f.write(cmd + "\n")


def warn(msg: str) -> None:
    """User-facing warning — exits 0."""
    send_command(f"message-warning 'readability: {msg}'")


def fatal(msg: str) -> None:
    """Script/system error — exits 1."""
    send_command(f"message-error 'readability: {msg}'")
    sys.exit(1)


# Backward-compatible alias
error = fatal


def main() -> None:
    try:
        from readability import Document
    except ImportError:
        error("readability-lxml not installed (pip install readability-lxml)")
        return

    if not QUTE_HTML:
        error("QUTE_HTML not set")
        return

    with open(QUTE_HTML, "r", encoding="utf-8", errors="replace") as f:
        raw_html = f.read()

    doc = Document(raw_html)
    title   = doc.title()
    content = doc.summary(html_partial=True)

    html = f"""<!DOCTYPE html>
            <html lang="en">
            <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>{title}</title>
            {READABLE_CSS}
            </head>
            <body>
            <h1>{title}</h1>
            <div id="reader-meta">
                Source: <a href="{QUTE_URL}">{QUTE_URL}</a>
            </div>
            {content}
            </body>
            </html>"""

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".html",
        prefix="qute-reader-",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        tmp.write(html)
        tmp_path = tmp.name

    send_command(f"open -t file://{tmp_path}")
    send_command(f"message-info 'Reader mode: {title}'")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover
        fatal(f"unexpected error: {exc}")


