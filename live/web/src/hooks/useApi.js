const API_BASE = '/api'

async function fetchJson(url, opts = {}) {
  const res = await fetch(`${API_BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function getDashboard() {
  return fetchJson('/dashboard')
}

export async function getAlerts() {
  return fetchJson('/alerts')
}

export async function getAlertDetail(id) {
  return fetchJson(`/alerts/${id}`)
}

export async function acknowledgeAlert(id) {
  return fetchJson(`/alerts/${id}/ack`, { method: 'POST' })
}

export async function getInvestigation(id) {
  return fetchJson(`/investigation/${id}`)
}

export async function getMapData() {
  return fetchJson('/map')
}

export async function getUsers() {
  return fetchJson('/users')
}

export async function getDatasetSummary() {
  return fetchJson('/dataset/summary')
}

export async function getDatasetRows(params = {}) {
  const clean = Object.entries(params).filter(([, v]) => v !== undefined)
  const qs = new URLSearchParams(clean).toString()
  return fetchJson(`/dataset/rows${qs ? `?${qs}` : ''}`)
}

export async function healthCheck() {
  return fetchJson('/health')
}
