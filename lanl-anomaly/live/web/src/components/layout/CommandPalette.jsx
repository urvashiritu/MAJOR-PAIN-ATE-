import { useState, useMemo, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, LayoutDashboard, AlertTriangle, Users as UsersIcon, User, Bell } from "lucide-react";
import { cn } from "../../lib/utils";
import { getUsers, getAlerts } from "../../hooks/useApi";

const sharedTransition = { type: "tween", ease: "easeOut", duration: 0.15 };

export default function CommandPalette({ onNavigate, onInvestigate }) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [users, setUsers] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const inputRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    getUsers().then((res) => { if (mounted) setUsers(res || []); }).catch(() => {});
    getAlerts().then((res) => { if (mounted) setAlerts(res || []); }).catch(() => {});
    return () => { mounted = false; };
  }, []);

  useEffect(() => {
    if (isOpen) {
      const t = setTimeout(() => inputRef.current?.focus(), 100);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setIsOpen((o) => !o);
      }
      if (e.key === "Escape" && isOpen) {
        e.preventDefault();
        e.stopPropagation();
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown, true);
    return () => window.removeEventListener("keydown", handleKeyDown, true);
  }, [isOpen]);

  const items = useMemo(() => {
    const nav = [
      { id: "page-dashboard", title: "Dashboard", section: "Navigate", icon: <LayoutDashboard size={16} />, action: () => onNavigate("dashboard") },
      { id: "page-alerts", title: "Alerts", section: "Navigate", icon: <AlertTriangle size={16} />, action: () => onNavigate("alerts") },
      { id: "page-users", title: "Users", section: "Navigate", icon: <UsersIcon size={16} />, action: () => onNavigate("users") },
    ];
    const userItems = users.slice(0, 6).map((u) => ({
      id: `user-${u.user_id ?? u.name}`,
      title: `${u.name || u.persona}${u.raw_id ? ` (${u.raw_id})` : ""}`,
      section: "Users",
      icon: <User size={16} />,
      action: () => onNavigate("users"),
    }));
    const alertItems = alerts.slice(0, 6).map((a) => ({
      id: `alert-${a.id}`,
      title: `${a.name || a.raw_id || `User ${a.user_id}`} — score ${(a.combined_score ?? 0).toFixed(2)}`,
      section: "Alerts",
      icon: <Bell size={16} />,
      action: () =>
        a.eventId != null && onInvestigate ? onInvestigate(a.eventId) : onNavigate("alerts"),
    }));
    return [...nav, ...userItems, ...alertItems];
  }, [users, alerts, onNavigate, onInvestigate]);

  const filteredItems = useMemo(
    () => items.filter((item) => item.title.toLowerCase().includes(query.toLowerCase())),
    [query, items],
  );

  useEffect(() => {
    requestAnimationFrame(() => setActiveIndex(0));
  }, [query]);

  const sections = useMemo(() => {
    const groups = {};
    filteredItems.forEach((item) => {
      if (!groups[item.section]) groups[item.section] = [];
      groups[item.section].push(item);
    });
    return Object.entries(groups).map(([name, items]) => ({ name, items }));
  }, [filteredItems]);

  const handleKeyDown = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % Math.max(filteredItems.length, 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((prev) => (prev - 1 + filteredItems.length) % Math.max(filteredItems.length, 1));
    } else if (e.key === "Enter") {
      const selected = filteredItems[activeIndex];
      if (selected) {
        selected.action();
        setIsOpen(false);
      }
    }
  };

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

      <div className="relative z-50 h-8 w-full max-w-[220px] md:w-56">
        <AnimatePresence mode="popLayout">
          {!isOpen ? (
            <motion.button
              key="trigger"
              layoutId="command-palette"
              onClick={() => setIsOpen(true)}
              className="glass-input group absolute top-0 left-0 flex h-8 w-full items-center gap-2.5 overflow-hidden px-3 text-ink-faint hover:text-ink-dim"
              transition={sharedTransition}
            >
              <motion.div layoutId="search-icon" transition={sharedTransition}>
                <Search size={14} className="opacity-40" />
              </motion.div>
              <motion.span layoutId="search-text" transition={sharedTransition} className="pr-6 text-xs font-medium">
                Find...
              </motion.span>
              <motion.kbd
                layoutId="search-shortcut"
                transition={sharedTransition}
                className="absolute right-2 rounded-sm border border-white/15 bg-white/5 px-1.5 py-0.5 text-[10px] font-bold text-ink-faint group-hover:text-ink-dim"
              >
                ⌘K
              </motion.kbd>
            </motion.button>
          ) : (
            <motion.div
              layoutId="command-palette"
              transition={sharedTransition}
              onClick={(e) => e.stopPropagation()}
              className="absolute -top-2 -left-2 z-50 flex h-80 w-[20rem] flex-col overflow-hidden rounded-lg border border-white/20 bg-paper-100 shadow-[0_32px_64px_-15px_rgba(0,0,0,0.6)] md:w-[400px]"
            >
              <div className="flex items-center border-b border-white/10 px-4 py-3.5">
                <motion.div layoutId="search-icon" transition={sharedTransition}>
                  <Search size={18} className="mr-3 text-ink-faint" strokeWidth={2.5} />
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
                      className="pointer-events-none absolute left-0 text-[15px] font-medium text-ink-faint"
                    >
                      Find...
                    </motion.span>
                  )}
                </div>
                <div className="ml-2 flex items-center gap-1.5">
                  <motion.span
                    layoutId="search-shortcut"
                    transition={sharedTransition}
                    className="rounded-sm border border-white/15 bg-white/5 p-0.5 px-1 text-[11px] font-bold text-ink-faint"
                  >
                    Esc
                  </motion.span>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-1.5 md:max-h-[380px]">
                {filteredItems.length === 0 ? (
                  <div className="py-12 text-center text-sm text-ink-faint">
                    No results found for &quot;{query}&quot;
                  </div>
                ) : (
                  <div className="space-y-4 py-1">
                    {sections.map((section) => (
                      <div key={section.name} className="space-y-1">
                        <h3 className="px-3 py-1 text-[11px] font-semibold tracking-wider text-ink-faint uppercase">
                          {section.name}
                        </h3>
                        <div className="space-y-0.5">
                          {section.items.map((item) => {
                            const globalIndex = filteredItems.findIndex((fi) => fi.id === item.id);
                            const isActive = globalIndex === activeIndex;
                            return (
                              <button
                                key={item.id}
                                className={cn(
                                  "group flex w-full items-center justify-between rounded-sm px-3 py-2.5 text-left",
                                  isActive ? "bg-white/10 text-ink" : "text-ink-dim hover:text-ink",
                                )}
                                onMouseEnter={() => setActiveIndex(globalIndex)}
                                onClick={() => { item.action(); setIsOpen(false); }}
                              >
                                <div className="flex items-center gap-3">
                                  <span className={cn(isActive ? "text-ochre" : "text-ink-faint group-hover:text-ink/60")}>
                                    {item.icon}
                                  </span>
                                  <span className="text-[14px] leading-none font-medium">{item.title}</span>
                                </div>
                              </button>
                            );
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
  );
}
