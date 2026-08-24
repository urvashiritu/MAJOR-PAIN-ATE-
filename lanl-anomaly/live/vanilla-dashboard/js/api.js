const API = "";

async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${API}${path}`, opts);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const getDashboard     = ()       => api("GET", "/api/dashboard");
export const getAlerts        = ()       => api("GET", "/api/alerts");
export const getUsers         = ()       => api("GET", "/api/users");
export const getStats         = ()       => api("GET", "/api/stats");
export const getHealth        = ()       => api("GET", "/api/health");
export const getInvestigation = (id)     => api("GET", `/api/investigation/${id}`);
export const getUserProfile   = (id)     => api("GET", `/api/users/${id}/profile`);
export const ackAlert         = (id)     => api("POST", `/api/alerts/${id}/ack`);
export const resetDashboard   = ()       => api("POST", "/api/reset");

let _sse = null;
let _callbacks = {};

export function connectSSE(callbacks) {
  _callbacks = callbacks || {};
  if (_sse) _sse.close();
  _sse = new EventSource(`/events/stream`);
  _sse.addEventListener("open", () => _callbacks.onConnect?.());
  _sse.addEventListener("score", () => _callbacks.onScore?.());
  _sse.onerror = () => {
    _callbacks.onDisconnect?.();
    _sse.close();
    setTimeout(() => connectSSE(_callbacks), 3000);
  };
}

export function disconnectSSE() {
  if (_sse) { _sse.close(); _sse = null; }
}
