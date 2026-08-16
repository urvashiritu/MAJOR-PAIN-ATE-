from pathlib import Path
from collections import defaultdict, deque
import re
import subprocess
import time

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Identity Anomaly Detection",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# PATHS
# ============================================================

DATA_DIR = Path("data")
MODEL_DIR = Path("models")
OUTPUT_DIR = Path("outputs")

AUTH_LOG = Path("/var/log/auth.log")


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
"""
<style>

/* =========================================================
   GLOBAL
   ========================================================= */

.stApp {
    background:
        radial-gradient(
            circle at 10% 0%,
            rgba(80, 100, 255, 0.12),
            transparent 30%
        ),
        radial-gradient(
            circle at 90% 10%,
            rgba(0, 220, 180, 0.08),
            transparent 30%
        ),
        #070b14;

    color: #f5f7fb;
}


/* =========================================================
   HERO
   ========================================================= */

.hero {
    padding: 34px;
    margin-bottom: 24px;

    border-radius: 20px;

    background:
        linear-gradient(
            135deg,
            rgba(27, 37, 70, 0.96),
            rgba(10, 15, 28, 0.98)
        );

    border: 1px solid rgba(
        255,
        255,
        255,
        0.08
    );

    box-shadow:
        0 20px 60px rgba(
            0,
            0,
            0,
            0.35
        );
}

.hero-title {
    font-size: 38px;
    font-weight: 800;
    line-height: 1.1;
    letter-spacing: -1px;
}

.hero-subtitle {
    margin-top: 10px;
    font-size: 15px;
    color: #9da7bd;
}


/* =========================================================
   METRIC CARDS
   ========================================================= */

.metric-card {
    padding: 20px;
    min-height: 118px;

    border-radius: 16px;

    background:
        linear-gradient(
            145deg,
            rgba(25, 32, 52, 0.96),
            rgba(11, 16, 29, 0.96)
        );

    border: 1px solid rgba(
        255,
        255,
        255,
        0.07
    );

    box-shadow:
        0 10px 30px rgba(
            0,
            0,
            0,
            0.25
        );
}

.metric-label {
    color: #8e99b0;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.metric-value {
    margin-top: 7px;
    font-size: 28px;
    font-weight: 800;
}

.metric-description {
    margin-top: 4px;
    color: #778197;
    font-size: 11px;
}


/* =========================================================
   SECTION TITLES
   ========================================================= */

.section-title {
    margin-top: 20px;
    margin-bottom: 4px;
    font-size: 25px;
    font-weight: 750;
}

.section-description {
    margin-bottom: 16px;
    color: #8b95aa;
    font-size: 14px;
}


/* =========================================================
   LIVE PANEL
   ========================================================= */

.live-panel {
    padding: 20px;

    border-radius: 18px;

    background:
        linear-gradient(
            135deg,
            rgba(15, 25, 40, 0.98),
            rgba(8, 12, 22, 0.98)
        );

    border: 1px solid rgba(
        0,
        220,
        180,
        0.15
    );
}


/* =========================================================
   BUTTONS
   ========================================================= */

.stButton > button {
    border-radius: 10px;

    border: 1px solid rgba(
        255,
        255,
        255,
        0.10
    );

    font-weight: 650;

    transition:
        transform 0.2s ease,
        box-shadow 0.2s ease;
}

.stButton > button:hover {
    transform: translateY(-2px);

    box-shadow:
        0 8px 25px rgba(
            0,
            0,
            0,
            0.25
        );
}


/* =========================================================
   TABS
   ========================================================= */

.stTabs [data-baseweb="tab"] {
    font-weight: 650;
}


/* =========================================================
   DATAFRAME
   ========================================================= */

[data-testid="stDataFrame"] {
    border-radius: 14px;
    overflow: hidden;
}

</style>
""",
unsafe_allow_html=True,
)


# ============================================================
# HERO
# ============================================================

