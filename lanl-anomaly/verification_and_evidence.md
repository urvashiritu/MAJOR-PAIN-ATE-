# Verification and Evidence Register

**Inspection date:** 31 October 2026  
**Target:** `lanl-anomaly` current working tree.  
**Rule:** Each entry distinguishes executable/current evidence from historical documentation. File references are relative to `lanl-anomaly/` unless stated otherwise.

## Commands and actions executed

| ID | Command/action | Result |
|---|---|---|
| C-01 | Recursive file inventory excluding virtualenv and large binary artifacts | Mapped docs, code, models, reports, UI, tests and data. No `MPrepochapter.pdf` found in searched `/home/girish`; no report screenshots/plots found outside vendor package assets. |
| C-02 | `cat`/inspection of README variants, setup guides, project notes, experiment log and feature/model docs | Found conflicts summarized below. |
| C-03 | `venv/bin/python` DuckDB read-only queries against `data/processed/lanl_scores.parquet` | Exact row/label/entity counts and replay counts below. No files written. |
| C-04 | `venv/bin/python` model bundle/checkpoint load (`joblib.load`, `torch.load`) | Bundle schemas and estimator parameters printed. sklearn emitted version compatibility warnings: saved with 1.9.0, current runtime 1.9.1. No model files written. |
| C-05 | Python `ast.parse` across project `.py` excluding `venv` and `__pycache__` | 31 project Python files parsed; PASS. No bytecode written. |
| C-06 | `venv/bin/python test_live.py` | Failed before test execution: `ModuleNotFoundError: No module named 'playwright'` on import. It did not contact the application or create screenshots. |
| C-07 | No full model training, score generation, database rebuild, server launch or Playwright audit | Deliberately not run: raw source DB absent; training is expensive; UI audit writes screenshots; Playwright absent. |
| C-08 | Render Markdown to A4 PDF with temporary HTML and headless Chrome; inspect with `pdfinfo` and `pdftotext` | PDF generated successfully, 17 A4 pages, 421 KB. Extracted text contains the report chapters, metrics, references and appendix. Temporary renderer files are under `/tmp`. |

## Independently verified claims

| Claim | Verification/evidence | Scope / limit |
|---|---|---|
| Shipped score artifact has 29,905,488 rows | DuckDB `SELECT count(*) FROM read_parquet('data/processed/lanl_scores.parquet')` returned 29,905,488. | Directly verified artifact row count. |
| Score artifact has 702 red labels | Same parquet query returned `sum(is_red)=702`. | Label rows in this artifact, not original redteam file row count. |
| Entity counts: 604 source users, 5,658 destination users, 8,162 source computers, 8,085 destination computers | `count(distinct ...)` query against score parquet. | Event artifact scope. |
| Stored threshold is 0.18719510711736984 | Parquet min/max threshold identical; `models/lanl_lgb_21feat.joblib` threshold metadata matches. | Offline score/RUN 9 bundle. |
| Stored score parquet block-threshold counts | Query: TP=598, FP=269, FN=104, TN=29,904,517 for `anomaly_score >= threshold`. | Full dataset, includes training rows; not held-out. |
| Curated interval count | Query `WHERE time BETWEEN 765000 AND 767000`: 9,954 rows, 20 red labels. Source `live/replay.py` lines 22–23 defines window. | Curated replay only. |
| Curated interval detection | Decision values in parquet: 19 red BLOCK + 1 red FLAG; 12 normal BLOCK; no other normal flags. | 20/20 red at FLAG/BLOCK, 12 normal alerts; does not imply generalization. |
| Live model is 13 inputs | `live/scorer.py` lines 16–25 selects `lanl_lgb_13feat.joblib`; loaded bundle has 13 `features`, model `n_features_in_=13`. | Current live scorer. |
| Live and offline model thresholds differ | Live scorer constant `0.19347506966661734`; 21-feature bundle/parquet `0.18719510711736984`. | Confirms separate scoring generations. |
| Current live scorer builds 21-key dict but predicts on bundle features | `live/scorer.py` lines 545–549 indexes `_lgb_features`; bundle has 13 names. | Only 13 are used by current model. |
| RUN 9 bundle architecture/config and metrics | `lanl_lgb_21feat.joblib`: 21 input names; LGBMClassifier; 500 estimators, 63 leaves, 0.03 learning rate, class weight 3, min child 100, alpha .5, lambda 5, seed 42; ROC .9999204, PR .3682408, F1 .4866, TP 136, FP 183, threshold .187195. | Metadata is verified; underlying held-out arrays are unavailable, so metrics are not independently recalculated. |
| Current model-metrics endpoint metadata contradicts current scorer | `live/app.py` `/api/model/metrics` hardcodes source `models/lanl_lgb_21feat.joblib`; imported `MODEL_PATH` comes from current scorer’s 13-feature path. `test_live.py` asserts 21. | Verified source inconsistency; endpoint not runtime-exercised. |
| Model files load with version warning | Read-only load produced sklearn `InconsistentVersionWarning` from 1.9.0 to 1.9.1 for IsolationForest, ExtraTreeRegressor, StandardScaler and LabelEncoder. | Warning is not proof of broken predictions, but reproducibility risk. |
| Source code syntax parses | 31 Python files passed `ast.parse`. | Syntax only; does not verify imports/runtime. |

