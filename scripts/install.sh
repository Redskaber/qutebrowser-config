#!/usr/bin/env bash
# scripts/install.sh
# ==================
# Deploy qutebrowser config to ~/.config/qutebrowser/
#
# Supports two deployment models:
#
#   MODEL A — In-place (you already cloned/live inside ~/.config/qutebrowser)
#   ─────────────────────────────────────────────────────────────────────────
#   PROJECT_ROOT == QUTE_CONFIG_DIR
#   Nothing to copy/link.  Just fix permissions and wire userscripts/.
#
#   MODEL B — External repo (project lives elsewhere, deploy to qute config dir)
#   ─────────────────────────────────────────────────────────────────────────
#   PROJECT_ROOT != QUTE_CONFIG_DIR
#   Copy (default) or symlink (--link) dirs/files into QUTE_CONFIG_DIR.
#
# Usage:
#   ./scripts/install.sh [--dry-run] [--backup] [--link]
#
# Options:
#   --dry-run   Show what would be done, don't do it
#   --backup    Backup existing config before deploying (Model B only)
#   --link      Use symlinks instead of copies (Model B live-dev mode)

set -euo pipefail

# ── Path resolution ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(basename "$SCRIPT_DIR")" == "scripts" ]]; then
  PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
  SCRIPTS_SUBDIR="$SCRIPT_DIR"
else
  PROJECT_ROOT="$SCRIPT_DIR"
  SCRIPTS_SUBDIR="$PROJECT_ROOT/scripts"
fi

QUTE_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/qutebrowser"
QUTE_SCRIPTS_DIR="$QUTE_CONFIG_DIR/userscripts"

# Detect in-place model: project root IS the qute config dir
INPLACE=false
if [[ "$(realpath "$PROJECT_ROOT")" == "$(realpath "$QUTE_CONFIG_DIR")" ]]; then
  INPLACE=true
fi

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
    echo ""
    echo "  --link    Use symlinks instead of copies (external-repo mode)"
    echo "  --backup  Backup existing config dir before deploying"
    echo ""
    echo "  If the project already lives inside ~/.config/qutebrowser/"
    echo "  (in-place mode), copy/link steps are skipped automatically."
    exit 0
    ;;
  *)
    echo "Unknown option: $arg"
    exit 1
    ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
log() { echo "  $*"; }
info() { echo "→ $*"; }
warn() { echo "  ⚠  $*"; }
ok() { echo "  ✓  $*"; }

dry() {
  # Return 0 (skip real work) in dry-run; 1 (run real work) otherwise
  $DRY_RUN && {
    echo "  [dry] $*"
    return 0
  } || return 1
}

do_link() {
  local src="$1" dst="$2"
  dry "ln -sf $src → $dst" && return
  [ -e "$dst" ] || [ -L "$dst" ] && rm -rf "$dst"
  ln -sf "$src" "$dst"
  log "linked: $dst → $src"
}

do_copy() {
  local src="$1" dst="$2"
  dry "cp -r $src → $dst" && return
  cp -r "$src" "$dst"
  log "copied: $dst"
}

do_install() {
  local src="$1" dst="$2"
  # Never copy/link a path to itself
  [[ "$(realpath "$src" 2>/dev/null)" == "$(realpath "$dst" 2>/dev/null)" ]] && return
  $USE_LINKS && do_link "$src" "$dst" || do_copy "$src" "$dst"
}

# chmod +x resolving symlinks to set the bit on the real source file
do_chmod_x() {
  local path="$1"
  dry "chmod +x $path" && return
  local real
  real="$(realpath "$path" 2>/dev/null || echo "$path")"
  [ -f "$real" ] && chmod +x "$real"
}

# ── In-place detection notice ─────────────────────────────────────────────────
if $INPLACE; then
  info "In-place mode: project root == qute config dir"
  info "  $PROJECT_ROOT"
  info "  Skipping all copy/link steps; fixing permissions only."
fi

# ── Backup (Model B only) ─────────────────────────────────────────────────────
if ! $INPLACE && $BACKUP && [ -d "$QUTE_CONFIG_DIR" ]; then
  BACKUP_DIR="${QUTE_CONFIG_DIR}.bak.$(date +%Y%m%d_%H%M%S)"
  info "Backing up existing config to $BACKUP_DIR"
  dry "cp -r $QUTE_CONFIG_DIR $BACKUP_DIR" || cp -r "$QUTE_CONFIG_DIR" "$BACKUP_DIR"
fi

# ── Ensure config dir exists ──────────────────────────────────────────────────
dry "mkdir -p $QUTE_CONFIG_DIR" || mkdir -p "$QUTE_CONFIG_DIR"

# ── Deploy package directories (Model B only) ─────────────────────────────────
if ! $INPLACE; then
  info "Deploying package directories"
  for dir in core layers strategies policies themes keybindings docs; do
    src="$PROJECT_ROOT/$dir"
    dst="$QUTE_CONFIG_DIR/$dir"
    [ -d "$src" ] || {
      log "skip (not found): $dir/"
      continue
    }
    if [ -d "$dst" ] && ! $USE_LINKS; then
      dry "rm -rf $dst" || rm -rf "$dst"
    fi
    do_install "$src" "$dst"
  done

  info "Deploying root modules"
  for f in config.py orchestrator.py; do
    do_install "$PROJECT_ROOT/$f" "$QUTE_CONFIG_DIR/$f"
  done
else
  info "Package directories: already in place (skipped)"
fi

