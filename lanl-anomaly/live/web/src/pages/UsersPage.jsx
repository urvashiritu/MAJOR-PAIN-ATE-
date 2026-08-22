import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { getUsers } from "../hooks/useApi";

export default function UsersPage() {
  const [users, setUsers] = useState([]);

  useEffect(() => {
    getUsers().then(setUsers).catch(console.error);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
    >
      <h2 className="text-sm font-bold text-ink uppercase tracking-wider mb-4">Users</h2>

      <div className="panel overflow-hidden">
        <table className="table-glass">
          <thead>
            <tr>
              <th>User</th>
              <th>Raw ID</th>
              <th>Persona</th>
              <th>Live Events</th>
              <th>Flags</th>
              <th>Max Score</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.user_id}>
                <td className="text-ink font-bold">{u.name}</td>
                <td className="text-ink-dim">{u.raw_id}</td>
                <td>
                  <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded ${
                    u.persona === "attacker" ? "bg-critical/20 text-critical" : "bg-low/20 text-low"
                  }`}>
                    {u.persona}
                  </span>
                </td>
                <td className="text-ink">{u.live_events ?? 0}</td>
                <td className="text-ink">{u.flags ?? 0}</td>
                <td className="text-ink font-bold">{(u.max_score ?? 0).toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.div>
  );
}
