import { useState } from "react";
import SeverityBadge from "../common/SeverityBadge";

const COLS = [
  { key: "name", label: "User" },
  { key: "src_computer", label: "Source" },
  { key: "dst_computer", label: "Dest" },
  { key: "auth_type", label: "Auth" },
  { key: "result", label: "Result" },
  { key: "combined_score", label: "Score" },
  { key: "decision", label: "Decision" },
  { key: "ts", label: "Time" },
];

export default function EventTable({ events, onInvestigate, maxRows, maxHeight }) {
  const [sortKey, setSortKey] = useState("combined_score");
  const [sortDir, setSortDir] = useState("desc");

  if (!events?.length) return null;

  const sorted = [...events].sort((a, b) => {
    const av = a[sortKey] ?? 0, bv = b[sortKey] ?? 0;
    if (typeof av === "string") return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortDir === "asc" ? av - bv : bv - av;
  });
  const rows = maxRows ? sorted.slice(0, maxRows) : sorted;

  const toggle = (key) => {
    if (sortKey === key) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 hairline">
        <div className="text-xs uppercase tracking-wider text-ink-faint font-semibold">
          Scored Events
        </div>
        {maxRows && sorted.length > rows.length && (
          <span className="text-[10px] text-ink-faint uppercase tracking-widest">
            top {rows.length} of {sorted.length}
          </span>
        )}
      </div>
      <div className="overflow-auto" style={maxHeight ? { maxHeight } : undefined}>
        <table className="table-glass">
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key} onClick={() => toggle(c.key)} className="cursor-pointer">
                  {c.label} {sortKey === c.key ? (sortDir === "asc" ? "↑" : "↓") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((e) => (
              <tr key={e.id} onClick={() => onInvestigate?.(e.id)} className="cursor-pointer">
                <td className="text-ink">{e.name || e.raw_id || e.user_id}</td>
                <td>{e.src_computer}</td>
                <td>{e.dst_computer}</td>
                <td>{e.auth_type}</td>
                <td>
                  <span className={e.result === "Success" ? "text-low" : "text-critical"}>
                    {e.result}
                  </span>
                </td>
                <td className="text-ink font-bold">{(e.combined_score ?? 0).toFixed(3)}</td>
                <td>
                  <SeverityBadge level={e.risk_level} />
                </td>
                <td className="text-ink-faint">{e.ts}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
