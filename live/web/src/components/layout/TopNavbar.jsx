import { useState } from 'react'
import { motion } from 'framer-motion'
import { Bell, RefreshCw, ChevronDown } from 'lucide-react'
import CommandPalette from './CommandPalette'
import StatusIndicator from '../common/StatusIndicator'

const timeRanges = ['Last 24 Hours', 'Last 7 Days', 'Last 30 Days', 'Custom']

export default function TopNavbar({ onNavigate }) {
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [selectedRange, setSelectedRange] = useState('Last 24 Hours')
  const [showRangeDropdown, setShowRangeDropdown] = useState(false)

  return (
    <motion.header
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.4, 0, 0.2, 1] }}
      className="panel sticky top-0 z-40 mx-4 mt-4 px-4 py-2.5 flex items-center gap-4"
      style={{ background: 'rgba(11,14,20,0.92)' }}
    >
      <div className="flex-1 flex justify-start">
        <CommandPalette onNavigate={onNavigate} />
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
              className="absolute right-0 top-full mt-1 z-20 panel-inset min-w-[180px] p-1"
            >
              {timeRanges.map((range) => (
                <button
                  key={range}
                  onClick={() => { setSelectedRange(range); setShowRangeDropdown(false) }}
                  className={`w-full text-left px-3 py-2 text-sm rounded-sm transition-colors ${
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
        className={`flex items-center gap-1.5 px-3 py-2 rounded-sm text-sm transition-all ${
          autoRefresh ? 'bg-ochre/10 text-ochre' : 'text-white/40 hover:text-white/60'
        }`}
      >
        <RefreshCw size={14} className={autoRefresh ? 'animate-spin' : ''} />
        <span className="hidden sm:inline">Auto</span>
      </button>

      <StatusIndicator state="active" label="Live" size="sm" className="hidden lg:flex" labelClassName="text-[11px] text-low font-semibold uppercase tracking-wider" />

      <div className="relative">
        <button className="p-2 rounded-sm hover:bg-white/5 text-white/40 hover:text-white/70 transition-all relative">
          <Bell size={18} />
          <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-critical" />
        </button>
      </div>

      <div className="w-8 h-8 border border-ink/25 flex items-center justify-center text-[11px] font-semibold text-ink/70 cursor-pointer">
        OP
      </div>
    </motion.header>
  )
}
