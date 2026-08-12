import { motion } from 'framer-motion'
import { AlertTriangle, ArrowRight } from 'lucide-react'

export default function HighRiskBanner({ alert, onInvestigate }) {
  if (!alert) return null

  const label = alert.severity === 'critical' ? 'CRITICAL' : 'HIGH'

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
      className="glass-card-elevated p-4 mb-4 glow-red"
      style={{
        borderLeft: '3px solid #ef4444',
      }}
    >
      <div className="flex items-center gap-4">
        <div className="p-2.5 rounded-xl bg-red-500/10 flex-shrink-0">
          <AlertTriangle size={20} className="text-red-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="badge badge-critical">
              <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
              {label}
            </span>
            <span className="text-sm font-semibold text-white/90">{alert.type || 'Anomaly Detected'}</span>
          </div>
          <p className="text-sm text-white/60 truncate">
            <span className="font-medium text-red-400">{alert.displayName}</span> — {alert.description || 'flagged for investigation'}
          </p>
        </div>
        <div className="text-right flex-shrink-0">
          <motion.span
            className="text-2xl font-bold text-red-400"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', damping: 10, delay: 0.3 }}
          >
            {alert.riskScore}
          </motion.span>
          <div className="text-[10px] text-white/25 font-medium">RISK</div>
        </div>
        <button
          onClick={() => onInvestigate?.(alert)}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-red-500/15 text-red-400 text-sm font-medium hover:bg-red-500/25 transition-all flex-shrink-0"
        >
          Investigate
          <ArrowRight size={14} />
        </button>
      </div>
    </motion.div>
  )
}
