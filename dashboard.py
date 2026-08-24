import streamlit as st
import pandas as pd
import numpy as np
import subprocess
import os
import re
import time
from pathlib import Path
from datetime import datetime

# ============================================================
# OPTIONAL ACTIVITY MONITOR
# ============================================================


try:
    from activity_monitor import (
        setup_monitor_directory,
        install_audit_rule,
        read_events,
    )
    ACTIVITY_MONITOR_AVAILABLE = True
except Exception:
    ACTIVITY_MONITOR_AVAILABLE = False


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Identity Anomaly Detection",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.html(
    """
<style>

@import url(
    'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap'
);

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background:
        radial-gradient(
            circle at 10% 10%,
            rgba(90, 100, 255, 0.12),
            transparent 30%
        ),
        radial-gradient(
            circle at 90% 20%,
            rgba(0, 220, 180, 0.08),
            transparent 30%
        ),
        #070a12;
}

/* Main container */

.block-container {
    max-width: 1450px;
    padding-top: 2rem;
    padding-bottom: 3rem;
}

/* Hero */

.hero {
    padding: 2.2rem 2.4rem;
    border-radius: 24px;
    background:
        linear-gradient(
            135deg,
            rgba(24, 30, 58, 0.96),
            rgba(10, 15, 30, 0.96)
        );
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow:
        0 20px 60px rgba(0,0,0,0.35);
    margin-bottom: 1.5rem;
}

.hero-title {
    font-size: 2.7rem;
    font-weight: 800;
    letter-spacing: -1px;
    margin-bottom: 0.5rem;
}

.hero-subtitle {
    color: #aeb7cc;
    font-size: 1.05rem;
    line-height: 1.6;
}

/* Section */

.section-title {
    font-size: 1.55rem;
    font-weight: 750;
    margin-top: 2rem;
    margin-bottom: 0.25rem;
}

.section-subtitle {
    color: #8f99ae;
    margin-bottom: 1.1rem;
}

/* Cards */

.metric-card {
    background:
        linear-gradient(
            145deg,
            rgba(23, 29, 50, 0.95),
            rgba(12, 17, 31, 0.95)
        );
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 18px;
    padding: 1.15rem 1.2rem;
    min-height: 115px;
    transition: all 0.2s ease;
}

.metric-card:hover {
    transform: translateY(-2px);
    border-color: rgba(130,140,255,0.35);
}

.metric-label {
    color: #8e98ae;
    font-size: 0.85rem;
    margin-bottom: 0.35rem;
}

.metric-value {
    font-size: 1.75rem;
    font-weight: 750;
}

.metric-help {
    color: #727d94;
    font-size: 0.75rem;
    margin-top: 0.3rem;
}

/* Status */

.status-live {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 13px;
    border-radius: 999px;
    background: rgba(0, 220, 150, 0.10);
    border: 1px solid rgba(0, 220, 150, 0.25);
    color: #5ff0bc;
    font-size: 0.82rem;
    font-weight: 600;
}

.status-live::before {
    content: "";
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #45e7ae;
    box-shadow: 0 0 12px #45e7ae;
}

/* Model header */

.model-header {
    padding: 1.3rem 1.5rem;
    border-radius: 18px;
    background: rgba(20,25,44,0.85);
    border: 1px solid rgba(255,255,255,0.07);
    margin-bottom: 1rem;
}

.best-model {
    padding: 1rem 1.3rem;
    border-radius: 16px;
    background: rgba(50, 150, 255, 0.08);
    border: 1px solid rgba(50, 150, 255, 0.25);
    margin: 1rem 0;
}

/* Formula */

.formula {
    background: #0b0f1b;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 1rem 1.2rem;
    font-family: monospace;
    color: #d9e0ef;
    margin: 0.5rem 0 1rem 0;
}

/* Tables */

div[data-testid="stDataFrame"] {
    border-radius: 14px;
    overflow: hidden;
}

/* Buttons */

.stButton > button {
    border-radius: 11px;
    font-weight: 600;
}

/* Tabs */

.stTabs [data-baseweb="tab"] {
    font-weight: 600;
}

</style>
"""
)


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
MODELS_DIR = BASE_DIR / "models"

DEMO_DIR = Path.home() / "Projects" / "finalproject" / "demo_sensitive"


# ============================================================
# HELPERS
# ============================================================

