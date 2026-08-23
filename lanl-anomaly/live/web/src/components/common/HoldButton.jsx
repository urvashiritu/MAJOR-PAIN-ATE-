import { useState } from "react";
import { motion, useAnimation } from "framer-motion";
import { Trash2 } from "lucide-react";
import { cn } from "../../lib/utils";

export default function HoldButton({
  className,
  holdDuration = 3000,
  onHoldComplete,
  children,
  ...props
}) {
  const [isHolding, setIsHolding] = useState(false);
  const [completed, setCompleted] = useState(false);
  const controls = useAnimation();

  async function handleHoldStart() {
    setIsHolding(true);
    setCompleted(false);
    controls.set({ width: "0%" });
    await controls.start({
      width: "100%",
      transition: { duration: holdDuration / 1000, ease: "linear" },
    });
    setCompleted(true);
    setIsHolding(false);
  }

  function handleHoldEnd() {
    if (completed) {
      onHoldComplete?.();
      setCompleted(false);
    }
    setIsHolding(false);
    controls.stop();
    controls.start({ width: "0%", transition: { duration: 0.1 } });
  }

  return (
    <button
      className={cn(
        "relative min-w-[200px] touch-none overflow-hidden rounded-lg px-5 py-3",
        "font-semibold text-sm transition-colors",
        "bg-[color:var(--critical)]/10 border border-[color:var(--critical)]/30",
        "text-[color:var(--critical)] hover:bg-[color:var(--critical)]/15",
        "dark:bg-[color:var(--critical)]/15 dark:border-[color:var(--critical)]/40",
        "dark:text-[color:var(--critical)] dark:hover:bg-[color:var(--critical)]/20",
        className
      )}
      onMouseDown={handleHoldStart}
      onMouseLeave={handleHoldEnd}
      onMouseUp={handleHoldEnd}
      onTouchCancel={handleHoldEnd}
      onTouchEnd={handleHoldEnd}
      onTouchStart={handleHoldStart}
      {...props}
    >
      <motion.div
        animate={controls}
        className="absolute top-0 left-0 h-full bg-[color:var(--critical)]/20 dark:bg-[color:var(--critical)]/25"
        initial={{ width: "0%" }}
      />
      <span className="relative z-10 flex w-full items-center justify-center gap-2">
        <Trash2 className="h-4 w-4" />
        {isHolding ? "Release to Confirm" : children || "Hold to Reset"}
      </span>
    </button>
  );
}
