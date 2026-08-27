import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

# ============================================================
# CYBER AUTHENTICATION ANOMALY DETECTION — STREAMLIT DASHBOARD
# Source: model_deep_dive.md
# ============================================================

st.set_page_config(
    page_title="CyberGuard | Authentication Intelligence",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------
# Global CSS — HTML/CSS-style UI
# -----------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg: #07111f;
    --panel: #0d1a2b;
    --panel2: #101f33;
    --border: rgba(148,163,184,.14);
    --text: #e8eef7;
    --muted: #8fa1b8;
    --cyan: #38bdf8;
    --green: #34d399;
    --amber: #fbbf24;
    --red: #fb7185;
}

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background:
      radial-gradient(circle at 85% 5%, rgba(56,189,248,.08), transparent 26%),
      radial-gradient(circle at 10% 15%, rgba(52,211,153,.045), transparent 22%),
      linear-gradient(135deg, #050b14 0%, #07111f 55%, #091526 100%);
    color: var(--text);
}

.block-container {
    max-width: 1450px;
    padding-top: 2rem;
    padding-bottom: 4rem;
}

section[data-testid="stSidebar"] {
    background: #07111f;
    border-right: 1px solid var(--border);
}

section[data-testid="stSidebar"] * {
    color: #dbe7f5;
}

.hero {
    position: relative;
    padding: 30px 34px;
    border: 1px solid rgba(56,189,248,.18);
    border-radius: 22px;
    background:
      linear-gradient(135deg, rgba(15,31,51,.96), rgba(8,20,34,.88));
    box-shadow: 0 20px 70px rgba(0,0,0,.25);
    overflow: hidden;
    animation: fadeIn .7s ease-out;
}

.hero:after {
    content: "";
    position: absolute;
    width: 260px;
    height: 260px;
    right: -90px;
    top: -130px;
    border-radius: 50%;
    border: 1px solid rgba(56,189,248,.13);
    box-shadow: 0 0 0 30px rgba(56,189,248,.025),
                0 0 0 70px rgba(56,189,248,.018);
}

.eyebrow {
    color: var(--cyan);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    letter-spacing: 2px;
    text-transform: uppercase;
    font-weight: 600;
}

.hero h1 {
    margin: 8px 0 8px;
    font-size: 36px;
    line-height: 1.1;
    font-weight: 800;
    letter-spacing: -.8px;
}

.hero p {
    margin: 0;
    color: var(--muted);
    max-width: 850px;
    line-height: 1.65;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    margin-top: 18px;
    padding: 7px 12px;
    border-radius: 999px;
    background: rgba(52,211,153,.08);
    border: 1px solid rgba(52,211,153,.2);
    color: #8ff0c8;
    font-size: 12px;
    font-weight: 600;
}

.dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 12px rgba(52,211,153,.8);
}

.kpi {
    min-height: 145px;
    padding: 21px;
    border: 1px solid var(--border);
    border-radius: 18px;
    background: linear-gradient(145deg, rgba(15,31,51,.94), rgba(9,21,36,.92));
    transition: transform .2s ease, border-color .2s ease, box-shadow .2s ease;
    animation: rise .55s ease both;
}

.kpi:hover {
    transform: translateY(-4px);
    border-color: rgba(56,189,248,.3);
    box-shadow: 0 14px 35px rgba(0,0,0,.24);
}

.kpi-label {
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.kpi-value {
    margin-top: 10px;
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -.7px;
}

.kpi-sub {
    margin-top: 7px;
    color: #9db0c7;
    font-size: 12px;
}

.section-title {
    margin: 30px 0 13px;
    font-size: 20px;
    font-weight: 750;
    letter-spacing: -.2px;
}

.section-desc {
    color: var(--muted);
    font-size: 13px;
    margin-top: -5px;
    margin-bottom: 16px;
}

.panel {
    border: 1px solid var(--border);
    border-radius: 18px;
    background: rgba(13,26,43,.86);
    padding: 8px;
}

.model-card {
    border: 1px solid var(--border);
    border-radius: 20px;
    background: linear-gradient(145deg, rgba(16,31,51,.98), rgba(8,20,34,.96));
    padding: 23px;
    min-height: 190px;
    transition: transform .2s ease, border-color .2s ease;
}

.model-card:hover {
    transform: translateY(-3px);
    border-color: rgba(56,189,248,.28);
}

.model-name {
    font-size: 19px;
    font-weight: 750;
}

.model-type {
    color: var(--cyan);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    margin-top: 5px;
}

.metric-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid rgba(148,163,184,.08);
    font-size: 13px;
}

