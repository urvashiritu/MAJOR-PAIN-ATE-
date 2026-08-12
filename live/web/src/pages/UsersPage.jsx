import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Search, Shield, AlertTriangle, MoreHorizontal } from 'lucide-react'
import { getUsers } from '../hooks/useApi'

function riskColor(risk) {
  return risk >= 70 ? 'text-red-400' : risk >= 40 ? 'text-amber-400' : 'text-green-400'
}

export default function UsersPage() {
  const [users, setUsers] = useState([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    getUsers()
      .then(res => setUsers(res.personas || []))
      .catch(() => setUsers([]))
  }, [])

  const filtered = users.filter(u =>
    (u.name || '').toLowerCase().includes(query.toLowerCase()) ||
    u.persona.toLowerCase().includes(query.toLowerCase()) ||
    (u.country || '').toLowerCase().includes(query.toLowerCase())
  )

  const flagged = users.filter(u => u.flags > 0)

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-5 pt-3">
      <div className="max-w-[1440px] mx-auto">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-lg font-semibold text-white">Users</h1>
            <p className="text-sm text-white/50">{users.length} users monitored</p>
          </div>
          <div className="relative max-w-xs w-full">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
            <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search users..." className="glass-input w-full pl-9 pr-3 py-2 text-sm" />
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
          {[
            { label: 'Total Users', value: users.length, change: 'monitored personas', color: 'text-white' },
            { label: 'Flagged', value: flagged.length, change: 'with active flags', color: 'text-red-400' },
            { label: 'Attacker', value: users.filter(u => u.persona === 'attacker').length, change: 'known attacker', color: 'text-amber-400' },
            { label: 'Avg Max Rule', value: users.length ? Math.round(users.reduce((s, u) => s + (u.max_rule || 0), 0) / users.length) : 0, change: 'anomaly rule score', color: 'text-green-400' },
          ].map((stat, i) => (
            <motion.div key={stat.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="glass-card-sm p-4">
              <p className="text-xs text-white/40 mb-1">{stat.label}</p>
              <p className={`text-2xl font-semibold ${stat.color}`}>{stat.value}</p>
              <p className="text-[10px] text-white/30 mt-0.5">{stat.change}</p>
            </motion.div>
          ))}
        </div>

        <div className="glass-card-sm overflow-hidden">
          <table className="table-glass w-full">
            <thead>
              <tr>
                <th>User</th>
                <th>Persona</th>
                <th>Country</th>
                <th>IP</th>
                <th>Flags</th>
                <th>Max Rule</th>
                <th>Live Events</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u, i) => (
                <motion.tr key={u.user_id || u.name} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
                  <td>
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center text-[10px] font-semibold text-white">
                        {(u.name || u.persona).slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white/90">{u.name || u.persona}</p>
                        <p className="text-[10px] text-white/40">@{u.persona}</p>
                      </div>
                    </div>
                  </td>
                  <td className="text-sm text-white/60">{u.persona}</td>
                  <td className="text-sm text-white/60">{u.country}</td>
                  <td className="font-mono text-xs text-white/50">{u.ip}</td>
                  <td>
                    {u.flags > 0 ? (
                      <span className="badge badge-critical flex items-center gap-0.5"><AlertTriangle size={10} /> {u.flags}</span>
                    ) : (
                      <span className="text-white/30 text-xs">—</span>
                    )}
                  </td>
                  <td>
                    <span className={`font-bold text-sm ${riskColor(u.max_rule || 0)}`}>
                      {u.max_rule ?? '—'}
                    </span>
                  </td>
                  <td className="text-sm text-white/60">{u.live_events}</td>
                  <td><MoreHorizontal size={14} className="text-white/20 hover:text-white/50 cursor-pointer" /></td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </motion.div>
  )
}