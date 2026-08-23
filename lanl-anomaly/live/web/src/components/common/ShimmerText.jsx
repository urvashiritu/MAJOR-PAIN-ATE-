import { motion } from "framer-motion";

/**
 * Shimmer Text — adapted from KokonutUI (MIT, kokonutui.com, @dorianbaffier)
 * Looping gradient sweep across letters. Colors come via `className`
 * gradient stops so callers control the palette.
 */
export default function ShimmerText({ text, className }) {
  return (
    <motion.span
      animate={{ backgroundPosition: ["200% center", "-200% center"] }}
      className={`inline-block bg-[length:200%_100%] bg-gradient-to-r bg-clip-text font-bold text-transparent ${className || ""}`}
      transition={{ duration: 2.5, ease: "linear", repeat: Number.POSITIVE_INFINITY }}
    >
      {text}
    </motion.span>
  );
}
