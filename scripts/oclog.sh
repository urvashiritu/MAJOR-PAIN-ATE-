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

# ---------- prev/next chains (per day) + auto-index ----------

alias_of() { # ".../10-57_ses_abc123.md" -> "path|HH-MM abc123"
  local t="${1#"$OUT_BASE"/}" b
  b="$(basename "${1%.md}")"
  printf '%s|%s %s' "${t%.md}" "${b:0:5}" "${b:10:6}"
}

relink_chains() {
  shopt -s nullglob
  local day_dir files f i n prev next nav pl nl
  for day_dir in "$OUT_BASE"/*/; do
    files=("$day_dir"*.md)
    n=${#files[@]}
    (( n )) || continue
    for i in "${!files[@]}"; do
      f="${files[$i]}"
      prev=""; next=""
      (( i > 0 )) && prev=$(alias_of "${files[$((i - 1))]}")
      (( i < n - 1 )) && next=$(alias_of "${files[$((i + 1))]}")
      nav=""
      [[ -n "$prev" ]] && nav+="← [[${prev%%|*}|${prev#*|}]] "
      [[ -n "$prev" && -n "$next" ]] && nav+="· "
      [[ -n "$next" ]] && nav+="[[${next%%|*}|${next#*|}]] →"
      awk -v nav="$nav" '
        !ins && /^---$/ { print; print ""; print "**" nav "**"; ins = 1; next }
        /^\*\*← / { next }
        { print }
      ' "$f" >"$f.tmp" && mv "$f.tmp" "$f"
    done
  done
}

write_index() {
  {
    echo "# Session Memory Index"
    echo
    echo "opencode session memory · regenerable via \`scripts/oclog.sh\` · open this folder in Obsidian for tree/graph view"
    echo
    local d f n model tin tout base
    for d in "$OUT_BASE"/*/; do
      echo "## $(basename "${d%/}")"
      echo
      for f in "$d"*.md; do
        n="${f%.md}"
        base="$(basename "$n")"
        model=$(grep -m1 '| Model |' "$f" | sed 's/^| Model | \([^ (]*\).*/\1/')
        tin=$(grep -m1 '| Tokens in |' "$f" | sed 's/^| Tokens in | \([^|]*\) |.*/\1/' | tr -d ' ')
        tout=$(grep -m1 '| Tokens out |' "$f" | sed 's/^| Tokens out | \([^|]*\) |.*/\1/' | tr -d ' ')
        echo "- [[${n#"$OUT_BASE"/}|${base:0:5} ${base:10:6}]] · $model · in $tin / out $tout"
      done
      echo
    done
  } >"$OUT_BASE/_index.md"
}

relink_chains
write_index

echo "logged: $OUT ($(wc -l <"$OUT") lines)"
