import { useState } from 'react'
import { motion } from 'framer-motion'
import { Search, Bell, RefreshCw, ChevronDown } from 'lucide-react'

const timeRanges = ['Last 24 Hours', 'Last 7 Days', 'Last 30 Days', 'Custom']

export default function TopNavbar() {
  const [searchFocused, setSearchFocused] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedRange, setSelectedRange] = useState('Last 24 Hours')
  const [showRangeDropdown, setShowRangeDropdown] = useState(false)

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
      className="glass sticky top-0 z-40 mx-4 mt-4 px-4 py-2.5 flex items-center gap-4"
      style={{ borderRadius: '16px' }}
    >
      <div className="relative flex-1 max-w-md">
        <Search
          size={16}
          className={`absolute left-3 top-1/2 -translate-y-1/2 transition-colors ${
            searchFocused ? 'text-blue-400' : 'text-white/30'
          }`}
        />
        <input
          type="text"
          placeholder="Search users, IPs, devices..."
          onFocus={() => setSearchFocused(true)}
          onBlur={() => setSearchFocused(false)}
          className="glass-input w-full pl-9 pr-3 py-2 text-sm"
          aria-label="Global search"
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
          <kbd className="hidden sm:inline-flex text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/30 font-mono">
            ⌘K
          </kbd>
        </div>
      </div>

      <div className="relative">
        <button
          onClick={() => setShowRangeDropdown(!showRangeDropdown)}
          className="glass-input flex items-center gap-2 px-3 py-2 text-sm text-white/60 hover:text-white/80"
        >
          <span>{selectedRange}</span>
          <ChevronDown size={14} />
        </button>
        {showRangeDropdown && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setShowRangeDropdown(false)} />
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              className="absolute right-0 top-full mt-1 z-20 glass-card-sm min-w-[180px] p-1"
            >
              {timeRanges.map((range) => (
                <button
                  key={range}
                  onClick={() => { setSelectedRange(range); setShowRangeDropdown(false) }}
                  className={`w-full text-left px-3 py-2 text-sm rounded-lg transition-colors ${
                    selectedRange === range ? 'bg-white/10 text-white' : 'text-white/60 hover:text-white/80 hover:bg-white/5'
                  }`}
                >
                  {range}
                </button>
              ))}
            </motion.div>
          </>
        )}
      </div>

      <button
        onClick={() => setAutoRefresh(!autoRefresh)}
        className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm transition-all ${
          autoRefresh ? 'bg-blue-500/10 text-blue-400' : 'text-white/40 hover:text-white/60'
        }`}
      >
        <RefreshCw size={14} className={autoRefresh ? 'animate-spin-slow' : ''} />
        <span className="hidden sm:inline">Auto</span>
      </button>

      <div className="relative">
        <button className="p-2 rounded-xl hover:bg-white/5 text-white/40 hover:text-white/70 transition-all relative">
          <Bell size={18} />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500" style={{ boxShadow: '0 0 6px rgba(239,68,68,0.6)' }} />
        </button>
      </div>

      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-400 to-purple-500 flex items-center justify-center text-xs font-semibold text-white cursor-pointer">
        OP
      </div>
    </motion.header>
  )
}
