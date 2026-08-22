import SeverityBadge from "../common/SeverityBadge";

export default function AlertFeed({ alerts, onInvestigate }) {
  if (!alerts?.length) {
    return (
      <div className="panel p-4 text-ink-faint text-xs text-center py-8">
        No alerts yet
      </div>
    );
  }

  return (
    <div className="panel p-4">
      <div className="text-xs uppercase tracking-wider text-ink-faint mb-3 font-semibold">
        Recent Alerts
      </div>
      <div className="space-y-2 max-h-[400px] overflow-y-auto">
        {alerts.map((a) => (
          <button
            key={a.id}
            onClick={() => onInvestigate?.(a.eventId)}
            className="w-full text-left p-3 rounded-md bg-paper-100 hover:bg-paper-200 transition-colors"
          >
            <div className="flex items-center justify-between mb-1">
              <SeverityBadge level={a.severity} />
              <span className="text-[10px] text-ink-faint">{a.timestamp}</span>
            </div>
            <div className="text-xs text-ink">
              {a.name || a.raw_id || `User ${a.user_id}`}
            </div>
            <div className="text-[11px] text-ink-dim mt-1">
              Score: {(a.combined_score ?? 0).toFixed(3)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
