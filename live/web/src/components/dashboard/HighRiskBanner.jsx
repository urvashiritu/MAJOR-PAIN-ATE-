import { motion } from 'framer-motion'
import { AlertTriangle, ArrowRight } from 'lucide-react'
import StatusIndicator from '../common/StatusIndicator'

export default function HighRiskBanner({ alert, onInvestigate }) {
  if (!alert) return null

  const label = alert.severity === 'critical' ? 'VERDICT: CRITICAL' : 'VERDICT: HIGH'

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
      className="panel p-4 mb-4 border-critical/60"
      style={{ borderLeft: '3px solid #e5484d' }}
    >
      <div className="flex items-center gap-4">
        <div className="p-2 border border-critical/60 flex-shrink-0">
          <AlertTriangle size={18} className="text-critical" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="stamp stamp-critical">
              <StatusIndicator state="down" size="sm" className="gap-1" />
              {label}
            </span>
            <span className="text-sm font-semibold text-ink/90 tracking-wide">{alert.type || 'Anomaly Detected'}</span>
          </div>
          <p className="text-sm text-ink/dim truncate font-mono">
            <span className="font-bold text-critical">{alert.displayName}</span>
            <span className="text-ink/faint"> :: </span>
            {alert.description || 'flagged for investigation'}
          </p>
        </div>
        <div className="text-right flex-shrink-0">
          <p className="text-[10px] tracking-[0.2em] text-ink/faint uppercase mb-1">risk://</p>
          <motion.span
            className="tape-num text-critical"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
          >
            {alert.riskScore}
          </motion.span>
        </div>
        <button
          onClick={() => onInvestigate?.(alert)}
          className="flex items-center gap-1.5 px-4 py-2 border border-critical/60 text-critical text-sm font-semibold hover:bg-critical/10 transition-all flex-shrink-0"
        >
          Investigate
          <ArrowRight size={14} />
        </button>
      </div>
    </motion.div>
  )
}