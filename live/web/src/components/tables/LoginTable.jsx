import { useState } from 'react'
import { motion } from 'framer-motion'
import { Search, ChevronDown } from 'lucide-react'
import GlassCard from '../glass/GlassCard'
import SeverityBadge from '../common/SeverityBadge'

const statusConfig = {
  blocked: { className: 'badge-critical', label: 'Blocked' },
  flagged: { className: 'badge-high', label: 'Flagged' },
  allowed: { className: 'badge-low', label: 'Allowed' },
}

export default function LoginTable({ logins, onRowClick }) {
  const items = logins || []
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState(null)
  const [sortDir, setSortDir] = useState('desc')

  const filtered = items.filter(
    (r) =>
      String(r.user ?? '').toLowerCase().includes(search.toLowerCase()) ||
      String(r.displayName ?? '').toLowerCase().includes(search.toLowerCase()) ||
      String(r.ip ?? '').includes(search)
  )

  const sorted = [...filtered].sort((a, b) => {
    if (!sortField) return 0
    const va = a[sortField], vb = b[sortField]
    if (typeof va === 'number') return sortDir === 'asc' ? va - vb : vb - va
    return sortDir === 'asc' ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va))
  })

  const toggleSort = (f) => {
    if (sortField === f) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(f); setSortDir('desc') }
  }

  const SortIcon = ({ field }) =>
    sortField === field ? (
      <ChevronDown size={11} className={`inline ml-0.5 transition-transform ${sortDir === 'asc' ? 'rotate-180' : ''}`} />
    ) : null

  return (
    <GlassCard className="p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-white/80">Recent Logins</h3>
        <div className="relative w-48">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-white/25" />
          <input
            type="text"
            placeholder="Search..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="glass-input w-full pl-8 pr-2.5 py-1 text-xs"
          />
        </div>
      </div>
      <div className="overflow-x-auto" style={{ maxHeight: '260px', overflowY: 'auto' }}>
        <table className="table-glass w-full">
          <thead className="sticky top-0 z-10" style={{ background: '#060f2d' }}>
            <tr>
              <th className="cursor-pointer hover:text-white/60" onClick={() => toggleSort('user')}>User <SortIcon field="user" /></th>
              <th className="cursor-pointer hover:text-white/60" onClick={() => toggleSort('ip')}>IP <SortIcon field="ip" /></th>
              <th>Country</th>
              <th>Device</th>
              <th>OS</th>
              <th className="cursor-pointer hover:text-white/60" onClick={() => toggleSort('riskScore')}>Risk <SortIcon field="riskScore" /></th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center text-sm text-white/40 py-8">No recent logins</td>
              </tr>
            )}
            {sorted.slice(0, 6).map((row, i) => (
              <motion.tr
                key={row.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.02 }}
                onClick={() => onRowClick?.(row)}
                className="cursor-pointer"
              >
                <td>
                  <span className="text-sm font-medium text-white/80">{row.displayName}</span>
                  <span className="text-xs text-white/35 ml-1.5">@{row.user}</span>
                </td>
                <td className="font-mono text-xs">{row.ip}</td>
                <td className="text-xs">{row.country}</td>
                <td className="text-xs text-white/50">{row.device || 'Unknown'}</td>
                <td className="text-xs text-white/50">{row.os || 'Unknown'}</td>
                <td>
                  <span className={`font-bold text-sm ${row.riskScore >= 70 ? 'text-red-400' : row.riskScore >= 40 ? 'text-amber-400' : 'text-green-400'}`}>
                    {row.riskScore}
                  </span>
                </td>
                <td>
                  <SeverityBadge
                    severity={row.status === 'blocked' ? 'critical' : row.status === 'flagged' ? 'high' : 'low'}
                    label={statusConfig[row.status]?.label || row.status}
                  />
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-white/[0.04]">
        <span className="text-xs text-white/35">{sorted.length} results</span>
        <div className="flex gap-1">
          <button className="px-2.5 py-1 text-xs rounded-lg bg-white/5 text-white/45 hover:bg-white/10 transition-all">Previous</button>
          <button className="px-2.5 py-1 text-xs rounded-lg bg-blue-500/15 text-blue-400">1</button>
          <button className="px-2.5 py-1 text-xs rounded-lg bg-white/5 text-white/45 hover:bg-white/10 transition-all">Next</button>
        </div>
      </div>
    </GlassCard>
  )
}
