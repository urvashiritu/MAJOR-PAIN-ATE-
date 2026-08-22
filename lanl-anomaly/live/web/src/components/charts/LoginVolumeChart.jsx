import {
  ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="text-ink-dim text-[10px] mb-1">Hour {label}</div>
      {payload.map((p, i) => (
        <div key={i} className="text-xs" style={{ color: p.color }}>
          {p.name}: {p.value}
        </div>
      ))}
    </div>
  );
};

export default function LoginVolumeChart({ events = [] }) {
  const hourly = Array.from({ length: 24 }, (_, h) => ({
    hour: h,
    label: `${h.toString().padStart(2, "0")}:00`,
    success: 0,
    fail: 0,
    score: 0,
    count: 0,
  }));

  events.forEach((e) => {
    const t = e.ts;
    if (!t) return;
    const h = parseInt(t.split(":")[0], 10);
    if (isNaN(h)) return;
    hourly[h].count++;
    if (e.result === "Success") hourly[h].success++;
    else hourly[h].fail++;
    hourly[h].score += e.combined_score || 0;
  });

  hourly.forEach((h) => {
    h.avgScore = h.count > 0 ? h.score / h.count : 0;
  });

  return (
    <div className="w-full">
      <div className="text-xs uppercase tracking-wider text-ink-faint mb-3 font-semibold">
        Login Volume by Hour
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <ComposedChart data={hourly} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis
            dataKey="label"
            tick={{ fill: "#5a6274", fontSize: 8 }}
            axisLine={false}
            tickLine={false}
            interval={2}
          />
          <YAxis
            yAxisId="left"
            tick={{ fill: "#5a6274", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={[0, 1]}
            tick={{ fill: "#5a6274", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Bar yAxisId="left" dataKey="success" stackId="a" fill="#57b06c" radius={[0, 0, 0, 0]} name="Success" />
          <Bar yAxisId="left" dataKey="fail" stackId="a" fill="#e5484d" radius={[3, 3, 0, 0]} name="Failure" />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="avgScore"
            stroke="#e8a33d"
            strokeWidth={2}
            dot={false}
            name="Avg Score"
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-1 justify-center">
        <div className="flex items-center gap-1 text-[9px] text-ink-faint">
          <div className="w-2 h-2 rounded-sm" style={{ background: "#57b06c" }} /> Success
        </div>
        <div className="flex items-center gap-1 text-[9px] text-ink-faint">
          <div className="w-2 h-2 rounded-sm" style={{ background: "#e5484d" }} /> Failure
        </div>
        <div className="flex items-center gap-1 text-[9px] text-ink-faint">
          <div className="w-2 h-0.5 rounded" style={{ background: "#e8a33d" }} /> Avg Score
        </div>
      </div>
    </div>
  );
}
