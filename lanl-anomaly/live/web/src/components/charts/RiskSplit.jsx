import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { PieChart, Pie, Cell, Sector, Tooltip, ResponsiveContainer } from "recharts";
import OdometerNumber from "../common/OdometerNumber";

const FRONT_COLORS = {
  low: "#57b06c",
  medium: "#e8a33d",
  high: "#ff9b9e",
  critical: "#e5484d",
};

const keyOf = (entry) => (entry.name || "").toLowerCase();

const colorOf = (entry) => entry.color || FRONT_COLORS[keyOf(entry)] || "#718296";

const renderActiveSector = (props) => {
  const { cx, cy, innerRadius, outerRadius, ...rest } = props;
  return (
    <g>
      <Sector {...rest} cx={cx} cy={cy} innerRadius={innerRadius} outerRadius={outerRadius + 7} />
      <Sector
        {...rest}
        cx={cx}
        cy={cy}
        innerRadius={innerRadius - 3}
        outerRadius={innerRadius - 1}
        fillOpacity={0.35}
      />
    </g>
  );
};

const RiskTooltip = ({ active, payload, total }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const share = total ? Math.round((d.value / total) * 100) : 0;
  return (
    <div className="chart-tooltip">
      <div className="flex items-center gap-1.5 mb-1">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{ background: colorOf(d), boxShadow: `0 0 6px ${colorOf(d)}66` }}
        />
        <span className="text-[10px] uppercase tracking-wider text-ink-dim font-semibold">
          {d.name}
        </span>
      </div>
      <div className="text-ink text-xs font-bold">
        <span style={{ color: colorOf(d) }}>{d.value}</span> events · {share}%
      </div>
    </div>
  );
};

export default function RiskSplit({ data = [], title = "Risk Split" }) {
  const [activeIdx, setActiveIdx] = useState(null);

  const total = useMemo(() => data.reduce((s, d) => s + (d.value || 0), 0), [data]);
  const hasData = data.length > 0 && total > 0;

  return (
    <div className="w-full">
      <div className="text-xs uppercase tracking-wider text-ink-faint mb-2 font-semibold">
        {title}
      </div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut", delay: 0.1 }}
        className="relative"
      >
        {hasData ? (
          <>
            <ResponsiveContainer width="100%" height={150}>
              <PieChart>
                <defs>
                  {data.map((entry) => {
                    const c = colorOf(entry);
                    return (
                      <linearGradient
                        key={`rs-g-${keyOf(entry)}`}
                        id={`rs-grad-${keyOf(entry)}`}
                        x1="0"
                        y1="0"
                        x2="0"
                        y2="1"
                      >
                        <stop offset="0%" stopColor={c} stopOpacity={1} />
                        <stop offset="100%" stopColor={c} stopOpacity={0.55} />
                      </linearGradient>
                    );
                  })}
                </defs>
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={38}
                  outerRadius={64}
                  paddingAngle={3}
                  cornerRadius={3}
                  stroke="none"
                  activeIndex={activeIdx ?? undefined}
                  activeShape={renderActiveSector}
                  isAnimationActive
                  animationBegin={250}
                  animationDuration={900}
                  onMouseEnter={(_, i) => setActiveIdx(i)}
                  onMouseLeave={() => setActiveIdx(null)}
                >
                  {data.map((entry) => (
                    <Cell
                      key={keyOf(entry)}
                      fill={`url(#rs-grad-${keyOf(entry)})`}
                      fillOpacity={activeIdx == null || activeIdx === data.indexOf(entry) ? 1 : 0.35}
                      style={{ transition: "fill-opacity 0.25s ease" }}
                    />
                  ))}
                </Pie>
                <Tooltip content={<RiskTooltip total={total} />} />
              </PieChart>
            </ResponsiveContainer>

            {/* center total */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none pb-4">
              <OdometerNumber value={total} className="text-lg font-bold text-ink leading-none" />
              <span className="text-[9px] uppercase tracking-wider text-ink-faint mt-0.5">
                events
              </span>
            </div>
          </>
        ) : (
          <div className="h-[150px] flex items-center justify-center text-ink-faint text-[10px]">
            No events yet
          </div>
        )}
      </motion.div>

      {/* hover-synced legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 justify-center">
        {data.map((r, i) => (
          <button
            key={keyOf(r)}
            type="button"
            onMouseEnter={() => setActiveIdx(i)}
            onMouseLeave={() => setActiveIdx(null)}
            className={`flex items-center gap-1.5 px-1 py-0.5 rounded transition-colors duration-150 cursor-pointer ${
              activeIdx === i ? "bg-[color:var(--wash)]" : ""
            }`}
          >
            <span
              className="w-1.5 h-1.5 rounded-full transition-transform duration-150"
              style={{
                background: colorOf(r),
                transform: activeIdx === i ? "scale(1.6)" : "scale(1)",
                boxShadow: activeIdx === i ? `0 0 8px ${colorOf(r)}88` : "none",
              }}
            />
            <span
              className={`text-[10px] transition-colors duration-150 ${
                activeIdx === i ? "text-ink font-semibold" : "text-ink-faint"
              }`}
            >
              {r.name}: {r.value}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
