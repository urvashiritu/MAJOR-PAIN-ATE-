import { useState, useEffect } from "react";
import { Activity } from "lucide-react";
import { getHealth } from "../../hooks/useApi";
import CommandPalette from "./CommandPalette";
import SwitchButton from "../common/SwitchButton";

const TABS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "alerts", label: "Alerts" },
  { id: "users", label: "Users" },
  { id: "settings", label: "Settings" },
];

export default function TopNavbar({ activePage, onNavigate, onInvestigate }) {
  const [online, setOnline] = useState(false);

  useEffect(() => {
    getHealth().then((h) => setOnline(h.models_loaded)).catch(() => setOnline(false));
    const iv = setInterval(() => {
      getHealth().then((h) => setOnline(h.models_loaded)).catch(() => setOnline(false));
    }, 10000);
    return () => clearInterval(iv);
  }, []);

  return (
    <header className="sticky top-0 z-40 h-12 flex items-center justify-between px-5 border-b border-[color:var(--hairline)]"
      style={{ background: "var(--nav-bg)", backdropFilter: "blur(8px)" }}>
      <div className="flex items-center gap-4">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => onNavigate(t.id)}
            className={`text-xs uppercase tracking-wider transition-colors ${
              activePage === t.id ? "text-ochre font-bold" : "text-ink-faint hover:text-ink-dim"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <CommandPalette onNavigate={onNavigate} onInvestigate={onInvestigate} />
        <SwitchButton />
        <div className="flex items-center gap-2 text-xs text-ink-dim">
          <div className={`live-dot ${online ? "" : "opacity-30"}`} />
          <span>{online ? "MODELS LOADED" : "OFFLINE"}</span>
        </div>
        <Activity className="w-3.5 h-3.5 text-ochre" />
      </div>
    </header>
  );
}
