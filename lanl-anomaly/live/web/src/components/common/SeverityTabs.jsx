import { useState, useEffect } from "react";
import { motion, LayoutGroup } from "framer-motion";
import { cn } from "../../lib/utils";

export default function SeverityTabs({ tabs, defaultActiveId, onChange, className }) {
  const [active, setActive] = useState(defaultActiveId);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  const handleChange = (id) => {
    setActive(id);
    onChange?.(id);
  };

  if (!isMounted) return null;

  return (
    <LayoutGroup>
      <nav
        className={cn(
          "relative flex items-center gap-0.5 sm:gap-1 p-1 sm:p-1.5 rounded-full",
          "border border-white/15 bg-gradient-to-b from-paper-100 to-paper-200",
          "shadow-[inset_0_-2px_4px_rgba(0,0,0,0.25),inset_0_1px_0_rgba(255,255,255,0.05)]",
          "transition-all duration-300",
          className,
        )}
      >
        {tabs.map((tab) => {
          const isActive = active === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => handleChange(tab.id)}
              className="relative px-4 py-2 sm:px-6 sm:py-2 rounded-full outline-none"
            >
              {isActive && (
                <motion.div
                  layoutId="active-pill"
                  transition={{ type: "spring", stiffness: 380, damping: 30, mass: 0.9 }}
                  className="absolute inset-0 rounded-full bg-ink/90 shadow-sm"
                />
              )}
              <motion.span
                layout="position"
                className={cn(
                  "relative z-10 text-xs sm:text-sm font-semibold transition-colors duration-200",
                  isActive ? "text-paper" : "text-ink-dim hover:text-ink/80",
                )}
              >
                {tab.label}
              </motion.span>
            </button>
          );
        })}
      </nav>
    </LayoutGroup>
  );
}
