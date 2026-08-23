import { AnimatePresence, motion } from "framer-motion";
import { useDashboardData } from "../hooks/useDashboardData";
import KpiCards from "../components/dashboard/KpiCards";
import HighRiskBanner from "../components/dashboard/HighRiskBanner";
import AlertFeed from "../components/dashboard/AlertFeed";
import EventTable from "../components/tables/EventTable";
import ThreatGauge from "../components/charts/ThreatGauge";
import ScoreTrend from "../components/charts/ScoreTrend";
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

  // Gauge driven by worst recent score (reacts to attacks; average dilutes the signal)
  const threatValue = events.length
    ? Math.max(...events.map((e) => e.combined_score || 0))
    : 0;
  const bannerAlert = alerts.find(
    (a) => a.severity === "critical" || a.severity === "high",
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
    >
      {/* Row A — slim KPI cards */}
      <KpiCards kpis={kpis} events={events} />

      {/* Row B — attack banner (animates in only when high/critical alert exists) */}
      <AnimatePresence>
        <HighRiskBanner alert={bannerAlert} onInvestigate={onInvestigate} />
      </AnimatePresence>

      {/* Row C — live alert feed (hero) + threat gauge */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 mb-4">
        <div className="xl:col-span-7">
          <AlertFeed alerts={alerts.slice(0, 12)} onInvestigate={onInvestigate} />
        </div>
        <div className="xl:col-span-5">
          <div className="panel p-4 h-full flex items-center justify-center">
            <ThreatGauge value={threatValue} label="Current Threat Level" />
          </div>
        </div>
      </div>

      {/* Row D — score timeline + risk split */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 mb-4">
        <div className="xl:col-span-8 panel p-4">
          <ScoreTrend events={events} />
        </div>
        <div className="xl:col-span-4 panel p-4">
          <div className="text-xs uppercase tracking-wider text-ink-faint mb-2 font-semibold">
            Risk Split
          </div>
          <ResponsiveContainer width="100%" height={150}>
            <PieChart>
              <Pie
                data={riskDist}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={35}
                outerRadius={60}
                paddingAngle={2}
              >
                {riskDist.map((entry, i) => (
                  <Cell key={i} fill={entry.color || COLORS[entry.name?.toLowerCase()]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "#151a24",
                  border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 6,
                  fontSize: 11,
                }}
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
        </div>
      </div>

      {/* Row E — compact event table */}
      <EventTable events={events} onInvestigate={onInvestigate} maxRows={10} maxHeight={260} />
    </motion.div>
  );
}
