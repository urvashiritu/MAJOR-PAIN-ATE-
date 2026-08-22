import { motion } from "framer-motion";
import { LayoutDashboard, Bell, Users, Shield, ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "../../lib/utils";

const NAV = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "alerts", label: "Alerts", icon: Bell },
  { id: "users", label: "Users", icon: Users },
];

export default function Sidebar({ activePage, setActivePage, collapsed, setCollapsed }) {
  return (
    <motion.aside
      className="sidebar fixed left-0 top-0 h-screen z-50 flex flex-col"
      animate={{ width: collapsed ? 72 : 256 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
    >
      <div className="flex items-center gap-2 px-4 h-14 border-b border-white/[0.07]">
        <Shield className="w-5 h-5 text-ochre shrink-0" />
        {!collapsed && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-sm font-bold text-ochre whitespace-nowrap"
          >
            LANL SOC
          </motion.span>
        )}
      </div>

      <nav className="flex-1 p-2 space-y-1">
        {NAV.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActivePage(id)}
            className={cn("sidebar-item w-full", activePage === id && "active")}
          >
            <Icon className="w-4 h-4 shrink-0" />
            {!collapsed && <span>{label}</span>}
          </button>
        ))}
      </nav>

      <button
        onClick={() => setCollapsed(!collapsed)}
        className="p-3 text-ink-faint hover:text-ink transition-colors"
      >
        {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </button>
    </motion.aside>
  );
}