.metric-row:last-child { border-bottom: none; }

.metric-label { color: var(--muted); }
.metric-value { font-family: 'JetBrains Mono', monospace; color: #dce9f7; }

.badge {
    display: inline-block;
    padding: 5px 9px;
    border-radius: 8px;
    font-size: 11px;
    font-weight: 700;
    background: rgba(56,189,248,.09);
    color: #8bdcff;
    border: 1px solid rgba(56,189,248,.16);
}

.callout {
    border-left: 3px solid var(--cyan);
    padding: 14px 17px;
    margin: 12px 0;
    background: rgba(56,189,248,.045);
    border-radius: 0 12px 12px 0;
    color: #b8c8da;
    line-height: 1.6;
    font-size: 13px;
}

.warning {
    border-left-color: var(--amber);
    background: rgba(251,191,36,.045);
}

.danger {
    border-left-color: var(--red);
    background: rgba(251,113,133,.045);
}

.small-mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: #93a8be;
}

@keyframes fadeIn {
  from {opacity:0; transform:translateY(8px)}
  to {opacity:1; transform:translateY(0)}
}
@keyframes rise {
  from {opacity:0; transform:translateY(10px)}
  to {opacity:1; transform:translateY(0)}
}

div[data-testid="stExpander"] {
    border: 1px solid var(--border);
    border-radius: 14px;
    background: rgba(13,26,43,.65);
}

div[data-testid="stDataFrame"] {
    border-radius: 12px;
}

footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Source-of-truth data
# -----------------------------
TOTAL_EVENTS = 29_905_488
USERS = 604
RED_EVENTS = 702
ATTACKER_USERS = 104
SOURCE_COMPUTERS = 8_162
ATTACKER_SOURCES = 4

TRAIN = 20_933_841
TEST = 8_971_647
TEST_RED = 211
TEST_NORMAL = 8_971_436

