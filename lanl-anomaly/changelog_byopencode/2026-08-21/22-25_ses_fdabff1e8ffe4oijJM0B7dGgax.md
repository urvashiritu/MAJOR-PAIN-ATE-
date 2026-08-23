# Session Log — `ses_fdabff1e8ffe4oijJM0B7dGgax`

| Field | Value |
|---|---|
| Started | 2026-08-21 22:25 |
| Last activity | 22:36 |
| Title | New session - 2026-08-21T16:55:50.039Z |
| Model | mimo-v2.5-free (opencode, variant: default) |
| Agent/mode | build |
| opencode | v1.18.21 |
| Tokens in | 214.4K |
| Tokens out | 1.5K |
| Reasoning | 1.2K |
| Cache read | 376.7K |
| Cost | $0 |

---

**← [[2026-08-21/22-13_ses_fdacb0ec5ffeyQQfb3BYmd7xGv|22-13 fdacb0]] · [[2026-08-21/22-36_ses_fdab61681ffe1Ilcm0l28m1dVh|22-36 fdab61]] →**







## [22:25] USER

Prompt:

# OmniRoute Setup Prompt for Your YouTube Audience

Copy and paste the prompt below into Claude Code, Antigravity, or any AI coding assistant.

> **Read this first — it's the part every other guide gets wrong.**
>
> This sets up the **Claude Code CLI** (terminal). The **Claude Desktop app cannot be routed through
> OmniRoute at all.** Not with `~/.zshrc`, not with `launchctl setenv`, not with a Launch Agent plist,
> and not with `~/.claude/settings.json`. This was verified by controlled test, not assumed — see
> "Why the Desktop app can't work" at the bottom. If a guide hands you `launchctl` commands for the
> desktop app, those commands run fine and then silently do nothing.
>
> Verified on macOS, Claude Code 2.1.222, OmniRoute 3.8.49.

---

## The Prompt

I need you to configure my **Claude Code CLI** to route through OmniRoute — an AI gateway running
locally on my machine. Do **not** attempt to configure the Claude Desktop app: it overwrites
`ANTHROPIC_BASE_URL` and strips `ANTHROPIC_API_KEY` after any config is read, so it cannot be
redirected. If I ask you to do that anyway, tell me it's not possible instead of writing config that
appears to work.

### What is OmniRoute?

OmniRoute is a local AI gateway (runs on `localhost:20128`) that routes my AI requests through
multiple providers with auto-fallback, letting me use hundreds of providers through a single
endpoint. It's already installed and running via the `omniroute` command.

The reason this works with Claude Code specifically: OmniRoute serves the **native Anthropic Messages
format** at `/v1/messages` — the exact wire protocol Claude Code speaks. It is not a translation
shim.

### How Claude Code connects to OmniRoute

| Variable | Value |
|---|---|
| `ANTHROPIC_BASE_URL` | `http://localhost:20128` (**no** `/v1` suffix) |
| `ANTHROPIC_API_KEY` | `omniroute` (or your key from Dashboard → Endpoints) |
| `ANTHROPIC_MODEL` | the model or combo to use (see options below) |
| `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY` | `1` — shows gateway models in the `/model` picker |
| `CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT` | `1` — prevents context window warnings |

### Step 1 — Prove the gateway is up before changing anything

```bash
curl -s -X POST http://localhost:20128/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: omniroute" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"auto/best-coding","max_tokens":50,"messages":[{"role":"user","content":"Reply with exactly: OMNIROUTE_OK"}]}'
```

You should get a normal Anthropic-shaped JSON response containing `OMNIROUTE_OK`. If this fails, stop
here and fix OmniRoute — nothing downstream can work.

### Step 2 — Add the env block to `~/.zshrc` (Mac) or `~/.bashrc` (Linux)

