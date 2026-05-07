#!/usr/bin/env bash
# scripts/install.sh
# ==================
# Deploy qutebrowser config to ~/.config/qutebrowser/
#
# Usage:
#   ./scripts/install.sh [--dry-run] [--backup] [--link] [--force]
#
# Options:
#   --dry-run   Show what would be done, don't do it
#   --backup    Backup existing config before deploying (Model B only)
#   --link      Use symlinks instead of copies (Model B live-dev mode)
#   --force     Skip confirmation prompts (use with caution)

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

INPLACE=false
if [[ "$(realpath "$PROJECT_ROOT" 2>/dev/null || echo "$PROJECT_ROOT")" == "$(realpath "$QUTE_CONFIG_DIR" 2>/dev/null || echo "$QUTE_CONFIG_DIR")" ]]; then
  INPLACE=true
fi

DRY_RUN=false
BACKUP=false
USE_LINKS=false
FORCE=false

for arg in "$@"; do
  case $arg in
  --dry-run) DRY_RUN=true ;;
  --backup) BACKUP=true ;;
  --link) USE_LINKS=true ;;
  --force) FORCE=true ;;
  --help)
    cat <<EOF
Usage: $0 [--dry-run] [--backup] [--link] [--force]

  --link      Use symlinks instead of copies (external-repo mode)
  --backup    Backup existing config dir before deploying
  --force     Skip confirmation prompts

If the project already lives inside ~/.config/qutebrowser/ (in-place mode),
copy/link steps are skipped automatically.
EOF
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
  $DRY_RUN && {
    echo "  [dry] $*"
    return 0
  } || return 1
}

confirm() {
  $FORCE && return 0
  local prompt="$1"
  read -r -p "$prompt [y/N] " response
  [[ "$response" =~ ^[Yy]$ ]]
}

do_link() {
  local src="$1" dst="$2"
  dry "ln -sf $src → $dst" && return
  # If dst is a real directory (not symlink) and we are about to overwrite, warn
  if [[ -e "$dst" && ! -L "$dst" ]]; then
    warn "$dst already exists as a regular file/directory and will be removed"
    confirm "Continue?" || {
      log "skipped $dst"
      return
    }
    rm -rf "$dst"
  elif [[ -L "$dst" ]]; then
    rm -f "$dst"
  fi
  ln -sf "$src" "$dst"
  log "linked: $dst → $src"
}

do_copy() {
  local src="$1" dst="$2"
  dry "cp -r $src → $dst" && return
  if [[ -e "$dst" ]]; then
    warn "$dst already exists and will be removed"
    confirm "Continue?" || {
      log "skipped $dst"
      return
    }
    rm -rf "$dst"
  fi
  cp -r "$src" "$dst"
  log "copied: $dst"
}

do_install() {
  local src="$1" dst="$2"
  # Never copy/link a path to itself
  if [[ "$(realpath "$src" 2>/dev/null || echo "$src")" == "$(realpath "$dst" 2>/dev/null || echo "$dst")" ]]; then
    return
  fi
  $USE_LINKS && do_link "$src" "$dst" || do_copy "$src" "$dst"
}

do_chmod_x() {
  local path="$1"
  dry "chmod +x $path" && return
  local real
  real="$(realpath "$path" 2>/dev/null || echo "$path")"
  [[ -f "$real" ]] && chmod +x "$real"
}

# ── In-place detection notice ─────────────────────────────────────────────────
if $INPLACE; then
  info "In-place mode: project root == qute config dir"
  info "  $PROJECT_ROOT"
  info "  Skipping all copy/link steps; fixing permissions only."
fi

