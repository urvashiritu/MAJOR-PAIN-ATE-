#!/usr/bin/env bash
# Set up the LANL anomaly detection demo on a fresh machine.
#
#   ./bootstrap.sh              full setup (deps + dataset)
#   ./bootstrap.sh --deps-only  just Python deps
#   ./bootstrap.sh --verify     check an existing setup, change nothing
#
# Override the dataset location with LANL_DUCKDB_URL / LANL_DUCKDB_ID.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ── Config ────────────────────────────────────────────────────────────
# Google Drive file id for lanl.duckdb.zst. The sharing must be
# "Anyone with the link". Override with LANL_DUCKDB_ID or LANL_DUCKDB_URL.
LANL_DUCKDB_ID="${LANL_DUCKDB_ID:-REPLACE_WITH_YOUR_DRIVE_FILE_ID}"
LANL_DUCKDB_URL="${LANL_DUCKDB_URL:-}"

DUCKDB_PATH="data/raw/lanl/lanl.duckdb"
ZST_PATH="data/raw/lanl/lanl.duckdb.zst"   # the file you host
DUCKDB_BYTES=10399002624        # size of the database after decompression
DUCKDB_MIN_BYTES=9000000000     # refuse anything meaningfully smaller
ZST_MIN_BYTES=5000000000        # smallest compressed file we accept
ZST_MAX_BYTES=6500000000        # largest compressed file we accept
VENV="${VENV:-venv}"
PY="$VENV/bin/python"

MODE="${1:-full}"

say()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m  %s\n' "$*"; }
warn() { printf '\033[1;33m  !!\033[0m  %s\n' "$*"; }
die()  { printf '\033[1;31m  XX\033[0m  %s\n' "$*" >&2; exit 1; }

file_size() { stat -c %s "$1" 2>/dev/null || stat -f %z "$1"; }

# ── Verify the dataset is real and usable ─────────────────────────────
verify_duckdb() {
  say "Verifying dataset"

  if [[ ! -f "$DUCKDB_PATH" ]]; then
    die "missing $DUCKDB_PATH"
  fi

  local size
  size=$(file_size "$DUCKDB_PATH")
  printf '  size: %s bytes (expected %s)\n' "$size" "$DUCKDB_BYTES"

  if [[ "$size" -lt "$DUCKDB_MIN_BYTES" ]]; then
    die "dataset is truncated ($size < $DUCKDB_MIN_BYTES bytes) — re-run ./bootstrap.sh"
  fi
  [[ "$size" -eq "$DUCKDB_BYTES" ]] || warn "size differs from the known-good build; continuing"

  # Opening it is the only real proof. A file can be the right length and
  # still be a truncated Drive response.
  "$PY" - "$DUCKDB_PATH" <<'PYEOF'
import sys, duckdb
con = duckdb.connect(sys.argv[1], read_only=True)
n = con.execute("SELECT COUNT(*) FROM feat").fetchone()[0]
assert n > 29_000_000, f"feat has only {n:,} rows, expected ~29.9M"
red = con.execute("SELECT COUNT(*) FROM feat WHERE is_red").fetchone()[0]
print(f"  feat rows: {n:,}  (red: {red})")
PYEOF
  ok "dataset opens and feat is intact"
}

verify_models() {
  say "Verifying models"
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
  [[ $missing -eq 0 ]] || die "models incomplete — run: git lfs pull"
  ok "models present"
}

verify_scores() {
  say "Verifying scores parquet"
  [[ -f data/processed/lanl_scores.parquet ]] \
    || die "missing data/processed/lanl_scores.parquet — run: git lfs pull"
  "$PY" - <<'PYEOF'
import pandas as pd
df = pd.read_parquet("data/processed/lanl_scores.parquet", columns=["anomaly_score"])
assert len(df) > 29_000_000, f"only {len(df):,} rows, expected ~29.9M"
print(f"  scored rows: {len(df):,}")
PYEOF
  ok "scores parquet readable"
}

# ── Fetch and decompress the dataset ──────────────────────────────────
# A file the user copied here by hand. This makes a USB stick or a phone
# transfer enough to set up a machine. No network is used.
use_local_copy() {
  if [[ -f "$DUCKDB_PATH" ]]; then
    local size
    size=$(file_size "$DUCKDB_PATH")
    if [[ "$size" -eq "$DUCKDB_BYTES" ]]; then
      ok "found lanl.duckdb in place — no download necessary"
      return 0
    fi
    warn "lanl.duckdb is $size bytes, which is not correct"
    return 1
  fi

  if [[ -f "$ZST_PATH" ]]; then
    local size
    size=$(file_size "$ZST_PATH")
    if [[ "$size" -lt "$ZST_MIN_BYTES" || "$size" -gt "$ZST_MAX_BYTES" ]]; then
      warn "lanl.duckdb.zst is $size bytes. This copy is probably incomplete."
      warn "Copy the file again, or delete it to download a new one."
      return 1
    fi
    ok "found lanl.duckdb.zst ($size bytes) — using the local copy"
    decompress_duckdb
    return $?
  fi

  return 1
}