def load_csv(filename):

    path = OUTPUT_DIR / filename

    if not path.exists():
        return None

    try:
        return pd.read_csv(path)
    except Exception:
        return None


def first_existing_column(df, names):

    if df is None:
        return None

    for name in names:
        if name in df.columns:
            return name

    return None


def metric_value(df, model, possible_names):

    if df is None or df.empty:
        return None

    model_col = first_existing_column(
        df,
        [
            "model",
            "Model",
            "algorithm",
            "Algorithm",
        ],
    )

    if model_col is None:
        return None

    rows = df[
        df[model_col]
        .astype(str)
        .str.lower()
        .str.contains(
            model.lower(),
            regex=False,
        )
    ]

    if rows.empty:
        return None

    for col in possible_names:

        if col in rows.columns:

            value = rows.iloc[0][col]

            try:
                value = float(value)

                if value <= 1:
                    value *= 100

                return value

            except Exception:
                return value

    return None


def confusion_values(df, model):

    if df is None or df.empty:
        return None

    model_col = first_existing_column(
        df,
        [
            "model",
            "Model",
            "algorithm",
            "Algorithm",
        ],
    )

    if model_col is None:
        return None

    rows = df[
        df[model_col]
        .astype(str)
        .str.lower()
        .str.contains(
            model.lower(),
            regex=False,
        )
    ]

    if rows.empty:
        return None

    row = rows.iloc[0]

    def get(names):

        for name in names:
            if name in row.index:

                try:
                    return int(float(row[name]))
                except Exception:
                    return None

        return None

    tp = get(["TP", "tp", "true_positive", "true_positives"])
    tn = get(["TN", "tn", "true_negative", "true_negatives"])
    fp = get(["FP", "fp", "false_positive", "false_positives"])
    fn = get(["FN", "fn", "false_negative", "false_negatives"])

    if all(
        value is not None
        for value in [tp, tn, fp, fn]
    ):
        return tp, tn, fp, fn

    return None


