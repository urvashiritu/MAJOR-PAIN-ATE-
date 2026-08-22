import { motion } from "framer-motion";
import { useDashboardData } from "../hooks/useDashboardData";
import KpiCards from "../components/dashboard/KpiCards";
import AlertFeed from "../components/dashboard/AlertFeed";
import EventTable from "../components/tables/EventTable";
import GlassCard from "../components/common/GlassCard";
import ThreatGauge from "../components/charts/ThreatGauge";
import ScoreTrend from "../components/charts/ScoreTrend";
import ActivityHeatmap from "../components/charts/ActivityHeatmap";
import LoginVolumeChart from "../components/charts/LoginVolumeChart";
import ThreatRings from "../components/charts/ThreatRings";
import TopOffenders from "../components/charts/TopOffenders";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

const COLORS = { low: "#57b06c", medium: "#e8a33d", high: "#ff9b9e", critical: "#e5484d" };

export default function DashboardPage({ onInvestigate }) {
  const { data, loading } = useDashboardData();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="live-dot mr-2" />
        <span className="text-ink-faint text-xs">Loading dashboard...</span>
      </div>
    );
  }

  const kpis = data?.kpis || {};
  const events = data?.recentEvents || [];
  const alerts = data?.alerts || [];
  const riskDist = data?.riskDistribution || [];

  const avgScore = events.length > 0
    ? events.reduce((s, e) => s + (e.combined_score || 0), 0) / events.length
    : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
    >
      {/* Row 1: KPI Cards with sparklines */}
      <KpiCards kpis={kpis} events={events} />

      {/* Row 2: Threat Gauge + Score Trend */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 mb-5">
        <GlassCard className="p-4 flex items-center justify-center">
          <ThreatGauge value={avgScore} label="Current Threat Level" />
        </GlassCard>
        <GlassCard className="p-4 xl:col-span-2">
          <ScoreTrend events={events} />
        </GlassCard>
      </div>

      {/* Row 3: Activity Heatmap (full width) */}
      <GlassCard className="p-4 mb-5">
        <ActivityHeatmap events={events} />
      </GlassCard>

      {/* Row 4: Login Volume + Threat Rings */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 mb-5">
        <GlassCard className="p-4 xl:col-span-2">
          <LoginVolumeChart events={events} />
        </GlassCard>
        <GlassCard className="p-4 flex items-center justify-center">
          <ThreatRings kpis={kpis} />
        </GlassCard>
      </div>

      {/* Row 5: Top Offenders + Alert Feed */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5 mb-5">
        <GlassCard className="p-4">
          <TopOffenders events={events} />
        </GlassCard>
        <AlertFeed alerts={alerts} onInvestigate={onInvestigate} />
      </div>

      {/* Row 6: Risk Distribution mini + Event Table */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-5 mb-5">
        <GlassCard className="p-4">
          <div className="text-xs uppercase tracking-wider text-ink-faint mb-3 font-semibold">
            Risk Split
          </div>
          <ResponsiveContainer width="100%" height={140}>
            <PieChart>
              <Pie data={riskDist} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={30} outerRadius={55}>
                {riskDist.map((entry, i) => (
                  <Cell key={i} fill={entry.color || COLORS[entry.name?.toLowerCase()]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ background: "#151a24", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 6, fontSize: 11 }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-2 mt-1 justify-center">
            {riskDist.map((r) => (
              <div key={r.name} className="flex items-center gap-1 text-[9px] text-ink-faint">
                <div className="w-1.5 h-1.5 rounded-full" style={{ background: r.color }} />
                {r.name}: {r.value}
              </div>
            ))}
          </div>
        </GlassCard>
        <div className="xl:col-span-3">
          <EventTable events={events} onInvestigate={onInvestigate} />
        </div>
      </div>
    </motion.div>
  );
}