### Source line references

| Claim area | Source location |
|---|---|
| Raw auth columns and red-team tuple parsing | `src/00_build_slice.py:33-57` |
| Stream scan and cohort sampling (seed, user pattern, 500 normal users) | `src/00_build_slice.py:66-113`, `116-159` |
| Initial feature SQL, labels, failure/velocity windows | `src/01_build_features.py:35-65` |
| Guarded feature rebuild and limited verification fields | `src/01_build_features.py:30-33`, `75-97`, `100-134` |
| RUN 9 feature stacking, split, model params and save bundle | `eval_lstm.py:272-320`, `515-535`, `570-625` |
| User-grouped nested split and 13-feature model training | `src/retrain13_both.py:46-55`, `183-227`, `461-470` |
| LSTM-AE categorical fields, context, hyperparameters, model and loss | `src/05_lstm_autoencoder.py:34-46`, `49-112`, `172-235`, `242-450` |
| Current scorer bundle path, threshold, prediction feature selection | `live/scorer.py:16-28`, `97-105`, `414-565` |
| 21 feature names and SQL feature path, including constant `pairs_last_100` | `live/db.py:9-15`, `17-135` |
| Replay window, parquet source, labels and event conversion | `live/replay.py:21-27`, `34-114` |
| User-specific explanations and 20-event cold start | `live/app.py:526-595`; cold-start constant `live/app.py:46` |
| Authentication gate and role behavior | `live/app.py:99-116`; sign-in route `live/app.py:315-342` |
| Password and TOTP checks; demo credentials | `live/auth.py:11-42`, `45-118` |
| Metrics API's hard-coded 21-feature path and payload | `live/app.py:1215-1257` |
| Smoke test's Playwright import and 21-feature assertion | `test_live.py:10-16`, `44-55` |
| Held-out split sizes and RUN 9 findings | `reports/experiment_log.md:250-270`, `673-707`, `773-807` |
| Full-dataset historical score run, which is different from current parquet counts | `reports/experiment_log.md:1116-1145` |
| README held-out and full-data claims | `README.md:98-118` |
| Demo score example and curated replay claim | `DEMO_TLDR.md:35-78` |
| Dataset/bootstrap requirements and model checks | `SETUP.md:6-31`, `81-95`; `bootstrap.sh` dataset/model verification functions |

## User-requested figures: evidence decisions

