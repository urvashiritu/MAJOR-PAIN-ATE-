import { useState } from "react";
import { Sun } from "lucide-react";
import { cn } from "../../lib/utils";

export default function SwitchButton({ showLabel = true, className }) {
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  );

  const toggleTheme = () => {
    const next = !isDark;
    setIsDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("theme", next ? "dark" : "light");
  };

  return (
    <button
      onClick={toggleTheme}
      title="Toggle theme"
      className={cn(
        "group relative h-10 px-4 rounded-lg",
        "transition-all duration-200 ease-out",
        "bg-gradient-to-b from-[color:var(--surface)] to-[color:var(--surface-2)]",
        "hover:from-[color:var(--surface-2)] hover:to-[color:var(--surface-3)]",
        "border border-[color:var(--hairline)]",
        "hover:border-[color:var(--hairline)]",
        "text-[color:var(--ink-dim)]",
        "hover:text-[color:var(--ink)]",
        "shadow-[0_1px_2px_-1px_rgb(0_0_0/0.1),0_1px_3px_-2px_rgb(0_0_0/0.1)]",
        "dark:shadow-[0_1px_2px_-1px_rgb(0_0_0/0.3),0_1px_3px_-2px_rgb(0_0_0/0.3)]",
        "hover:shadow-[0_2px_4px_-2px_rgb(0_0_0/0.15),0_2px_6px_-3px_rgb(0_0_0/0.15)]",
        "dark:hover:shadow-[0_2px_4px_-2px_rgb(0_0_0/0.4),0_2px_6px_-3px_rgb(0_0_0/0.4)]",
        "active:shadow-[0_0px_1px_0_rgb(0_0_0/0.1)]",
        "dark:active:shadow-[0_0px_1px_0_rgb(0_0_0/0.2)]",
        "backdrop-blur-sm",
        "after:absolute after:inset-0 after:rounded-lg after:bg-gradient-to-t after:from-white/10 after:to-transparent after:opacity-0 hover:after:opacity-100 after:transition-opacity",
        "before:absolute before:inset-[1px] before:rounded-[7px] before:bg-gradient-to-b before:from-white/20 before:to-transparent before:opacity-0 hover:before:opacity-100 before:transition-opacity dark:before:from-white/5",
        className
      )}
    >
      <div className="flex items-center gap-2 transition-all duration-300 ease-out">
        <Sun
          className={cn(
            "h-4 w-4 transition-all duration-700 ease-in-out",
            "group-hover:rotate-[360deg] group-hover:scale-110",
            isDark ? "rotate-180" : "rotate-0",
            "transform-gpu",
            isDark
              ? "text-[color:var(--ink-dim)] group-hover:text-[color:var(--ink)]"
              : "text-ochre group-hover:text-ochre",
            "drop-shadow-[0_0_12px_rgba(232,163,61,0.3)]",
            "group-active:scale-95"
          )}
        />
        {showLabel && (
          <span className="relative font-medium capitalize text-xs transition-opacity duration-300 ease-out">
            <span
              className={cn(
                "absolute inset-0 transition-opacity duration-300 ease-out",
                isDark ? "opacity-0" : "opacity-100"
              )}
            >
              Light
              <span
                className={cn(
                  "absolute -bottom-px left-0 h-px w-full",
                  "bg-gradient-to-r from-[color:var(--ink-faint)]/0 via-[color:var(--ink-faint)]/50 to-[color:var(--ink-faint)]/0",
                  "opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                )}
              />
            </span>
            <span
              className={cn(
                "absolute inset-0 transition-opacity duration-300 ease-out",
                isDark ? "opacity-100" : "opacity-0"
              )}
            >
              Dark
              <span
                className={cn(
                  "absolute -bottom-px left-0 h-px w-full",
                  "bg-gradient-to-r from-[color:var(--ink-faint)]/0 via-[color:var(--ink-faint)]/50 to-[color:var(--ink-faint)]/0",
                  "opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                )}
              />
            </span>
            <span className="opacity-0">Light</span>
          </span>
        )}
      </div>

      <span
        className={cn(
          "absolute inset-0 pointer-events-none z-[1]",
          "bg-gradient-to-r from-transparent via-white/[0.08] to-transparent",
          "translate-x-[-100%] group-hover:translate-x-[100%]",
          "transition-transform duration-500 ease-in-out"
        )}
      />

      <span
        className={cn(
          "absolute inset-0 pointer-events-none z-[2] transition-opacity duration-500",
          "opacity-0 group-hover:opacity-100",
          isDark
            ? "bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.07),transparent_70%)]"
            : "bg-[radial-gradient(circle_at_50%_50%,rgba(232,163,61,0.12),transparent_70%)]"
        )}
      />
    </button>
  );
}
