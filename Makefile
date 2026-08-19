PY := venv/bin/python
DATA := data/processed

# Pipeline order: 00 -> 02 -> 01 -> 03 -> 04, then the full-sample model
# experiment (07). File numbers are phase numbers, not execution order.
# Live decisions (live/) are rule-driven; src/07 (all models on the full
# 1M sample) is the model deliverable.

.PHONY: all clean features sample validate rules ensemble-full demo demo-reset demo-web

all: rules ensemble-full

ensemble-full: reports/ensemble_full_comparison.csv

reports/ensemble_full_comparison.csv: $(DATA)/features.parquet
	$(PY) src/07_ensemble_full.py

demo: demo-reset
	$(PY) live/app.py

demo-reset:
	$(PY) live/seed_demo.py

demo-web:
	cd live/web && npm run build

clean: $(DATA)/rba_clean.parquet

$(DATA)/rba_clean.parquet: data/raw/rba-dataset.csv
	$(PY) src/00_clean_dataset.py

features: $(DATA)/rba_features.parquet

$(DATA)/rba_features.parquet: $(DATA)/rba_clean.parquet
	$(PY) src/02_feature_engineering.py

sample: $(DATA)/sample.parquet

$(DATA)/sample.parquet: $(DATA)/rba_features.parquet
	$(PY) src/01_load_and_sample.py

validate: $(DATA)/sample.parquet
	$(PY) src/03_validate_contract.py

rules: reports/rule_baseline_scores.parquet

reports/rule_baseline_scores.parquet: $(DATA)/sample.parquet
	$(PY) src/04_rule_baseline.py
