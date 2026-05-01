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
# Directory layout deployed:
#   config.py          ← qutebrowser entry point
#   orchestrator.py    ← wiring / composition root
#   core/              ← FSM, pipeline, lifecycle, protocol, strategy, incremental
#   layers/            ← base, privacy, appearance, behavior, performance, user
#   strategies/        ← merge, profile, search, download strategies
#   policies/          ← content, network, security, host policies
#   themes/            ← extended color schemes (nord, dracula, solarized-*, …)
#   keybindings/       ← catalog, conflict detection
#   docs/              ← ARCHITECTURE.md, EXTENDING.md, KEYBINDINGS.md
#   scripts/           ← userscripts (deployed to userscripts/ dir)
#   tests/             ← test suite (not deployed to qutebrowser dir)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
QUTE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/qutebrowser"
QUTE_SCRIPTS_DIR="$QUTE_CONFIG_DIR/userscripts"

DRY_RUN=false
BACKUP=false
USE_LINKS=false

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
for d in "$QUTE_CONFIG_DIR" "$QUTE_SCRIPTS_DIR"; do
  dry "mkdir -p $d" || mkdir -p "$d"
done

# ── Deploy package directories ────────────────────────────────────────────────
info "Deploying package directories"
for dir in core layers strategies policies themes keybindings docs; do
  src="$PROJECT_ROOT/$dir"
  dst="$QUTE_CONFIG_DIR/$dir"
  [ -d "$src" ] || {
    log "skip (not found): $dir"
    continue
  }
  if [ -d "$dst" ] && ! $USE_LINKS; then
    dry "rm -rf $dst" || rm -rf "$dst"
  fi
  do_install "$src" "$dst"
done

# ── Deploy root Python files ─────────────────────────────────────────────────
info "Deploying root modules"
for f in config.py orchestrator.py; do
  do_install "$PROJECT_ROOT/$f" "$QUTE_CONFIG_DIR/$f"
done

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
  "$QUTE_CONFIG_DIR/layers/"*.py \
  "$QUTE_CONFIG_DIR/strategies/"*.py \
  "$QUTE_CONFIG_DIR/policies/"*.py \
  "$QUTE_CONFIG_DIR/themes/"*.py \
  "$QUTE_CONFIG_DIR/keybindings/"*.py; do
  [ -f "$f" ] || continue
  if dry "python3 -m py_compile $f"; then continue; fi
  python3 -m py_compile "$f" && log "ok: $(basename $f)" || log "SYNTAX ERROR: $f"
done

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
$DRY_RUN && echo "  [DRY RUN] No files were changed" ||
  echo "  ✓ Config deployed to $QUTE_CONFIG_DIR"
echo ""
echo "  Layout:"
echo "    config.py           ← entry point (ONLY file qutebrowser loads)"
echo "    orchestrator.py     ← wires all modules"
echo "    core/               ← FSM, pipeline, lifecycle, protocol, strategy, health"
echo "    layers/             ← base, privacy, appearance, behavior, context, performance, user"
echo "    strategies/         ← merge, profile, search, download"
echo "    policies/           ← content, network, security, host"
echo "    themes/             ← 12 extended color schemes"
echo "    keybindings/        ← catalog + conflict detection"
echo "    docs/               ← ARCHITECTURE.md, EXTENDING.md, KEYBINDINGS.md"
echo "    userscripts/        ← open_with.py, search_sel.py, readability.py, …"
echo ""
echo "  Post-install:"
echo "    python3 scripts/gen_keybindings.py    # regenerate docs/KEYBINDINGS.md"
echo "    python3 tests/test_health.py          # run health check tests"
echo ""
echo "  To reload in qutebrowser: :config-source  or  ${LEADER_KEY:-,}r"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
