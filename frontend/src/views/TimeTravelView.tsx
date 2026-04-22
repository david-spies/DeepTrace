import React, { useEffect, useState } from "react";
import { useStore } from "@/store";
import { fetchTimeline } from "@/utils/api";
import type { TimelineEvent } from "@/types";
import { formatDistanceToNowStrict } from "date-fns";

const STATUS_COLOR: Record<string, string> = {
  COMPLETED: "var(--cyan)",
  FAILED:    "var(--red)",
  BLOCKED:   "var(--red)",
  STARTED:   "var(--text2)",
  KILLED:    "var(--amber)",
};

const AGENT_COLORS: Record<string, string> = {};
const PALETTE = ["#3b9eff", "#00e5a0", "#00d4ff", "#ffb347", "#9b6dff", "#ff6b9d", "#ff4560"];
let colorIdx = 0;
const agentColor = (name: string) => {
  if (!AGENT_COLORS[name]) AGENT_COLORS[name] = PALETTE[colorIdx++ % PALETTE.length];
  return AGENT_COLORS[name];
};

export function TimeTravelView() {
  const { activeTrace, timelineEvents, setTimeline, scrubPosition, setScrubPosition } = useStore();
  const [loading, setLoading] = useState(false);
  const [traceId, setTraceId] = useState("");
  const [inputId, setInputId] = useState("");

  useEffect(() => {
    if (activeTrace?.trace_id && activeTrace.trace_id !== traceId) {
      setTraceId(activeTrace.trace_id);
    }
  }, [activeTrace]);

  useEffect(() => {
    if (!traceId) return;
    setLoading(true);
    fetchTimeline(traceId)
      .then((data: any) => {
        setTimeline(data.events ?? []);
        setScrubPosition(100);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [traceId, setTimeline, setScrubPosition]);

  const visibleCount = Math.max(1, Math.round((scrubPosition / 100) * timelineEvents.length));
  const visibleEvents = timelineEvents.slice(0, visibleCount);
  const currentEvent = timelineEvents[visibleCount - 1];

  const timeOffset = (t: number): string => {
    if (!timelineEvents.length) return "T+0.0s";
    const base = timelineEvents[0].t;
    return `T+${(t - base).toFixed(2)}s`;
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* Header */}
      <div style={{
        padding: "10px 14px", background: "var(--bg1)",
        borderBottom: "1px solid var(--border)", flexShrink: 0,
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <input
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") setTraceId(inputId); }}
          placeholder="Enter trace ID…"
          style={{
            flex: 1, background: "var(--bg3)", border: "1px solid var(--border2)",
            borderRadius: 3, padding: "4px 8px", fontSize: 11,
            color: "var(--text0)", fontFamily: "JetBrains Mono, monospace",
          }}
        />
        <button
          className="toolbar-btn"
          onClick={() => setTraceId(inputId)}
          disabled={!inputId}
        >
          Load
        </button>
        {traceId && (
          <span style={{ fontSize: 9, color: "var(--cyan)", fontFamily: "monospace" }}>
            {traceId.substring(0, 20)}…
          </span>
        )}
      </div>

      {/* Events */}
      <div style={{ flex: 1, overflowY: "auto", padding: "10px 14px" }}
           className="tt-events-scroll">
        {loading && (
          <div style={{ color: "var(--text2)", fontSize: 11, padding: "20px 0", textAlign: "center" }}>
            Loading trace…
          </div>
        )}
        {!loading && !timelineEvents.length && (
          <div style={{ color: "var(--text2)", fontSize: 11, padding: "20px 0", textAlign: "center" }}>
            No events — load a trace ID above, or click an agent node and press "Trace"
          </div>
        )}
        {visibleEvents.map((ev, i) => (
          <EventRow
            key={`${ev.span_id}-${i}`}
            event={ev}
            isCurrent={i === visibleCount - 1}
            timeLabel={timeOffset(ev.t)}
          />
        ))}
      </div>

      {/* Scrubber */}
      <div style={{
        padding: "10px 14px", background: "var(--bg1)",
        borderTop: "1px solid var(--border)", flexShrink: 0,
      }}>
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          fontSize: 9, color: "var(--text2)", marginBottom: 6,
          textTransform: "uppercase", letterSpacing: "0.1em",
        }}>
          <span>Trace Timeline — Scrub to replay</span>
          <span style={{ color: "var(--cyan)" }}>
            {currentEvent ? timeOffset(currentEvent.t) : "T+0.0s"}
            {" "}· event {visibleCount}/{timelineEvents.length}
          </span>
        </div>
        <input
          type="range" min={0} max={100} value={scrubPosition}
          onChange={(e) => setScrubPosition(Number(e.target.value))}
          style={{ width: "100%", accentColor: "var(--cyan)", cursor: "pointer" }}
        />
      </div>
    </div>
  );
}

function EventRow({
  event, isCurrent, timeLabel,
}: { event: TimelineEvent; isCurrent: boolean; timeLabel: string }) {
  const hasAnomaly = event.anomalies.length > 0;
  const statusColor = STATUS_COLOR[event.status] ?? "var(--text2)";
  const aColor = agentColor(event.agent);

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "60px 110px 1fr 60px",
      gap: 8, padding: "5px 8px",
      borderRadius: 3,
      marginBottom: 2,
      borderBottom: "1px solid var(--border)",
      background: isCurrent
        ? "rgba(0,212,255,0.05)"
        : hasAnomaly ? "rgba(155,109,255,0.07)" : "transparent",
      borderLeft: hasAnomaly ? "2px solid var(--purple)" : "2px solid transparent",
      fontSize: 10, lineHeight: 1.5,
      transition: "background 0.2s",
    }}>
      <span style={{ color: statusColor, fontFamily: "monospace", fontSize: 9 }}>
        {timeLabel}
      </span>
      <span style={{ color: aColor, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        [{event.agent.substring(0, 12)}]
      </span>
      <span style={{ color: hasAnomaly ? "var(--purple)" : "var(--text1)" }}>
        {event.tool ? `🔧 ${event.tool}: ` : ""}
        {(event as any).desc ?? `${event.kind} — ${event.status}`}
        {hasAnomaly && (
          <span style={{ marginLeft: 6, fontSize: 8, color: "var(--purple)" }}>
            ⚠ {event.anomalies.join(", ")}
          </span>
        )}
      </span>
      <span style={{ color: "var(--amber)", textAlign: "right", fontSize: 9 }}>
        {event.token_total ? `+${event.token_total} tok` : ""}
      </span>
    </div>
  );
}
