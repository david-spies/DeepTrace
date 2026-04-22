import React, { useEffect, useState } from "react";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import {
  fetchSummary, fetchTokenDebt, fetchLatencyP, fetchCostBreakdown,
} from "@/utils/api";
import type { MetricsSummary, LatencyPercentile, CostBreakdown } from "@/types";

// ─────────────────────────────────────────
// Shared styles
// ─────────────────────────────────────────
const CHART_STYLE = {
  background: "transparent",
  fontSize: 9,
  fontFamily: "JetBrains Mono, monospace",
};

const AXIS_STYLE = {
  tick: { fill: "#4d6a82", fontSize: 9 },
  axisLine: { stroke: "#1e2d3d" },
  tickLine: false as const,
};

const GRID_STYLE = { stroke: "#1e2d3d", strokeDasharray: "3 3" };

const TOOLTIP_STYLE = {
  contentStyle: {
    background: "#131920", border: "1px solid #2a3f54",
    borderRadius: 4, fontSize: 10,
    fontFamily: "JetBrains Mono, monospace",
  },
  labelStyle: { color: "#8ba8c4" },
  itemStyle:  { color: "#e8f0f8" },
};

function MetricCard({
  label, value, sub, color = "var(--cyan)",
}: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div style={{
      background: "var(--bg2)", border: "1px solid var(--border)",
      borderRadius: 4, padding: "10px 12px", flex: 1, minWidth: 0,
    }}>
      <div style={{ fontSize: 8, color: "var(--text2)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, color, fontFamily: "Syne, sans-serif" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 9, color: "var(--text2)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

// ─────────────────────────────────────────
// METRICS VIEW
// ─────────────────────────────────────────
export function MetricsView() {
  const [summary, setSummary]     = useState<MetricsSummary | null>(null);
  const [tokenDebt, setTokenDebt] = useState<any[]>([]);
  const [latency, setLatency]     = useState<LatencyPercentile[]>([]);
  const [costs, setCosts]         = useState<CostBreakdown[]>([]);
  const [window, setWindow]       = useState("1h");
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      fetchSummary().then((d) => setSummary(d as any)),
      fetchTokenDebt().then((d: any) => setTokenDebt(d.ranking ?? [])),
      fetchLatencyP(window).then((d: any) => setLatency(d.percentiles ?? [])),
      fetchCostBreakdown("24h").then((d: any) => setCosts(d.breakdown ?? [])),
    ]).finally(() => setLoading(false));
  }, [window]);

  if (loading && !summary) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
        color: "var(--text2)", fontSize: 11 }}>
        Loading metrics…
      </div>
    );
  }

  const totalCost = costs.reduce((s, c) => s + (c.cost ?? 0), 0);

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 16 }}>

      {/* Summary cards */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <MetricCard
          label="Total Tokens"
          value={summary ? ((summary.total_tokens ?? 0) / 1000).toFixed(1) + "k" : "—"}
          sub="last 24h"
          color="var(--cyan)"
        />
        <MetricCard
          label="Anomalies"
          value={summary?.anomaly_count ?? "—"}
          sub="active alerts"
          color="var(--red)"
        />
        <MetricCard
          label="Session Cost"
          value={`$${totalCost.toFixed(2)}`}
          sub="USD est."
          color="var(--amber)"
        />
        <MetricCard
          label="Avg Latency"
          value={summary ? Math.round(summary.avg_latency ?? 0) + "ms" : "—"}
          sub={`P99 ${Math.round(summary?.p99_latency ?? 0)}ms`}
          color="var(--green)"
        />
        <MetricCard
          label="Agents"
          value={summary?.unique_agents ?? "—"}
          sub={`${summary?.unique_traces ?? 0} traces`}
          color="var(--purple)"
        />
      </div>

      {/* Token Debt Bar Chart */}
      <ChartSection title="Token Debt by Agent" subtitle="High-to-low token consumption — prune verbose agents">
        {tokenDebt.length > 0 ? (
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={tokenDebt.slice(0, 12)}
              layout="vertical"
              style={CHART_STYLE}
              margin={{ top: 0, right: 16, left: 0, bottom: 0 }}
            >
              <CartesianGrid {...GRID_STYLE} horizontal={false} />
              <XAxis type="number" {...AXIS_STYLE}
                tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v} />
              <YAxis type="category" dataKey="agent_name" width={90} {...AXIS_STYLE}
                tick={{ ...AXIS_STYLE.tick, fontSize: 9 }} />
              <Tooltip {...TOOLTIP_STYLE}
                formatter={(v: any) => [v.toLocaleString(), "Tokens"]} />
              <Bar dataKey="total_tokens" radius={[0, 3, 3, 0]}>
                {tokenDebt.slice(0, 12).map((entry, i) => (
                  <Cell
                    key={i}
                    fill={
                      entry.total_tokens > 10000 ? "#ff4560" :
                      entry.total_tokens > 5000  ? "#ffb347" : "#00e5a0"
                    }
                    fillOpacity={0.75}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : <EmptyChart />}
      </ChartSection>

      {/* Latency Percentiles */}
      <ChartSection
        title="Latency Percentiles"
        subtitle="P50 / P90 / P99 per agent"
        controls={
          <WindowPicker value={window} onChange={setWindow} options={["1h","6h","24h"]} />
        }
      >
        {latency.length > 0 ? (
          <ResponsiveContainer width="100%" height={180}>
            <BarChart
              data={latency.slice(0, 10)}
              style={CHART_STYLE}
              margin={{ top: 0, right: 8, left: 0, bottom: 28 }}
            >
              <CartesianGrid {...GRID_STYLE} />
              <XAxis dataKey="agent_name" {...AXIS_STYLE}
                angle={-30} textAnchor="end" interval={0}
                tick={{ ...AXIS_STYLE.tick, fontSize: 8 }} />
              <YAxis {...AXIS_STYLE}
                tickFormatter={(v) => `${v}ms`} />
              <Tooltip {...TOOLTIP_STYLE}
                formatter={(v: any, name: string) => [`${Math.round(v)}ms`, name.toUpperCase()]} />
              <Bar dataKey="p50" fill="#00e5a0" fillOpacity={0.6} name="p50" radius={[2, 2, 0, 0]} />
              <Bar dataKey="p90" fill="#ffb347" fillOpacity={0.7} name="p90" radius={[2, 2, 0, 0]} />
              <Bar dataKey="p99" fill="#ff4560" fillOpacity={0.75} name="p99" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : <EmptyChart />}
        <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
          {[
            { color: "#00e5a0", label: "P50" },
            { color: "#ffb347", label: "P90" },
            { color: "#ff4560", label: "P99" },
          ].map(({ color, label }) => (
            <span key={label} style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 9, color: "var(--text2)" }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: "inline-block" }} />
              {label}
            </span>
          ))}
        </div>
      </ChartSection>

      {/* Cost Breakdown */}
      <ChartSection title="Cost Breakdown" subtitle="USD estimate by agent × model (last 24h)">
        {costs.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {costs.slice(0, 12).map((row, i) => {
              const maxCost = Math.max(...costs.map((c) => c.cost ?? 0));
              const pct = maxCost > 0 ? ((row.cost ?? 0) / maxCost) * 100 : 0;
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 10 }}>
                  <span style={{ color: "var(--cyan)", minWidth: 90, fontSize: 9, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {row.agent_name}
                  </span>
                  <span style={{ color: "var(--text2)", fontSize: 8, minWidth: 80, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {row.model}
                  </span>
                  <div style={{ flex: 1, background: "var(--bg3)", borderRadius: 2, height: 6, overflow: "hidden" }}>
                    <div style={{
                      width: `${pct}%`, height: "100%", borderRadius: 2,
                      background: (row.cost ?? 0) > 1 ? "#ff4560" : (row.cost ?? 0) > 0.3 ? "#ffb347" : "#00e5a0",
                      transition: "width 0.6s ease",
                    }} />
                  </div>
                  <span style={{ color: "var(--amber)", minWidth: 44, textAlign: "right", fontSize: 9 }}>
                    ${(row.cost ?? 0).toFixed(3)}
                  </span>
                  <span style={{ color: "var(--text2)", minWidth: 52, textAlign: "right", fontSize: 8 }}>
                    {((row.tokens ?? 0) / 1000).toFixed(1)}k tok
                  </span>
                </div>
              );
            })}
          </div>
        ) : <EmptyChart />}
      </ChartSection>

    </div>
  );
}