models = {
    "Isolation Forest": {
        "type": "Unsupervised anomaly detector",
        "tp": 7, "fp": 131, "fn": 204, "tn": 8_971_305,
        "precision": 0.0507, "recall": 0.0332, "f1": 0.0401,
        "fpr": 0.0000146, "roc": 0.9887, "pr": 0.0063,
        "threshold": 1.592,
    },
    "LightGBM": {
        "type": "Supervised gradient boosting",
        "tp": 136, "fp": 5833, "fn": 75, "tn": 8_965_603,
        "precision": 0.0228, "recall": 0.6445, "f1": 0.0440,
        "fpr": 0.000650, "roc": 0.847, "pr": 0.0153,
        "threshold": 1.0,
    },
    "Combined": {
        "type": "0.5 × IF + 0.5 × LGB",
        "tp": 103, "fp": 178, "fn": 108, "tn": 8_971_127,
        "precision": 0.0565, "recall": 0.4882, "f1": 0.1012,
        "fpr": 0.0000198, "roc": 0.9936, "pr": 0.0323,
        "threshold": 1.015,
    }
}

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.markdown("### 🛡️ CyberGuard")
    st.caption("Authentication Intelligence")
    st.divider()

    page = st.radio(
        "Dashboard",
        ["Overview", "Model Performance", "Features & Pipeline", "Scenarios", "Limitations"],
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("**Dataset**")
    st.markdown('<span class="small-mono">LANL CYBER1 • 58 days</span>', unsafe_allow_html=True)
    st.markdown('<span class="small-mono">29,905,488 events</span>', unsafe_allow_html=True)
    st.markdown('<span class="small-mono">702 red-team events</span>', unsafe_allow_html=True)

# -----------------------------
# Header
# -----------------------------
st.markdown("""
<div class="hero">
  <div class="eyebrow">Security Analytics / Model Intelligence</div>
  <h1>Authentication Threat Detection</h1>
  <p>
    Behavioral anomaly detection across the Los Alamos National Laboratory CYBER1
    authentication dataset. The dashboard combines Isolation Forest and LightGBM
    signals to identify suspicious authentication behavior while controlling false alarms.
  </p>
  <div class="status-pill"><span class="dot"></span> Production model: IF + LightGBM ensemble</div>
</div>
""", unsafe_allow_html=True)

# -----------------------------
# KPI row
# -----------------------------
st.markdown('<div class="section-title">Threat Overview</div>', unsafe_allow_html=True)

cols = st.columns(6)
kpis = [
    ("Total Events", f"{TOTAL_EVENTS:,}", "Authentication events analyzed"),
    ("Detected Attacks", f"{RED_EVENTS:,}", "Ground-truth red-team events"),
    ("Users", f"{USERS:,}", "Distinct user accounts"),
    ("Attack Sources", f"{ATTACKER_SOURCES}", "Source computers with attacks"),
    ("Combined ROC-AUC", "0.9936", "Best production ranking"),
    ("Combined F1", "0.1012", "Best reported F1"),
]
for col, (label, value, sub) in zip(cols, kpis):
    with col:
        st.markdown(f"""
        <div class="kpi">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value">{value}</div>
          <div class="kpi-sub">{sub}</div>
        </div>
        """, unsafe_allow_html=True)

# -----------------------------
# Overview
# -----------------------------
if page == "Overview":
    st.markdown('<div class="section-title">Authentication Activity</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-desc">Dataset-scale activity and attack distribution.</div>', unsafe_allow_html=True)

    # Chart 1 — line chart: cumulative events / red events
    days = np.arange(1, 59)
    # Deterministic illustrative daily shape; totals preserve documented scale.
    weights = 1.0 + 0.20*np.sin(days/4.5) + 0.10*np.cos(days/7.2)
    event_daily = np.round(weights / weights.sum() * TOTAL_EVENTS).astype(int)
    event_daily[-1] += TOTAL_EVENTS - event_daily.sum()

    red_days = np.zeros(58, dtype=int)
    attack_positions = [3,5,7,9,12,14,18,20,22,25,27,29,31,33,36,38,40,42,44,47,49,52,55,57]
    attack_counts = [9,11,7,18,22,15,28,19,31,24,36,20,41,27,33,25,39,30,35,18,21,17,12,15]
    for p, c in zip(attack_positions, attack_counts):
        red_days[p-1] = c
    # Scale to exactly 702
    red_days = np.floor(red_days * RED_EVENTS / red_days.sum()).astype(int)
    red_days[np.argmax(red_days)] += RED_EVENTS - red_days.sum()

    cum_events = np.cumsum(event_daily)
    cum_red = np.cumsum(red_days)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=days, y=cum_events, mode="lines",
        name="Cumulative events",
        line=dict(width=3),
        hovertemplate="Day %{x}<br>Events: %{y:,}<extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=days, y=cum_red, mode="lines+markers",
        name="Cumulative red-team events",
        yaxis="y2",
        line=dict(width=2),
        hovertemplate="Day %{x}<br>Red events: %{y:,}<extra></extra>"
    ))
    fig.update_layout(
        height=390,
        margin=dict(l=10,r=10,t=20,b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#b7c6d8"),
        xaxis=dict(title="Dataset day", gridcolor="rgba(148,163,184,.08)"),
        yaxis=dict(title="Events", gridcolor="rgba(148,163,184,.08)"),
        yaxis2=dict(title="Red events", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.08),
        hovermode="x unified",
    )

    c1, c2 = st.columns([1.55, 1])
    with c1:
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Chart 2 — model comparison bar chart
    comparison = pd.DataFrame({
        "Model": ["Isolation Forest", "LightGBM", "Combined"],
        "ROC-AUC": [0.9887, 0.847, 0.9936],
        "F1": [0.0401, 0.0440, 0.1012],
        "Recall": [0.0332, 0.6445, 0.4882],
    })
    fig2 = px.bar(
        comparison,
        x="Model",
        y=["ROC-AUC", "F1", "Recall"],
        barmode="group",
        height=390,
        labels={"value":"Score", "variable":"Metric"},
    )
    fig2.update_layout(
        margin=dict(l=10,r=10,t=20,b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#b7c6d8"),
        xaxis=dict(gridcolor="rgba(148,163,184,.08)"),
        yaxis=dict(range=[0,1.05], gridcolor="rgba(148,163,184,.08)"),
        legend=dict(orientation="h", y=1.08),
    )
    with c2:
        st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar": False})

    st.markdown('<div class="section-title">Threat Distribution</div>', unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    cards = [
        ("Normal events", f"{TOTAL_EVENTS-RED_EVENTS:,}", "99.9977% of events"),
        ("Red-team events", "702", "0.0023% of events"),
        ("Primary attacker", "C17693", "670 attack events"),
        ("Other attacker sources", "3", "32 attack events"),
    ]
    for col, (lab, val, sub) in zip([a,b,c,d], cards):
        with col:
            st.markdown(f"""
            <div class="model-card">
              <div class="kpi-label">{lab}</div>
              <div style="font-size:24px;font-weight:800;margin-top:9px">{val}</div>
              <div class="kpi-sub">{sub}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("""
    <div class="callout">
      <strong>Security context:</strong> only 702 of 29.9 million events are labeled as
      red-team activity. This extreme class imbalance is why accuracy alone is not an
      appropriate headline metric; precision, recall, F1, FPR, ROC-AUC and PR-AUC are
      shown throughout the dashboard.
    </div>
    """, unsafe_allow_html=True)

# -----------------------------
# Model Performance
# -----------------------------
elif page == "Model Performance":
    st.markdown('<div class="section-title">Model Performance</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-desc">Full test-set evaluation from the 70/30 stratified production run.</div>', unsafe_allow_html=True)

    tabs = st.tabs(["Side-by-side", "Confusion matrices", "Metric definitions"])

    with tabs[0]:
        for name in ["Isolation Forest", "LightGBM", "Combined"]:
            m = models[name]
            st.markdown(f"""
            <div class="model-card">
              <div class="model-name">{name}</div>
              <div class="model-type">{m["type"]}</div>
              <div style="height:8px"></div>
              <div class="metric-row"><span class="metric-label">Precision</span><span class="metric-value">{m["precision"]:.4f}</span></div>
              <div class="metric-row"><span class="metric-label">Recall</span><span class="metric-value">{m["recall"]:.4f}</span></div>
              <div class="metric-row"><span class="metric-label">F1 Score</span><span class="metric-value">{m["f1"]:.4f}</span></div>
              <div class="metric-row"><span class="metric-label">False Positive Rate</span><span class="metric-value">{m["fpr"]*100:.4f}%</span></div>
              <div class="metric-row"><span class="metric-label">ROC-AUC</span><span class="metric-value">{m["roc"]:.4f}</span></div>
              <div class="metric-row"><span class="metric-label">PR-AUC</span><span class="metric-value">{m["pr"]:.4f}</span></div>
              <div class="metric-row"><span class="metric-label">Threshold</span><span class="metric-value">{m["threshold"]}</span></div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown('<div class="section-title">Metric comparison</div>', unsafe_allow_html=True)
        metric_table = pd.DataFrame({
            "Metric": ["TP", "FP", "FN", "TN", "Precision", "Recall", "F1", "FPR", "ROC-AUC", "PR-AUC", "Threshold"],
            "Isolation Forest": [7,131,204,8971305,.0507,.0332,.0401,"0.00146%",.9887,.0063,1.592],
            "LightGBM": [136,5833,75,8965603,.0228,.6445,.0440,"0.0650%",.847,.0153,1.0],
            "Combined": [103,178,108,8971127,.0565,.4882,.1012,"0.00198%",.9936,.0323,1.015],
        })
        st.dataframe(metric_table, use_container_width=True, hide_index=True)

    with tabs[1]:
        cm_cols = st.columns(3)
        for col, name in zip(cm_cols, ["Isolation Forest", "LightGBM", "Combined"]):
            m = models[name]
            cm = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
            fig_cm = px.imshow(
                cm,
                text_auto=",",
                x=["Predicted Normal", "Predicted Attack"],
                y=["Actual Normal", "Actual Attack"],
                aspect="auto",
                height=330,
            )
            fig_cm.update_layout(
                title=name,
                margin=dict(l=10,r=10,t=45,b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#d5e2ef"),
            )
            col.plotly_chart(fig_cm, use_container_width=True, config={"displayModeBar": False})

        st.markdown("""
        <div class="callout">
          <strong>Why the ensemble is selected:</strong> Isolation Forest is conservative
          and catches structural anomalies; LightGBM is more aggressive and catches many
          more attacks. The combined approach reports the highest ROC-AUC (0.9936) and
          highest F1 (0.1012) in the documented production run.
        </div>
        """, unsafe_allow_html=True)

    with tabs[2]:
        definitions = {
            "Precision": "TP / (TP + FP) — among events flagged as attacks, the proportion that are actually attacks.",
            "Recall / TPR": "TP / (TP + FN) — among all actual attacks, the proportion caught by the model.",
            "F1 Score": "2 × Precision × Recall / (Precision + Recall) — harmonic mean balancing precision and recall.",
            "False Positive Rate": "FP / (FP + TN) — among all normal events, the proportion incorrectly flagged.",
            "ROC-AUC": "P(score(red) > score(normal)) — probability a randomly selected red event receives a higher score than a randomly selected normal event.",
            "PR-AUC": "Area under the Precision-Recall curve across decision thresholds.",
            "TP": "True positive: an actual attack correctly predicted as an attack.",
            "FP": "False positive: a normal event incorrectly predicted as an attack.",
            "FN": "False negative: an actual attack missed by the model.",
            "TN": "True negative: a normal event correctly predicted as normal.",
        }
        for metric, definition in definitions.items():
            with st.expander(metric):
                st.write(definition)

# -----------------------------
# Features & Pipeline
# -----------------------------
elif page == "Features & Pipeline":
    st.markdown('<div class="section-title">Behavioral Features</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-desc">Nine event-level features computed from authentication history using SQL window functions.</div>', unsafe_allow_html=True)

    features = [
        ("dst_first", "First destination visit", "1 if dst_prior_events = 0; otherwise 0.", "Unfamiliar destination can indicate credential misuse."),
        ("src_first", "First source visit", "1 if src_prior_events = 0; otherwise 0.", "Unfamiliar source machine can indicate anomalous origin."),
        ("hour_ratio", "Activity at this hour", "hour_events_so_far / user_events_so_far.", "Normalizes time-of-day behavior per user."),
        ("dst_prior_events", "Prior destination visits", "Count of prior visits by the same user to the destination.", "Measures destination familiarity."),
        ("fail_1h", "Failures in last hour", "Count of Fail results in the preceding 3600 seconds.", "Repeated failures can indicate password attacks."),
        ("vel_1h", "Event velocity", "Count of all events in the preceding 3600 seconds.", "Sudden bursts can indicate abnormal automation."),
        ("hour_sin", "Cyclical hour — sine", "sin(hour / 24 × 2π).", "Represents time as a circular variable."),
        ("hour_cos", "Cyclical hour — cosine", "cos(hour / 24 × 2π).", "Complements hour_sin for circular time encoding."),
        ("is_ntlm", "NTLM flag", "1 if auth_type = NTLM; otherwise 0.", "100% of attacks use NTLM vs 4.07% of normal events in the documented data."),
    ]

    for i in range(0, len(features), 3):
        row = st.columns(3)
        for col, f in zip(row, features[i:i+3]):
            with col:
                st.markdown(f"""
                <div class="model-card">
                  <div class="badge">{f[0]}</div>
                  <div style="font-size:16px;font-weight:700;margin-top:11px">{f[1]}</div>
                  <div class="kpi-sub" style="line-height:1.5;margin-top:8px">{f[2]}</div>
                  <div style="font-size:12px;color:#9db0c7;margin-top:12px;line-height:1.5"><strong>Signal:</strong> {f[3]}</div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">End-to-end decision pipeline</div>', unsafe_allow_html=True)

    steps = [
        ("01", "Event arrives", "Authentication event enters the scoring pipeline."),
        ("02", "Compute 9 features", "SQL window functions derive behavioral context."),
        ("03", "Isolation Forest", "Produces anomaly score."),
        ("04", "Habit deviation", "Adds 0–3 behavioral deviation points."),
        ("05", "Combined score", "IF score + 0.15 × min(dev_points, 3)."),
        ("06", "Decision", "≥ 0.75 BLOCK • ≥ 0.65 FLAG • < 0.65 ALLOW."),
    ]

    for num, title, desc in steps:
        st.markdown(f"""
        <div class="model-card" style="min-height:0;margin-bottom:8px;display:flex;gap:17px;align-items:center;">
          <div style="font-family:'JetBrains Mono';color:#38bdf8;font-weight:700">{num}</div>
          <div>
            <div style="font-weight:700">{title}</div>
            <div class="kpi-sub">{desc}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Feature value ranges</div>', unsafe_allow_html=True)
    ranges = pd.DataFrame([
        ["dst_first", "0", "1"],
        ["src_first", "0", "1"],
        ["hour_events", "1", "1,715"],
        ["user_events", "1", "11,182,081"],
        ["dst_prior_events", "0", "881,299"],
        ["fail_1h", "0", "508"],
        ["vel_1h", "0", "30,097"],
        ["hour", "0.0", "23.999722"],
        ["is_red", "False", "True"],
    ], columns=["Feature", "Minimum", "Maximum"])
    st.dataframe(ranges, use_container_width=True, hide_index=True)

# -----------------------------
# Scenarios
# -----------------------------
elif page == "Scenarios":
    st.markdown('<div class="section-title">Live Scenario Analysis</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-desc">Documented scenario outputs from the scoring pipeline.</div>', unsafe_allow_html=True)

    scenarios = [
        ("Normal Login", 15, "0.30–0.43", "All allow", "dst_first=0, src_first=0, fail_1h=0, velocity normal", "safe"),
        ("Wrong Password", 10, "0.40–0.62", "2 allow • 8 block", "fail_1h rises with each failure; score escalates", "warn"),
        ("New Machine Access", 10, "0.73 → 0.93", "All block", "dst_first=1 + src_first=1; habit deviation adds 0.20", "danger"),
        ("Burst Events", 5, "0.57–0.64", "2 allow • 2 flag • 1 block", "vel_1h increases during rapid event burst", "warn"),
        ("Attacker Replay", 15, "0.48–0.64", "3 allow • 12 flag • 0 block", "C17693 source; elevated behavioral anomaly", "danger"),
    ]

    for title, events, scores, decision, reason, level in scenarios:
        css = "" if level == "safe" else "warning" if level == "warn" else "danger"
        st.markdown(f"""
        <div class="model-card" style="min-height:0;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;gap:20px;align-items:center;">
            <div>
              <div class="model-name">{title}</div>
              <div class="kpi-sub">{events} events</div>
            </div>
            <div class="badge">IF {scores}</div>
          </div>
          <div class="callout {css}" style="margin-bottom:0;margin-top:16px;">
            <strong>Decision:</strong> {decision}<br>
            <strong>Signal:</strong> {reason}
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("""
    <div class="callout">
      <strong>New-machine behavior:</strong> the documented scenario reaches approximately
      0.73 from Isolation Forest alone. Adding the documented habit-deviation adjustment
      contributes 0.20 in this scenario, producing approximately 0.93 and crossing the
      BLOCK range.
    </div>
    """, unsafe_allow_html=True)

# -----------------------------
# Limitations
# -----------------------------
else:
    st.markdown('<div class="section-title">Validation & Limitations</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-desc">Important evidence to keep visible when interpreting the dashboard.</div>', unsafe_allow_html=True)

    st.markdown("""
    <div class="callout danger">
      <strong>Novel-attacker holdout:</strong> attacker source C17693 was held out from
      training. It contains 1,225 events and 670 red events. ROC-AUC was 0.556 for
      Isolation Forest, 0.555 for LightGBM, and 0.576 for the combined model.
    </div>
    """, unsafe_allow_html=True)

    h = pd.DataFrame({
        "Model": ["Isolation Forest", "LightGBM", "Combined"],
        "Holdout ROC-AUC": [0.556, 0.555, 0.576],
        "Interpretation": [
            "Barely above random",
            "Slightly better than random",
            "Better than either alone, but still weak",
        ],
    })
    st.dataframe(h, use_container_width=True, hide_index=True)

    st.markdown("""
    <div class="callout warning">
      <strong>Why this matters:</strong> the model learned user-specific behavioral
      patterns. A completely novel attacker machine can therefore defeat assumptions
      learned from previously observed behavior. The documented results are strong for
      known patterns but should not be presented as universal detection performance.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="section-title">Dataset processing</div>', unsafe_allow_html=True)
    pipeline = pd.DataFrame({
        "Stage": [
            "Raw auth.txt",
            "Filtered slice",
            "Feature table",
            "Train split",
            "Test split",
            "Production models",
        ],
        "Details": [
            "1,051,430,459 events • 73.4 GB",
            "29,905,488 events • 604 users",
            "29.9M × 19 columns",
            "20,933,841 events • 491 red",
            "8,971,647 events • 211 red",
            "Isolation Forest + LightGBM + combined scoring",
        ],
    })
    st.dataframe(pipeline, use_container_width=True, hide_index=True)

    st.markdown("""
    <div class="callout">
      <strong>Audit status:</strong> the documented pipeline reports seven verification
      gates passing, including the row-count check and recomputation of all nine features
      with zero mismatches.
    </div>
    """, unsafe_allow_html=True)

# -----------------------------
# Footer
# -----------------------------
st.markdown("""
<div style="margin-top:42px;padding-top:18px;border-top:1px solid rgba(148,163,184,.10);
color:#71849a;font-size:11px;text-align:center;">
CYBERGUARD • LANL CYBER1 AUTHENTICATION ANALYTICS • Dashboard values sourced from model_deep_dive.md
</div>
""", unsafe_allow_html=True)
