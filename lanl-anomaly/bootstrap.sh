#!/usr/bin/env bash
# Set up the LANL anomaly detection demo on a machine.
#
#   ./bootstrap.sh              full setup
#   ./bootstrap.sh --deps-only  install the Python packages and the LFS files
#   ./bootstrap.sh --verify     check the setup. This changes nothing.
#
# The database is 9.7 GiB, so Git LFS cannot carry it. You must copy the file
# to this machine before you run this script. See SETUP.md.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ── Config ────────────────────────────────────────────────────────────
DATA_DIR="data/raw/lanl"
DUCKDB_PATH="$DATA_DIR/lanl.duckdb"
ZST_PATH="$DATA_DIR/lanl.duckdb.zst"

DUCKDB_BYTES=10399002624   # the size of the database
DUCKDB_MIN_BYTES=9000000000
ZST_MIN_BYTES=5000000000   # the smallest correct compressed file
ZST_MAX_BYTES=6500000000   # the largest correct compressed file

VENV="${VENV:-venv}"
PY="$VENV/bin/python"
MODE="${1:-full}"

say()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m  %s\n' "$*"; }
warn() { printf '\033[1;33m  !!\033[0m  %s\n' "$*"; }
die()  { printf '\033[1;31m  XX\033[0m  %s\n' "$*" >&2; exit 1; }

file_size() { stat -c %s "$1" 2>/dev/null || stat -f %z "$1"; }

have_dataset() { [[ -f "$DUCKDB_PATH" || -f "$ZST_PATH" ]]; }

# ── The dataset ───────────────────────────────────────────────────────
dataset_help() {
  cat <<EOF

  The script did not find the database.

  Copy this file to this computer:

      lanl.duckdb.zst   (5,613,536,885 bytes)

  Put the file in this directory:

      $REPO_ROOT/$DATA_DIR

  A memory stick, a phone cable, or a network share all work. The file name
  must stay lanl.duckdb.zst. Then run ./bootstrap.sh again.

  You can also copy lanl.duckdb (10,399,002,624 bytes) instead. The script
  uses that file directly.

EOF
}

decompress_duckdb() {
  say "Decompressing lanl.duckdb.zst (5.6 GB becomes 9.7 GiB)"

  command -v zstd >/dev/null \
    || die "zstd is not installed. Install it with: sudo apt install zstd"

  # Write to a temporary name first. A partial write must never look complete.
  local tmp="${DUCKDB_PATH}.partial"
  rm -f "$tmp"
  zstd -d -T0 -f "$ZST_PATH" -o "$tmp" \
    || die "zstd could not read $ZST_PATH. This copy is probably incomplete."

  local size
  size=$(file_size "$tmp")
  [[ "$size" -eq "$DUCKDB_BYTES" ]] \
    || die "decompressed to $size bytes, but the database is $DUCKDB_BYTES bytes. This copy is not correct."

  mv "$tmp" "$DUCKDB_PATH"
  ok "decompressed to $(numfmt --to=iec "$size")"
}

# Use the file the user copied here. This never uses the network.
install_dataset() {
  if [[ -f "$DUCKDB_PATH" ]]; then
    local size
    size=$(file_size "$DUCKDB_PATH")
    if [[ "$size" -eq "$DUCKDB_BYTES" ]]; then
      ok "lanl.duckdb is in place"
      return 0
    fi
    warn "lanl.duckdb is $size bytes, but the database is $DUCKDB_BYTES bytes"
    return 1
  fi

  if [[ -f "$ZST_PATH" ]]; then
    local size
    size=$(file_size "$ZST_PATH")
    if [[ "$size" -lt "$ZST_MIN_BYTES" || "$size" -gt "$ZST_MAX_BYTES" ]]; then
      warn "lanl.duckdb.zst is $size bytes, so this copy is not correct"
      warn "Copy the file again. The correct size is between"
      warn "  $ZST_MIN_BYTES and $ZST_MAX_BYTES bytes."
      return 1
    fi
    ok "found lanl.duckdb.zst ($size bytes)"
    decompress_duckdb
    return $?
  fi

  dataset_help
  return 1
}

