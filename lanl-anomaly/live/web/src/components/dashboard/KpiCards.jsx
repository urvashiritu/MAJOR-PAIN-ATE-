import { AreaChart, Area, ResponsiveContainer } from "recharts";
import GlassCard from "../common/GlassCard";

function Sparkline({ data = [], color = "#e8a33d" }) {
  return (
    <ResponsiveContainer width="100%" height={32}>
      <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
        <defs>
          <linearGradient id={`spark-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.3} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="v"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#spark-${color.replace("#", "")})`}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

const CARDS = [
  {
    key: "totalEvents",
    label: "Events Scored",
    color: "#6ea8e8",
    bg: "rgba(110,168,232,0.08)",
    border: "rgba(110,168,232,0.2)",
  },
  {
    key: "anomalies",
    label: "Anomalies",
    color: "#e5484d",
    bg: "rgba(229,72,77,0.08)",
    border: "rgba(229,72,77,0.2)",
  },
  {
    key: "highRiskUsers",
    label: "High-Risk Users",
    color: "#ff9b9e",
    bg: "rgba(255,155,158,0.08)",
    border: "rgba(255,155,158,0.2)",
  },
  {
    key: "usersMonitored",
    label: "Users Monitored",
    color: "#57b06c",
    bg: "rgba(87,176,108,0.08)",
    border: "rgba(87,176,108,0.2)",
  },
];

export default function KpiCards({ kpis = {}, events = [] }) {
  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
      {CARDS.map((card) => {
        const value = kpis[card.key] || 0;
        const sparkData = events.slice(-20).map((e, i) => {
          if (card.key === "totalEvents") return { v: i + 1 };
          if (card.key === "anomalies") return { v: events.slice(0, i + 1).filter((x) => x.decision === "flag" || x.decision === "block").length };
          if (card.key === "highRiskUsers") return { v: new Set(events.slice(0, i + 1).filter((x) => x.decision === "flag" || x.decision === "block").map((x) => x.user_id)).size };
          return { v: new Set(events.slice(0, i + 1).map((x) => x.user_id)).size };
        });

        return (
          <GlassCard
            key={card.key}
            className="p-4"
            style={{ background: card.bg, borderColor: card.border }}
          >
            <div className="text-[10px] uppercase tracking-wider text-ink-faint mb-1 font-semibold">
              {card.label}
            </div>
            <div className="flex items-end justify-between">
              <div className="text-3xl font-bold" style={{ color: card.color }}>
                {value}
              </div>
            </div>
            <div className="mt-2">
              <Sparkline data={sparkData} color={card.color} />
            </div>
          </GlassCard>
        );
      })}
    </div>
  );
}
