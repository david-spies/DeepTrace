import { useEffect, useRef } from "react";
import { createLiveSocket } from "@/utils/api";
import { useStore } from "@/store";
import type { TraceSpan, AnomalyAlert, TopologySnapshot } from "@/types";

/**
 * Subscribes to the DeepTrace live WebSocket feed and
 * merges incoming spans/alerts into the global store.
 */
export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const { pushAlert, setTopology, setMetrics, setAgents } = useStore();

  useEffect(() => {
    wsRef.current = createLiveSocket((data) => {
      const msg = data as Record<string, unknown>;

      // Incoming span — check for anomalies
      if (msg.agent_name && msg.span_id) {
        const span = msg as unknown as TraceSpan;
        if (span.has_anomaly && span.anomalies?.length) {
          span.anomalies.forEach((type) => {
            pushAlert({
              rule_id:     type,
              severity:    type.includes("CRITICAL") || type.includes("ZERO_TRUST") ? "CRITICAL" : "HIGH",
              agent:       span.agent_name,
              trace_id:    span.trace_id,
              span_id:     span.span_id,
              description: `${type} on ${span.agent_name}`,
              evidence:    { token_velocity: span.token_velocity },
              timestamp:   span.timestamp,
            });
          });
        }
        return;
      }

      // Topology snapshot push
      if (msg.nodes && msg.edges) {
        setTopology(msg as unknown as TopologySnapshot);
        return;
      }

      // Alert push
      if (msg.rule_id) {
        pushAlert(msg as unknown as AnomalyAlert);
        return;
      }

      // Metrics push
      if (msg.total_spans !== undefined) {
        setMetrics(msg as any);
        return;
      }
    });

    return () => wsRef.current?.close();
  }, [pushAlert, setTopology, setMetrics, setAgents]);

  return wsRef.current;
}
