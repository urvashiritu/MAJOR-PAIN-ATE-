import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Filter, Clock, CheckCircle } from 'lucide-react'
import GlassCard from '../components/glass/GlassCard'
import SeverityBadge from '../components/common/SeverityBadge'
import { getAlerts, acknowledgeAlert } from '../hooks/useApi'

const filters = ['All', 'Critical', 'High', 'Medium', 'Low', 'Acknowledged']

function formatTime(ts) {
  const d = new Date(ts)
  const now = new Date()
  const diff = Math.floor((now - d) / 60000)
  if (diff < 60) return `${diff}m ago`
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
  return d.toLocaleDateString()
}

export default function AlertsPage() {
  const [activeFilter, setActiveFilter] = useState('All')
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)

  async function loadAlerts() {
    try {
      setAlerts(await getAlerts())
    } catch { /* keep last list */ }
    setLoading(false)
  }

  useEffect(() => { loadAlerts() }, [])

  const filtered = activeFilter === 'All'
    ? alerts
    : activeFilter === 'Acknowledged'
    ? alerts.filter(a => a.status === 'acknowledged')
    : alerts.filter(a => a.severity === activeFilter.toLowerCase())

  const handleAck = async (alert) => {
    await acknowledgeAlert(alert.id)
    loadAlerts()
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="p-5 pt-3"
    >
      <div className="max-w-[1440px] mx-auto">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-lg font-semibold text-white">Alerts</h1>
            <p className="text-sm text-white/50">{filtered.length} alerts ({alerts.filter(a => a.status === 'new').length} new)</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-white/40 flex items-center gap-1"><Clock size={12} /> Last 24 hours</span>
            <button className="glass-input flex items-center gap-1.5 px-3 py-1.5 text-xs text-white/60">
              <Filter size={12} /> Filter
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2 mb-5">
          {filters.map(f => (
            <button
              key={f}
              onClick={() => setActiveFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeFilter === f ? 'bg-white/10 text-white' : 'text-white/50 hover:text-white/70 hover:bg-white/5'
              }`}
            >
              {f}
            </button>
          ))}
        </div>

        <GlassCard className="overflow-hidden">
          <table className="table-glass w-full">
            <thead>
              <tr>
                <th>Severity</th>
                <th>User</th>
                <th>Type</th>
                <th className="hidden md:table-cell">Description</th>
                <th>Risk</th>
                <th>Time</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-center text-sm text-white/40 py-8">No alerts</td>
                </tr>
              )}
              {filtered.map((alert, i) => (
                <motion.tr
                  key={alert.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                >
                  <td><SeverityBadge severity={alert.severity} pulse={alert.status === 'new'} /></td>
                  <td className="font-medium text-white/90">{alert.displayName}</td>
                  <td><span className="text-white/70">{alert.type}</span></td>
                  <td className="hidden md:table-cell text-white/50 max-w-[200px] truncate">{alert.description}</td>
                  <td>
                    <span className={`font-bold text-sm ${alert.riskScore >= 70 ? 'text-red-400' : alert.riskScore >= 40 ? 'text-amber-400' : 'text-green-400'}`}>
                      {alert.riskScore}
                    </span>
                  </td>
                  <td className="text-xs text-white/40">{formatTime(alert.timestamp)}</td>
                  <td>
                    {alert.status === 'new' ? (
                      <span className="badge badge-new">New</span>
                    ) : alert.status === 'acknowledged' ? (
                      <span className="badge badge-info">Acked</span>
                    ) : (
                      <span className="badge badge-low">Dismissed</span>
                    )}
                  </td>
                  <td>
                    {alert.status === 'new' && (
                      <button
                        onClick={() => handleAck(alert)}
                        className="flex items-center gap-1 px-2 py-1 rounded-lg bg-blue-500/10 text-blue-400 text-xs hover:bg-blue-500/20 transition-all"
                      >
                        <CheckCircle size={11} /> Ack
                      </button>
                    )}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </GlassCard>
      </div>
    </motion.div>
  )
}
