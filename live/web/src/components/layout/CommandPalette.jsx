import { useState, useMemo, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, LayoutDashboard, AlertTriangle, Users as UsersIcon, Database, User, Bell, ArrowRight } from 'lucide-react'
import { cn } from '../../lib/utils'
import { getUsers, getAlerts } from '../../hooks/useApi'

const sharedTransition = { type: 'tween', ease: 'easeOut', duration: 0.15 }

export default function CommandPalette({ onNavigate }) {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)
  const [users, setUsers] = useState([])
  const [alerts, setAlerts] = useState([])
  const inputRef = useRef(null)

  useEffect(() => {
    let mounted = true
    getUsers().then(res => { if (mounted) setUsers(res.personas || []) }).catch(() => {})
    getAlerts().then(res => { if (mounted) setAlerts(res || []) }).catch(() => {})
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    if (isOpen) {
      const t = setTimeout(() => inputRef.current?.focus(), 100)
      return () => clearTimeout(t)
    }
  }, [isOpen])

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setIsOpen(o => !o)
      }
      if (e.key === 'Escape' && isOpen) {
        e.preventDefault()
        e.stopPropagation()
        setIsOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown, true)
    return () => window.removeEventListener('keydown', handleKeyDown, true)
  }, [isOpen])

  const items = useMemo(() => {
    const nav = [
      { id: 'page-dashboard', title: 'Dashboard', section: 'Navigate', icon: <LayoutDashboard size={16} />, action: () => onNavigate('dashboard') },
      { id: 'page-alerts', title: 'Alerts', section: 'Navigate', icon: <AlertTriangle size={16} />, action: () => onNavigate('alerts') },
      { id: 'page-users', title: 'Users', section: 'Navigate', icon: <UsersIcon size={16} />, action: () => onNavigate('users') },
      { id: 'page-dataset', title: 'Dataset', section: 'Navigate', icon: <Database size={16} />, action: () => onNavigate('dataset') },
    ]
    const userItems = users.slice(0, 5).map(u => ({
      id: `user-${u.user_id || u.name}`,
      title: u.name || u.persona,
      section: 'Users',
      icon: <User size={16} />,
      action: () => onNavigate('users'),
    }))
    const alertItems = alerts.slice(0, 5).map(a => ({
      id: `alert-${a.id}`,
      title: a.displayName || a.display_name || a.type,
      section: 'Alerts',
      icon: <Bell size={16} />,
      action: () => onNavigate('alerts'),
    }))
    return [...nav, ...userItems, ...alertItems]
  }, [users, alerts, onNavigate])

  const filteredItems = useMemo(
    () => items.filter(item => item.title.toLowerCase().includes(query.toLowerCase())),
    [query, items],
  )

  useEffect(() => {
    requestAnimationFrame(() => setActiveIndex(0))
  }, [query])

  const sections = useMemo(() => {
    const groups = {}
    filteredItems.forEach(item => {
      if (!groups[item.section]) groups[item.section] = []
      groups[item.section].push(item)
    })
    return Object.entries(groups).map(([name, items]) => ({ name, items }))
  }, [filteredItems])

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex(prev => (prev + 1) % filteredItems.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex(prev => (prev - 1 + filteredItems.length) % filteredItems.length)
    } else if (e.key === 'Enter') {
      const selected = filteredItems[activeIndex]
      if (selected) {
        selected.action()
        setIsOpen(false)
      }
    }
  }

  return (
    <>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px]"
            onClick={() => setIsOpen(false)}
          />
        )}
      </AnimatePresence>

      <div className="relative z-50 h-10 w-full max-w-[280px] md:w-64">
        <AnimatePresence mode="popLayout">
          {!isOpen ? (
            <motion.button
              key="trigger"
              layoutId="command-pallete"
              onClick={() => setIsOpen(true)}
              className="glass-input group absolute top-0 left-0 flex h-10 w-full items-center gap-3 overflow-hidden px-4 py-2 text-ink/faint hover:text-ink/80"
              transition={sharedTransition}
            >
              <motion.div layoutId="search-icon" transition={sharedTransition}>
                <Search size={16} className="opacity-40" />
              </motion.div>
              <motion.span layoutId="search-text" transition={sharedTransition} className="pr-8 text-sm font-medium">
                Find...
              </motion.span>
              <motion.kbd
                layoutId="search-shortcut"
                transition={sharedTransition}
                className="absolute right-2 rounded-sm border border-ink/15 bg-white/5 px-2 py-0.5 text-[11px] font-bold text-ink/faint group-hover:text-ink/60"
              >
                ⌘K
              </motion.kbd>
            </motion.button>
          ) : (
            <motion.div
              layoutId="command-pallete"
              transition={sharedTransition}
              onClick={(e) => e.stopPropagation()}
              className="absolute -top-2 -left-2 z-50 flex h-80 w-[20rem] flex-col overflow-hidden rounded-lg border-[1.4px] border-ink/20 bg-paper-100 shadow-[0_32px_64px_-15px_rgba(0,0,0,0.6)] md:w-[400px]"
            >
              <div className="flex items-center border-b-[1.4px] border-ink/10 px-4 py-3.5">
                <motion.div layoutId="search-icon" transition={sharedTransition}>
                  <Search size={18} className="mr-3 text-ink/faint" strokeWidth={2.5} />
                </motion.div>
                <div className="relative flex flex-1 items-center">
                  <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    className="w-full bg-transparent text-base font-medium text-ink outline-none md:text-[15px]"
                  />
                  {!query && (
                    <motion.span
                      layoutId="search-text"
                      transition={sharedTransition}
                      className="pointer-events-none absolute left-0 text-[15px] font-medium text-ink/faint"
                    >
                      Find...
                    </motion.span>
                  )}
                </div>
                <div className="ml-2 flex items-center gap-1.5">
                  <motion.span
                    layoutId="search-shortcut"
                    transition={sharedTransition}
                    className="rounded-sm border border-ink/15 bg-white/5 p-0.5 px-1 text-[11px] font-bold text-ink/faint"
                  >
                    Esc
                  </motion.span>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-1.5 md:max-h-[380px]">
                {filteredItems.length === 0 ? (
                  <div className="py-12 text-center text-sm text-ink/faint">
                    No results found for "{query}"
                  </div>
                ) : (
                  <div className="space-y-4 py-1">
                    {sections.map((section) => (
                      <div key={section.name} className="space-y-1">
                        <h3 className="px-3 py-1 text-[11px] font-semibold tracking-wider text-ink/faint uppercase">
                          {section.name}
                        </h3>
                        <div className="space-y-0.5">
                          {section.items.map((item) => {
                            const globalIndex = filteredItems.findIndex(fi => fi.id === item.id)
                            const isActive = globalIndex === activeIndex
                            return (
                              <button
                                key={item.id}
                                className={cn(
                                  'group flex w-full items-center justify-between rounded-sm px-3 py-2.5 text-left',
                                  isActive ? 'bg-ink/10 text-ink' : 'text-ink/dim hover:text-ink',
                                )}
                                onMouseEnter={() => setActiveIndex(globalIndex)}
                                onClick={() => { item.action(); setIsOpen(false) }}
                              >
                                <div className="flex items-center gap-3">
                                  <span className={cn(isActive ? 'text-ochre' : 'text-ink/faint group-hover:text-ink/60')}>
                                    {item.icon}
                                  </span>
                                  <span className="text-[14px] leading-none font-medium">{item.title}</span>
                                </div>
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  )
}