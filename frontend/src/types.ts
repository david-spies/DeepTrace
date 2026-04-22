// ─────────────────────────────────────────
// CORE DOMAIN TYPES
// ─────────────────────────────────────────

export type SpanStatus = "STARTED" | "COMPLETED" | "FAILED" | "KILLED" | "BLOCKED";
export type SpanKind   = "AGENT" | "LLM_CALL" | "TOOL_CALL" | "SPAWN" | "CONTEXT";
export type AgentStatus = "ok" | "warn" | "err" | "idle" | "killed";
export type LatencyTier = "fast" | "normal" | "slow";
export type Severity    = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface ToolInvocation {
  tool_name:   string;
  inputs:      Record<string, unknown>;
  output?:     string;
  blocked:     boolean;
  duration_ms: number;
  merkle_hash: string;
}

export interface TraceSpan {
  trace_id:           string;
  span_id:            string;
  parent_span_id?:    string;
  agent_name:         string;
  roles:              string[];
  kind:               SpanKind;
  status:             SpanStatus;
  timestamp:          number;
  duration_ms:        number;
  model:              string;
  token_input:        number;
  token_output:       number;
  token_total:        number;
  token_velocity:     number;
  latency_tier:       LatencyTier;
  context_fragment_pct: number;
  tool_invocations:   ToolInvocation[];
  system_resources:   string[];
  anomalies:          string[];
  has_anomaly:        boolean;
  error?:             string;
  metadata:           Record<string, unknown>;
  service_name:       string;
  environment:        string;
  cost_usd:           number;
  children?:          TraceSpan[];
}

export interface Agent {
  name:             string;
  status:           AgentStatus;
  model:            string;
  roles:            string[];
  token_total:      number;
  call_count:       number;
  environment:      string;
  has_anomaly:      boolean;
  last_seen:        number;
  system_resources: string[];
  blocked_resources?: string[];
}

// ─────────────────────────────────────────
// TOPOLOGY GRAPH
// ─────────────────────────────────────────

export interface TopologyNode {
  id:          string;
  status:      string;
  model:       string;
  roles:       string[];
  token_total: number;
  calls:       number;
  has_anomaly: boolean;
  environment: string;
  // D3 physics fields (added at runtime)
  x?:  number;
  y?:  number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
}

export interface TopologyEdge {
  from:       string;
  to:         string;
  source:     string | TopologyNode;
  target:     string | TopologyNode;
  weight:     number;
  latency_ms?: number;
  blocked?:   boolean;
  kind:       string;
  relation?:  string;
}

export interface TopologySnapshot {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

// ─────────────────────────────────────────
// ANOMALY / SECURITY
// ─────────────────────────────────────────

export interface AnomalyAlert {
  id?:          string;
  rule_id:      string;
  severity:     Severity;
  agent:        string;
  trace_id:     string;
  span_id:      string;
  description:  string;
  evidence:     Record<string, unknown>;
  timestamp:    number;
  resolved?:    boolean;
}

export interface PermissionCell {
  value: "ALLOWED" | "BLOCKED" | "ANOMALY" | "NONE";
  count?: number;
}

export interface PermissionMatrix {
  agents:    string[];
  resources: string[];
  cells:     Record<string, string>;   // "AgentName-ResourceName" -> status
}

// ─────────────────────────────────────────
// METRICS
// ─────────────────────────────────────────

export interface MetricsSummary {
  total_spans:    number;
  anomaly_count:  number;
  total_tokens:   number;
  total_cost:     number;
  avg_latency:    number;
  p99_latency:    number;
  unique_agents:  number;
  unique_traces:  number;
}

export interface TokenHistoryPoint {
  minute:      string;
  tokens:      number;
  avg_latency: number;
  spans:       number;
}

export interface LatencyPercentile {
  agent_name: string;
  p50:        number;
  p90:        number;
  p99:        number;
  avg:        number;
  max:        number;
}

export interface CostBreakdown {
  agent_name: string;
  model:      string;
  cost:       number;
  tokens:     number;
}

// ─────────────────────────────────────────
// TIMELINE (Time-Travel)
// ─────────────────────────────────────────

export interface TimelineEvent {
  t:           number;
  agent:       string;
  kind:        SpanKind | "TOOL_CALL";
  status:      SpanStatus;
  duration_ms: number;
  token_total: number;
  anomalies:   string[];
  span_id:     string;
  tool?:       string;
  merkle_hash?: string;
}

// ─────────────────────────────────────────
// WEBSOCKET MESSAGES
// ─────────────────────────────────────────

export type WsMessageType =
  | "SPAN"
  | "ALERT"
  | "TOPOLOGY_UPDATE"
  | "AGENT_KILLED"
  | "HOTPATCH"
  | "PONG";

export interface WsMessage {
  type:    WsMessageType;
  payload: unknown;
  ts:      number;
}
