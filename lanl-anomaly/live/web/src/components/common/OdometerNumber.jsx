import { motion } from "framer-motion";

const DIGITS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
const EM = 1.05;

function Digit({ d }) {
  return (
    <span
      className="inline-block overflow-hidden align-baseline"
      style={{ height: `${EM}em` }}
    >
      <motion.span
        className="block"
        initial={false}
        animate={{ y: `-${d * EM}em` }}
        transition={{ type: "spring", stiffness: 260, damping: 28, mass: 0.9 }}
      >
        {DIGITS.map((n) => (
          <span key={n} className="block" style={{ height: `${EM}em`, lineHeight: `${EM}em` }}>
            {n}
          </span>
        ))}
      </motion.span>
    </span>
  );
}

export default function OdometerNumber({ value = 0, className = "" }) {
  const safe = Math.max(0, Math.round(Number(value) || 0));
  const chars = String(safe).split("");
  const len = chars.length;
  return (
    <span className={`inline-flex tabular-nums ${className}`} aria-label={String(safe)}>
      {chars.map((c, i) =>
        /\d/.test(c) ? (
          <Digit key={`${len}-${i}`} d={Number(c)} />
        ) : (
          <span key={`${len}-${i}`}>{c}</span>
        ),
      )}
    </span>
  );
}
