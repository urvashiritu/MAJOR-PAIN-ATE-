#!/usr/bin/env python3
"""Train a normal-only Isolation Forest for the company sign-in demo.

Uses the existing 9-feature Parquet cache. Red-team rows are excluded from
training and used only for a small evaluation report. The saved score is an
additional anomaly signal; it does not replace LightGBM or automatically
block events.
"""
import json
from pathlib import Path

import duckdb
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / 'data' / 'processed' / 'lanl_feat_13feat_29.9M.parquet'
MODEL_OUT = ROOT / 'models' / 'lanl_if_normal_13feat.joblib'
REPORT_OUT = ROOT / 'reports' / 'normal_if_13_report.json'
FEATURES = [
    'dst_first', 'src_first', 'hour_ratio', 'dst_prior_events', 'fail_1h',
    'vel_1h', 'hour_sin', 'hour_cos', 'is_ntlm', 'pair_first',
    'src_dst_pair_first', 'fail_rate', 'dst_first_x_ntlm',
]
SAMPLE_SIZE = 250_000
CALIBRATION_FPR = 1e-4


def matrix(rows):
    n = len(rows['time'])
    x = np.empty((n, len(FEATURES)), dtype=np.float32)
    x[:, 0] = rows['dst_first']
    x[:, 1] = rows['src_first']
    x[:, 2] = rows['hour_events'] / np.maximum(rows['user_events'], 1)
    x[:, 3] = rows['dst_prior_events']
    x[:, 4] = rows['fail_1h']
    x[:, 5] = rows['vel_1h']
    radians = rows['hour'] / 24.0 * 2.0 * np.pi
    x[:, 6] = np.sin(radians)
    x[:, 7] = np.cos(radians)
    x[:, 8] = rows['is_ntlm']
    x[:, 9] = rows['pair_first']
    x[:, 10] = rows['src_dst_pair_first']
    x[:, 11] = rows['fail_1h'] / (rows['vel_1h'] + 1.0)
    x[:, 12] = x[:, 0] * x[:, 8]
    for col in (3, 4, 5):
        x[:, col] = np.log1p(x[:, col])
    return x


def load_sample(con, is_red, limit=None):
    sample = f"USING SAMPLE {limit} ROWS (reservoir, 42)" if limit else ''
    query = f"""
        SELECT time, hour, is_red, dst_first, src_first, hour_events,
               user_events, dst_prior_events, fail_1h, vel_1h, is_ntlm,
               pair_first, src_dst_pair_first
        FROM (
            SELECT time, hour, is_red, dst_first, src_first, hour_events,
                   user_events, dst_prior_events, fail_1h, vel_1h, is_ntlm,
                   pair_first, src_dst_pair_first
            FROM read_parquet('{INPUT.as_posix()}')
            WHERE is_red = {str(is_red).upper()}
        ) {sample}
    """
    return con.execute(query).fetchnumpy()


def main():
    if not INPUT.exists():
        raise SystemExit(f'Missing feature cache: {INPUT}')
    con = duckdb.connect(':memory:')
    normal = load_sample(con, False, SAMPLE_SIZE)
    red = load_sample(con, True)
    con.close()

    x = matrix(normal)
    cut = int(len(x) * 0.8)
    x_train, x_cal = x[:cut], x[cut:]
    scaler = StandardScaler().fit(x_train)
    x_train_s = scaler.transform(x_train)
    x_cal_s = scaler.transform(x_cal)
    model = IsolationForest(
        n_estimators=200, max_samples=512, contamination='auto',
        n_jobs=-1, random_state=42,
    ).fit(x_train_s)

    cal_scores = -model.score_samples(x_cal_s)
    threshold = float(np.quantile(cal_scores, 1.0 - CALIBRATION_FPR))
    red_scores = -model.score_samples(scaler.transform(matrix(red)))
    red_y = np.ones(len(red_scores), dtype=np.uint8)
    normal_eval_scores = cal_scores
    normal_y = np.zeros(len(normal_eval_scores), dtype=np.uint8)
    eval_scores = np.concatenate([normal_eval_scores, red_scores])
    eval_y = np.concatenate([normal_y, red_y])
    predictions = eval_scores > threshold
    report = {
        'model': 'IsolationForest trained on benign events only',
        'feature_count': len(FEATURES),
        'normal_training_rows': len(x_train),
        'normal_calibration_rows': len(x_cal),
        'red_team_evaluation_rows': len(red_scores),
        'calibration_target_fpr': CALIBRATION_FPR,
        'calibration_observed_fpr': float(np.mean(cal_scores > threshold)),
        'red_team_recall_at_calibration_threshold': float(np.mean(red_scores > threshold)),
        'sample_pr_auc': float(average_precision_score(eval_y, eval_scores)),
        'sample_roc_auc': float(roc_auc_score(eval_y, eval_scores)),
        'note': 'PR-AUC is on a sampled class mixture and is not a population estimate.',
    }
    bundle = {
        'model': model, 'scaler': scaler, 'features': FEATURES,
        'log_features': ['dst_prior_events', 'fail_1h', 'vel_1h'],
        'threshold': threshold, 'calibration_fpr': CALIBRATION_FPR,
        'report': report,
    }
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_OUT)
    REPORT_OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f'model: {MODEL_OUT}')


if __name__ == '__main__':
    main()
