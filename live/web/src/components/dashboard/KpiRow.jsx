import { motion } from 'framer-motion'
import { Activity, AlertTriangle, Users, Shield } from 'lucide-react'
import GlassCard from '../GlassCard'
import Sparkline from '../common/Sparkline'

function KPICardInner({ icon: Icon, label, value, change, color, iconColor, spark }) {
  return (
    <GlassCard className="p-4">
      <div className="flex items-start justify-between mb-3">
        <div className="p-2 border border-ink/15">
          <Icon size={15} className={iconColor} />
        </div>
        <span className="text-[10px] font-semibold tracking-widest text-ink/faint uppercase">{label}</span>
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="tape-perf pr-4 flex-1">
          <p className="tape-num">{value}</p>
          <div className="flex items-center gap-2 mt-1.5">
            {change !== undefined && (
              <span className={`kpi-change ${change >= 0 ? 'text-high' : 'text-low'}`}>
                {change >= 0 ? '↑' : '↓'} {Math.abs(change).toFixed(1)}%
              </span>
            )}
            <span className="text-[10px] text-ink/faint">24h</span>
          </div>
        </div>
        <div className="w-16 h-8">
          <Sparkline data={spark} color={color} height={32} />
        </div>
      </div>
    </GlassCard>
  )
}

export default function KpiRow({ totalEvents, anomalies, highRiskUsers, usersMonitored, eventsChange, anomalyChange, spark }) {
  const kpis = [
    { icon: Activity,     label: 'Total Events',    value: totalEvents,  change: eventsChange,  color: '#6ea8e8', iconColor: 'text-info' },
    { icon: AlertTriangle,label: 'Anomalies',        value: anomalies,   change: anomalyChange, color: '#e8a33d', iconColor: 'text-ochre' },
    { icon: Shield,       label: 'High Risk Users',  value: highRiskUsers,change: undefined,    color: '#e5484d', iconColor: 'text-critical' },
    { icon: Users,        label: 'Users Monitored',  value: usersMonitored,change: undefined,   color: '#57b06c', iconColor: 'text-low' },
  ]

  const fmt = new Intl.NumberFormat('en-US')

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
      {kpis.map((kpi, i) => (
        <motion.div
          key={kpi.label}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.07, duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
        >
          <KPICardInner {...kpi} value={fmt.format(kpi.value)} />
        </motion.div>
      ))}
    </div>
  )
}