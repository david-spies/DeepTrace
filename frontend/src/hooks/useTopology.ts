import { useEffect, useRef, useCallback } from "react";
import * as d3 from "d3";
import type { TopologyNode, TopologyEdge } from "@/types";

interface UseTopologyOptions {
  nodes:    TopologyNode[];
  edges:    TopologyEdge[];
  width:    number;
  height:   number;
  onSelect: (node: TopologyNode) => void;
}

const STATUS_COLOR: Record<string, string> = {
  ok:     "#00e5a0",
  warn:   "#ffb347",
  err:    "#ff4560",
  idle:   "#4d6a82",
  killed: "#4d6a82",
  SYSTEM: "#ff6b9d",
};

const LATENCY_EDGE_COLOR = (latency?: number, blocked?: boolean): string => {
  if (blocked) return "#ff4560";
  if (!latency || latency < 200) return "#00e5a0";
  if (latency < 2000) return "#ffb347";
  return "#ff4560";
};

const NODE_RADIUS = (node: TopologyNode): number => {
  const base = node.id.toLowerCase().includes("db") ||
               node.id.toLowerCase().includes("system") ? 18 : 24;
  const tokenBoost = Math.min(14, Math.sqrt((node.token_total ?? 0) / 500));
  return base + tokenBoost;
};

