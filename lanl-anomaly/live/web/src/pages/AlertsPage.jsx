import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { getAlerts, ackAlert } from "../hooks/useApi";
import { useDashboardData } from "../hooks/useDashboardData";
import SeverityBadge from "../components/common/SeverityBadge";
import ActivityHeatmap from "../components/charts/ActivityHeatmap";
import ThreatRings from "../components/charts/ThreatRings";
import TopOffenders from "../components/charts/TopOffenders";

export default function AlertsPage({ onInvestigate }) {
  const [alerts, setAlerts] = useState([]);
  const [filter, setFilter] = useState("all");
  const { data } = useDashboardData();
  const events = data?.recentEvents || [];
  const kpis = data?.kpis || {};

  useEffect(() => {
    getAlerts().then(setAlerts).catch(console.error);
    const iv = setInterval(() => getAlerts().then(setAlerts).catch(() => {}), 5000);
    return () => clearInterval(iv);
  }, []);

  const filtered = filter === "all" ? alerts : alerts.filter((a) => a.severity === filter);

  const handleAck = async (id) => {
    await ackAlert(id);
    setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, status: "acknowledged" } : a));
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
    >
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-sm font-bold text-ink uppercase tracking-wider">Alerts</h2>
        <div className="flex gap-1">
          {["all", "critical", "high", "medium", "low"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-0.5 text-[10px] uppercase tracking-wider rounded border transition-colors ${
                filter === f
                  ? "border-ochre text-ochre bg-ochre/10"
                  : "border-white/10 text-ink-faint hover:text-ink-dim"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 mb-4">
        <div className="xl:col-span-2 panel p-4">
          <ActivityHeatmap events={events} />
        </div>
        <div className="panel p-4 flex items-center justify-center">
          <ThreatRings kpis={kpis} />
        </div>
      </div>

      <div className="panel p-4 mb-4">
        <TopOffenders events={events} />
      </div>

      <div className="panel overflow-hidden">
        <table className="table-glass">
          <thead>
            <tr>
              <th>Severity</th>
              <th>User</th>
              <th>Score</th>
              <th>Decision</th>
              <th>Time</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((a) => (
              <tr key={a.id}>
                <td><SeverityBadge level={a.severity} /></td>
                <td className="text-ink">{a.name || a.raw_id}</td>
                <td className="text-ink font-bold">{(a.combined_score ?? 0).toFixed(3)}</td>
                <td className="text-ink-dim">{a.decision}</td>
                <td className="text-ink-faint">{a.timestamp}</td>
                <td>
                  <span className={`text-[10px] uppercase ${a.status === "acknowledged" ? "text-low" : "text-critical"}`}>
                    {a.status}
                  </span>
                </td>
                <td>
                  <div className="flex gap-1">
                    <button
                      onClick={() => onInvestigate(a.eventId)}
                      className="px-2 py-0.5 text-[10px] bg-ochre/20 text-ochre rounded hover:bg-ochre/30 transition-colors"
                    >
                      Investigate
                    </button>
                    {a.status !== "acknowledged" && (
                      <button
                        onClick={() => handleAck(a.id)}
                        className="px-2 py-0.5 text-[10px] bg-white/5 text-ink-faint rounded hover:bg-white/10 transition-colors"
                      >
                        Ack
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={7} className="text-center text-ink-faint py-8">No alerts</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
