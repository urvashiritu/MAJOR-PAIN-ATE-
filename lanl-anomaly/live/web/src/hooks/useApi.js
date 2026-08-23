const BASE = "/api";

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export async function getDashboard() { return get("/dashboard"); }
export async function getAlerts() { return get("/alerts"); }
export async function getUsers() { return get("/users"); }
export async function getHealth() { return get("/health"); }
export async function getInvestigation(eventId) { return get(`/investigation/${eventId}`); }
export async function getUserProfile(userId) { return get(`/users/${userId}/profile`); }
export async function ackAlert(alertId) { return post(`/alerts/${alertId}/ack`); }
export async function getStats() { return get("/stats"); }
export async function resetDashboard() { return post("/reset"); }
