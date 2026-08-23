import { useState, useEffect } from "react";
import { useSpring, useMotionValueEvent } from "framer-motion";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";

const RADIUS = 70;
const STROKE = 14;

const SEGMENTS = [
  { range: [0, 0.4], color: "#57b06c" },
  { range: [0.4, 0.7], color: "#e8a33d" },
  { range: [0.7, 1.0], color: "#e5484d" },
];

function getGaugeColor(value) {
  for (const seg of SEGMENTS) {
    if (value >= seg.range[0] && value < seg.range[1]) return seg.color;
  }
  return SEGMENTS[SEGMENTS.length - 1].color;
}

function getLabel(value) {
  if (value < 0.4) return "LOW";
  if (value < 0.7) return "ELEVATED";
  return "CRITICAL";
}

export default function ThreatGauge({ value = 0, label = "Threat Level" }) {
  const target = Math.min(Math.max(value, 0), 1);
  const spring = useSpring(0, { stiffness: 60, damping: 18, mass: 1 });
  const [display, setDisplay] = useState(target);

  useEffect(() => {
    spring.set(target);
  }, [target, spring]);

  useMotionValueEvent(spring, "change", (v) => setDisplay(v));

  const angle = display * 180;
  const color = getGaugeColor(display);
  const statusLabel = getLabel(display);

  const data = [
    { value: angle, fill: color },
    { value: 180 - angle, fill: "rgba(255,255,255,0.05)" },
  ];

  return (
    <div className="flex flex-col items-center">
      <div className="text-xs uppercase tracking-wider text-ink-faint mb-2 font-semibold">
        {label}
      </div>
      <div className="relative" style={{ width: RADIUS * 2 + 20, height: RADIUS + 30 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              cx="50%"
              cy="85%"
              startAngle={180}
              endAngle={0}
              innerRadius={RADIUS - STROKE}
              outerRadius={RADIUS}
              stroke="none"
              isAnimationActive={false}
            >
              {data.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.fill}
                  style={{ transition: "fill 0.5s ease" }}
                />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-end pb-1">
          <div className="text-3xl font-bold tabular-nums" style={{ color }}>
            {(display * 100).toFixed(0)}
          </div>
          <div
            className="text-[10px] uppercase tracking-widest font-bold mt-0.5"
            style={{ color }}
          >
            {statusLabel}
          </div>
        </div>
      </div>
      <div className="flex gap-4 mt-1">
        {SEGMENTS.map((seg, i) => (
          <div key={i} className="flex items-center gap-1 text-[9px] text-ink-faint">
            <div className="w-1.5 h-1.5 rounded-full" style={{ background: seg.color }} />
            {i === 0 ? "Safe" : i === 1 ? "Elevated" : "Critical"}
          </div>
        ))}
      </div>
    </div>
  );
}
