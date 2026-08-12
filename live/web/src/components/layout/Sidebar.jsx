import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard, AlertTriangle, Users, Database, Shield, ChevronLeft, ChevronRight,
} from 'lucide-react'
import { getDatasetSummary } from '../../hooks/useApi'

const navItems = [
  { icon: LayoutDashboard, label: 'Dashboard', id: 'dashboard' },
  { icon: AlertTriangle, label: 'Alerts', id: 'alerts' },
  { icon: Users, label: 'Users', id: 'users' },
  { icon: Database, label: 'Dataset', id: 'dataset' },
]

const bottomItems = []

export default function Sidebar({ collapsed, setCollapsed, activePage, setActivePage, newAlerts }) {
  const [summary, setSummary] = useState(null)

  useEffect(() => {
    let mounted = true
    getDatasetSummary()
      .then(s => { if (mounted) setSummary(s) })
      .catch(() => {})
    return () => { mounted = false }
  }, [])
  return (
    <motion.aside
      initial={{ width: collapsed ? 72 : 256 }}
      animate={{ width: collapsed ? 72 : 256 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
      className="h-screen flex flex-col py-4 px-3 sidebar fixed left-0 top-0 z-50 overflow-hidden"
    >
      <div className="flex items-center justify-between px-2 mb-6 mt-1">
        <AnimatePresence>
          {!collapsed && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-2"
            >
              <div className="w-7 h-7 border border-ochre/60 flex items-center justify-center">
                <Shield size={13} className="text-ochre" />
              </div>
              <span className="font-semibold text-sm text-ink/90 tracking-wider">SENTINEL</span>
            </motion.div>
          )}
        </AnimatePresence>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-sm hover:bg-white/5 text-white/40 hover:text-white/70 transition-all"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>

      <nav className="flex-1 flex flex-col gap-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActivePage(item.id)}
            className={`sidebar-item ${activePage === item.id ? 'active' : ''}`}
            title={collapsed ? item.label : undefined}
          >
            <item.icon size={18} />
            <AnimatePresence>
              {!collapsed && (
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex-1 text-left"
                >
                  {item.label}
                </motion.span>
              )}
            </AnimatePresence>
            {!collapsed && (newAlerts > 0) && (
              <span className="text-[11px] font-semibold bg-critical/10 text-critical px-1.5 py-0.5 rounded-full">
                {newAlerts}
              </span>
            )}
          </button>
        ))}
      </nav>

      <div className="pt-4 border-t border-white/[0.06]">
        {bottomItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActivePage(item.id)}
            className={`sidebar-item ${activePage === item.id ? 'active' : ''}`}
            title={collapsed ? item.label : undefined}
          >
            <item.icon size={18} />
            {!collapsed && (
              <span>{item.label}</span>
            )}
          </button>
        ))}

        {!collapsed && (
          <div className="mt-4 px-3 py-3 rounded-sm bg-white/[0.03] space-y-2.5">
            <div className="flex items-center gap-2 mb-2.5">
              <div className="w-7 h-7 border border-ink/25 flex items-center justify-center text-[10px] font-semibold text-ink/70">
                OP
              </div>
              <div>
                <p className="text-sm font-medium text-ink/80">Operator</p>
                <p className="text-xs text-ink/faint">SOC · Analyst</p>
              </div>
            </div>
            <div className="text-[10px] font-semibold text-white/40 uppercase tracking-wider">Current Dataset</div>
            {[
              { name: 'Total Events', value: summary ? summary.total.toLocaleString() : '…' },
              { name: 'Flagged', value: summary ? summary.flagged.toLocaleString() : '…' },
              { name: 'Attack Share', value: summary ? `${summary.attackShare}%` : '…' },
              { name: 'ML Anomalies', value: summary ? summary.mlReady ? 'Ensemble live' : 'offline' : '…' },
            ].map((m, i) => (
              <motion.div
                key={m.name}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.3 + i * 0.05 }}
                className="flex items-center justify-between"
              >
                <div className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${summary ? 'bg-green-500' : 'bg-white/20'}`} />
                  <span className="text-[11px] text-white/60 truncate">{m.name}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span className="text-[10px] text-white/30 font-mono">{m.value}</span>
                </div>
              </motion.div>
            ))}
            <div className="pt-2 mt-1 border-t border-white/[0.06] space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-white/40">Avg ML Score</span>
                <span className="text-[10px] text-low font-mono">{summary ? summary.avgMl.toFixed(3) : '…'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-white/40">Rule Threshold</span>
                <span className="text-[10px] text-white/60 font-mono">{summary ? summary.avgRule : '…'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-white/40">ATO Score</span>
                <span className="text-[10px] text-low font-mono">{summary ? summary.ato : '…'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] text-white/40">Success Rate</span>
                <span className="text-[10px] text-white/60 font-mono">{summary ? `${((summary.success / summary.total) * 100).toFixed(1)}%` : '…'}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </motion.aside>
  )
}