| Figure/claim | Status | Source / notes |
|---|---|---|
| 29.9 million events | **Verified** as 29,905,488 in score parquet. | `data/processed/lanl_scores.parquet`, direct DuckDB count; docs `README.md`. |
| 702 red-team events | **Verified** in parquet labels. | Same artifact count. Source redteam file absent, so original label matching could not be rerun. |
| 20/20 curated replay attacks | **Verified from saved output**: 20 red labels in interval; 19 BLOCK, 1 FLAG. | `live/replay.py` window 765000–767000 and score parquet query. This is curated only. |
| 12 false positives in replay | **Verified from saved output**: 12 normal rows at BLOCK; no normal FLAG in interval. | Same query. |
| 136/240 held-out detections | **Supported by RUN 9 model metadata and experiment log**, not independently recomputed. | `models/lanl_lgb_21feat.joblib`; `reports/experiment_log.md` RUN 9. Held-out score vector absent. |
| 21 features displayed in live explanation | **Not accurate as a statement about current model inputs.** Bundle has 21 inputs for offline RUN 9, current scorer has 13 model inputs; it creates 21 named feature values. Replay event feature dict is empty. | `live/scorer.py`, `live/replay.py`, model bundle. |
| Example live anomaly score 3.35e-8 | **Unverified historical example.** Found in `DEMO_TLDR.md`; not found in retained structured output or source literal. | Do not report as reproduced. |
| Example block threshold 0.187195 | **Verified for offline score parquet/RUN 9**; **not the current live threshold**, which is 0.193475. | `live/scorer.py`, 21-feature model bundle, parquet. |

## Held-out metric provenance and arithmetic

RUN 9 evidence appears in `reports/experiment_log.md` around lines 673–707 and 773–810, and in the 21-feature bundle. The related split table reports 5,399,886 total test rows and 240 red labels; hence normal/unlabeled test rows = 5,399,646. With TP=136 and FP=183:

- FN = 240−136 = 104.
- TN = 5,399,646−183 = 5,399,463.
- Precision = 136/(136+183) = 0.4263.
- Recall = 136/240 = 0.5667.
- F1 = 2×0.4263×0.5667/(0.4263+0.5667) ≈ 0.4866.
- FPR = 183/(183+5,399,463) ≈ 0.00003389 = 0.003389%.
- Test prevalence = 240/5,399,886 ≈ 0.00004445; PR random baseline is prevalence-scale.

F1 and confusion arithmetic are internally consistent. AUC values cannot be recomputed without per-event held-out scores/labels. Accuracy is not reported as a model quality claim. “Normal” denotes not red-labeled, not verified benign.

## Discrepancies and stale documentation

1. **13-feature live bundle vs 21-feature batch bundle.** `live/scorer.py` chooses `lanl_lgb_13feat.joblib` and threshold 0.193475. `README.md`, `LIVE_README.md`, bootstrap model check and model metrics API describe/use the 21-feature bundle and threshold 0.187195. Current score parquet is a separate 21-feature offline output.
2. **API metadata is hard-coded to wrong generation.** `live/app.py` model metrics returns source string `models/lanl_lgb_21feat.joblib` while scorer import `MODEL_PATH` points to 13-feature bundle. `test_live.py` requires feature_count 21. Neither endpoint nor test could run because app prerequisites unavailable.
3. **Feature 17 differs by path.** `live/db.py` `FEATURE_SQL` writes `pairs_last_100=0.0`; `live/scorer.py` computes distinct destinations from a sliding history. Offline training and live features therefore can differ on this input.
4. **Full-data count is not held-out.** README and project notes quote 598/702 from full score parquet. It includes training rows and differs from held-out 136/240.
5. **Block-only versus alert decision.** Full parquet at score >= threshold has 598 red and 269 normal. The ALLOW/FLAG/BLOCK decision includes threshold×0.7 FLAG band: 11 additional red and 103 additional non-red flagged. Docs’ “598 caught” counts BLOCK threshold only.
6. **Replay decision labels casing.** Stored parquet uses uppercase `ALLOW`, `FLAG`, `BLOCK`; `live/replay.py` lowercases before serving. Counts must account for case conversion.
7. **RUN 9 threshold provenance.** `eval_lstm.py` sweeps on `y_test` in the evaluation path shown around threshold/overlap code; log states test metrics and threshold. A later `retrain13_both.py` uses a nested validation split. Do not attribute the later nested-validation protection to RUN 9 without exact run provenance. This is potential test-threshold leakage and should be resolved before a thesis performance claim.
8. **Training report maturity.** `reports/both_report.json` explicitly states row-stratified split leaked 97% of red-team users. It is an early experiment and not valid as held-out user generalization evidence.
9. **Dataset build verification scope.** `src/01_build_features.py` compares only listed fields in `COMPARE_COLS` and joins on time/user/source/destination; it does not guarantee every derived column is equal.
10. **Current missing prerequisites.** Raw `lanl.duckdb`, `redteam.txt`, `users.txt`, and some raw slice artifacts show absent/deleted in the checkout; `test_live.py` cannot import Playwright. App setup and full test audit remain unverified.
11. **Documentation references.** The report’s requested `MPrepochapter.pdf` was not found under `/home/girish`; exact page/section formatting could not be inspected.
12. **Research references inside project notes.** `docs/AI-SPEC.md` and feature research cite future-dated or difficult-to-trace items (e.g. “RAD CIKM 2026”, HLSF arXiv ID) and expected AUC values. These were excluded from confirmed bibliography unless independently located in primary bibliographic sources. Expected feature AUCs are not measured project results.

