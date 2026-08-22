export default function ThreatRings({ kpis = {} }) {
  const rings = [
    {
      label: "Anomaly Rate",
      value: kpis.totalEvents > 0 ? (kpis.anomalies / kpis.totalEvents) * 100 : 0,
      color: "#e8a33d",
      max: 100,
    },
    {
      label: "Block Rate",
      value: kpis.totalEvents > 0 ? ((kpis.blocked || 0) / kpis.totalEvents) * 100 : 0,
      color: "#e5484d",
      max: 100,
    },
    {
      label: "Coverage",
      value: kpis.usersMonitored > 0 ? Math.min((kpis.usersMonitored / 4) * 100, 100) : 0,
      color: "#57b06c",
      max: 100,
    },
  ];

  const size = 140;
  const center = size / 2;
  const ringWidth = 10;
  const gap = 6;

  return (
    <div className="w-full">
      <div className="text-xs uppercase tracking-wider text-ink-faint mb-3 font-semibold">
        System Health
      </div>
      <div className="flex justify-center">
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {rings.map((ring, i) => {
            const r = center - ringWidth / 2 - i * (ringWidth + gap);
            const circumference = 2 * Math.PI * r;
            const pct = Math.min(ring.value / ring.max, 1);
            const dashoffset = circumference * (1 - pct);
            return (
              <g key={ring.label}>
                <circle
                  cx={center}
                  cy={center}
                  r={r}
                  fill="none"
                  stroke="rgba(255,255,255,0.06)"
                  strokeWidth={ringWidth}
                />
                <circle
                  cx={center}
                  cy={center}
                  r={r}
                  fill="none"
                  stroke={ring.color}
                  strokeWidth={ringWidth}
                  strokeDasharray={circumference}
                  strokeDashoffset={dashoffset}
                  strokeLinecap="round"
                  transform={`rotate(-90 ${center} ${center})`}
                  style={{ transition: "stroke-dashoffset 0.6s ease" }}
                />
              </g>
            );
          })}
          <text x={center} y={center - 4} textAnchor="middle" fill="#e8ecf4" fontSize={18} fontWeight={700}>
            {kpis.totalEvents || 0}
          </text>
          <text x={center} y={center + 12} textAnchor="middle" fill="#5a6274" fontSize={8}>
            EVENTS
          </text>
        </svg>
      </div>
      <div className="flex flex-col gap-1.5 mt-2">
        {rings.map((ring) => (
          <div key={ring.label} className="flex items-center justify-between text-[10px]">
            <div className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full" style={{ background: ring.color }} />
              <span className="text-ink-dim">{ring.label}</span>
            </div>
            <span className="text-ink font-semibold">{ring.value.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
