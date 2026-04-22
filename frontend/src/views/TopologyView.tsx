import React, { useEffect, useRef, useState } from "react";
import { useStore } from "@/store";
import { useTopology } from "@/hooks/useTopology";
import { fetchTopology } from "@/utils/api";
import type { TopologyNode } from "@/types";

export function TopologyView() {
  const { topology, setTopology, selectAgent, liveMode, setLiveMode } = useStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ w: 800, h: 600 });

  // Fit SVG to container
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      setDims({ w: entry.contentRect.width, h: entry.contentRect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Poll topology when live
  useEffect(() => {
    if (!liveMode) return;
    const poll = async () => {
      try {
        const data = await fetchTopology() as any;
        // Normalise edge source/target to string ids for D3
        const edges = (data.edges ?? []).map((e: any) => ({
          ...e,
          source: e.from,
          target: e.to,
        }));
        setTopology({ nodes: data.nodes ?? [], edges });
      } catch { /* silent */ }
    };
    poll();
    const iv = setInterval(poll, 4000);
    return () => clearInterval(iv);
  }, [liveMode, setTopology]);

  const handleSelect = (node: TopologyNode) => {
    const agent = {
      name:             node.id,
      status:           (node.status ?? "idle") as any,
      model:            node.model ?? "",
      roles:            node.roles ?? [],
      token_total:      node.token_total ?? 0,
      call_count:       node.calls ?? 0,
      environment:      node.environment ?? "",
      has_anomaly:      node.has_anomaly ?? false,
      last_seen:        Date.now() / 1000,
      system_resources: [],
    };
    selectAgent(agent);
  };

  const svgRef = useTopology({
    nodes:    topology.nodes as any,
    edges:    topology.edges as any,
    width:    dims.w,
    height:   dims.h,
    onSelect: handleSelect,
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* Toolbar */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8, padding: "8px 12px",
        background: "var(--bg1)", borderBottom: "1px solid var(--border)", flexShrink: 0,
      }}>
        <button
          className={`toolbar-btn ${liveMode ? "active" : ""}`}
          onClick={() => setLiveMode(!liveMode)}
        >
          {liveMode ? "◉ Live" : "◎ Paused"}
        </button>
        <div className="toolbar-sep" />
        <LegendDot color="var(--green)" label="healthy" />
        <LegendDot color="var(--amber)" label="warning" />
        <LegendDot color="var(--red)"   label="error" />
        <LegendDot color="var(--purple)"label="anomaly" />
        <div className="toolbar-sep" />
        <span style={{ fontSize: 9, color: "var(--text2)" }}>
          edge: <span style={{ color: "var(--green)" }}>green</span> &lt;200ms&nbsp;
          <span style={{ color: "var(--amber)" }}>amber</span> &lt;2s&nbsp;
          <span style={{ color: "var(--red)" }}>red</span> &gt;2s
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 9, color: "var(--text2)" }}>
          {topology.nodes.length} nodes · {topology.edges.length} edges
        </span>
      </div>

      {/* Canvas */}
      <div ref={containerRef} style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        <svg
          ref={svgRef}
          width={dims.w}
          height={dims.h}
          style={{ display: "block" }}
        />
        {topology.nodes.length === 0 && (
          <div style={{
            position: "absolute", inset: 0, display: "flex", alignItems: "center",
            justifyContent: "center", flexDirection: "column", gap: 12,
            color: "var(--text2)", fontSize: 12,
          }}>
            <span style={{ fontSize: 28, opacity: 0.3 }}>◈</span>
            <span>No agents detected — instrument your agents with the DeepTrace SDK</span>
          </div>
        )}
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9, color: "var(--text2)" }}>
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: color, display: "inline-block" }} />
      {label}
    </span>
  );
}
