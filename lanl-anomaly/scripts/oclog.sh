#!/usr/bin/env bash
# oclog.sh — save an opencode session as a readable changelog entry (universal memory).
#
# Usage:
#   bash scripts/oclog.sh            # logs the most recently updated session
#   bash scripts/oclog.sh latest     # same as above
#   bash scripts/oclog.sh ses_xxx    # log a specific session id
#
# Output: changelog_byopencode/<YYYY-MM-DD>/<HH-MM>_<sessionID>.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_BASE="$ROOT/changelog_byopencode"
TMP="$(mktemp /tmp/opencode-export.XXXXXX.json)"
trap 'rm -f "$TMP"' EXIT

SID="${1:-latest}"
if [[ -z "$SID" || "$SID" == "latest" ]]; then
  SID="$(opencode session list | awk '/^ses_/ {print $1; exit}')"
fi
[[ -n "$SID" ]] || { echo "error: no sessions found" >&2; exit 1; }

opencode export "$SID" >"$TMP"

TITLE=$(jq -r '.info.title // "untitled"' "$TMP")
MODEL=$(jq -r '.info.model.id // "?"' "$TMP")
PROVIDER=$(jq -r '.info.model.providerID // "?"' "$TMP")
VARIANT=$(jq -r '.info.model.variant // "-"' "$TMP")
AGENT=$(jq -r '.info.agent // "-"' "$TMP")
VERSION=$(jq -r '.info.version // "?"' "$TMP")
COST=$(jq -r '.info.cost // 0' "$TMP")
TIN=$(jq -r '.info.tokens.input // 0' "$TMP")
TOUT=$(jq -r '.info.tokens.output // 0' "$TMP")
TREAS=$(jq -r '.info.tokens.reasoning // 0' "$TMP")
TCACHE=$(jq -r '.info.tokens.cache.read // 0' "$TMP")
CREATED=$(jq -r '.info.time.created // 0' "$TMP")
COMPLETED=$(jq -r '.info.time.completed // .info.time.updated // 0' "$TMP")

DAY=$(date -d "@$((CREATED / 1000))" '+%Y-%m-%d')
STAMP=$(date -d "@$((CREATED / 1000))" '+%H-%M')
START_ISO=$(date -d "@$((CREATED / 1000))" '+%Y-%m-%d %H:%M')
END_ISO=$(date -d "@$((COMPLETED / 1000))" '+%H:%M')

hum() {
  awk -v n="$1" 'BEGIN {
    if (n >= 1000000) printf "%.2fM", n / 1000000;
    else if (n >= 1000) printf "%.1fK", n / 1000;
    else printf "%d", n;
  }'
}

OUT_DIR="$OUT_BASE/$DAY"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/${STAMP}_${SID}.md"

{
  cat <<EOF
# Session Log — \`$SID\`

| Field | Value |
|---|---|
| Started | $START_ISO |
| Last activity | $END_ISO |
| Title | $TITLE |
| Model | $MODEL ($PROVIDER, variant: $VARIANT) |
| Agent/mode | $AGENT |
| opencode | v$VERSION |
| Tokens in | $(hum "$TIN") |
| Tokens out | $(hum "$TOUT") |
| Reasoning | $(hum "$TREAS") |
| Cache read | $(hum "$TCACHE") |
| Cost | \$$COST |

---

EOF

  jq -r '
    def hhmm: ((.time.created // 0) / 1000 | floor | localtime | strftime("%H:%M"));
    .messages[]
    | (.info.role // "?") as $role
    | select($role == "user" or $role == "assistant")
    | (.info | hhmm) as $t
    | "\n## [\($t)] \(if $role == "user" then "USER" else "ASSISTANT" end)\n",
      ([.parts[]?
        | if .type == "text" then .text
          elif .type == "tool" then "> ⚙ tool: \(.tool // "?") (\(.state.status // "?"))"
          elif .type == "reasoning" then empty
          elif .type == "file" then "> 📎 file attachment"
          elif .type == "snapshot" then empty
          else empty
          end
      ] | join("\n\n"))
  ' "$TMP"
} >"$OUT"

echo "logged: $OUT ($(wc -l <"$OUT") lines)"
