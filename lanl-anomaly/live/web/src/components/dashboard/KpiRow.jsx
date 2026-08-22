import GlassCard from "../common/GlassCard";

const KPIS = [
  { key: "totalEvents", label: "Events Scored", color: "#6ea8e8" },
  { key: "anomalies", label: "Anomalies", color: "#e5484d" },
  { key: "highRiskUsers", label: "High-Risk Users", color: "#ff9b9e" },
  { key: "usersMonitored", label: "Users Monitored", color: "#57b06c" },
];

export default function KpiRow({ kpis }) {
  if (!kpis) return null;
  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
      {KPIS.map(({ key, label, color }) => (
        <GlassCard key={key} className="p-4">
          <div className="kpi-label mb-1">{label}</div>
          <div className="kpi-number" style={{ color }}>
            {kpis[key] ?? 0}
          </div>
        </GlassCard>
      ))}
    </div>
  );
}