// ─────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────
function ChartSection({
  title, subtitle, controls, children,
}: { title: string; subtitle?: string; controls?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div style={{
      background: "var(--bg1)", border: "1px solid var(--border)",
      borderRadius: 4, padding: "12px 14px",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text0)", marginBottom: 2 }}>{title}</div>
          {subtitle && <div style={{ fontSize: 9, color: "var(--text2)" }}>{subtitle}</div>}
        </div>
        {controls}
      </div>
      {children}
    </div>
  );
}

function EmptyChart() {
  return (
    <div style={{ height: 100, display: "flex", alignItems: "center", justifyContent: "center",
      color: "var(--text2)", fontSize: 10 }}>
      No data — connect agents to start collecting metrics
    </div>
  );
}

function WindowPicker({
  value, onChange, options,
}: { value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <div style={{ display: "flex", gap: 4 }}>
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          style={{
            padding: "2px 8px", borderRadius: 3, fontSize: 9, cursor: "pointer",
            background: value === o ? "var(--cyan-dim)" : "var(--bg3)",
            color: value === o ? "var(--cyan)" : "var(--text2)",
            border: `1px solid ${value === o ? "rgba(0,212,255,.3)" : "var(--border2)"}`,
            fontFamily: "JetBrains Mono, monospace",
          }}
        >
          {o}
        </button>
      ))}
    </div>
  );
}