# ── Resolve scripts source dir ────────────────────────────────────────────────
# Prefer scripts/ subdir if it has .py files; fall back to project root
if [ -d "$SCRIPTS_SUBDIR" ] && ls "$SCRIPTS_SUBDIR"/*.py &>/dev/null 2>&1; then
  SCRIPTS_SRC="$SCRIPTS_SUBDIR"
else
  SCRIPTS_SRC="$PROJECT_ROOT"
fi

KNOWN_SCRIPTS=(
  open_with.py
  search_sel.py
  readability.py
  tab_restore.py
  password.py
  context_switch.py
  download.py
)

# ── Wire userscripts/ ─────────────────────────────────────────────────────────
info "Wiring userscripts/ → $SCRIPTS_SRC"

# In in-place or --link mode: userscripts/ is (or becomes) a directory symlink
# pointing at the scripts/ source dir.  That's the `userscripts -> scripts`
# layout already present in your config dir.
if $INPLACE || $USE_LINKS; then
  # Step 1: chmod +x all .py files at source FIRST
  for script_name in "${KNOWN_SCRIPTS[@]}"; do
    src="$SCRIPTS_SRC/$script_name"
    [ -f "$src" ] && do_chmod_x "$src"
  done
  # Sweep any extras (skip gen_* and test_* — not userscripts)
  for script in "$SCRIPTS_SRC"/*.py; do
    [ -f "$script" ] || continue
    base="$(basename "$script")"
    [[ "$base" == gen_* || "$base" == test_* || "$base" == install* ]] && continue
    do_chmod_x "$script"
  done

  # Step 2: Ensure userscripts/ is a symlink to SCRIPTS_SRC
  # (idempotent — skip if already pointing at the right place)
  current_target=""
  [ -L "$QUTE_SCRIPTS_DIR" ] && current_target="$(realpath "$QUTE_SCRIPTS_DIR" 2>/dev/null || true)"
  scripts_real="$(realpath "$SCRIPTS_SRC" 2>/dev/null || echo "$SCRIPTS_SRC")"

  if [[ "$current_target" == "$scripts_real" ]]; then
    ok "userscripts/ → $SCRIPTS_SRC (already correct)"
  else
    dry "ln -sf $SCRIPTS_SRC $QUTE_SCRIPTS_DIR" && true || {
      [ -e "$QUTE_SCRIPTS_DIR" ] || [ -L "$QUTE_SCRIPTS_DIR" ] && rm -rf "$QUTE_SCRIPTS_DIR"
      ln -sf "$SCRIPTS_SRC" "$QUTE_SCRIPTS_DIR"
      ok "userscripts/ → $SCRIPTS_SRC"
    }
  fi

else
  # Copy mode (Model B, no --link): deploy individual files
  log "mode: copy individual files"
  dry "mkdir -p $QUTE_SCRIPTS_DIR" || mkdir -p "$QUTE_SCRIPTS_DIR"

  for script_name in "${KNOWN_SCRIPTS[@]}"; do
    src="$SCRIPTS_SRC/$script_name"
    if [ -f "$src" ]; then
      dst="$QUTE_SCRIPTS_DIR/$script_name"
      do_copy "$src" "$dst"
      dry "chmod +x $dst" || chmod +x "$dst"
    else
      log "skip (not found): $script_name"
    fi
  done
fi

# ── Make gen_keybindings.py executable ───────────────────────────────────────
for gkb in "$SCRIPTS_SRC/gen_keybindings.py" "$SCRIPTS_SUBDIR/gen_keybindings.py"; do
  [ -f "$gkb" ] && {
    do_chmod_x "$gkb"
    break
  }
done

# ── Verify Python syntax ──────────────────────────────────────────────────────
info "Verifying Python syntax"
SYNTAX_ERRORS=0
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
  if dry "python3 -m py_compile $(basename "$f")"; then continue; fi
  if python3 -m py_compile "$f" 2>/dev/null; then
    ok "$(basename "$f")"
  else
    warn "SYNTAX ERROR: $f"
    SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
  fi
done
[ "$SYNTAX_ERRORS" -gt 0 ] && warn "$SYNTAX_ERRORS syntax error(s) — check above"

# ── Post-install userscript sanity check ─────────────────────────────────────
info "Userscript sanity check"
ALL_OK=true
for script_name in "${KNOWN_SCRIPTS[@]}"; do
  target="$QUTE_SCRIPTS_DIR/$script_name"
  if [ -L "$target" ] || [ -f "$target" ]; then
    real="$(realpath "$target" 2>/dev/null || echo "$target")"
    if [ -x "$real" ]; then
      ok "$script_name"
    else
      warn "$script_name exists but not executable — fixing"
      dry "chmod +x $real" || chmod +x "$real"
      ALL_OK=false
    fi
  else
    log "not deployed: $script_name"
  fi
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if $DRY_RUN; then
  echo "  [DRY RUN] No files were changed"
elif $INPLACE; then
  echo "  ✓ In-place config ready at $QUTE_CONFIG_DIR"
else
  echo "  ✓ Config deployed to $QUTE_CONFIG_DIR"
fi
echo ""
echo "  Deployment model: $($INPLACE && echo 'in-place (project == config dir)' || echo 'external repo')"
echo "  Scripts source:   $SCRIPTS_SRC"
echo "  userscripts/:     $([ -L "$QUTE_SCRIPTS_DIR" ] && echo "→ $(readlink "$QUTE_SCRIPTS_DIR")" || echo "$QUTE_SCRIPTS_DIR")"
echo ""
echo "  Post-install:"
echo "    python3 scripts/gen_keybindings.py   # regenerate KEYBINDINGS.md"
echo "    python3 tests/test_health.py         # run health checks"
echo ""
echo "  Reload qutebrowser:  :config-source   or   ,r"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
