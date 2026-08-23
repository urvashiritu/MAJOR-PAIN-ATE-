import { AnimatePresence, motion } from "framer-motion";
import SeverityBadge from "../common/SeverityBadge";

export default function AlertFeed({ alerts = [], onInvestigate }) {
  return (
    <div className="panel p-4 h-full">
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs uppercase tracking-wider text-ink-faint font-semibold">
          Recent Alerts
        </div>
        <span className="text-[10px] uppercase tracking-widest text-ink-faint flex items-center gap-1.5">
          <span className="live-dot" /> live
        </span>
      </div>
      <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
        <AnimatePresence initial={false}>
          {alerts.length === 0 && (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="panel-inset text-ink-faint text-xs text-center py-10"
            >
              No alerts yet — feed will update live
            </motion.div>
          )}
          {alerts.map((a) => (
            <motion.button
              layout
              key={a.id}
              onClick={() => onInvestigate?.(a.eventId)}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 10 }}
              transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
              className="w-full text-left p-3 rounded-md bg-paper-100 hover:bg-paper-200 transition-colors"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="badge-transition inline-flex">
                  <SeverityBadge level={a.severity} />
                </span>
                <span className="text-[10px] text-ink-faint">{a.timestamp}</span>
              </div>
              <div className="text-xs text-ink font-mono">
                {a.name || a.raw_id || `User ${a.user_id}`}
              </div>
              <div className="flex items-center justify-between mt-1">
                <div className="text-[11px] text-ink-dim">
                  Score: {(a.combined_score ?? 0).toFixed(3)}
                </div>
                <div
                  className="h-1 w-16 rounded-full overflow-hidden bg-[color:var(--wash)]"
                  title={`score ${((a.combined_score ?? 0) * 100).toFixed(0)}%`}
                >
                  <div
                    className="h-full"
                    style={{
                      width: `${Math.min(100, (a.combined_score ?? 0) * 100)}%`,
                      background:
                        a.severity === "critical"
                          ? "#e5484d"
                          : a.severity === "high"
                            ? "#ff9b9e"
                            : "#e8a33d",
                    }}
                  />
                </div>
              </div>
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
