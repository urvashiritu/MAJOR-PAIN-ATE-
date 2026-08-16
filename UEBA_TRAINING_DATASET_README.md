# UEBA model training dataset

Canonical output: `ueba_model_training_events.parquet`.

This is an event-level, leakage-safe feature set for unsupervised identity anomaly detection. Use exactly the 24 `MODEL_FEATURES` printed by `scripts/build_ueba_training_dataset.py` as `X` for Isolation Forest, One-Class SVM, Local Outlier Factor, and Elliptic Envelope. Scale continuous features with a robust scaler before models that need it.

Do **not** fit a model on `event_id`, `event_timestamp`, `user_id`, or columns starting with `eval_`. They are identifiers, chronological split metadata, and evaluation-only outcomes respectively.

The feature values at an event use only prior events of that user. First-login and missing-device cases are explicit numeric features. Counts and time gaps are log transformed so high-volume users do not dominate. Known attack/ATO flags are retained only to assess alerts after scoring.

Split by time: fit a baseline on earlier timestamps, set thresholds on a validation period, and report results on later timestamps. Score each event before using it to update that user's production baseline.
