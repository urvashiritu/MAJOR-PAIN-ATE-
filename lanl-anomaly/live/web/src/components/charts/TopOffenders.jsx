import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

const COLORS = ["#e5484d", "#ff9b9e", "#e8a33d", "#6ea8e8", "#57b06c"];

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="text-ink text-xs font-bold">{d.name}</div>
      <div className="text-ink-dim text-[10px]">
        {d.flags} anomalies | Max score: {d.maxScore?.toFixed(3)}
      </div>
    </div>
  );
};

export default function TopOffenders({ events = [] }) {
  const userMap = {};
  events.forEach((e) => {
    const key = e.name || `User ${e.user_id}`;
    if (!userMap[key]) {
      userMap[key] = { name: key, flags: 0, maxScore: 0, total: 0 };
    }
    userMap[key].total++;
    if (e.decision === "flag" || e.decision === "block") {
      userMap[key].flags++;
    }
    if ((e.combined_score || 0) > userMap[key].maxScore) {
      userMap[key].maxScore = e.combined_score;
    }
  });

  const data = Object.values(userMap)
    .sort((a, b) => b.flags - a.flags || b.maxScore - a.maxScore)
    .slice(0, 8);

  return (
    <div className="w-full">
      <div className="text-xs uppercase tracking-wider text-ink-faint mb-3 font-semibold">
        Top Offenders
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 10, left: 0, bottom: 0 }}>
          <XAxis type="number" tick={{ fill: "#5a6274", fontSize: 9 }} axisLine={false} tickLine={false} />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fill: "#8b93a5", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={70}
          />
          <Tooltip content={<CustomTooltip />} />
          <Bar dataKey="flags" radius={[0, 3, 3, 0]} name="Anomalies">
            {data.map((entry, i) => (
              <Cell key={i} fill={COLORS[Math.min(i, COLORS.length - 1)]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
