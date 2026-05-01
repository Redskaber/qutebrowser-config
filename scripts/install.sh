#!/usr/bin/env bash
# scripts/install.sh
# ==================
# Deploy qutebrowser config to ~/.config/qutebrowser/
#
# Usage:
#   ./scripts/install.sh [--dry-run] [--backup] [--link]
#
# Options:
#   --dry-run   Show what would be done, don't do it
#   --backup    Backup existing config before deploying
#   --link      Use symlinks instead of copies (for live development)
#
# NixOS note:
#   If you manage qutebrowser via home-manager, set:
#     programs.qutebrowser.configPyContent = builtins.readFile ./config.py;
#   and point extraConfigPy at this directory instead.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
QUTE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/qutebrowser"
QUTE_SCRIPTS_DIR="$QUTE_CONFIG_DIR/userscripts"

DRY_RUN=false
BACKUP=false
USE_LINKS=false

# ── Parse arguments ──────────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
  --dry-run) DRY_RUN=true ;;
  --backup) BACKUP=true ;;
  --link) USE_LINKS=true ;;
  --help)
    echo "Usage: $0 [--dry-run] [--backup] [--link]"
    exit 0
    ;;
  *)
    echo "Unknown option: $arg"
    exit 1
    ;;
  esac
done

# ── Helpers ──────────────────────────────────────────────────────────────────
log() { echo "  $*"; }
info() { echo "→ $*"; }
dry() { $DRY_RUN && echo "  [dry] $*" && return 0 || return 1; }

do_copy() {
  local src="$1" dst="$2"
  if dry "cp $src → $dst"; then return; fi
  cp -r "$src" "$dst"
  log "copied: $dst"
}

do_link() {
  local src="$1" dst="$2"
  if dry "ln -sf $src → $dst"; then return; fi
  ln -sf "$src" "$dst"
  log "linked: $dst → $src"
}

do_install() {
  local src="$1" dst="$2"
  $USE_LINKS && do_link "$src" "$dst" || do_copy "$src" "$dst"
}

# ── Backup ───────────────────────────────────────────────────────────────────
if $BACKUP && [ -d "$QUTE_CONFIG_DIR" ]; then
  BACKUP_DIR="${QUTE_CONFIG_DIR}.bak.$(date +%Y%m%d_%H%M%S)"
  info "Backing up existing config to $BACKUP_DIR"
  dry "cp -r $QUTE_CONFIG_DIR $BACKUP_DIR" || cp -r "$QUTE_CONFIG_DIR" "$BACKUP_DIR"
fi

# ── Create directories ───────────────────────────────────────────────────────
info "Creating config directories"
dry "mkdir -p $QUTE_CONFIG_DIR" || mkdir -p "$QUTE_CONFIG_DIR"
dry "mkdir -p $QUTE_SCRIPTS_DIR" || mkdir -p "$QUTE_SCRIPTS_DIR"

# ── Deploy core modules ───────────────────────────────────────────────────────
info "Deploying architecture modules"
for dir in core layers; do
  src="$PROJECT_ROOT/$dir"
  dst="$QUTE_CONFIG_DIR/$dir"
  if [ -d "$dst" ] && ! $USE_LINKS; then
    dry "rm -rf $dst" || rm -rf "$dst"
  fi
  do_install "$src" "$dst"
done

# ── Deploy orchestrator ───────────────────────────────────────────────────────
info "Deploying orchestrator"
do_install "$PROJECT_ROOT/orchestrator.py" "$QUTE_CONFIG_DIR/orchestrator.py"

# ── Deploy config.py ─────────────────────────────────────────────────────────
info "Deploying config.py"
do_install "$PROJECT_ROOT/config.py" "$QUTE_CONFIG_DIR/config.py"

# ── Deploy userscripts ────────────────────────────────────────────────────────
info "Deploying userscripts"
for script in "$PROJECT_ROOT/scripts/"*.py; do
  [ -f "$script" ] || continue
  dst_script="$QUTE_SCRIPTS_DIR/$(basename "$script")"
  do_install "$script" "$dst_script"
  dry "chmod +x $dst_script" || chmod +x "$dst_script"
done

# ── Verify Python syntax ─────────────────────────────────────────────────────
info "Verifying Python syntax"
for f in \
  "$QUTE_CONFIG_DIR/config.py" \
  "$QUTE_CONFIG_DIR/orchestrator.py" \
  "$QUTE_CONFIG_DIR/core/"*.py \
  "$QUTE_CONFIG_DIR/layers/"*.py; do
  [ -f "$f" ] || continue
  if dry "python3 -m py_compile $f"; then continue; fi
  python3 -m py_compile "$f" && log "ok: $f" || log "SYNTAX ERROR: $f"
done

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
$DRY_RUN && echo "  [DRY RUN] No files were changed" || echo "  ✓ Config deployed to $QUTE_CONFIG_DIR"
echo ""
echo "  Structure:"
echo "    config.py           ← entry point (only this runs)"
echo "    orchestrator.py     ← wires all modules"
echo "    core/               ← pipeline, state, protocol, layer"
echo "    layers/             ← base, privacy, appearance, behavior"
echo "    userscripts/        ← readability.py, password.py"
echo ""
echo "  To reload in qutebrowser: :config-source"
echo "  Keybinding: ,r"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
