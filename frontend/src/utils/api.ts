const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8080";
const WS   = import.meta.env.VITE_WS_URL  ?? "ws://localhost:8080";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

// ── Topology ──────────────────────────────
export const fetchTopology    = () => request("/metrics/topology");
export const fetchSummary     = () => request("/metrics/summary");
export const fetchTokenDebt   = () => request("/metrics/token-debt");
export const fetchLatencyP    = (w = "1h") => request(`/metrics/latency-percentiles?window=${w}`);
export const fetchCostBreakdown = (w = "24h") => request(`/metrics/cost-breakdown?window=${w}`);

// ── Agents ────────────────────────────────
export const fetchAgents       = () => request("/agents/");
export const fetchAgent        = (name: string) => request(`/agents/${encodeURIComponent(name)}`);
export const fetchAgentSpans   = (name: string, limit = 50) =>
  request(`/agents/${encodeURIComponent(name)}/spans?limit=${limit}`);
export const fetchTokenHistory = (name: string, window = "1h") =>
  request(`/agents/${encodeURIComponent(name)}/token_history?window=${window}`);
export const killAgent         = (name: string, reason = "") =>
  request(`/agents/${encodeURIComponent(name)}/kill`, {
    method: "POST",
    body: JSON.stringify({ reason, operator: "dashboard" }),
  });
export const hotpatchAgent = (name: string, delta: string, reason = "") =>
  request(`/agents/${encodeURIComponent(name)}/hotpatch`, {
    method: "POST",
    body: JSON.stringify({ system_prompt_delta: delta, reason, operator: "dashboard" }),
  });

// ── Traces ────────────────────────────────
export const fetchTrace    = (id: string) => request(`/traces/${encodeURIComponent(id)}`);
export const fetchTimeline = (id: string) => request(`/traces/${encodeURIComponent(id)}/timeline`);
export const fetchMerkle   = (id: string) => request(`/traces/${encodeURIComponent(id)}/merkle`);
export const replayTrace   = (id: string, mods = {}) =>
  request(`/traces/${encodeURIComponent(id)}/replay`, {
    method: "POST",
    body: JSON.stringify({ modifications: mods, sandbox: true }),
  });

// ── Security ─────────────────────────────
export const fetchHeatmap          = () => request("/security/heatmap");
export const fetchAnomalies        = (resolved = false) =>
  request(`/security/anomalies?resolved=${resolved}`);
export const fetchViolations       = (hours = 24) =>
  request(`/security/violations?hours=${hours}`);
export const fetchPromptInjection  = () => request("/security/prompt-injection");
export const fetchAuditTrail       = (start: number, end: number) =>
  request(`/security/audit-trail?start_ts=${start}&end_ts=${end}`);

// ── WebSocket ────────────────────────────
export function createLiveSocket(
  onMessage: (data: unknown) => void,
  onClose?: () => void,
): WebSocket {
  const ws = new WebSocket(`${WS}/ws/live`);
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)); } catch { /* ignore parse errors */ }
  };
  ws.onclose = () => {
    onClose?.();
    // Auto-reconnect after 3s
    setTimeout(() => createLiveSocket(onMessage, onClose), 3000);
  };
  ws.onerror = () => ws.close();

  // Heartbeat ping every 25s
  const hb = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 25_000);
  ws.addEventListener("close", () => clearInterval(hb));

  return ws;
}
