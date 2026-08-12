import { motion } from 'framer-motion'

export default function GlassCard({ children, className = '', hover = true, onClick, ...props }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
      onClick={onClick}
      className={`panel ${hover ? 'panel-hover' : ''} ${onClick ? 'cursor-pointer' : ''} ${className}`}
      {...props}
    >
      {children}
    </motion.div>
  )
}

export function GlassCardSm({ children, className = '', hover = true, onClick }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      onClick={onClick}
      className={`panel ${hover ? 'panel-hover' : ''} ${onClick ? 'cursor-pointer' : ''} ${className}`}
    >
      {children}
    </motion.div>
  )
}

export function GlassDivider({ className = '' }) {
  return <div className={`glass-divider my-4 ${className}`} />
}