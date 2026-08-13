# Agent preferences

- Never use `2>&1` or pipe/filter command output in a way that hides it. The user wants to see full command output.
- Always follow the Karpathy guidelines (think before coding, simplicity first, surgical changes, goal-driven execution with verification) — apply them to every task by default.
- Load the `karpathy-guidelines` skill at the start of every session/task and follow it.

## Context efficiency

- When the task shifts or context feels stale, start a fresh session (`/new`) instead of continuing a long thread. Long sessions replay the full history every turn and blow up token usage.
- Do not re-read whole files once their contents are already in context. Prefer targeted `grep`/`Glob` lookups over full `Read` calls.
- Reference files like `README.md`, `PROJECT_ROADMAP.md`, and `COMPLETE_PROJECT_REFERENCE.md` should be read once per session at most.
