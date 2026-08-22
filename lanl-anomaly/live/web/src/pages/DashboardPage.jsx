import { motion } from "framer-motion";
import { useDashboardData } from "../hooks/useDashboardData";
import KpiRow from "../components/dashboard/KpiRow";
import AlertFeed from "../components/dashboard/AlertFeed";
import EventTable from "../components/tables/EventTable";
import GlassCard from "../components/common/GlassCard";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

const COLORS = { low: "#57b06c", medium: "#e8a33d", high: "#ff9b9e", critical: "#e5484d" };

export default function DashboardPage({ onInvestigate }) {
  const { data, loading } = useDashboardData();

  if (loading) {
    return <div className="text-ink-faint text-xs py-8 text-center">Loading...</div>;
  }

  const kpis = data?.kpis;
  const events = data?.recentEvents || [];
  const alerts = data?.alerts || [];
  const riskDist = data?.riskDistribution || [];

  // Score distribution for chart
  const scoreBuckets = [
    { range: "0-0.25", count: events.filter((e) => e.combined_score < 0.25).length },
    { range: "0.25-0.5", count: events.filter((e) => e.combined_score >= 0.25 && e.combined_score < 0.5).length },
    { range: "0.5-0.6", count: events.filter((e) => e.combined_score >= 0.5 && e.combined_score < 0.6).length },
    { range: "0.6-0.8", count: events.filter((e) => e.combined_score >= 0.6 && e.combined_score < 0.8).length },
    { range: "0.8-1.0", count: events.filter((e) => e.combined_score >= 0.8).length },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
    >
      <KpiRow kpis={kpis} />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 mb-5">
        <GlassCard className="p-4 xl:col-span-2">
          <div className="text-xs uppercase tracking-wider text-ink-faint mb-3 font-semibold">
            Score Distribution
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={scoreBuckets}>
              <XAxis dataKey="range" tick={{ fill: "#5a6274", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#5a6274", fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{ background: "#151a24", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, fontSize: 11 }}
                labelStyle={{ color: "#8b93a5" }}
              />
              <Bar dataKey="count" fill="#e8a33d" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </GlassCard>

        <AlertFeed alerts={alerts} onInvestigate={onInvestigate} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 mb-5">
        <GlassCard className="p-4">
          <div className="text-xs uppercase tracking-wider text-ink-faint mb-3 font-semibold">
            Risk Distribution
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={riskDist} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={40} outerRadius={70}>
                {riskDist.map((entry, i) => (
                  <Cell key={i} fill={entry.color || COLORS[entry.name?.toLowerCase()]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: "#151a24", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, fontSize: 11 }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-3 mt-2">
            {riskDist.map((r) => (
              <div key={r.name} className="flex items-center gap-1.5 text-[10px] text-ink-dim">
                <div className="w-2 h-2 rounded-full" style={{ background: r.color }} />
                {r.name}: {r.value}
              </div>
            ))}
          </div>
        </GlassCard>

        <div className="xl:col-span-2">
          <EventTable events={events} onInvestigate={onInvestigate} />
        </div>
      </div>
    </motion.div>
  );
}
