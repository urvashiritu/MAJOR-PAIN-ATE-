import { motion } from 'framer-motion'
import { Activity, AlertTriangle, Users, Shield } from 'lucide-react'
import GlassCard from '../glass/GlassCard'
import Sparkline from '../common/Sparkline'
import useAnimatedCounter from '../../hooks/useAnimatedCounter'

function KPICardInner({ icon: Icon, label, value, change, delta, color, iconBg, iconColor, spark }) {
  const animatedValue = useAnimatedCounter(value)

  return (
    <GlassCard className="p-5">
      <div className="flex items-start justify-between mb-3">
        <div className={`p-2.5 rounded-xl ${iconBg}`}>
          <Icon size={18} className={iconColor} />
        </div>
        <div className="w-20 h-9">
          <Sparkline data={spark} color={color} height={36} />
        </div>
      </div>
      <p className="kpi-number text-white">
        {animatedValue}
      </p>
      <div className="flex items-center justify-between mt-0.5">
        <p className="kpi-label">{label}</p>
      </div>
      <div className="flex items-center gap-2 mt-0.5">
        {delta !== undefined && (
          <span className="text-[10px] font-medium text-white/30">
            <span className={delta >= 0 ? 'text-red-400/60' : 'text-green-400/60'}>
              {delta >= 0 ? '+' : ''}{delta}
            </span> since last check
          </span>
        )}
        {change !== undefined && (
          <span className={`kpi-change ${change >= 0 ? 'text-red-400' : 'text-green-400'}`}>
            {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
          </span>
        )}
      </div>
    </GlassCard>
  )
}

export default function KpiRow({ totalEvents, anomalies, highRiskUsers, usersMonitored, eventsChange, anomalyChange, spark }) {
  const kpis = [
    { icon: Activity,     label: 'Total Events',    value: totalEvents,  change: eventsChange,  delta: undefined, color: '#3b82f6', iconBg: 'bg-blue-500/10',    iconColor: 'text-blue-400' },
    { icon: AlertTriangle,label: 'Anomalies',        value: anomalies,   change: anomalyChange, delta: undefined, color: '#f59e0b', iconBg: 'bg-amber-500/10',  iconColor: 'text-amber-400' },
    { icon: Shield,       label: 'High Risk Users',  value: highRiskUsers,change: undefined,     delta: undefined, color: '#ef4444', iconBg: 'bg-red-500/10',     iconColor: 'text-red-400' },
    { icon: Users,        label: 'Users Monitored',  value: usersMonitored,change: undefined,   delta: undefined, color: '#22c55e', iconBg: 'bg-green-500/10',   iconColor: 'text-green-400' },
  ]

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
      {kpis.map((kpi, i) => (
        <motion.div
          key={kpi.label}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.08, duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
        >
          <KPICardInner {...kpi} spark={spark} />
        </motion.div>
      ))}
    </div>
  )
}
