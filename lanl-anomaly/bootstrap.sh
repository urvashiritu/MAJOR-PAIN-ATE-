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
# Google Drive file id for lanl.duckdb. Sharing must be "Anyone with the link".
LANL_DUCKDB_ID="${LANL_DUCKDB_ID:-147vxAEqS7hGj_KDSG8JJc2hLNq4lyd4c}"
LANL_DUCKDB_URL="${LANL_DUCKDB_URL:-}"

DUCKDB_PATH="data/raw/lanl/lanl.duckdb"
DUCKDB_BYTES=10399002624        # exact size of the real database
DUCKDB_MIN_BYTES=9000000000     # refuse anything meaningfully smaller
VENV="${VENV:-venv}"
PY="$VENV/bin/python"

MODE="${1:-full}"

say()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m  ok\033[0m  %s\n' "$*"; }
warn() { printf '\033[1;33m  !!\033[0m  %s\n' "$*"; }
die()  { printf '\033[1;31m  XX\033[0m  %s\n' "$*" >&2; exit 1; }

# ── Verify the dataset is real and usable ─────────────────────────────
verify_duckdb() {
  say "Verifying dataset"

  if [[ ! -f "$DUCKDB_PATH" ]]; then
    die "missing $DUCKDB_PATH"
  fi

  local size
  size=$(stat -c %s "$DUCKDB_PATH" 2>/dev/null || stat -f %z "$DUCKDB_PATH")
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
print(f"  feat rows: {n:,}")
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

# ── Fetch the dataset ────────────────────────────────────────────────
fetch_duckdb() {
  say "Fetching lanl.duckdb (~9.7 GiB)"
  mkdir -p "$(dirname "$DUCKDB_PATH")"

  if [[ -f "$DUCKDB_PATH" ]]; then
    local size
    size=$(stat -c %s "$DUCKDB_PATH" 2>/dev/null || stat -f %z "$DUCKDB_PATH")
    if [[ "$size" -eq "$DUCKDB_BYTES" ]]; then
      ok "already present and correct size — skipping download"
      return
    fi
    warn "existing file is $size bytes, resuming"
  fi

  if [[ -z "$LANL_DUCKDB_URL" ]]; then
    "$PY" -m pip install -q gdown || die "could not install gdown"
    # gdown is the happy path. It is known to fail on some large Drive files.
    if "$PY" -m gdown "$LANL_DUCKDB_ID" -O "$DUCKDB_PATH" --continue;
      then
        ok "gdown finished"
        return
      fi
    warn "gdown failed, falling back to curl with confirm token"
  fi

  # Drive serves an HTML "too big for virus scan" page above ~100 MB.
  # confirm=t skips it; -C - resumes a partial file.
  curl -fL --retry 10 --retry-delay 5 -C - \
       -o "$DUCKDB_PATH" \
       "${LANL_DUCKDB_URL:-https://drive.usercontent.google.com/download?id=${LANL_DUCKDB_ID}&export=download&confirm=t}"
  ok "curl finished"
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
    verify_duckdb || fetch_duckdb
    verify_duckdb
    verify_models
    verify_scores
    printf '\n\033[1;32mSetup complete.\033[0m Start it with:\n  LANL_DEV=1 %s -m live.app\n' "$PY"
    ;;
esac