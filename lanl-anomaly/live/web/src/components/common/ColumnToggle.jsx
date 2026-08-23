import { useState } from "react";
import { motion } from "framer-motion";
import { Columns, ChevronDown } from "lucide-react";
import { cn } from "../../lib/utils";

export default function ColumnToggle({ columns, visible, onChange, className }) {
  const [open, setOpen] = useState(false);

  const toggle = (key) => {
    const next = visible.includes(key)
      ? visible.filter((k) => k !== key)
      : [...visible, key];
    if (next.length > 0) onChange(next);
  };

  return (
    <div className={cn("relative", className)}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="glass-input flex items-center gap-1.5 px-3 py-2 text-xs text-ink-dim hover:text-ink"
      >
        <Columns size={13} />
        <span className="hidden sm:inline">Columns</span>
        <ChevronDown size={12} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="absolute right-0 top-full mt-1 z-20 panel-inset min-w-[190px] p-1.5"
          >
            {columns.map((col) => (
              <label
                key={col.key}
                className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-sm cursor-pointer hover:bg-[color:var(--wash)] transition-colors"
              >
                <input
                  type="checkbox"
                  checked={visible.includes(col.key)}
                  onChange={() => toggle(col.key)}
                  className="accent-[#e8a33d]"
                />
                <span className="text-xs text-ink">{col.label}</span>
              </label>
            ))}
          </motion.div>
        </>
      )}
    </div>
  );
}
