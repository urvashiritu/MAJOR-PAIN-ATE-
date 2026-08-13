# Logs-Lab Explainable UI

A **standalone** web app that shows, in plain words and plain numbers, what the
synthetic logs-lab experiment learned — and how it compares to the main project's
RBA model. It is deliberately **separate from the live dashboard** (`live/`): this is
an audit view for anyone (no ML background needed) to understand the training run,
the scores, and a single login's verdict one clue at a time.

It reads the trained artifacts from `logs-lab/` and the RBA comparison numbers from
the main project's `reports/`. It does **not** write anything.

## Run

```bash
make logs-lab-ui-bg    # background, logs -> logs-lab/runs/ui-*.log
# or, foreground:
venv/bin/python logs-lab/ui/app.py
```

Then open **http://127.0.0.1:5001** (Flask). It needs `logs-lab/` to have been
built first (`make logs-lab-prepare`).

## What the page shows

1. **01 · The dataset** — total events and the per-source success/failure split
   (6 sources, 600k synthetic events).
2. **02 · The exam is held out** — the 55/15/30 train/val/test chronological split,
   shown as a bar. This is why the numbers are honest: the test set is never touched
   while tuning.
3. **03 · Three strategies, one winner** — F1 / precision / recall / ROC-AUC for
   Hist Gradient Boosting, Logistic Regression and Isolation Forest, each decoded
   into "in plain English".
4. **04 · Every decision, explained** — 20 test-set logins; click any row for a
   gauge (score vs threshold) plus a waterfall of *which clues pushed suspicion up
   or down*, with a plain-language label per clue.
5. **05 · Logs-Lab vs RBA** — the same class of model on the main dataset, plus the
   IP-blocklist "cheat sheet" baseline. Shows *why* RBA scores higher (it was given
   the answer key) and why logs-lab's numbers are the honest test.

## API

All endpoints are JSON.

| Endpoint | Returns |
|---|---|
| `GET /` | the page itself (`templates/explain.html`) |
| `GET /api/overview` | total events, per-source counts, split sizes, all model metrics, RBA comparison block |
| `GET /api/events?n=20` | newest test-set events with id / user / source / result / risk score |
| `GET /api/explain/<row_id>` | verdict + threshold + per-feature contribution list for one event |

## How the explanation is computed

No black box. Each feature's contribution is a **perturbation**:

```
contribution(f) = model_score(event) - model_score(event with f set to its train baseline)
```

- the baseline for a boolean feature is its most common value in the training split,
- the baseline for a numeric feature is the training median,
- a positive contribution means the clue pushed the score **up** (more suspicious),
- a negative one means it pushed the score **down**.

The contributions sum to a rough estimate of why the model moved from a neutral
score to the final one, and each is re-labeled into a human sentence (e.g. "This IP
seen for this user before" → **▼ pushed it down**).

## Design

- Watermelon design language (dark paper, hairline borders, ochre accent, monospace)
  matching the main app, but fully **self-contained**: a single Flask file
  (`app.py`) + one HTML template, no build step, no JS framework.
- Styling lives in the template so the UI can be copied anywhere.
