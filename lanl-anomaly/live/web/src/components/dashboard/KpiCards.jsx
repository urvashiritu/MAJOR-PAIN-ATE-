import { motion } from "framer-motion";
import { Activity, ShieldAlert, UserX, Users } from "lucide-react";
import Sparkline from "../common/Sparkline";
import OdometerNumber from "../common/OdometerNumber";

const CARDS = [
  {
    key: "totalEvents",
    label: "Events Scored",
    Icon: Activity,
    color: "#6ea8e8",
  },
  {
    key: "anomalies",
    label: "Anomalies",
    Icon: ShieldAlert,
    color: "#e5484d",
  },
  {
    key: "highRiskUsers",
    label: "High-Risk Users",
    Icon: UserX,
    color: "#ff9b9e",
  },
  {
    key: "usersMonitored",
    label: "Users Monitored",
    Icon: Users,
    color: "#57b06c",
  },
];

const gridVariants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
};

const cardVariants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.4, 0, 0.2, 1] } },
};

export default function KpiCards({ kpis = {}, events = [] }) {
  return (
    <motion.div
      variants={gridVariants}
      initial="hidden"
      animate="show"
      className="grid grid-cols-2 xl:grid-cols-4 gap-4 mb-4"
    >
      {CARDS.map(({ key, label, Icon, color }) => {
        const value = kpis[key] || 0;
        const sparkData = events.slice(-20).map((e, i) => {
          if (key === "totalEvents") return { value: i + 1 };
          const upto = events.slice(0, i + 1);
          if (key === "anomalies")
            return { value: upto.filter((x) => x.decision === "flag" || x.decision === "block").length };
          if (key === "highRiskUsers")
            return {
              value: new Set(
                upto.filter((x) => x.decision === "flag" || x.decision === "block").map((x) => x.user_id),
              ).size,
            };
          return { value: new Set(upto.map((x) => x.user_id)).size };
        });

        return (
          <motion.div variants={cardVariants} key={key}>
            <div className="panel panel-hover p-3 h-full">
              <div className="flex items-start justify-between mb-2">
                <div className="p-2 border border-white/15">
                  <Icon size={15} style={{ color }} />
                </div>
                <span className="tape-label">{label}</span>
              </div>
              <div className="flex items-end justify-between gap-3">
                <div className="tape-perf pr-3 flex-1 min-w-0">
                  <p className="tape-num" style={{ color }}>
                    <OdometerNumber value={value} />
                  </p>
                  <div className="flex items-center gap-1.5 mt-1">
                    <span className="text-[10px] text-ink-faint uppercase tracking-widest">live</span>
                    <span className="live-dot" />
                  </div>
                </div>
                <div className="w-16 h-8 flex-shrink-0">
                  <Sparkline data={sparkData} color={color} height={32} />
                </div>
              </div>
            </div>
          </motion.div>
        );
      })}
    </motion.div>
  );
}
