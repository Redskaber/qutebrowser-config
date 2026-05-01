"""
themes/extended.py
==================
Extended Theme Definitions

Additional ColorScheme instances beyond the built-ins in layers/appearance.py.
Each theme is a pure data value — no logic, no side effects.

To add a custom theme:
  1. Define a ColorScheme() below
  2. Add it to EXTENDED_THEMES dict
  3. register_all_themes() merges it into layers/appearance.THEMES
  4. Set THEME = "your-theme-name" in config.py

All hex values are lowercase #rrggbb CSS colors.
Font values are Qt font family names.

Themes in this file:
  nord, dracula, solarized-dark, solarized-light, catppuccin-frappe,
  everforest-dark, kanagawa, palenight,
  glass  — frosted-glass / Gaussian-blur aesthetic; deep cold substrate,
           ice-blue accents, desaturated semantics. Modern. Minimal. Premium.
"""

from __future__ import annotations

from typing import Dict

# Import ColorScheme and THEMES from the appearance layer
# This is the only cross-layer import — themes extend appearance data, not logic.
from layers.appearance import ColorScheme, THEMES

# ─────────────────────────────────────────────
# Extended Color Schemes
# ─────────────────────────────────────────────
EXTENDED_THEMES: Dict[str, ColorScheme] = {

    "nord": ColorScheme(
        bg="#2e3440", bg_alt="#3b4252", bg_surface="#434c5e",
        fg="#d8dee9", fg_dim="#4c566a", fg_strong="#eceff4",
        accent="#88c0d0", accent2="#81a1c1",
        success="#a3be8c", warning="#ebcb8b", error="#bf616a", info="#8fbcbb",
        hint_bg="#2e3440", hint_fg="#bf616a", hint_border="#88c0d0",
        select_bg="#434c5e", select_fg="#d8dee9",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "dracula": ColorScheme(
        bg="#282a36", bg_alt="#21222c", bg_surface="#44475a",
        fg="#f8f8f2", fg_dim="#6272a4", fg_strong="#ffffff",
        accent="#bd93f9", accent2="#ff79c6",
        success="#50fa7b", warning="#f1fa8c", error="#ff5555", info="#8be9fd",
        hint_bg="#282a36", hint_fg="#ff5555", hint_border="#bd93f9",
        select_bg="#44475a", select_fg="#f8f8f2",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "solarized-dark": ColorScheme(
        bg="#002b36", bg_alt="#073642", bg_surface="#094555",
        fg="#839496", fg_dim="#586e75", fg_strong="#fdf6e3",
        accent="#268bd2", accent2="#6c71c4",
        success="#859900", warning="#b58900", error="#dc322f", info="#2aa198",
        hint_bg="#002b36", hint_fg="#dc322f", hint_border="#268bd2",
        select_bg="#073642", select_fg="#839496",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "solarized-light": ColorScheme(
        bg="#fdf6e3", bg_alt="#eee8d5", bg_surface="#d0cbb4",
        fg="#657b83", fg_dim="#93a1a1", fg_strong="#002b36",
        accent="#268bd2", accent2="#6c71c4",
        success="#859900", warning="#b58900", error="#dc322f", info="#2aa198",
        hint_bg="#fdf6e3", hint_fg="#dc322f", hint_border="#268bd2",
        select_bg="#eee8d5", select_fg="#657b83",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "one-dark": ColorScheme(
        bg="#282c34", bg_alt="#21252b", bg_surface="#3e4451",
        fg="#abb2bf", fg_dim="#5c6370", fg_strong="#ffffff",
        accent="#61afef", accent2="#c678dd",
        success="#98c379", warning="#e5c07b", error="#e06c75", info="#56b6c2",
        hint_bg="#282c34", hint_fg="#e06c75", hint_border="#61afef",
        select_bg="#3e4451", select_fg="#abb2bf",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "everforest-dark": ColorScheme(
        bg="#2d353b", bg_alt="#272e33", bg_surface="#3d484d",
        fg="#d3c6aa", fg_dim="#7a8478", fg_strong="#e6e2cc",
        accent="#7fbbb3", accent2="#d699b6",
        success="#a7c080", warning="#dbbc7f", error="#e67e80", info="#83c092",
        hint_bg="#2d353b", hint_fg="#e67e80", hint_border="#7fbbb3",
        select_bg="#3d484d", select_fg="#d3c6aa",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "gruvbox-light": ColorScheme(
        bg="#fbf1c7", bg_alt="#f2e5bc", bg_surface="#d5c4a1",
        fg="#3c3836", fg_dim="#928374", fg_strong="#1d2021",
        accent="#458588", accent2="#b16286",
        success="#79740e", warning="#b57614", error="#9d0006", info="#427b58",
        hint_bg="#fbf1c7", hint_fg="#9d0006", hint_border="#458588",
        select_bg="#d5c4a1", select_fg="#3c3836",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "modus-vivendi": ColorScheme(
        # Emacs Modus Vivendi — WCAG AAA compliant dark theme
        bg="#000000", bg_alt="#0d0d0d", bg_surface="#1e1e1e",
        fg="#ffffff", fg_dim="#989898", fg_strong="#ffffff",
        accent="#79a8ff", accent2="#b6a0ff",
        success="#44bc44", warning="#d0bc00", error="#ff5f5f", info="#00d3d0",
        hint_bg="#000000", hint_fg="#ff5f5f", hint_border="#79a8ff",
        select_bg="#1e1e1e", select_fg="#ffffff",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "catppuccin-macchiato": ColorScheme(
        bg="#24273a", bg_alt="#1e2030", bg_surface="#363a4f",
        fg="#cad3f5", fg_dim="#6e738d", fg_strong="#ffffff",
        accent="#8aadf4", accent2="#c6a0f6",
        success="#a6da95", warning="#eed49f", error="#ed8796", info="#91d7e3",
        hint_bg="#24273a", hint_fg="#ed8796", hint_border="#8aadf4",
        select_bg="#363a4f", select_fg="#cad3f5",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "catppuccin-frappe": ColorScheme(
        bg="#303446", bg_alt="#292c3c", bg_surface="#414559",
        fg="#c6d0f5", fg_dim="#626880", fg_strong="#ffffff",
        accent="#8caaee", accent2="#ca9ee6",
        success="#a6d189", warning="#e5c890", error="#e78284", info="#85c1dc",
        hint_bg="#303446", hint_fg="#e78284", hint_border="#8caaee",
        select_bg="#414559", select_fg="#c6d0f5",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "kanagawa": ColorScheme(
        # Kanagawa — inspired by the Great Wave painting
        bg="#1f1f28", bg_alt="#16161d", bg_surface="#2a2a37",
        fg="#dcd7ba", fg_dim="#727169", fg_strong="#e6c384",
        accent="#7e9cd8", accent2="#957fb8",
        success="#98bb6c", warning="#dca561", error="#c34043", info="#7fb4ca",
        hint_bg="#1f1f28", hint_fg="#c34043", hint_border="#7e9cd8",
        select_bg="#2d4f67", select_fg="#dcd7ba",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "palenight": ColorScheme(
        bg="#292d3e", bg_alt="#1b1e2b", bg_surface="#34384e",
        fg="#a6accd", fg_dim="#676e95", fg_strong="#ffffff",
        accent="#82aaff", accent2="#c792ea",
        success="#c3e88d", warning="#ffcb6b", error="#f07178", info="#89ddff",
        hint_bg="#292d3e", hint_fg="#f07178", hint_border="#82aaff",
        select_bg="#34384e", select_fg="#a6accd",
        font_mono="JetBrainsMono Nerd Font", font_sans="Noto Sans",
        font_size_ui="10pt", font_size_web="16px",
    ),

    "glass": ColorScheme(
        bg          = "#0d0f14",   # substrate — deep cold-black
        bg_alt      = "#080a0e",   # obsidian well
        bg_surface  = "#161b26",   # frosted panel — blue-black midnight
        fg          = "#c8d4e8",   # cool silver-white
        fg_dim      = "#4a5568",   # receding blue-grey slate
        fg_strong   = "#f0f4ff",   # pure emphasis white
        accent      = "#7ab8f5",   # ice blue — primary interactive
        accent2     = "#9d8fe8",   # soft violet — secondary / match
        success     = "#6db88a",   # desaturated sage
        warning     = "#c9a84c",   # warm sand
        error       = "#d96b7a",   # dusty rose
        info        = "#5bbcd4",   # pale cyan
        hint_bg     = "#161b26",   # glass panel bg for hint overlay
        hint_fg     = "#7ab8f5",   # ice-blue hint labels — crisp, scannable
        hint_border = "#7ab8f5",   # matching border — unified ice rail
        select_bg   = "#1e2d45",   # deep navy tint selection
        select_fg   = "#f0f4ff",   # strong white on selection
        font_mono   = "JetBrainsMono Nerd Font",
        font_sans   = "Noto Sans",
        font_size_ui  = "10pt",
        font_size_web = "16px",
    ),
}


# ─────────────────────────────────────────────
# Registration
# ─────────────────────────────────────────────
def register_all_themes() -> None:
    """
    Merge EXTENDED_THEMES into layers/appearance.THEMES.
    Call once during config initialization.
    Extended themes silently override built-ins if names collide.
    """
    before = set(THEMES.keys())
    THEMES.update(EXTENDED_THEMES)
    added = set(THEMES.keys()) - before
    if added:
        import logging
        logging.getLogger("qute.themes").debug(
            "[themes] registered extended themes: %s", sorted(added)
        )


def list_themes() -> list[str]:
    """Return all available theme names (built-ins + extended)."""
    return sorted(THEMES.keys())


