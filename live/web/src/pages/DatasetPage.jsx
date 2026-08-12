import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Search, Database, ChevronLeft, ChevronRight } from 'lucide-react'
import GlassCard from '../components/glass/GlassCard'
import SeverityBadge from '../components/common/SeverityBadge'
import { getDatasetSummary, getDatasetRows } from '../hooks/useApi'

const PER_PAGE = 25

function fmtScore(v) {
  if (v === null || v === undefined) return '—'
  return (v > 0 && v < 1 ? v.toExponential(2) : v.toFixed(2))
}

export default function DatasetPage() {
  const [summary, setSummary] = useState(null)
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDatasetSummary().then(setSummary).catch(() => {})
  }, [])

  useEffect(() => {
    let mounted = true
    setLoading(true)
    getDatasetRows({ page, perPage: PER_PAGE, search: query || undefined })
      .then(res => {
        if (!mounted) return
        setRows(res.rows)
        setTotal(res.total)
      })
      .catch(() => { if (mounted) setRows([]) })
      .finally(() => { if (mounted) setLoading(false) })
    return () => { mounted = false }
  }, [page, query])

  const totalPages = Math.max(1, Math.ceil(total / PER_PAGE))

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-5 pt-3">
      <div className="max-w-[1440px] mx-auto">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-lg font-semibold text-white flex items-center gap-2">
              <Database size={18} className="text-blue-400" /> Dataset
            </h1>
            <p className="text-sm text-white/50">Login events flagged by the anomaly engine — {summary ? summary.total.toLocaleString() : '…'} rows, {summary ? summary.flagged.toLocaleString() : '…'} flagged</p>
          </div>
          <div className="relative max-w-xs w-full">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
            <input
              value={query}
              onChange={e => { setQuery(e.target.value); setPage(1) }}
              placeholder="Search (user id, ip, country...)"
              className="glass-input w-full pl-9 pr-3 py-2 text-sm"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
          {[
            { label: 'Total Events', value: summary?.total ? summary.total.toLocaleString() : '…' },
            { label: 'Flagged', value: summary?.flagged ? summary.flagged.toLocaleString() : '…' },
            { label: 'Attack Share', value: summary ? `${summary.attackShare}%` : '…' },
            { label: 'Risk Critical', value: summary?.riskDist?.critical ? summary.riskDist.critical.toLocaleString() : '…' },
          ].map((stat, i) => (
            <motion.div key={stat.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="glass-card-sm p-4">
              <p className="text-xs text-white/40 mb-1">{stat.label}</p>
              <p className="text-2xl font-semibold text-white">{stat.value}</p>
            </motion.div>
          ))}
        </div>

        <GlassCard className="overflow-hidden">
          <table className="table-glass w-full">
            <thead>
              <tr>
                <th>Time</th>
                <th>User</th>
                <th>Country</th>
                <th className="hidden md:table-cell">Device</th>
                <th className="hidden md:table-cell">OS</th>
                <th>Success</th>
                <th>Rule</th>
                <th>ML</th>
                <th>Risk</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr><td colSpan={9} className="text-center text-sm text-white/40 py-8">Loading…</td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={9} className="text-center text-sm text-white/40 py-8">No rows match</td></tr>
              )}
              {rows.map(row => (
                <motion.tr key={row.row_id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
                  <td className="text-xs text-white/50 font-mono">{row.ts.replace('T', ' ').slice(0, 19)}</td>
                  <td className="font-mono text-xs text-white/70">{row.user_id}</td>
                  <td className="text-xs">{row.country}</td>
                  <td className="hidden md:table-cell text-xs text-white/50">{row.device_type}</td>
                  <td className="hidden md:table-cell text-xs text-white/50">{row.os_family}</td>
                  <td className="text-xs">{row.login_success
                    ? <span className="text-green-400">yes</span>
                    : <span className="text-red-400">no</span>}</td>
                  <td className="font-mono text-xs">{row.rule_score}</td>
                  <td className="font-mono text-xs">{fmtScore(row.ml_score)}</td>
                  <td><SeverityBadge severity={row.risk_level} /></td>
                </motion.tr>
              ))}
            </tbody>
          </table>

          <div className="flex items-center justify-between mt-3 pt-3 border-t border-white/[0.04] px-4 pb-3">
            <span className="text-xs text-white/35">{total.toLocaleString()} total</span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-2.5 py-1 text-xs rounded-lg bg-white/5 text-white/45 hover:bg-white/10 disabled:opacity-30 transition-all"
              >
                <ChevronLeft size={12} /> Prev
              </button>
              <span className="text-xs text-white/50 px-2">Page {page} / {totalPages}</span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-2.5 py-1 text-xs rounded-lg bg-white/5 text-white/45 hover:bg-white/10 disabled:opacity-30 transition-all"
              >
                Next <ChevronRight size={12} />
              </button>
            </div>
          </div>
        </GlassCard>
      </div>
    </motion.div>
  )
}