verify_duckdb() {
  say "Checking the database"

  [[ -f "$DUCKDB_PATH" ]] || die "missing $DUCKDB_PATH"

  local size
  size=$(file_size "$DUCKDB_PATH")
  printf '  size: %s bytes (expected %s)\n' "$size" "$DUCKDB_BYTES"

  if [[ "$size" -lt "$DUCKDB_MIN_BYTES" ]]; then
    die "the database is incomplete ($size bytes). Copy the file again."
  fi
  [[ "$size" -eq "$DUCKDB_BYTES" ]] \
    || warn "the size differs from the correct build, but the file is large enough"

  # Opening the file is the only real check. A file can have the correct
  # length and still be incomplete.
  "$PY" - "$DUCKDB_PATH" <<'PYEOF'
import sys, duckdb
con = duckdb.connect(sys.argv[1], read_only=True)
rows = con.execute("SELECT COUNT(*) FROM feat").fetchone()[0]
assert rows > 29_000_000, f"feat has only {rows:,} rows, but it must have about 29.9M"
red = con.execute("SELECT COUNT(*) FROM feat WHERE is_red").fetchone()[0]
print(f"  feat rows: {rows:,}  (red team events: {red})")
PYEOF
  ok "the database opens and the table feat is correct"
}

# ── The packages and the models ───────────────────────────────────────
verify_models() {
  say "Checking the models"
  local missing=0
  for f in models/lanl_lgb_21feat.joblib \
           models/lanl_lstm_ae_2ep_bs128_20260913_162002.pt; do
    if [[ -f "$f" ]]; then
      printf '  %-56s %s\n' "$f" "$(du -h "$f" | cut -f1)"
    else
      warn "missing $f"
      missing=1
    fi
  done
  [[ $missing -eq 0 ]] || die "the models are incomplete. Run: git lfs pull"
  ok "the models are in place"
}

verify_scores() {
  say "Checking the scores parquet"
  [[ -f data/processed/lanl_scores.parquet ]] \
    || die "missing data/processed/lanl_scores.parquet. Run: git lfs pull"
  "$PY" - <<'PYEOF'
import pandas as pd
df = pd.read_parquet("data/processed/lanl_scores.parquet", columns=["anomaly_score"])
assert len(df) > 29_000_000, f"the file has only {len(df):,} rows, but it must have about 29.9M"
print(f"  scored rows: {len(df):,}")
PYEOF
  ok "the scores parquet is readable"
}

install_deps() {
  say "Installing the Python packages into $VENV"

  if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
    ok "created $VENV"
  fi

  "$VENV/bin/pip" install -q --upgrade pip

  # The CUDA build of torch is about 5.9 GB. The demo does not use a GPU.
  # This script installs the CPU build. Set USE_GPU=1 for the CUDA build.
  if [[ "${USE_GPU:-0}" == "1" ]]; then
    "$VENV/bin/pip" install -q -r requirements.txt
  else
    "$VENV/bin/pip" install -q --index-url https://download.pytorch.org/whl/cpu \
                                   --extra-index-url https://pypi.org/simple \
                                   -r requirements.txt
  fi
  ok "the packages are installed"

  "$PY" -c "import live.app" >/dev/null 2>&1 \
    || die "live.app does not import. Run: $PY -c 'import live.app' to see the error"
  ok "live.app imports"
}

fetch_lfs() {
  say "Fetching the Git LFS files (about 1.5 GB)"
  if ! command -v git-lfs >/dev/null; then
    die "git-lfs is not installed. Install it with: sudo apt install git-lfs"
  fi
  git lfs install >/dev/null 2>&1 || true
  git lfs pull
  ok "the LFS files are in place"
}

finish() {
  printf '\n\033[1;32mThe setup is complete.\033[0m Start the demo with:\n  LANL_DEV=1 %s -m live.app\n' "$PY"
}

# ── Main ──────────────────────────────────────────────────────────────
printf '\033[1mLANL anomaly detection — bootstrap\033[0m\n'

case "$MODE" in
  --verify)
    [[ -x "$PY" ]] || die "there is no $VENV directory. Run ./bootstrap.sh first"
    verify_duckdb; verify_models; verify_scores
    printf '\n\033[1;32mAll checks passed.\033[0m Start it with:\n  LANL_DEV=1 %s -m live.app\n' "$PY"
    ;;
  --deps-only)
    install_deps; fetch_lfs
    ;;
  *)
    install_deps
    fetch_lfs
    # install_dataset returns 1 and prints help if the file is not here.
    install_dataset || die "the database is not available"
    verify_duckdb
    verify_models
    verify_scores
    finish
    ;;
esac