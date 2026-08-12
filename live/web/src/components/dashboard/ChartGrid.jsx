import { motion } from 'framer-motion'
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import GlassCard from '../GlassCard'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload) return null
  return (
    <div className="chart-tooltip">
      <p className="text-xs text-white/50 mb-1">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} className="text-sm font-medium" style={{ color: entry.color }}>
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  )
}

function AnomalyTrendChart({ data }) {
  if (!data || data.length === 0) return <GlassCard className="p-5 lg:col-span-2"><p className="text-white/40 text-sm">No anomaly data</p></GlassCard>
  return (
    <GlassCard className="p-5 lg:col-span-2">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-white/80">Anomalies Over Time</h3>
        <div className="flex items-center gap-3 text-xs text-white/40">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-info" /> Detected</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-ochre" /> False Positives</span>
        </div>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#6ea8e8" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#6ea8e8" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="fg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#e8a33d" stopOpacity={0.15} />
                <stop offset="100%" stopColor="#e8a33d" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
            <XAxis dataKey="date" stroke="rgba(255,255,255,0.15)" tick={{ fontSize: 12 }} />
            <YAxis stroke="rgba(255,255,255,0.15)" tick={{ fontSize: 12 }} />
            <Tooltip content={<CustomTooltip />} />
            <Area type="monotone" dataKey="anomalies" name="Detected" stroke="#6ea8e8" strokeWidth={2} fill="url(#ag)" strokeLinecap="round" animationDuration={800} />
            <Area type="monotone" dataKey="falsePositives" name="False Positives" stroke="#e8a33d" strokeWidth={2} fill="url(#fg)" strokeLinecap="round" animationDuration={1000} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </GlassCard>
  )
}

function RiskDistributionChart({ data }) {
  const COLORS = ['#e5484d', '#ff9b9e', '#e8a33d', '#57b06c']
  if (!data || data.length === 0) return <GlassCard className="p-5"><p className="text-white/40 text-sm">No risk data</p></GlassCard>
  return (
    <GlassCard className="p-5">
      <h3 className="text-sm font-semibold text-white/80 mb-4">Risk Distribution</h3>
      <div className="h-64 flex items-center">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="value" stroke="none">
              {data.map((e, i) => <Cell key={e.name} fill={COLORS[i] || COLORS[0]} />)}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="flex flex-col gap-2.5">
          {data.map((item, i) => (
            <div key={item.name} className="flex items-center gap-2.5 text-xs">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[i] || COLORS[0] }} />
              <span className="text-white/50">{item.name}</span>
              <span className="text-white/80 font-medium">{item.value}</span>
            </div>
          ))}
        </div>
      </div>
    </GlassCard>
  )
}

function UserActivityChart({ data }) {
  if (!data || data.length === 0) return <GlassCard className="p-5"><p className="text-white/40 text-sm">No activity data</p></GlassCard>
  return (
    <GlassCard className="p-5">
      <h3 className="text-sm font-semibold text-white/80 mb-4">Activity by Hour</h3>
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
            <XAxis dataKey="hour" stroke="rgba(255,255,255,0.15)" tick={{ fontSize: 10 }} interval={1} />
            <YAxis stroke="rgba(255,255,255,0.15)" tick={{ fontSize: 10 }} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="normal" name="Normal" fill="#232c40" radius={[3, 3, 0, 0]} animationDuration={600} />
            <Bar dataKey="anomalous" name="Anomalous" fill="#e5484d" radius={[3, 3, 0, 0]} animationDuration={800} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </GlassCard>
  )
}

function TopAnomalyReasons({ data }) {
  if (!data || data.length === 0) return <GlassCard className="p-5"><p className="text-white/40 text-sm">No reason data</p></GlassCard>
  return (
    <GlassCard className="p-5">
      <h3 className="text-sm font-semibold text-white/80 mb-4">Top Anomaly Reasons</h3>
      <div className="space-y-2.5">
        {data.slice(0, 6).map((item) => (
          <div key={item.reason}>
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-sm text-white/70">{item.reason}</span>
              <span className="text-xs text-white/40">{item.count}</span>
            </div>
            <div className="h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
              <motion.div
                className="h-full bg-ochre"
                initial={{ width: 0 }}
                animate={{ width: `${item.percentage}%` }}
                transition={{ duration: 0.8, ease: [0.4, 0, 0.2, 1] }}
              />
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  )
}

function ActiveInvestigations({ alerts, onInvestigate }) {
  const items = (alerts || []).filter(a => a.status !== 'dismissed').slice(0, 3)
  return (
    <GlassCard className="p-5">
      <h3 className="text-sm font-semibold text-white/80 mb-3">Active Alerts</h3>
      <div className="space-y-2">
        {items.length === 0 && (
          <p className="text-sm text-white/40 py-4 text-center">No active alerts</p>
        )}
        {items.map((inv) => (
          <div key={inv.id} onClick={() => onInvestigate?.(inv)} className="flex items-center gap-3 p-2.5 rounded-sm hover:bg-white/[0.03] transition-colors cursor-pointer">
            <div className={`w-2 h-2 rounded-full flex-shrink-0 ${inv.severity === 'critical' ? 'bg-critical' : inv.severity === 'high' ? 'bg-ochre' : 'bg-info'}`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-white/80 truncate">{inv.displayName}</span>
                <span className="text-xs text-white/40">{inv.type}</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-white/40 mt-0.5">
                <span>{formatTime(inv.timestamp)}</span>
                <span>·</span>
                <span>{inv.status}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
      {items.length > 0 && (
        <button onClick={() => onInvestigate?.(items[0])} className="w-full mt-3 text-xs text-info hover:text-info transition-colors text-center">
          Open Investigation →
        </button>
      )}
    </GlassCard>
  )
}

function formatTime(ts) {
  const d = new Date(ts)
  const now = new Date()
  const diff = Math.floor((now - d) / 60000)
  if (diff < 60) return `${diff}m ago`
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
  return d.toLocaleDateString()
}

export default function ChartGrid({ anomalyTrend, riskDistribution, userActivity, topReasons, alerts, onInvestigate }) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <AnomalyTrendChart data={anomalyTrend} />
        <RiskDistributionChart data={riskDistribution} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <UserActivityChart data={userActivity} />
        <TopAnomalyReasons data={topReasons} />
        <ActiveInvestigations alerts={alerts} onInvestigate={onInvestigate} />
      </div>
    </div>
  )
}