def show_metric_card(
    label,
    value,
    description="",
    is_percent=False,
):

    if value is None:
        display = "N/A"
    elif isinstance(value, str):
        display = value
    elif is_percent:
        display = f"{float(value):.2f}%"
    elif isinstance(value, (int, np.integer)):
        display = f"{int(value):,}"
    else:
        display = f"{float(value):,.2f}"

    st.html(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{display}</div>
            <div class="metric-help">{description}</div>
        </div>
        """
    )


def section_title(title, subtitle=""):

    st.html(
        f"""
        <div class="section-title">{title}</div>
        <div class="section-subtitle">{subtitle}</div>
        """
    )


def safe_number(value):

    try:
        return int(value)
    except Exception:
        return None


# ============================================================
# HERO
# ============================================================

st.html(
    """
<div class="hero">

    <div class="hero-title">
        Identity Anomaly Detection
    </div>

    <div class="hero-subtitle">
        Multi-source authentication analytics,
        behavioral anomaly detection and
        live SSH monitoring.
    </div>

</div>
"""
)


# ============================================================
# LOAD OUTPUTS
# ============================================================

normalized_df = load_csv(
    "normalized_authentication_events.csv"
)

features_df = load_csv(
    "authentication_features.csv"
)

evaluation_df = load_csv(
    "model_evaluation.csv"
)

risk_df = load_csv(
    "test_risk_scores.csv"
)


# ============================================================
# OVERVIEW METRICS
# ============================================================

section_title(
    "System Overview",
    "Current authentication and anomaly-detection statistics.",
)

total_events = (
    len(normalized_df)
    if normalized_df is not None
    else 0
)

total_anomalies = None

if evaluation_df is not None and not evaluation_df.empty:

    model_col = first_existing_column(
        evaluation_df,
        [
            "model",
            "Model",
            "algorithm",
            "Algorithm",
        ],
    )

    f1_col = first_existing_column(
        evaluation_df,
        [
            "f1_score",
            "F1 Score",
            "f1",
            "F1",
        ],
    )

    if model_col and f1_col:

        temp = evaluation_df.copy()

        temp["_f1"] = pd.to_numeric(
            temp[f1_col],
            errors="coerce",
        )

        temp = temp.dropna(
            subset=["_f1"]
        )

        if not temp.empty:

            selected_model = str(
                temp.loc[
                    temp["_f1"].idxmax(),
                    model_col,
                ]
            )

            confusion = confusion_values(
                evaluation_df,
                selected_model,
            )

            if confusion:

                tp, tn, fp, fn = confusion
                total_anomalies = tp + fn

if total_anomalies is None and risk_df is not None and not risk_df.empty:

    prediction_col = first_existing_column(
        risk_df,
        [
            "prediction",
            "Prediction",
            "anomaly",
            "is_anomaly",
            "label",
        ],
    )

    if prediction_col:

        values = risk_df[prediction_col]

        total_anomalies = int(
            (
                pd.to_numeric(
                    values,
                    errors="coerce",
                )
                == -1
            ).sum()
        )

        if total_anomalies == 0:

            total_anomalies = int(
                (
                    values.astype(str)
                    .str.lower()
                    .isin(
                        [
                            "anomaly",
                            "true",
                            "1",
                            "attack",
                        ]
                    )
                ).sum()
            )


best_model = "Not available"

if evaluation_df is not None and not evaluation_df.empty:

    model_col = first_existing_column(
        evaluation_df,
        [
            "model",
            "Model",
            "algorithm",
            "Algorithm",
        ],
    )

    f1_col = first_existing_column(
        evaluation_df,
        [
            "f1_score",
            "F1 Score",
            "f1",
            "F1",
        ],
    )

    if model_col and f1_col:

        temp = evaluation_df.copy()

        temp["_f1"] = pd.to_numeric(
            temp[f1_col],
            errors="coerce",
        )

        if temp["_f1"].max() <= 1:
            temp["_f1"] *= 100

        temp = temp.dropna(
            subset=["_f1"]
        )

        if not temp.empty:

            best_model = str(
                temp.loc[
                    temp["_f1"].idxmax(),
                    model_col,
                ]
            )


c1, c2, c3, c4 = st.columns(4)

with c1:
    show_metric_card(
        "Total Events",
        total_events,
        "Normalized authentication events",
    )

with c2:
    show_metric_card(
        "Total Anomalies",
        total_anomalies,
        "Actual anomalies in the evaluated test set",
    )

with c3:
    show_metric_card(
        "Models Evaluated",
        (
            len(evaluation_df)
            if evaluation_df is not None
            else 0
        ),
        "Unsupervised ML models",
    )

with c4:
    show_metric_card(
        "Best Model",
        best_model,
        "Highest F1 score",
    )


# ============================================================
# DATA UNDERSTANDING
# ============================================================

section_title(
    "Data Understanding",
    "See how heterogeneous raw authentication logs become ML-ready data.",
)

data_tab1, data_tab2, data_tab3 = st.tabs(
    [
        "Normalized Events",
        "Feature Dataset",
        "Dataset Summary",
    ]
)


with data_tab1:

    if normalized_df is not None:

        st.write(
            f"Normalized dataset: "
            f"**{len(normalized_df):,} events**"
        )

        st.dataframe(
            normalized_df.head(100),
            hide_index=True,
        )

        st.caption(
            "Each source-specific parser converts its original "
            "format into a common authentication schema."
        )

    else:

        st.warning(
            "normalized_authentication_events.csv not found."
        )


with data_tab2:

    if features_df is not None:

        st.write(
            f"Feature dataset: "
            f"**{len(features_df):,} rows × "
            f"{len(features_df.columns)} columns**"
        )

        st.dataframe(
            features_df.head(100),
            hide_index=True,
        )

        st.caption(
            "Behavioral features are used as input to the "
            "anomaly-detection models."
        )

    else:

        st.warning(
            "authentication_features.csv not found."
        )


with data_tab3:

    if normalized_df is not None:

        source_col = first_existing_column(
            normalized_df,
            [
                "source",
                "source_type",
                "log_type",
                "dataset",
            ],
        )

        if source_col:

            source_counts = (
                normalized_df[
                    source_col
                ]
                .value_counts()
                .reset_index()
            )

            source_counts.columns = [
                "Source",
                "Events",
            ]

            st.dataframe(
                source_counts,
                hide_index=True,
            )

        else:

            st.info(
                "Source column was not found."
            )

    else:

        st.warning(
            "No normalized dataset available."
        )


# ============================================================
# MODEL PERFORMANCE
# ============================================================

section_title(
    "Model Performance",
    "Each anomaly-detection model is evaluated independently.",
)


MODELS = {
    "Isolation Forest": [
        "IsolationForest",
        "Isolation Forest",
    ],
    "One-Class SVM": [
        "OneClassSVM",
        "One-Class SVM",
    ],
    "Local Outlier Factor": [
        "LocalOutlierFactor",
        "Local Outlier Factor",
        "LOF",
    ],
    "Elliptic Envelope": [
        "EllipticEnvelope",
        "Elliptic Envelope",
    ],
}


def find_model_name(options):

    if evaluation_df is None:
        return options[0]

    model_col = first_existing_column(
        evaluation_df,
        [
            "model",
            "Model",
            "algorithm",
            "Algorithm",
        ],
    )

    if model_col is None:
        return options[0]

    available = (
        evaluation_df[model_col]
        .astype(str)
        .tolist()
    )

    for option in options:

        for actual in available:

            if option.lower() in actual.lower():

                return actual

    return options[0]


model_tabs = st.tabs(
    list(MODELS.keys())
)


for tab, (display_name, options) in zip(
    model_tabs,
    MODELS.items(),
):

    with tab:

        actual_model = find_model_name(
            options
        )

        st.html(
            f"""
            <div class="model-header">

                <h2 style="margin:0;">
                    {display_name}
                </h2>

                <div style="
                    color:#8f99ae;
                    margin-top:5px;
                ">
                    Independent anomaly detection evaluation
                </div>

            </div>
            """
        )

        # ----------------------------------------------------
        # METRICS
        # ----------------------------------------------------

        accuracy = metric_value(
            evaluation_df,
            actual_model,
            [
                "accuracy",
                "Accuracy",
                "accuracy_score",
            ],
        )

        precision = metric_value(
            evaluation_df,
            actual_model,
            [
                "precision",
                "Precision",
                "precision_score",
            ],
        )

        recall = metric_value(
            evaluation_df,
            actual_model,
            [
                "recall",
                "Recall",
                "recall_score",
            ],
        )

        f1 = metric_value(
            evaluation_df,
            actual_model,
            [
                "f1_score",
                "F1 Score",
                "f1",
                "F1",
            ],
        )

        roc_auc = metric_value(
            evaluation_df,
            actual_model,
            [
                "roc_auc",
                "ROC-AUC",
                "roc_auc_score",
                "AUC",
            ],
        )

        m1, m2, m3, m4, m5 = st.columns(5)

        with m1:
            show_metric_card(
                "Accuracy",
                accuracy,
                "Overall correct predictions",
                is_percent=True,
            )

        with m2:
            show_metric_card(
                "Precision",
                precision,
                "Trustworthiness of alerts",
                is_percent=True,
            )

        with m3:
            show_metric_card(
                "Recall",
                recall,
                "Anomalies successfully detected",
                is_percent=True,
            )

        with m4:
            show_metric_card(
                "F1 Score",
                f1,
                "Precision / recall balance",
                is_percent=True,
            )

        with m5:
            show_metric_card(
                "ROC-AUC",
                roc_auc,
                "Anomaly separation ability",
                is_percent=True,
            )

        # ----------------------------------------------------
        # CONFUSION MATRIX
        # ----------------------------------------------------

        st.markdown(
            "### Confusion Matrix"
        )

        confusion = confusion_values(
            evaluation_df,
            actual_model,
        )

        if confusion:

            tp, tn, fp, fn = confusion

            matrix = pd.DataFrame(
                [
                    [tn, fp],
                    [fn, tp],
                ],
                index=[
                    "Actually Normal",
                    "Actually Anomaly",
                ],
                columns=[
                    "Predicted Normal",
                    "Predicted Anomaly",
                ],
            )

            st.dataframe(
                matrix,
            )

            cm1, cm2, cm3, cm4 = st.columns(4)

            with cm1:
                show_metric_card(
                    "True Negative",
                    tn,
                    "Normal → Normal",
                )

            with cm2:
                show_metric_card(
                    "False Positive",
                    fp,
                    "Normal → Anomaly",
                )

            with cm3:
                show_metric_card(
                    "False Negative",
                    fn,
                    "Anomaly → Normal",
                )

            with cm4:
                show_metric_card(
                    "True Positive",
                    tp,
                    "Anomaly → Anomaly",
                )

        else:

            st.info(
                "TP/TN/FP/FN are not currently stored "
                "in model_evaluation.csv."
            )

            st.caption(
                "The metric values above are still displayed "
                "from the saved evaluation results."
            )

        # ----------------------------------------------------
        # HOW METRICS ARE CALCULATED
        # ----------------------------------------------------

        with st.expander(
            "How were these metrics calculated?"
        ):

            st.markdown(
                """
### Accuracy

Measures the percentage of all predictions that were correct.

`Accuracy = (TP + TN) / (TP + TN + FP + FN)`

---

### Precision

Measures how many events flagged as anomalies were actually anomalies.

`Precision = TP / (TP + FP)`

High precision means fewer false alarms.

---

### Recall

Measures how many actual anomalies were successfully detected.

`Recall = TP / (TP + FN)`

High recall means fewer attacks are missed.

---

### F1 Score

Combines precision and recall using their harmonic mean.

`F1 = 2 × (Precision × Recall) / (Precision + Recall)`

We use F1 as the primary metric for selecting the best model because
both missed anomalies and false alarms matter.

---

### ROC-AUC

Measures how well the model separates anomalous events from normal
events across different decision thresholds.

Values closer to `1.0` indicate better separation.
"""
            )

        # ----------------------------------------------------
        # MODEL INTERPRETATION
        # ----------------------------------------------------

        with st.expander(
            "How does this model work?"
        ):

            if display_name == "Isolation Forest":

                st.write(
                    """
                    Isolation Forest isolates unusual observations by
                    randomly selecting features and split points.

                    Anomalies generally require fewer random splits to
                    isolate than normal observations.

                    Therefore, unusual authentication behavior tends
                    to receive a stronger anomaly score.
                    """
                )

            elif display_name == "One-Class SVM":

                st.write(
                    """
                    One-Class SVM learns a boundary around the normal
                    training data.

                    Events falling outside that learned boundary are
                    considered potential anomalies.
                    """
                )

            elif display_name == "Local Outlier Factor":

                st.write(
                    """
                    Local Outlier Factor compares the local density of
                    an observation with the density around its neighbors.

                    An event that is significantly less dense than its
                    neighbors can be classified as an outlier.
                    """
                )

            else:

                st.write(
                    """
                    Elliptic Envelope estimates the central distribution
                    of the training data and identifies observations
                    that fall far outside that distribution.

                    It is useful when normal observations approximately
                    follow an elliptical distribution.
                    """
                )


# ============================================================
# BEST MODEL
# ============================================================

if best_model != "Not available":

    st.html(
        f"""
        <div class="best-model">

            <b>Selected Model:</b>
            {best_model}

            <br>

            <span style="color:#8f99ae;">
                Selected using the highest available F1 score.
            </span>

        </div>
        """
    )


# ============================================================
# LIVE SSH MONITOR
# ============================================================

section_title(
    "Live SSH Monitor",
    "Monitor authentication events from the local SSH service.",
)

ssh_col1, ssh_col2 = st.columns([3, 1])

with ssh_col1:

    st.html(
        """
        <span class="status-live">
            LIVE MONITOR
        </span>
        """
    )

with ssh_col2:

    auto_refresh = st.checkbox(
        "Auto refresh",
        value=False,
    )


# ------------------------------------------------------------
# SSH LOG READER
# ------------------------------------------------------------

def read_ssh_events():

    events = []

    try:

        result = subprocess.run(
            [
                "sudo",
                "journalctl",
                "-u",
                "ssh",
                "-n",
                "100",
                "--no-pager",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return events

        for line in result.stdout.splitlines():

            if not any(
                keyword in line
                for keyword in [
                    "Accepted password",
                    "Accepted publickey",
                    "Failed password",
                    "Invalid user",
                    "authentication failure",
                ]
            ):
                continue

            status = "UNKNOWN"

            if "Accepted" in line:

                status = "SUCCESS"

            elif (
                "Failed password" in line
                or "Invalid user" in line
                or "authentication failure" in line
            ):

                status = "FAILED"

            user = "unknown"
            source_ip = "unknown"

            match = re.search(
                r"for (?:invalid user )?(\S+)",
                line,
            )

            if match:
                user = match.group(1)

            match = re.search(
                r"from ([^\s]+)",
                line,
            )

            if match:
                source_ip = match.group(1)

            events.append(
                {
                    "Log": line,
                    "User": user,
                    "Source IP": source_ip,
                    "Status": status,
                }
            )

    except Exception:
        pass

    return events


ssh_events = read_ssh_events()


if ssh_events:

    ssh_df = pd.DataFrame(
        ssh_events
    )

    total_ssh = len(ssh_df)

    failed_ssh = int(
        (
            ssh_df["Status"]
            == "FAILED"
        ).sum()
    )

    successful_ssh = int(
        (
            ssh_df["Status"]
            == "SUCCESS"
        ).sum()
    )

    a, b, c = st.columns(3)

    with a:
        show_metric_card(
            "SSH Events",
            total_ssh,
            "Recent SSH authentication events",
        )

    with b:
        show_metric_card(
            "Successful",
            successful_ssh,
            "Accepted authentication",
        )

    with c:
        show_metric_card(
            "Failed",
            failed_ssh,
            "Failed authentication",
        )

    st.dataframe(
        ssh_df.head(30),
        hide_index=True,
    )

else:

    st.info(
        "No SSH authentication events were found."
    )


# ============================================================
# CONTROLLED SSH ATTACK DEMO
# ============================================================

with st.expander(
    "Controlled SSH Attack Demonstration"
):

    st.warning(
        "This generates failed authentication attempts "
        "against localhost only."
    )

    attempts = st.slider(
        "Failed attempts",
        min_value=1,
        max_value=5,
        value=2,
    )

    if st.button(
        "Trigger Failed SSH Attempts"
    ):

        progress = st.progress(0)

        for i in range(attempts):

            try:

                subprocess.run(
                    [
                        "ssh",
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        "ConnectTimeout=2",
                        "invalid_demo_user@127.0.0.1",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=4,
                )

            except Exception:
                pass

            progress.progress(
                (i + 1) / attempts
            )

        st.success(
            f"Generated {attempts} controlled failed "
            f"SSH authentication attempt(s) against localhost."
        )

        time.sleep(1)

        st.rerun()


# ============================================================
# LIVE FILE ACTIVITY
# ============================================================

section_title(
    "Live Session Activity",
    "Monitor controlled file activity after SSH authentication.",
)


if ACTIVITY_MONITOR_AVAILABLE:

    try:

        setup_monitor_directory()

    except Exception:
        pass

    fc1, fc2 = st.columns(2)

    with fc1:

        if st.button(
            "Enable File Monitoring"
        ):

            success, message = (
                install_audit_rule()
            )

            if success:

                st.success(
                    message
                )

            else:

                st.error(
                    message
                )

    with fc2:

        if st.button(
            "Refresh File Activity"
        ):

            st.rerun()

    activity_events = read_events()

    if activity_events:

        activity_df = pd.DataFrame(
            activity_events
        )

        total_activity = len(
            activity_events
        )

        unique_files = len(
            set(
                event.get(
                    "path",
                    "",
                )
                for event in activity_events
            )
        )

        x1, x2, x3 = st.columns(3)

        with x1:

            show_metric_card(
                "File Events",
                total_activity,
                "Detected activity",
            )

        with x2:

            show_metric_card(
                "Files Accessed",
                unique_files,
                "Unique paths",
            )

        with x3:

            show_metric_card(
                "Monitoring",
                "ACTIVE",
                "Controlled directory",
            )

        st.dataframe(
            activity_df[
                [
                    "timestamp",
                    "event_type",
                    "path",
                    "process",
                    "user",
                    "pid",
                ]
            ].head(50),
            hide_index=True,
        )

    else:

        st.info(
            "No file activity detected yet."
        )

    st.caption(
        f"Controlled monitoring directory: {DEMO_DIR}"
    )

else:

    st.warning(
        "activity_monitor.py is not available. "
        "Create the file provided with this project update "
        "to enable live file monitoring."
    )


# ============================================================
# LIVE TEST INSTRUCTIONS
# ============================================================

with st.expander(
    "Live Demo Instructions"
):

    st.markdown(
        f"""
### 1. Start the dashboard

```bash
streamlit run dashboard.py
```

### 2. Generate controlled failed SSH events

Use the **Trigger Failed SSH Attempts** button above. It attempts SSH
authentication against `127.0.0.1` with an invalid demonstration user.

### 3. Enable controlled file monitoring

Use **Enable File Monitoring** to install an audit rule for only this
directory:

```text
{DEMO_DIR}
```

After a login session, access a file inside that directory and then use
**Refresh File Activity** to display any audit events returned by
`activity_monitor.py`.
"""
    )


if auto_refresh:

    time.sleep(5)
    st.rerun()
