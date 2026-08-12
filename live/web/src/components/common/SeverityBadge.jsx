import { motion } from 'framer-motion'

const severityConfig = {
  critical: { className: 'severity-badge critical', label: 'Critical' },
  high: { className: 'severity-badge high', label: 'High' },
  medium: { className: 'severity-badge medium', label: 'Medium' },
  low: { className: 'severity-badge low', label: 'Low' },
  info: { className: 'severity-badge low', label: 'Info' },
}

export default function SeverityBadge({ severity = 'info', label, pulse = false }) {
  const config = severityConfig[severity] || severityConfig.info

  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`${config.className} badge-transition ${pulse ? 'badge-pulse' : ''}`}
    >
      {pulse && (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
      )}
      {label || config.label}
    </motion.span>
  )
}
