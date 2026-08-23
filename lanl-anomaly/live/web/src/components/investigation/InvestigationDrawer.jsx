import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, AlertTriangle, Shield, User } from "lucide-react";
import { getInvestigation, ackAlert } from "../../hooks/useApi";
import SeverityBadge from "../common/SeverityBadge";

export default function InvestigationDrawer({ eventId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!eventId) return;
    setLoading(true);
    getInvestigation(eventId)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [eventId]);

  if (!eventId) return null;

  const features = data?.featureContributions || [];
  const timeline = data?.timeline || [];
  const baseline = data?.baseline || {};

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex justify-end"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      >
        {/* Backdrop */}
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

        {/* Drawer */}
        <motion.div
          className="relative w-full max-w-lg bg-paper-50 border-l border-[color:var(--hairline)] overflow-y-auto"
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 28, stiffness: 280 }}
        >
          {/* Header */}
          <div className="sticky top-0 z-10 bg-paper-50 border-b border-[color:var(--hairline)] p-4 flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <SeverityBadge level={data?.severity} />
                <span className="text-xs text-ink-dim">{data?.type}</span>
              </div>
              <h3 className="text-sm font-bold text-ink">
                {data?.displayName || "Unknown"}
              </h3>
              <p className="text-[11px] text-ink-faint mt-0.5">{data?.rawId}</p>
            </div>
            <button onClick={onClose} className="text-ink-faint hover:text-ink transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>

          {loading ? (
            <div className="p-8 text-center text-ink-faint text-xs">Loading...</div>
          ) : data ? (
            <div className="p-4 space-y-4">
              {/* Summary */}
              <div className="panel p-3">
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div>
                    <div className="kpi-label">Risk Score</div>
                    <div className="text-lg font-bold text-ink">{(data.combinedScore ?? 0).toFixed(3)}</div>
                  </div>
                  <div>
                    <div className="kpi-label">Anomaly (IF)</div>
                    <div className="text-lg font-bold text-info">{(data.ifScore ?? 0).toFixed(3)}</div>
                  </div>
                  <div>
                    <div className="kpi-label">Habit Breaks</div>
                    <div className={`text-lg font-bold ${(data.devPoints ?? 0) > 0 ? "text-critical" : "text-low"}`}>{data.devPoints ?? 0}</div>
                  </div>
                </div>
                {(data.devReasons ?? "").length > 0 && (
                  <div className="mt-2 text-[11px] text-ink-dim">{data.devReasons}</div>
                )}
              </div>

              {/* Event details */}
              <div className="panel p-3">
                <div className="text-xs uppercase tracking-wider text-ink-faint mb-2 font-semibold">Event</div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-ink-faint">Source:</span> <span className="text-ink">{data.src_computer}</span></div>
                  <div><span className="text-ink-faint">Dest:</span> <span className="text-ink">{data.dst_computer}</span></div>
                  <div><span className="text-ink-faint">Auth:</span> <span className="text-ink">{data.auth_type}</span></div>
                  <div><span className="text-ink-faint">Result:</span> <span className={data.result === "Success" ? "text-low" : "text-critical"}>{data.result}</span></div>
                </div>
                <div className="mt-2 text-[11px] text-ink-dim">{data.description}</div>
              </div>

              {/* Feature contributions */}
              {features.length > 0 && (
                <div className="panel p-3">
                  <div className="text-xs uppercase tracking-wider text-ink-faint mb-2 font-semibold">
                    Feature Signals
                  </div>
                  <div className="space-y-2">
                    {features.map((f, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <div className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ background: f.color }} />
                        <div>
                          <div className="text-xs text-ink font-semibold">{f.feature}</div>
                          <div className="text-[11px] text-ink-dim">{f.detail}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Model features */}
              {data.features && (
                <div className="panel p-3">
                  <div className="text-xs uppercase tracking-wider text-ink-faint mb-2 font-semibold">
                    Raw Features
                  </div>
                  <div className="grid grid-cols-2 gap-1.5">
                    {Object.entries(data.features).map(([k, v]) => (
                      <div key={k} className="flex justify-between text-[11px]">
                        <span className="text-ink-faint">{k}</span>
                        <span className="text-ink font-mono">{typeof v === "number" ? v.toFixed(4) : v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Baseline */}
              {baseline.totalEvents > 0 && (
                <div className="panel p-3">
                  <div className="text-xs uppercase tracking-wider text-ink-faint mb-2 font-semibold">
                    User Baseline
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div><span className="text-ink-faint">Total events:</span> <span className="text-ink">{baseline.totalEvents}</span></div>
                    <div><span className="text-ink-faint">Failure rate:</span> <span className="text-ink">{(baseline.failureRate * 100).toFixed(1)}%</span></div>
                    <div><span className="text-ink-faint">Avg events/hr:</span> <span className="text-ink">{baseline.avgEventsPerHour}</span></div>
                    <div><span className="text-ink-faint">Typical src:</span> <span className="text-ink">{baseline.typicalSrcComputers?.join(", ")}</span></div>
                  </div>
                </div>
              )}

              {/* Timeline */}
              {timeline.length > 0 && (
                <div className="panel p-3">
                  <div className="text-xs uppercase tracking-wider text-ink-faint mb-2 font-semibold">
                    Recent Events
                  </div>
                  <div className="space-y-1.5">
                    {timeline.map((t, i) => (
                      <div key={i} className="flex items-center gap-2 text-[11px]">
                        <div className={`w-1.5 h-1.5 rounded-full ${
                          t.severity === "critical" ? "bg-critical" :
                          t.severity === "high" ? "bg-high" : "bg-ink-faint"
                        }`} />
                        <span className="text-ink-faint w-14">{t.time}</span>
                        <span className="text-ink flex-1">{t.event}</span>
                        <span className="text-ink-dim">{(t.score ?? 0).toFixed(3)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2">
                <button
                  onClick={() => ackAlert(eventId)}
                  className="flex-1 px-3 py-2 text-xs bg-low/20 text-low rounded hover:bg-low/30 transition-colors"
                >
                  Acknowledge
                </button>
                <button
                  onClick={onClose}
                  className="flex-1 px-3 py-2 text-xs bg-[color:var(--wash)] text-ink-faint rounded hover:bg-[color:var(--wash-strong)] transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          ) : (
            <div className="p-8 text-center text-ink-faint text-xs">Not found</div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