# ── Backup (Model B only) ─────────────────────────────────────────────────────
if ! $INPLACE && $BACKUP && [[ -d "$QUTE_CONFIG_DIR" ]]; then
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
    [[ -d "$src" ]] || {
      log "skip (not found): $dir/"
      continue
    }
    if [[ -d "$dst" ]] && ! $USE_LINKS && ! $FORCE; then
      warn "$dst is an existing directory and will be replaced"
      confirm "Remove and re-deploy?" || {
        log "skipped $dir"
        continue
      }
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
# Safely check if SCRIPTS_SUBDIR contains any .py file (avoid `ls` triggering -e)
has_py_files() {
  [[ -d "$1" ]] && (
    shopt -s nullglob
    set -- "$1"/*.py
    [[ $# -gt 0 ]]
  )
}

if has_py_files "$SCRIPTS_SUBDIR"; then
  SCRIPTS_SRC="$SCRIPTS_SUBDIR"
else
  SCRIPTS_SRC="$PROJECT_ROOT"
fi

# ── Discover userscripts dynamically ──────────────────────────────────────────
# Exclude internal/dev files: __init__.py, gen_*, test_*, install*, diagnostics.py
discover_userscripts() {
  local src_dir="$1"
  for f in "$src_dir"/*.py; do
    [[ -f "$f" ]] || continue
    base="$(basename "$f")"
    [[ "$base" == "__init__.py" ]] && continue
    [[ "$base" == gen_* || "$base" == test_* || "$base" == install* ]] && continue
    [[ "$base" == "diagnostics.py" ]] && continue
    echo "$base"
  done
}

# ── Wire userscripts/ ─────────────────────────────────────────────────────────
info "Wiring userscripts/ → $SCRIPTS_SRC"

if $INPLACE || $USE_LINKS; then
  # Make all discovered scripts executable at source FIRST
  for script_name in $(discover_userscripts "$SCRIPTS_SRC"); do
    src="$SCRIPTS_SRC/$script_name"
    [[ -f "$src" ]] && do_chmod_x "$src"
  done

  # Ensure userscripts/ is a symlink to SCRIPTS_SRC (idempotent)
  current_target=""
  [[ -L "$QUTE_SCRIPTS_DIR" ]] && current_target="$(realpath "$QUTE_SCRIPTS_DIR" 2>/dev/null || true)"
  scripts_real="$(realpath "$SCRIPTS_SRC" 2>/dev/null || echo "$SCRIPTS_SRC")"

  if [[ "$current_target" == "$scripts_real" ]]; then
    ok "userscripts/ → $SCRIPTS_SRC (already correct)"
  else
    if [[ -e "$QUTE_SCRIPTS_DIR" && ! -L "$QUTE_SCRIPTS_DIR" ]]; then
      warn "$QUTE_SCRIPTS_DIR is a regular directory, will be replaced by symlink"
      confirm "Replace with symlink?" || {
        warn "userscripts deployment skipped"
        goto :skip_userscripts
      }
    fi
    dry "ln -sf $SCRIPTS_SRC $QUTE_SCRIPTS_DIR" || {
      rm -rf "$QUTE_SCRIPTS_DIR"
      ln -sf "$SCRIPTS_SRC" "$QUTE_SCRIPTS_DIR"
    }
    ok "userscripts/ → $SCRIPTS_SRC"
  fi
else
  # Copy mode: deploy each discovered script individually
  log "mode: copy individual files"
  dry "mkdir -p $QUTE_SCRIPTS_DIR" || mkdir -p "$QUTE_SCRIPTS_DIR"
  for script_name in $(discover_userscripts "$SCRIPTS_SRC"); do
    src="$SCRIPTS_SRC/$script_name"
    dst="$QUTE_SCRIPTS_DIR/$script_name"
    do_copy "$src" "$dst"
    dry "chmod +x $dst" || chmod +x "$dst"
  done
fi
: skip_userscripts

# ── Make gen_keybindings.py executable ───────────────────────────────────────
for gkb in "$SCRIPTS_SRC/gen_keybindings.py" "$SCRIPTS_SUBDIR/gen_keybindings.py"; do
  [[ -f "$gkb" ]] && {
    do_chmod_x "$gkb"
    break
  }
done

# ── Verify Python syntax ──────────────────────────────────────────────────────
info "Verifying Python syntax"
SYNTAX_ERRORS=0
# Enable nullglob to avoid literal '*' when no files match
shopt -s nullglob
for f in \
  "$QUTE_CONFIG_DIR/config.py" \
  "$QUTE_CONFIG_DIR/orchestrator.py" \
  "$QUTE_CONFIG_DIR/core/"*.py \
  "$QUTE_CONFIG_DIR/layers/"*.py \
  "$QUTE_CONFIG_DIR/strategies/"*.py \
  "$QUTE_CONFIG_DIR/policies/"*.py \
  "$QUTE_CONFIG_DIR/themes/"*.py \
  "$QUTE_CONFIG_DIR/keybindings/"*.py; do
  [[ -f "$f" ]] || continue
  if dry "python3 -m py_compile $(basename "$f")"; then continue; fi
  if python3 -m py_compile "$f" 2>/dev/null; then
    ok "$(basename "$f")"
  else
    warn "SYNTAX ERROR: $f"
    SYNTAX_ERRORS=$((SYNTAX_ERRORS + 1))
  fi
done
shopt -u nullglob
[[ $SYNTAX_ERRORS -gt 0 ]] && warn "$SYNTAX_ERRORS syntax error(s) — check above"

# ── Post-install userscript sanity check ─────────────────────────────────────
info "Userscript sanity check"
ALL_OK=true
for script_name in $(discover_userscripts "$SCRIPTS_SRC"); do
  target="$QUTE_SCRIPTS_DIR/$script_name"
  if [[ -L "$target" ]] || [[ -f "$target" ]]; then
    real="$(realpath "$target" 2>/dev/null || echo "$target")"
    if [[ -x "$real" ]]; then
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
