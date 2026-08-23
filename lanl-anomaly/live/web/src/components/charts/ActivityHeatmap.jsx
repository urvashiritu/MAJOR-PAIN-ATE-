import { useMemo } from "react";

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const LEVELS = [
  { min: 0, max: 0, cls: "heatmap-empty" },
  { min: 1, max: 2, cls: "heatmap-l1" },
  { min: 3, max: 5, cls: "heatmap-l2" },
  { min: 6, max: 9, cls: "heatmap-l3" },
  { min: 10, max: Infinity, cls: "heatmap-l4" },
];

function getLevel(count) {
  for (const l of LEVELS) {
    if (count >= l.min && count <= l.max) return l.cls;
  }
  return LEVELS[LEVELS.length - 1].cls;
}

function parseTime(ts) {
  if (!ts) return null;
  try {
    const parts = ts.split(":");
    return { hour: parseInt(parts[0], 10), min: parseInt(parts[1], 10) };
  } catch {
    return null;
  }
}

export default function ActivityHeatmap({ events = [] }) {
  const grid = useMemo(() => {
    const g = Array.from({ length: 7 }, () => Array(24).fill(0));
    events.forEach((e) => {
      const t = parseTime(e.ts);
      if (!t) return;
      const dayIdx = new Date().getDay();
      g[dayIdx][t.hour]++;
    });
    return g;
  }, [events]);

  const maxCount = useMemo(() => {
    let m = 0;
    grid.forEach((row) => row.forEach((c) => { if (c > m) m = c; }));
    return Math.max(m, 1);
  }, [grid]);

  const cellSize = 18;
  const gap = 2;
  const labelWidth = 28;
  const hourLabelHeight = 16;
  const width = labelWidth + 24 * (cellSize + gap);
  const height = 7 * (cellSize + gap) + hourLabelHeight;

  return (
    <div className="w-full">
      <div className="text-xs uppercase tracking-wider text-ink-faint mb-3 font-semibold">
        Activity Heatmap
      </div>
      <div className="overflow-x-auto">
        <svg width={width} height={height} className="block">
          {HOURS.map((h, i) => (
            <text
              key={h}
              x={labelWidth + i * (cellSize + gap) + cellSize / 2}
              y={10}
              textAnchor="middle"
              fill="#5a6274"
              fontSize={8}
            >
              {h % 3 === 0 ? `${h}` : ""}
            </text>
          ))}
          {DAYS.map((day, di) => (
            <g key={day}>
              <text
                x={labelWidth - 4}
                y={hourLabelHeight + di * (cellSize + gap) + cellSize / 2 + 3}
                textAnchor="end"
                fill="#5a6274"
                fontSize={9}
              >
                {day}
              </text>
              {HOURS.map((h, hi) => (
                <rect
                  key={`${di}-${hi}`}
                  x={labelWidth + hi * (cellSize + gap)}
                  y={hourLabelHeight + di * (cellSize + gap)}
                  width={cellSize}
                  height={cellSize}
                  rx={3}
                  className={`heatmap-cell ${getLevel(grid[di][hi])}`}
                  strokeWidth={0.5}
                >
                  <title>{`${day} ${h}:00 — ${grid[di][hi]} events`}</title>
                </rect>
              ))}
            </g>
          ))}
        </svg>
      </div>
      <div className="flex items-center gap-2 mt-2">
        <span className="text-[9px] text-ink-faint">Less</span>
        {LEVELS.map((l, i) => (
          <div
            key={i}
            className="w-3 h-3 rounded-sm"
            style={{ background: l.fill }}
            title={`${l.min === 0 ? "0" : l.min + "+"} events`}
          />
        ))}
        <span className="text-[9px] text-ink-faint">More</span>
      </div>
    </div>
  );
}
