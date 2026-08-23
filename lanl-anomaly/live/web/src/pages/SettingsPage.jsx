import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Settings, Shield, AlertTriangle } from "lucide-react";
import { getStats, resetDashboard } from "../hooks/useApi";
import HoldButton from "../components/common/HoldButton";

export default function SettingsPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [resetMsg, setResetMsg] = useState(null);

  function fetchStats() {
    getStats()
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => { fetchStats(); }, []);

  async function handleReset() {
    try {
      await resetDashboard();
      setResetMsg("Live data cleared.");
      fetchStats();
      setTimeout(() => setResetMsg(null), 3000);
    } catch {
      setResetMsg("Reset failed.");
      setTimeout(() => setResetMsg(null), 3000);
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.2 }}
      className="space-y-4"
    >
      <div className="flex items-center gap-2 mb-2">
        <Settings className="w-5 h-5 text-ochre" />
        <h1 className="text-lg font-bold text-ink">Settings</h1>
      </div>

      {/* System Status */}
      <div className="panel p-4">
        <h2 className="text-xs uppercase tracking-wider text-ink-faint font-semibold mb-3">System Status</h2>
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-ink-faint">
            <div className="live-dot" /> Loading...
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { label: "Live Events", value: stats?.live_events ?? 0, color: "text-ochre" },
              { label: "Alerts", value: stats?.alerts ?? 0, color: "text-[color:var(--critical)]" },
              { label: "History Events", value: stats?.history_events ?? 0, color: "text-[color:var(--low)]" },
              { label: "Users", value: stats?.users ?? 0, color: "text-ink" },
            ].map((s) => (
              <div key={s.label} className="panel-inset p-3 rounded-lg">
                <div className={`text-xl font-bold font-mono ${s.color}`}>{s.value.toLocaleString()}</div>
                <div className="text-[11px] text-ink-faint mt-1 uppercase tracking-wide">{s.label}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Danger Zone */}
      <div className="panel p-4 border-[color:var(--critical)]/20">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-4 h-4 text-[color:var(--critical)]" />
          <h2 className="text-xs uppercase tracking-wider text-[color:var(--critical)] font-semibold">Danger Zone</h2>
        </div>
        <p className="text-sm text-ink-dim mb-4">
          Clears all scored live events and alerts from the dashboard.
          Seeded history events and user profiles are preserved — the demo can continue normally after reset.
        </p>
        <HoldButton holdDuration={3000} onHoldComplete={handleReset}>
          Hold to Reset Live Data
        </HoldButton>
        {resetMsg && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mt-3 text-sm text-[color:var(--low)]"
          >
            {resetMsg}
          </motion.div>
        )}
      </div>

      {/* Model Configuration */}
      <div className="panel p-4">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-4 h-4 text-ochre" />
          <h2 className="text-xs uppercase tracking-wider text-ink-faint font-semibold">Model Configuration</h2>
        </div>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between py-1.5 border-b border-[color:var(--hairline)]">
            <span className="text-ink-faint">IF Model</span>
            <span className="text-ink font-mono text-xs">lanl_if.joblib</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-[color:var(--hairline)]">
            <span className="text-ink-faint">LGB Model</span>
            <span className="text-ink font-mono text-xs">lanl_lgb.joblib (display only)</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-[color:var(--hairline)]">
            <span className="text-ink-faint">Flag Threshold</span>
            <span className="text-ink font-mono text-xs">&ge; 0.65</span>
          </div>
          <div className="flex justify-between py-1.5 border-b border-[color:var(--hairline)]">
            <span className="text-ink-faint">Block Threshold</span>
            <span className="text-ink font-mono text-xs">&ge; 0.75</span>
          </div>
          <div className="flex justify-between py-1.5">
            <span className="text-ink-faint">Deviation Checks</span>
            <span className="text-ink font-mono text-xs">new_dst, new_src, velocity, auth_failures</span>
          </div>
        </div>
      </div>

      {/* Quick Commands */}
      <div className="panel p-4">
        <h2 className="text-xs uppercase tracking-wider text-ink-faint font-semibold mb-3">Quick Commands</h2>
        <div className="space-y-2 text-sm font-mono">
          <div className="panel-inset p-2.5 rounded-lg text-ink-dim">
            <span className="text-ochre">$</span> make demo-reset <span className="text-ink-faint"># full reset + re-seed</span>
          </div>
          <div className="panel-inset p-2.5 rounded-lg text-ink-dim">
            <span className="text-ochre">$</span> make demo <span className="text-ink-faint"># start server</span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