## Repository state and preservation

At inspection start, Git reported pre-existing changes:

- Deleted tracked items: `data/raw/lanl/lanl_auth_slice_29.9M.parquet`, `redteam.txt`, `slice.parquet`, `users.txt`.
- Modified tracked live files: `live/app.py`, `live/scorer.py`, `live/static/js/api.js`, `live/static/js/app.js`, `live/templates/_sidebar.html`.
- Untracked items included `lanl-anomaly.zip`, company simulator template/CSS, normal-only IF model/report artifacts, and `src/07_train_normal_if.py`.

These were not modified or removed. The two inspection documents are the only intended new files.

## Test and verification files: what they cover

| File | Intended coverage / precondition |
|---|---|
| `test_live.py` | API health, replay metadata/control, alerts/users, SPA render and console errors. Needs server, Playwright and artifacts. Import currently fails without Playwright. |
| `live/test_audit.py` | Browser workflow across dashboard, employee login, dataset, search and logout; writes screenshots and audit text. Needs Flask, LANL data, LANL_DEV, Playwright, Chromium. |
| `live/test_blind_event.py` | Experimental external-observer blind event attack/normal-state changes. Writes results to `/tmp`; not a unit test. |
| `live/verify.py` | Loads real DB/model and checks checkpoint, feature computation, model loading/scoring. Needs raw DuckDB and model dependencies. |
| `verify_scores.py` | Rebuilds/compares score features against database; raw DuckDB required. |
| `verify_exp2.py`, `verify_v2.py`, `verify.py`, `overlap_test.py` | Research/experiment verification paths, not all lightweight test cases. Inspect CLI and outputs before rerunning; most require full data and may be expensive. |

## Traceable primary literature and official references

- LANL Cyber1 dataset: <https://csr.lanl.gov/data/cyber1/>; dataset chapter citation in `project_technical_document.md`.
- Turcotte, Kent & Hash, *Unified Host and Network Data Set*, DOI <https://doi.org/10.1142/9781786345646_001>.
- Kent, Liebrock & Neil, authentication graphs, DOI <https://doi.org/10.1016/j.cose.2014.09.001>.
- Ho et al., Hopper, USENIX Security 2021: <https://www.usenix.org/conference/usenixsecurity21/presentation/ho>.
- Liu, Ting & Zhou, Isolation Forest, DOI <https://doi.org/10.1109/ICDM.2008.17>.
- Ke et al., LightGBM, NeurIPS 2017: <https://papers.nips.cc/paper/2017/hash/6449f44a102fde848669bdd9eb6b76fa-Abstract.html>.
- Du et al., DeepLog, DOI <https://doi.org/10.1145/3133956.3134015>.

