import { motion } from "framer-motion";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="text-ink-dim text-[10px] mb-1">{d.time}</div>
      <div className="text-ink text-xs font-bold">
        Score: <span style={{ color: d.color || "#e8a33d" }}>{d.score?.toFixed(3)}</span>
      </div>
      <div className="text-ink-dim text-[10px]">
        {d.name} → {d.dst_computer} [{d.decision}]
      </div>
    </div>
  );
};

export default function ScoreTrend({ events = [] }) {
  const data = [...events]
    .reverse()
    .map((e, i) => ({
      index: i,
      score: e.combined_score || 0,
      name: e.name || `User ${e.user_id}`,
      dst_computer: e.dst_computer,
      decision: e.decision,
      time: e.ts || "-",
      color:
        e.decision === "block"
          ? "#e5484d"
          : e.decision === "flag"
          ? "#ff9b9e"
          : "#57b06c",
    }));

  return (
    <div className="w-full">
      <div className="text-xs uppercase tracking-wider text-ink-faint mb-3 font-semibold">
        Anomaly Score Trend
      </div>
      <motion.div
        initial={{ clipPath: "inset(0 100% 0 0)" }}
        animate={{ clipPath: "inset(0 0% 0 0)" }}
        transition={{ duration: 1.1, ease: [0.4, 0, 0.2, 1], delay: 0.15 }}
      >
        <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
          <defs>
            <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#e8a33d" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#e8a33d" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis
            dataKey="index"
            tick={{ fill: "#5a6274", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[0, 1]}
            tick={{ fill: "#5a6274", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={0.7} stroke="#e5484d" strokeDasharray="4 4" strokeOpacity={0.5} />
          <ReferenceLine y={0.8} stroke="#e5484d" strokeDasharray="2 2" strokeOpacity={0.3} />
          <Area
            type="monotone"
            dataKey="score"
            stroke="#e8a33d"
            strokeWidth={2}
            fill="url(#scoreGrad)"
            dot={(props) => {
              const { cx, cy, payload } = props;
              return (
                <circle
                  cx={cx}
                  cy={cy}
                  r={payload.decision === "block" ? 5 : payload.decision === "flag" ? 4 : 3}
                  fill={payload.color}
                  stroke={payload.color}
                  strokeWidth={1}
                  fillOpacity={0.8}
                />
              );
            }}
          />
        </AreaChart>
        </ResponsiveContainer>
      </motion.div>
    </div>
  );
}
