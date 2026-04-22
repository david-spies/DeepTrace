import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";
import type {
  Agent, TopologySnapshot, AnomalyAlert,
  MetricsSummary, TraceSpan, TimelineEvent,
} from "@/types";

// ─────────────────────────────────────────
// STATE SHAPE
// ─────────────────────────────────────────

interface DeepTraceState {
  // Live topology
  topology:      TopologySnapshot;
  setTopology:   (t: TopologySnapshot) => void;

  // Agent list + selection
  agents:        Agent[];
  setAgents:     (a: Agent[]) => void;
  selectedAgent: Agent | null;
  selectAgent:   (a: Agent | null) => void;

  // Active trace detail
  activeTrace:   TraceSpan | null;
  setActiveTrace:(t: TraceSpan | null) => void;

  // Time travel
  timelineEvents:  TimelineEvent[];
  setTimeline:     (e: TimelineEvent[]) => void;
  scrubPosition:   number;            // 0–100
  setScrubPosition:(n: number) => void;

  // Alerts
  alerts:        AnomalyAlert[];
  pushAlert:     (a: AnomalyAlert) => void;
  clearAlert:    (span_id: string) => void;

  // Metrics
  metrics:       MetricsSummary | null;
  setMetrics:    (m: MetricsSummary) => void;

  // Live mode
  liveMode:      boolean;
  setLiveMode:   (v: boolean) => void;

  // Current view
  view: "topology" | "timetravel" | "security" | "metrics";
  setView: (v: DeepTraceState["view"]) => void;
}

// ─────────────────────────────────────────
// STORE
// ─────────────────────────────────────────

export const useStore = create<DeepTraceState>()(
  subscribeWithSelector((set) => ({
    topology:     { nodes: [], edges: [] },
    setTopology:  (t) => set({ topology: t }),

    agents:       [],
    setAgents:    (a) => set({ agents: a }),
    selectedAgent: null,
    selectAgent:   (a) => set({ selectedAgent: a }),

    activeTrace:    null,
    setActiveTrace: (t) => set({ activeTrace: t }),

    timelineEvents:  [],
    setTimeline:     (e) => set({ timelineEvents: e }),
    scrubPosition:   100,
    setScrubPosition:(n) => set({ scrubPosition: n }),

    alerts:    [],
    pushAlert: (a) =>
      set((s) => ({
        alerts: [a, ...s.alerts.filter((x) => x.span_id !== a.span_id)].slice(0, 200),
      })),
    clearAlert: (span_id) =>
      set((s) => ({ alerts: s.alerts.filter((a) => a.span_id !== span_id) })),

    metrics:    null,
    setMetrics: (m) => set({ metrics: m }),

    liveMode:    true,
    setLiveMode: (v) => set({ liveMode: v }),

    view:    "topology",
    setView: (v) => set({ view: v }),
  }))
);