export function useTopology({ nodes, edges, width, height, onSelect }: UseTopologyOptions) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simRef = useRef<d3.Simulation<TopologyNode, TopologyEdge> | null>(null);

  const redraw = useCallback(() => {
    if (!svgRef.current || !nodes.length) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    // ── Defs ────────────────────────────────────────
    const defs = svg.append("defs");

    // Arrow markers per latency tier
    ["#00e5a0", "#ffb347", "#ff4560", "#4d6a82"].forEach((col, i) => {
      defs.append("marker")
        .attr("id", `arrow-${i}`)
        .attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5)
        .attr("markerWidth", 5).attr("markerHeight", 5)
        .attr("orient", "auto-start-reverse")
        .append("path")
        .attr("d", "M1 1L9 5L1 9")
        .attr("fill", "none").attr("stroke", col)
        .attr("stroke-width", 1.5).attr("stroke-linecap", "round");
    });

    // Glow filter
    const glow = defs.append("filter").attr("id", "glow");
    glow.append("feGaussianBlur").attr("stdDeviation", 3).attr("result", "blur");
    const merge = glow.append("feMerge");
    merge.append("feMergeNode").attr("in", "blur");
    merge.append("feMergeNode").attr("in", "SourceGraphic");

    // ── Background grid ──────────────────────────────
    const grid = svg.append("g").attr("class", "grid");
    const step = 40;
    for (let x = 0; x < width; x += step) {
      grid.append("line")
        .attr("x1", x).attr("y1", 0).attr("x2", x).attr("y2", height)
        .attr("stroke", "rgba(0,212,255,0.03)").attr("stroke-width", 0.5);
    }
    for (let y = 0; y < height; y += step) {
      grid.append("line")
        .attr("x1", 0).attr("y1", y).attr("x2", width).attr("y2", y)
        .attr("stroke", "rgba(0,212,255,0.03)").attr("stroke-width", 0.5);
    }

    // ── Zoom container ───────────────────────────────
    const container = svg.append("g").attr("class", "container");
    svg.call(
      d3.zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.3, 4])
        .on("zoom", (e) => container.attr("transform", e.transform))
    );

    // ── Simulation ───────────────────────────────────
    const sim = d3.forceSimulation<TopologyNode>(nodes)
      .force("link", d3.forceLink<TopologyNode, TopologyEdge>(edges)
        .id((d) => d.id)
        .distance(130)
        .strength(0.4))
      .force("charge", d3.forceManyBody().strength(-600))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide<TopologyNode>((d) => NODE_RADIUS(d) + 20))
      .alphaDecay(0.03);
    simRef.current = sim;

    // ── Edges ────────────────────────────────────────
    const arrowMarker = (e: TopologyEdge) => {
      const col = LATENCY_EDGE_COLOR(e.latency_ms, e.blocked);
      if (col === "#00e5a0") return "url(#arrow-0)";
      if (col === "#ffb347") return "url(#arrow-1)";
      if (col === "#ff4560") return "url(#arrow-2)";
      return "url(#arrow-3)";
    };

    const linkGroup = container.append("g").attr("class", "links");
    const link = linkGroup.selectAll<SVGLineElement, TopologyEdge>("line")
      .data(edges)
      .join("line")
      .attr("stroke", (e) => LATENCY_EDGE_COLOR(e.latency_ms, e.blocked))
      .attr("stroke-opacity", 0.5)
      .attr("stroke-width", (e) => Math.max(0.5, Math.min(3, (e.weight ?? 1) * 0.15)))
      .attr("stroke-dasharray", (e) => e.blocked ? "5,4" : null)
      .attr("marker-end", arrowMarker);

    // Animated pulse dots on edges
    const pulseGroup = container.append("g").attr("class", "pulses");

    // ── Nodes ────────────────────────────────────────
    const nodeGroup = container.append("g").attr("class", "nodes");
    const nodeEl = nodeGroup.selectAll<SVGGElement, TopologyNode>("g")
      .data(nodes, (d) => d.id)
      .join("g")
      .attr("class", "node")
      .style("cursor", "pointer")
      .call(
        d3.drag<SVGGElement, TopologyNode>()
          .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag",  (e, d) => { d.fx = e.x; d.fy = e.y; })
          .on("end",   (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
      )
      .on("click", (_, d) => onSelect(d));

    // Glow halo for anomalous / selected nodes
    nodeEl.append("circle")
      .attr("r", (d) => NODE_RADIUS(d) * 2)
      .attr("fill", (d) => {
        if (d.has_anomaly) return "rgba(155,109,255,0.15)";
        if (d.status === "err") return "rgba(255,69,96,0.12)";
        return "rgba(0,212,255,0.05)";
      })
      .attr("stroke", "none");

    // Token ring arc (shows budget pressure)
    nodeEl.each(function(d) {
      if (!d.token_total) return;
      const pct = Math.min(1, d.token_total / 8000);
      const r = NODE_RADIUS(d) + 5;
      const arc = d3.arc<unknown>()
        .innerRadius(r - 1.5)
        .outerRadius(r + 0.5)
        .startAngle(-Math.PI / 2)
        .endAngle(-Math.PI / 2 + pct * Math.PI * 2);
      d3.select(this).append("path")
        .attr("d", arc as any)
        .attr("fill", pct > 0.85 ? "#ff4560" : pct > 0.6 ? "#ffb347" : "#00e5a0")
        .attr("opacity", 0.8);
    });

    // Main circle
    nodeEl.append("circle")
      .attr("r", (d) => NODE_RADIUS(d))
      .attr("fill", (d) => {
        const col = STATUS_COLOR[d.status] ?? STATUS_COLOR.idle;
        return col + "22";
      })
      .attr("stroke", (d) => STATUS_COLOR[d.status] ?? STATUS_COLOR.idle)
      .attr("stroke-width", 1.5);

    // Label
    nodeEl.append("text")
      .text((d) => d.id.substring(0, 2).toUpperCase())
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "central")
      .attr("fill", (d) => STATUS_COLOR[d.status] ?? STATUS_COLOR.idle)
      .attr("font-size", 9)
      .attr("font-weight", 700)
      .attr("font-family", "JetBrains Mono, monospace")
      .attr("dy", -3);

    // Name below node
    nodeEl.append("text")
      .text((d) => d.id)
      .attr("text-anchor", "middle")
      .attr("dy", (d) => NODE_RADIUS(d) + 13)
      .attr("fill", "#8ba8c4")
      .attr("font-size", 9)
      .attr("font-family", "JetBrains Mono, monospace");

    // Status dot
    nodeEl.append("circle")
      .attr("r", 4)
      .attr("cx", (d) => NODE_RADIUS(d) * 0.7)
      .attr("cy", (d) => -NODE_RADIUS(d) * 0.7)
      .attr("fill", (d) => STATUS_COLOR[d.status] ?? STATUS_COLOR.idle);

    // ── Tick ─────────────────────────────────────────
    sim.on("tick", () => {
      link
        .attr("x1", (e) => (e.source as TopologyNode).x ?? 0)
        .attr("y1", (e) => (e.source as TopologyNode).y ?? 0)
        .attr("x2", (e) => (e.target as TopologyNode).x ?? 0)
        .attr("y2", (e) => (e.target as TopologyNode).y ?? 0);
      nodeEl.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });
  }, [nodes, edges, width, height, onSelect]);

  useEffect(() => {
    redraw();
    return () => { simRef.current?.stop(); };
  }, [redraw]);

  return svgRef;
}