```bash
# === OmniRoute Configuration for Claude Code CLI ===
export ANTHROPIC_BASE_URL=http://localhost:20128
export ANTHROPIC_API_KEY=omniroute
export ANTHROPIC_MODEL=<MODEL_NAME>
export CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1
export CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1
# === End OmniRoute Configuration ===
```

Then run `source ~/.zshrc`, or open a new terminal.

### Step 3 — CRITICAL: check `~/.claude/settings.json` for a conflicting `env` block

This is the number one silent failure, and no other guide mentions it. Claude Code's
`settings.json` has an `env` block that **overrides your shell environment** for model variables. If
it pins Anthropic model names, OmniRoute rejects them:

```
API Error: 400 Ambiguous model 'claude-opus-5'. Use provider/model prefix
(ex: anthropic/claude-opus-5 or gh/claude-opus-5).
```

Open `~/.claude/settings.json`. If the `env` block contains any of the following, they will beat your
`~/.zshrc` and must be removed, or changed to valid OmniRoute model ids:

- `ANTHROPIC_MODEL`
- `ANTHROPIC_DEFAULT_OPUS_MODEL`
- `ANTHROPIC_DEFAULT_SONNET_MODEL`
- `ANTHROPIC_DEFAULT_HAIKU_MODEL`
- `ANTHROPIC_SMALL_FAST_MODEL`

Also check the top-level `"model"` key — a value like `sonnet` or `opus` resolves through the
`ANTHROPIC_DEFAULT_*` variables above.

**Precedence, highest wins:** `--model` flag → `settings.json` `env` → shell environment.

One important exception, confirmed by test: `settings.json` can set `ANTHROPIC_BASE_URL` **only if
nothing else has already set it**, and its `ANTHROPIC_API_KEY` is *never* honored as a credential.
This is why it is not a workaround for the desktop app.

### Step 4 — Verify the request actually reaches the gateway

```bash
claude -p "Reply with exactly: OMNIROUTE_OK" --model auto/best-coding --max-turns 1
```

Read the result carefully:

- Reply contains `OMNIROUTE_OK` → **working.**
- An error naming provider prefixes or ambiguous models → **also good**; that error came *from*
  OmniRoute, so routing works. Fix the model name (Step 3).
- `Invalid API key` → you're still hitting Anthropic. Your env block didn't apply.

### Available model options

- **Auto combos** (pre-built smart routing): `auto/best-coding`, `auto/best-reasoning`, `auto/best-fast`,
  `auto/best-vision`, `auto/best-chat`, `auto/pro-coding`, `auto/fast`, `auto/cheap`, `auto/smart`,
  `auto/offline`, `auto/best-free`, `auto/claude-opus`, `auto/claude-sonnet`
- **Custom combos** created in the OmniRoute dashboard: just the combo name, e.g. `da`
- **Specific providers**: always include the provider prefix, e.g. `openrouter/anthropic/claude-sonnet-4`
- **Free models**: `auto/best-free`, `auto/coding:free`

List everything your install actually exposes:

```bash
curl -s http://localhost:20128/v1/models | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data']]"
```

Note: a model only routes if you have a provider key that serves it. Check yours with
`omniroute keys list`.

### When switching models

Update `ANTHROPIC_MODEL` in `~/.zshrc`, then `source ~/.zshrc` or open a new terminal. For a one-off,
pass `--model <name>` — it overrides everything. No app restart, no `launchctl`, no plist, no
Launch Agent.

### To revert to normal Claude

Delete the block from `~/.zshrc` and open a new terminal. If a previous guide had you set GUI-level
variables, clean those up too:

```bash
launchctl unsetenv ANTHROPIC_BASE_URL
launchctl unsetenv ANTHROPIC_API_KEY
launchctl unsetenv ANTHROPIC_MODEL
launchctl unsetenv CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY
launchctl unsetenv CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT
launchctl remove com.omniroute.env 2>/dev/null
rm -f ~/Library/LaunchAgents/com.omniroute.env.plist
```

### How to interpret my request

