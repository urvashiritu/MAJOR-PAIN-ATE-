import { motion, AnimatePresence } from 'framer-motion'
import { Clock, ExternalLink, CheckCircle, XCircle } from 'lucide-react'
import GlassCard from '../GlassCard'
import SeverityBadge from '../common/SeverityBadge'

function formatTime(ts) {
  const d = new Date(ts)
  const now = new Date()
  const diff = Math.floor((now - d) / 60000)
  if (diff < 60) return `${diff}m ago`
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
  return d.toLocaleDateString()
}

const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 }

export default function AlertFeed({ alerts, onAlertClick }) {
  const items = [...(alerts || [])]
    .sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity])

  const newCount = items.filter(a => a.status === 'new').length

  return (
    <GlassCard className="p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-white/80">Recent Alerts</h3>
          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-sm bg-critical/10 text-critical">
            {newCount} new
          </span>
        </div>
        <button className="text-xs text-info hover:text-info transition-colors">
          View All
        </button>
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-white/40 py-8 text-center">No alerts</p>
      ) : (
      <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
        <AnimatePresence>
          {items.map((alert, i) => (
            <motion.div
              key={alert.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.025, duration: 0.25 }}
              onClick={() => onAlertClick?.(alert)}
              className="group flex items-start gap-3 p-3 rounded-sm hover:bg-white/[0.03] cursor-pointer transition-all"
            >
              <div className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${
                alert.severity === 'critical' ? 'bg-critical' :
                alert.severity === 'high' ? 'bg-critical' :
                alert.severity === 'medium' ? 'bg-ochre' : 'bg-low'
              }`} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <SeverityBadge severity={alert.severity} pulse={alert.status === 'new'} />
                  <span className="text-sm font-semibold text-white/90 truncate">{alert.displayName || alert.display_name}</span>
                  <span className="text-xs text-white/40">{alert.type}</span>
                </div>
                <p className="text-xs text-white/50 leading-relaxed truncate">{alert.description}</p>
                <div className="flex items-center gap-3 mt-1.5">
                  <span className="text-[11px] text-white/35 flex items-center gap-1">
                    <Clock size={10} />
                    {formatTime(alert.timestamp)}
                  </span>
                  <span className="text-[11px] font-mono text-white/25">{alert.mitreId || alert.mitre_id}</span>
                  {alert.status === 'acknowledged' && (
                    <span className="text-[10px] flex items-center gap-0.5 text-info">
                      <CheckCircle size={10} /> Acked
                    </span>
                  )}
                  {alert.status === 'dismissed' && (
                    <span className="text-[10px] flex items-center gap-0.5 text-white/30">
                      <XCircle size={10} /> Dismissed
                    </span>
                  )}
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <span className={`text-sm font-bold ${
                  (alert.riskScore || alert.risk_score) >= 70 ? 'text-critical' :
                  (alert.riskScore || alert.risk_score) >= 40 ? 'text-ochre' : 'text-low'
                }`}>
                  {alert.riskScore || alert.risk_score}
                </span>
                <div className="text-[10px] text-white/25 font-medium">RISK</div>
              </div>
              <ExternalLink size={13} className="text-white/15 group-hover:text-white/40 mt-0.5 transition-colors flex-shrink-0" />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
      )}
    </GlassCard>
  )
}
