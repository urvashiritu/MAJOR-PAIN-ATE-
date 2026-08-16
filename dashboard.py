import json
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="UEBA Security Analytics", page_icon="🛡️", layout="wide")
st.markdown("""<style>
div[data-testid='stMetric'] {background:#172033; padding:16px; border-radius:10px;}
</style>""", unsafe_allow_html=True)
path = Path("rba_dataset/models/ueba_model_results.json")
if not path.exists():
    st.error("No current results. Run `python scripts/train_ueba_models.py` first.")
    st.stop()

data = json.loads(path.read_text())
summary = data["dataset_summary"]
results = pd.DataFrame(data["results"])
st.title("🛡️ Identity Anomaly Detection Dashboard")
st.caption("Real-time UEBA model evaluation • full dataset overview • chronological holdout")

cols = st.columns(4)
cols[0].metric("Cleaned login events", f"{int(summary['total_events']):,}")
cols[1].metric("User identities", f"{int(summary['unique_users']):,}")
cols[2].metric("Known attack-IP events", f"{int(summary['attack_ip_events']):,}")
cols[3].metric("Known ATO events", f"{int(summary['ato_events']):,}")
st.caption(f"Dataset period: {summary['first_event']} to {summary['last_event']}")

st.success(f"Current best model: {data['best_model']} — selected using {data['selection_metric']}, which is suitable for rare attack events.")
st.info(data["method_note"])

st.header("Model performance")
st.dataframe(results[["model", "fit_rows", "test_rows", "attack_ip_roc_auc", "attack_ip_avg_precision", "precision_at_1pct_alerts", "alert_rate"]], hide_index=True, use_container_width=True)
left, right = st.columns(2)
with left:
    st.subheader("Detection quality")
    st.bar_chart(results.set_index("model")[["attack_ip_avg_precision", "attack_ip_roc_auc"]])
with right:
    st.subheader("Precision when alerting")
    st.bar_chart(results.set_index("model")[["precision_at_1pct_alerts"]])

st.header("Which model should you use?")
for result in data["results"]:
    label = result["model"] + (" — recommended" if result["model"] == data["best_model"] else "")
    with st.expander(label, expanded=result["model"] == data["best_model"]):
        st.write(result["why"])
        st.write(f"ROC-AUC: **{result['attack_ip_roc_auc']:.4f}** | Average Precision: **{result['attack_ip_avg_precision']:.4f}** | Precision at top 1% alerts: **{result['precision_at_1pct_alerts']:.4f}**")
        st.caption("Average precision matters most here because known attacks are uncommon. Do not interpret it as accuracy.")

st.header("Why did the system flag events?")
st.caption(data["explanation_method"])
impact = pd.Series(data["feature_impact"]).sort_values(ascending=False).head(12)
st.bar_chart(impact)

st.header("Highest-risk evaluation events")
alert_file = Path("rba_dataset/models/top_anomalous_events.csv")
if alert_file.exists():
    alerts = pd.read_csv(alert_file)
    st.dataframe(alerts, hide_index=True, use_container_width=True)

with st.expander("What is an event and what does the model predict?"):
    st.write("An event is one authentication/login attempt. The model outputs an anomaly score and risk level—not a guaranteed account-takeover verdict. It scores behaviour such as device and country changes, unusual timing, rapid sessions, and failed-then-success patterns.")
    st.write("`user_id` and timestamp are retained for user baselines and time splitting, but are never model inputs. Attack-IP and ATO flags are used only after scoring to evaluate the alerts.")
    st.code("\n".join(data["features"]))
