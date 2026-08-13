PY := venv/bin/python
DATA := data/processed

# Pipeline order: 00 -> 02 -> 01 -> 03 -> 04 -> 05 -> 06
# (file numbers are phase numbers, not execution order; see README)

.PHONY: all clean features sample validate rules models supervised logs-lab-prepare logs-lab-train logs-lab-train-bg logs-lab-ui logs-lab-ui-bg

all: supervised

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

models: reports/model_comparison.csv

reports/model_comparison.csv: reports/rule_baseline_scores.parquet
	$(PY) src/05_models_evaluation.py

supervised: reports/model_comparison.csv
	$(PY) src/06_supervised_model.py

logs-lab-train:
	$(PY) logs-lab/train_models.py

logs-lab-prepare:
	$(PY) logs-lab/parse_logs.py
	$(PY) logs-lab/train_models.py

logs-lab-ui:
	$(PY) logs-lab/ui/app.py

logs-lab-ui-bg:
	mkdir -p logs-lab/runs
	nohup $(PY) logs-lab/ui/app.py > logs-lab/runs/ui-$$(date +%F-%H%M%S).log 2>&1 &
	@echo "logs-lab UI running at http://127.0.0.1:5001 (log: logs-lab/runs/ui-*.log)"

logs-lab-train-bg:
	mkdir -p logs-lab/runs
	nohup $(PY) logs-lab/train_models.py > logs-lab/runs/train-$$(date +%F-%H%M%S).log &