`ANTHROPIC_MODEL` must be a **model id or a combo name** — never a bare provider name. Resolve what I
ask for as follows:

- **An exact id** (`auto/best-coding`, `aug/opus4.8`, `openrouter/anthropic/claude-sonnet-4`) → use it
  as-is.
- **A combo name I created** (`da`, `high-availability`) → use the bare name. This works; combos
  resolve on their own.
- **A bare provider name** (`openrouter`, `kimi`, `groq`) → **this is not valid and will fail** with
  `Unable to determine provider for model 'openrouter'`. Do not set it. Instead, run the model-list
  command below, show me the ids for that provider, and ask which one I want — or propose the closest
  `auto/*` combo and confirm before writing it.
- **A vague goal** ("cheapest", "best for coding", "something free") → map to the matching `auto/*`
  combo and tell me which one you picked.

Then confirm the choice is real before writing it to `~/.zshrc`:

```bash
curl -s http://localhost:20128/v1/models | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data']]" | grep -x "<MODEL_NAME>"
```

If that prints nothing, the id doesn't exist in my install — stop and ask me rather than writing it.
Also check `omniroute keys list`: a model only routes if I hold a provider key that serves it.

### My request

[TELL THE AI WHAT MODEL/COMBO/PROVIDER YOU WANT HERE]

---

## Example uses

Replace the last line with:

| What you say | What it sets |
|---|---|
| "Set me up with auto/best-coding" | `auto/best-coding` — used as-is |
| "Use free models" | `auto/best-free` |
| "Switch to my combo called da" | `da` — bare combo name, works |
| "Use the cheapest models" | `auto/cheap` |
| "Route through Claude Opus via OmniRoute" | `auto/claude-opus` |
| "Launch with OpenRouter" | ⚠️ nothing directly — a provider is not a model. The assistant should list your OpenRouter model ids and ask which one, or suggest an `auto/*` combo. |

## Prerequisites

1. Install OmniRoute: `npm install -g omniroute`
2. Add at least one provider key: `omniroute setup` (or the dashboard at `http://localhost:20128`)
3. Run OmniRoute in a terminal: `omniroute` — keep it running
4. Paste the prompt above into your AI assistant and tell it which model you want

---

## Why the Desktop app can't work

This is the section the original prompt got wrong. It isn't a configuration mistake you can fix —
the app is built to reclaim these variables.

`launchctl setenv` **does** successfully push variables into a GUI app. Measured live from inside a
running desktop session, these arrived intact:

```
CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1             ✅ arrived
CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1   ✅ arrived
ANTHROPIC_MODEL=auto/best-coding                         ✅ arrived
```

But the only two that matter did not:

```
ANTHROPIC_BASE_URL=https://api.anthropic.com             ❌ overwritten by the app
ANTHROPIC_API_KEY                                        ❌ stripped entirely
```