st.markdown(
"""
<div class="hero">
<div class="hero-title">Identity Anomaly Detection</div>
<div class="hero-subtitle">Multi-source authentication analytics, behavioral anomaly detection and live SSH monitoring.</div>
</div>
""",
unsafe_allow_html=True,
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def metric_card(label, value, description=""):

    html = f"""
<div class="metric-card">
<div class="metric-label">{label}</div>
<div class="metric-value">{value}</div>
<div class="metric-description">{description}</div>
</div>
"""

    st.markdown(
        html,
        unsafe_allow_html=True,
    )


def section_title(title, description=""):

    html = f"""
<div class="section-title">{title}</div>
<div class="section-description">{description}</div>
"""

    st.markdown(
        html,
        unsafe_allow_html=True,
    )


# ============================================================
# LOAD CSV
# ============================================================

@st.cache_data(ttl=5)
def load_csv(filename):

    path = OUTPUT_DIR / filename

    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


evaluation = load_csv(
    "model_evaluation.csv"
)

normalized = load_csv(
    "normalized_authentication_events.csv"
)

features = load_csv(
    "authentication_features.csv"
)

risk_data = load_csv(
    "test_risk_scores.csv"
)


# ============================================================
# LOAD BEST MODEL
# ============================================================

def load_best_model():

    best_file = MODEL_DIR / "best_model.txt"

    if not best_file.exists():
        return None, "N/A"

    name = (
        best_file
        .read_text()
        .strip()
    )

    model_files = {
        "IsolationForest":
            "isolation_forest.joblib",

        "OneClassSVM":
            "one_class_svm.joblib",

        "LOF":
            "local_outlier_factor.joblib",

        "EllipticEnvelope":
            "elliptic_envelope.joblib",
    }

    if name not in model_files:
        return None, name

    path = (
        MODEL_DIR /
        model_files[name]
    )

    if not path.exists():
        return None, name

    try:
        return joblib.load(path), name
    except Exception:
        return None, name


best_model, best_model_name = load_best_model()


# ============================================================
# TOP STATISTICS
# ============================================================

total_events = len(normalized)

anomalies = 0
high_risk = 0

if not risk_data.empty:

    if "risk_level" in risk_data.columns:

        anomalies = int(
            (
                risk_data["risk_level"]
                != "LOW"
            ).sum()
        )

        high_risk = int(
            (
                risk_data["risk_level"]
                == "HIGH"
            ).sum()
        )


best_f1 = 0.0

if not evaluation.empty:

    best_f1 = float(
        evaluation.iloc[0]["f1_score"]
    )


# ============================================================
# TOP METRICS
# ============================================================

c1, c2, c3, c4 = st.columns(4)

with c1:
    metric_card(
        "Total Events",
        f"{total_events:,}",
        "Normalized authentication events",
    )

with c2:
    metric_card(
        "Anomalies",
        f"{anomalies:,}",
        "Medium + high risk events",
    )

with c3:
    metric_card(
        "High Risk",
        f"{high_risk:,}",
        "Events requiring attention",
    )

with c4:
    metric_card(
        "Best Model",
        best_model_name,
        f"F1 Score: {best_f1:.4f}",
    )


# ============================================================
# LIVE SSH MONITOR
# ============================================================

st.divider()

section_title(
    "Live SSH Monitor",
    "Monitor authentication events from the local Linux SSH service.",
)


# ============================================================
# SSH PARSER
# ============================================================

SSH_HEADER = re.compile(
    r"^(?P<ts>\S+)"
    r"\s+(?P<host>\S+)"
    r"\s+sshd(?:-session)?\[\d+\]:\s+"
    r"(?P<msg>.*)$"
)

SSH_AUTH = re.compile(
    r"^(?P<action>Accepted|Failed)\s+"
    r"(?P<method>\S+)"
    r"(?:\s+password)?\s+for\s+"
    r"(?:(?:invalid user)\s+)?"
    r"(?P<user>\S+)\s+from\s+"
    r"(?P<ip>[0-9a-fA-F:.]+)\s+port\s+\d+"
)


def parse_ssh_line(line):

    match = SSH_HEADER.match(
        line.strip()
    )

    if not match:
        return None

    auth = SSH_AUTH.match(
        match.group("msg")
    )

    if not auth:
        return None

    try:

        timestamp = pd.to_datetime(
            match.group("ts"),
            utc=True,
        )

    except Exception:

        return None

    return {
        "timestamp": timestamp,
        "user_id": auth.group("user"),
        "source_ip": auth.group("ip"),
        "success": (
            auth.group("action")
            == "Accepted"
        ),
    }


# ============================================================
# SESSION STATE
# ============================================================

if "ssh_history" not in st.session_state:

    st.session_state.ssh_history = defaultdict(
        lambda: deque(maxlen=100)
    )


if "processed_ssh_events" not in st.session_state:

    st.session_state.processed_ssh_events = set()


if "live_results" not in st.session_state:

    st.session_state.live_results = []


# ============================================================
# LIVE FEATURES
# ============================================================

def create_live_features(event):

    user = event["user_id"]

    timestamp = event["timestamp"]

    history = (
        st.session_state
        .ssh_history[user]
    )

    hour = timestamp.hour

    is_night = int(
        hour < 6
        or hour >= 22
    )

    is_weekend = int(
        timestamp.weekday() >= 5
    )

    failed_before = sum(
        1
        for item in list(history)[-10:]
        if not item["success"]
    )

    rapid_logins = sum(
        1
        for item in history
        if (
            timestamp
            - item["timestamp"]
        ).total_seconds()
        <= 3600
    ) + 1

    today = timestamp.date()

    daily_count = sum(
        1
        for item in history
        if item["timestamp"].date()
        == today
    ) + 1

    return np.array(
        [[
            hour,
            is_night,
            is_weekend,
            0,
            0,
            failed_before,
            rapid_logins,
            daily_count,
        ]],
        dtype=float,
    )


# ============================================================
# RISK CALCULATION
# ============================================================

def calculate_risk(model, X):

    prediction = model.predict(X)[0]

    decision = model.decision_function(X)[0]

    risk = (
        100
        /
        (
            1
            +
            np.exp(
                np.clip(
                    decision * 5,
                    -50,
                    50,
                )
            )
        )
    )

    risk = float(
        np.clip(
            risk,
            0,
            100,
        )
    )

    if risk >= 75:
        level = "HIGH"

    elif risk >= 50:
        level = "MEDIUM"

    else:
        level = "LOW"

    return (
        prediction == -1,
        risk,
        level,
    )


# ============================================================
# READ LIVE SSH LOG
# ============================================================

def get_live_events():

    if not AUTH_LOG.exists():
        return []

    try:

        result = subprocess.run(
            [
                "sudo",
                "-n",
                "tail",
                "-n",
                "100",
                str(AUTH_LOG),
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )

        if result.returncode != 0:
            return []

        events = []

        for line in result.stdout.splitlines():

            event = parse_ssh_line(line)

            if event:
                events.append(event)

        return events

    except Exception:

        return []


# ============================================================
# PROCESS LIVE EVENTS
# ============================================================

if best_model is not None:

    events = get_live_events()

    for event in events:

        event_id = (
            str(event["timestamp"])
            + "|"
            + event["user_id"]
            + "|"
            + event["source_ip"]
            + "|"
            + str(event["success"])
        )

        if event_id in st.session_state.processed_ssh_events:
            continue

        st.session_state.processed_ssh_events.add(
            event_id
        )

        X = create_live_features(event)

        anomaly, risk, level = calculate_risk(
            best_model,
            X,
        )

        result = {
            **event,
            "anomaly": anomaly,
            "risk_score": risk,
            "risk_level": level,
            "failed_before_success":
                int(X[0][5]),
            "rapid_login_rate":
                int(X[0][6]),
            "login_frequency_today":
                int(X[0][7]),
        }

        st.session_state.live_results.append(
            result
        )

        st.session_state.ssh_history[
            event["user_id"]
        ].append(event)


# ============================================================
# LIVE CONTROLS
# ============================================================

control1, control2, control3 = st.columns(3)

with control1:

    if st.button(
        "Trigger Failed SSH Attempt",
        use_container_width=True,
    ):

        demo_user = (
            "demo_attack_"
            + str(int(time.time()))
        )

        try:

            subprocess.run(
                [
                    "ssh",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "PreferredAuthentications=password",
                    "-o",
                    "PubkeyAuthentication=no",
                    f"{demo_user}@localhost",
                    "exit",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            st.success(
                "SSH authentication event generated."
            )

            time.sleep(1)

            st.rerun()

        except Exception as e:

            st.error(str(e))


with control2:

    if st.button(
        "Refresh Live Monitor",
        use_container_width=True,
    ):

        st.rerun()


with control3:

    if st.button(
        "Clear Live Session",
        use_container_width=True,
    ):

        st.session_state.live_results = []

        st.session_state.ssh_history = defaultdict(
            lambda: deque(maxlen=100)
        )

        st.session_state.processed_ssh_events = set()

        st.rerun()


# ============================================================
# LIVE TABLE
# ============================================================

live_results = st.session_state.live_results

if live_results:

    live_df = pd.DataFrame(live_results)

    columns = [
        "timestamp",
        "user_id",
        "source_ip",
        "success",
        "anomaly",
        "risk_score",
        "risk_level",
    ]

    st.dataframe(
        live_df[columns]
        .sort_values(
            "timestamp",
            ascending=False,
        )
        .head(20),
        use_container_width=True,
        hide_index=True,
    )

    latest = live_results[-1]

    if latest["risk_level"] == "HIGH":

        st.error(
            f"HIGH RISK — "
            f"{latest['user_id']} "
            f"from {latest['source_ip']} "
            f"— Risk "
            f"{latest['risk_score']:.1f}/100"
        )

    elif latest["risk_level"] == "MEDIUM":

        st.warning(
            f"MEDIUM RISK — "
            f"Risk {latest['risk_score']:.1f}/100"
        )

    else:

        st.success(
            f"Normal SSH activity — "
            f"Risk {latest['risk_score']:.1f}/100"
        )

    a, b, c = st.columns(3)

    with a:

        metric_card(
            "Failed Before",
            latest["failed_before_success"],
            "Previous failed attempts",
        )

    with b:

        metric_card(
            "Rapid Logins",
            latest["rapid_login_rate"],
            "Events within one hour",
        )

    with c:

        metric_card(
            "Daily Frequency",
            latest["login_frequency_today"],
            "User events today",
        )

else:

    st.info(
        "Waiting for SSH authentication events. "
        "Use the trigger button or connect through SSH."
    )


# ============================================================
# DATA UNDERSTANDING
# ============================================================

st.divider()

section_title(
    "Data Understanding",
    "Understand the transformation from raw authentication logs to ML-ready data.",
)

raw_tab, parsed_tab, feature_tab = st.tabs(
    [
        "Original Raw Data",
        "Parsed / Normalized Data",
        "ML Features",
    ]
)


# ============================================================
# RAW DATA
# ============================================================

with raw_tab:

    raw_files = {

        "SSH":
            DATA_DIR / "ssh_auth.log",

        "Windows AD":
            DATA_DIR /
            "windows_security_events.xml",

        "VPN":
            DATA_DIR / "vpn_auth.log",

        "AWS":
            DATA_DIR /
            "aws_cloudtrail_console_login.json",

        "M365":
            DATA_DIR /
            "entra_signin_logs.json",

        "MySQL":
            DATA_DIR /
            "mysql_audit_logs.json",

        "Web":
            DATA_DIR /
            "web_authentication.jsonl",
    }

    selected_source = st.selectbox(
        "Authentication source",
        list(raw_files.keys()),
    )

    path = raw_files[selected_source]

    st.markdown(
        f"#### Original {selected_source} log"
    )

    if path.exists():

        try:

            with path.open(
                encoding="utf-8",
                errors="replace",
            ) as f:

                lines = []

                for _ in range(8):

                    line = f.readline()

                    if not line:
                        break

                    lines.append(
                        line.rstrip()
                    )

            st.code(
                "\n".join(lines),
                language="text",
            )

        except Exception as e:

            st.error(str(e))

    else:

        st.warning(
            f"{path} not found."
        )

    st.info(
        "Each authentication source has a different "
        "raw format. The corresponding parser extracts "
        "the useful attributes before normalization."
    )


# ============================================================
# PARSED DATA
# ============================================================

with parsed_tab:

    if normalized.empty:

        st.warning(
            "Run train.py first."
        )

    else:

        st.markdown(
            "#### Common normalized authentication schema"
        )

        st.dataframe(
            normalized.head(100),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown(
            """
**Transformation**

`Raw Source → Source Parser → Common Schema`

The seven different authentication sources are converted
into one consistent representation before feature engineering.
"""
        )

        col1, col2 = st.columns(2)

        with col1:

            source_counts = (
                normalized["source"]
                .value_counts()
                .reset_index()
            )

            source_counts.columns = [
                "source",
                "events",
            ]

            fig = px.bar(
                source_counts,
                x="source",
                y="events",
                title="Events by Source",
                text_auto=True,
            )

            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )

        with col2:

            success_counts = (
                normalized["success"]
                .value_counts()
                .reset_index()
            )

            success_counts.columns = [
                "result",
                "events",
            ]

            success_counts["result"] = (
                success_counts["result"]
                .map(
                    {
                        True: "Success",
                        False: "Failed",
                    }
                )
            )

            fig = px.pie(
                success_counts,
                names="result",
                values="events",
                title="Authentication Results",
                hole=0.55,
            )

            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
            )

            st.plotly_chart(
                fig,
                use_container_width=True,
            )


# ============================================================
# FEATURES
# ============================================================

with feature_tab:

    if features.empty:

        st.warning(
            "Run train.py first."
        )

    else:

        feature_columns = [
            "hour",
            "is_night",
            "is_weekend",
            "country_change",
            "device_change",
            "failed_before_success",
            "rapid_login_rate",
            "login_frequency_today",
        ]

        st.markdown(
            "#### Behavioral features"
        )

        st.dataframe(
            features[feature_columns].head(100),
            use_container_width=True,
            hide_index=True,
        )

        st.info(
            "These numerical behavioral signals are "
            "the inputs given to the anomaly-detection models."
        )


# ============================================================
# MODEL PERFORMANCE
# ============================================================

st.divider()

section_title(
    "Model Performance",
    "Comparison of all four anomaly-detection models.",
)

if evaluation.empty:

    st.warning(
        "Model evaluation data not found. Run train.py first."
    )

else:

    metrics = [
        "accuracy",
        "precision",
        "recall",
        "f1_score",
        "roc_auc",
    ]

    display = evaluation.copy()

    for column in metrics:

        display[column] = (
            display[column] * 100
        ).round(2)

    st.dataframe(
        display[
            [
                "rank",
                "model",
                "accuracy",
                "precision",
                "recall",
                "f1_score",
                "roc_auc",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    chart_data = evaluation.melt(
        id_vars="model",
        value_vars=metrics,
        var_name="metric",
        value_name="score",
    )

    chart_data["score"] *= 100

    fig = px.bar(
        chart_data,
        x="model",
        y="score",
        color="metric",
        barmode="group",
        text_auto=".1f",
        title="Model Metric Comparison",
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="Score (%)",
        xaxis_title="",
        legend_title="Metric",
    )

    fig.update_yaxes(
        range=[0, 100]
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

    best = evaluation.iloc[0]

    st.success(
        f"Best model: {best['model']}  •  "
        f"F1: {best['f1_score']:.4f}  •  "
        f"ROC-AUC: {best['roc_auc']:.4f}"
    )


# ============================================================
# ANOMALY ANALYSIS
# ============================================================

st.divider()

section_title(
    "Anomaly Analysis",
    "Risk distribution across the unseen test dataset.",
)

if risk_data.empty:

    st.warning(
        "Risk data not found."
    )

else:

    col1, col2 = st.columns(2)

    with col1:

        counts = (
            risk_data["risk_level"]
            .value_counts()
            .reindex(
                [
                    "LOW",
                    "MEDIUM",
                    "HIGH",
                ],
                fill_value=0,
            )
            .reset_index()
        )

        counts.columns = [
            "risk_level",
            "events",
        ]

        fig = px.bar(
            counts,
            x="risk_level",
            y="events",
            text_auto=True,
            title="Risk Distribution",
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

    with col2:

        fig = px.histogram(
            risk_data,
            x="ensemble_risk_score",
            nbins=40,
            title="Risk Score Distribution",
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Risk Score",
            yaxis_title="Events",
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "Identity Anomaly Detection • "
    "Multi-source Authentication Intelligence • "
    "Research Prototype"
)
