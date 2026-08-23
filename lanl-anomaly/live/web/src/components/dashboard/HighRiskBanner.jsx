import { motion } from "framer-motion";
import { AlertTriangle, ArrowRight } from "lucide-react";
import StatusIndicator from "../common/StatusIndicator";
import OdometerNumber from "../common/OdometerNumber";

export default function HighRiskBanner({ alert, onInvestigate }) {
  if (!alert) return null;

  const isCritical = alert.severity === "critical";
  const label = isCritical ? "VERDICT: CRITICAL" : "VERDICT: HIGH";

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
      className="panel p-3 mb-4"
      style={{ borderLeft: `3px solid ${isCritical ? "#e5484d" : "#ff9b9e"}` }}
    >
      <div className="flex items-center gap-4">
        <div
          className="p-2 flex-shrink-0 border"
          style={{ borderColor: isCritical ? "rgba(229,72,77,0.6)" : "rgba(255,155,158,0.5)" }}
        >
          <AlertTriangle size={18} style={{ color: isCritical ? "#e5484d" : "#ff9b9e" }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`stamp ${isCritical ? "stamp-critical" : "stamp-high"} badge-pulse`}
            >
              <StatusIndicator state="down" size="sm" className="gap-1" />
              {label}
            </span>
            <span className="text-sm font-semibold text-ink/90 tracking-wide">
              Live Attack Activity
            </span>
          </div>
          <p className="text-sm text-ink-dim truncate font-mono">
            <span className="font-bold" style={{ color: isCritical ? "#e5484d" : "#ff9b9e" }}>
              {alert.name || alert.raw_id || `User ${alert.user_id}`}
            </span>
            <span className="text-ink-faint"> :: </span>
            {alert.reasons || "flagged for investigation"}
          </p>
        </div>
        <div className="text-right flex-shrink-0 hidden sm:block">
          <p className="text-[10px] tracking-[0.2em] text-ink-faint uppercase mb-1">risk://</p>
          <motion.span
            className={`tape-num ${isCritical ? "text-critical" : ""}`}
            style={{ color: isCritical ? "#e5484d" : "#ff9b9e", fontSize: "1.4rem" }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
          >
            <OdometerNumber value={Math.round((alert.combined_score ?? 0) * 100)} />
          </motion.span>
        </div>
        <button
          onClick={() => onInvestigate?.(alert.eventId)}
          className="flex items-center gap-1.5 px-4 py-2 border text-sm font-semibold hover:bg-white/5 transition-all flex-shrink-0"
          style={{
            borderColor: isCritical ? "rgba(229,72,77,0.6)" : "rgba(255,155,158,0.5)",
            color: isCritical ? "#e5484d" : "#ff9b9e",
          }}
        >
          Investigate
          <ArrowRight size={14} />
        </button>
      </div>
    </motion.div>
  );
}