When the desktop app launches its agent, it sets `ANTHROPIC_BASE_URL` from its own internal API host,
blanks `ANTHROPIC_API_KEY` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_CUSTOM_HEADERS`, and injects an
OAuth token instead. Those variables are then locked on the child process.

**`settings.json` is not a way around this.** Three controlled runs of the real binary:

| Test | Setup | Result |
|---|---|---|
| A | `settings.json` base URL **+** an already-set base URL | hit Anthropic — `Invalid API key` |
| B | no `env` block at all, same conditions | **identical result** |
| C | `settings.json` base URL, nothing else set | reached OmniRoute ✅ |

A and B producing identical output is the proof: once something has already set the base URL, your
`settings.json` may as well not exist. The desktop app always sets it. Its `ANTHROPIC_API_KEY` also
failed as a credential — that run died at `Not logged in` before making any request.

**The underlying reason is authentication, not restriction for its own sake.** The desktop app signs
in with your **Claude subscription over OAuth**, not an API key. An OAuth token is only valid against
Anthropic's own endpoint, so the app pins the endpoint to match the credential it holds. Letting you
point it elsewhere would break its own login.

There is an enterprise-grade "inference gateway" provider inside the app that accepts a custom base
URL (alongside Bedrock, Vertex, and Foundry), but it's managed configuration behind a data-residency
gate — not a switch an individual user can flip.

**Bottom line:** terminal Claude Code → OmniRoute works and is fully supported by the env vars above.
Desktop app → OmniRoute is closed by design. Use the CLI for gateway work, the desktop app for
subscription work.  do this but for opencode use mcps if u want

## [22:25] ASSISTANT

I'll analyze the codebase to understand how opencode works and create a plan for configuring it to route through OmniRoute. Let me start by exploring the project structure.



> ⚙ tool: glob (completed)

## [22:26] ASSISTANT

> ⚙ tool: read (completed)

> ⚙ tool: read (completed)

## [22:26] ASSISTANT

> ⚙ tool: glob (completed)

> ⚙ tool: glob (completed)

## [22:26] ASSISTANT

> ⚙ tool: bash (completed)

## [22:27] ASSISTANT

> ⚙ tool: bash (completed)

## [22:27] USER

no i just want u to configure my omniroute models free models to opencode to be used in opencode

## [22:27] ASSISTANT

> ⚙ tool: bash (completed)

## [22:27] ASSISTANT

> ⚙ tool: bash (completed)

## [22:28] ASSISTANT

> ⚙ tool: bash (completed)

## [22:28] ASSISTANT

> ⚙ tool: bash (completed)

## [22:28] ASSISTANT

> ⚙ tool: bash (completed)

## [22:28] ASSISTANT

> ⚙ tool: bash (completed)

## [22:29] ASSISTANT

> ⚙ tool: bash (completed)

## [22:30] ASSISTANT

Now I understand the setup. Let me create a plan for you.

## Current State Analysis

1. **OmniRoute is running** on `localhost:20128` with many models available
2. **opencode already has OmniRoute configured** as a provider in `~/.config/opencode/opencode.json`
3. **Current config only includes 4 hardcoded models** - none are the free models

## Available Free Models from OmniRoute

The gateway exposes these free options:
- `auto/best-free` - auto-selects best free model
- `auto/coding:free` - auto-selects best free coding model  
- `oc/nemotron-3-ultra-free` - specific free model
- `oc/deepseek-v4-flash-free` - specific free model
- Many `openrouter/...:free` models

## Plan

**Add free models to your opencode config** (`~/.config/opencode/opencode.json`):

1. Add `auto/best-free` and `auto/coding:free` to the `models` section under the `omniroute` provider
2. These are "auto combos" that automatically route to the best available free model based on your configured provider keys

This way you can use:
- `opencode -m omniroute/auto/best-free` - best free model for general use
- `opencode -m omniroute/auto/coding:free` - best free model for coding

## Questions

1. **Which free model approach do you prefer?**
   - `auto/best-free` - general purpose, auto-selects best free
   - `auto/coding:free` - optimized for coding tasks
   - Both (recommended)

2. **Do you want to set a default model** so you don't need `-m` flag every time? (Can add `"defaultModel": "omniroute/auto/best-free"` to config)

3. **Should I verify the models work** with a quick test before finalizing?

## [22:30] USER

coding 

## [22:30] ASSISTANT



## [22:31] ASSISTANT



## [22:36] USER

coding

## [22:36] ASSISTANT

> ⚙ tool: read (completed)

## [22:36] ASSISTANT

> ⚙ tool: edit (completed)

## [22:36] ASSISTANT

Now let me verify it works:

> ⚙ tool: bash (completed)

## [22:36] ASSISTANT

> ⚙ tool: bash (completed)

## [22:36] ASSISTANT

Done. `omniroute/auto/coding:free` works.

**Usage:**
```bash
opencode -m omniroute/auto/coding:free
```

Or for a one-shot:
```bash
opencode run "your prompt" -m omniroute/auto/coding:free
```
