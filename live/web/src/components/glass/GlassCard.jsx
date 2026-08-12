import { motion } from 'framer-motion'

export default function GlassCard({ children, className = '', hover = true, glow = false, onClick, ...props }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
      whileHover={hover ? { y: -2, transition: { duration: 0.2 } } : undefined}
      onClick={onClick}
      className={`glass-card ${glow ? 'glow-blue' : ''} ${onClick ? 'cursor-pointer' : ''} ${className}`}
      {...props}
    >
      {children}
    </motion.div>
  )
}

export function GlassCardSm({ children, className = '', hover = true, onClick }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
      whileHover={hover ? { y: -1, transition: { duration: 0.15 } } : undefined}
      onClick={onClick}
      className={`glass-card-sm ${onClick ? 'cursor-pointer' : ''} ${className}`}
    >
      {children}
    </motion.div>
  )
}

export function GlassDivider({ className = '' }) {
  return <div className={`glass-divider my-4 ${className}`} />
}