decompress_duckdb() {
  say "Decompressing lanl.duckdb.zst (5.6 GB to 9.7 GiB)"

  command -v zstd >/dev/null || die "zstd is not installed. Install it with: sudo apt install zstd"

  # Decompress to a temporary name. A partial write must never look complete.
  local tmp="${DUCKDB_PATH}.partial"
  rm -f "$tmp"
  zstd -d -T0 -f "$ZST_PATH" -o "$tmp" || die "zstd could not read $ZST_PATH. The download is probably truncated."

  local size
  size=$(file_size "$tmp")
  [[ "$size" -eq "$DUCKDB_BYTES" ]] || die "decompressed to $size bytes, expected $DUCKDB_BYTES"

  mv "$tmp" "$DUCKDB_PATH"
  ok "decompressed to $(numfmt --to=iec "$size")"
}

fetch_zst() {
  say "Fetching lanl.duckdb.zst (5.6 GB)"
  mkdir -p "$(dirname "$ZST_PATH")"

  if [[ -f "$ZST_PATH" ]]; then
    local size
    size=$(file_size "$ZST_PATH")
    if [[ "$size" -ge "$ZST_MIN_BYTES" && "$size" -le "$ZST_MAX_BYTES" ]]; then
      ok "already downloaded ($size bytes)"
      return
    fi
    warn "existing .zst is $size bytes, resuming"
  fi

  if [[ "$LANL_DUCKDB_ID" == "REPLACE_WITH_YOUR_DRIVE_FILE_ID" && -z "$LANL_DUCKDB_URL" ]]; then
    say "No dataset found, and no download location is configured."
    cat <<EOF

  You have two ways to supply the database.

  1. Copy the file to this computer
     Copy $(basename "$ZST_PATH") (5.6 GB) or lanl.duckdb (9.7 GiB) into:
       $(pwd)/$(dirname "$ZST_PATH")
     A USB stick or a phone cable works. Then run ./bootstrap.sh again.

  2. Download the file
     Set LANL_DUCKDB_ID in this script to your Google Drive file id, or set
     LANL_DUCKDB_URL to a direct link. See SETUP.md.

EOF
    die "the dataset is not available"
  fi

  if [[ -z "$LANL_DUCKDB_URL" ]]; then
    "$PY" -m pip install -q gdown || die "could not install gdown"
    # gdown is the first choice. It fails on some large Drive files.
    if "$PY" -m gdown "$LANL_DUCKDB_ID" -O "$ZST_PATH" --continue; then
      ok "gdown finished"
      return
    fi
    warn "gdown failed, using curl with the confirm token"
  fi

  # Drive serves an HTML page instead of files above about 100 MB.
  # The token skips this page. -C - resumes a partial file.
  curl -fL --retry 10 --retry-delay 5 -C - \
       -o "$ZST_PATH" \
       "${LANL_DUCKDB_URL:-https://drive.usercontent.google.com/download?id=${LANL_DUCKDB_ID}&export=download&confirm=t}"
  ok "curl finished"
}

fetch_duckdb() {
  if [[ -f "$DUCKDB_PATH" ]]; then
    local size
    size=$(file_size "$DUCKDB_PATH")
    if [[ "$size" -eq "$DUCKDB_BYTES" ]]; then
      ok "lanl.duckdb is already correct — no download necessary"
      return
    fi
    warn "lanl.duckdb is $size bytes, which is not correct"
  fi
  fetch_zst
  decompress_duckdb
}

install_deps() {
  say "Installing Python deps into $VENV"

  if [[ ! -d "$VENV" ]]; then
    python3 -m venv "$VENV"
    ok "created $VENV"
  fi

  "$VENV/bin/pip" install -q --upgrade pip

  # The CUDA build of torch is ~2.5 GB and this demo never calls .cuda().
  # Default to the CPU wheel; set USE_GPU=1 if you want CUDA.
  if [[ "${USE_GPU:-0}" == "1" ]]; then
    "$VENV/bin/pip" install -q -r requirements.txt
  else
    "$VENV/bin/pip" install -q --index-url https://download.pytorch.org/whl/cpu \
                                   --extra-index-url https://pypi.org/simple \
                                   -r requirements.txt
  fi
  ok "deps installed"

  "$PY" -c "import live.app" >/dev/null 2>&1 \
    || die "live.app still will not import — run: $PY -c 'import live.app' to see why"
  ok "live.app imports"
}

fetch_lfs() {
  say "Fetching Git LFS assets (~1.5 GB)"
  command -v git-lfs >/dev/null && git lfs install >/dev/null 2>&1 || {
    warn "git-lfs not installed — install it, then re-run"
    return
  }
  git lfs pull
  ok "lfs assets fetched"
}

# ── Main ──────────────────────────────────────────────────────────────
printf '\033[1mLANL anomaly detection — bootstrap\033[0m\n'

case "$MODE" in
  --verify)
    [[ -x "$PY" ]] || die "no $VENV — run ./bootstrap.sh first"
    verify_duckdb; verify_models; verify_scores
    printf '\n\033[1;32mAll checks passed.\033[0m Start it with:\n  LANL_DEV=1 %s -m live.app\n' "$PY"
    ;;
  --deps-only)
    install_deps; fetch_lfs
    ;;
  *)
    install_deps
    fetch_lfs
    # Order matters. A file the user copied here wins over any download.
    if ! use_local_copy; then
      fetch_duckdb
    fi
    verify_duckdb
    verify_models
    verify_scores
    printf '\n\033[1;32mSetup complete.\033[0m Start it with:\n  LANL_DEV=1 %s -m live.app\n' "$PY"
    ;;
esac