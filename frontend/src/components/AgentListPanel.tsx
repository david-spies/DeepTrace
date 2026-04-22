import React, { useEffect } from "react";
import { useStore } from "@/store";
import { fetchAgents } from "@/utils/api";
import type { Agent } from "@/types";

const STATUS_COLOR: Record<string, string> = {
  ok:     "var(--green)",
  warn:   "var(--amber)",
  err:    "var(--red)",
  idle:   "var(--text2)",
  killed: "var(--text2)",
};

const STATUS_BG: Record<string, string> = {
  ok:     "",
  warn:   "",
  err:    "rgba(255,69,96,.07)",
  killed: "",
  idle:   "",
};

export function AgentListPanel() {
  const { agents, setAgents, selectedAgent, selectAgent, alerts, metrics } = useStore();

  useEffect(() => {
    const poll = async () => {
      try {
        const data = await fetchAgents() as any;
        setAgents(data.agents ?? []);
      } catch { /* silent */ }
    };
    poll();
    const iv = setInterval(poll, 5000);
    return () => clearInterval(iv);
  }, [setAgents]);

  return (
    <div style={{
      background: "var(--bg1)", borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column", overflow: "hidden",
    }}>

      {/* Agents section */}
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{
          fontSize: 8, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase",
          color: "var(--text2)", marginBottom: 8,
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          Agents
          <span style={{ color: "var(--text1)", fontWeight: 400, textTransform: "none",
            letterSpacing: 0, fontSize: 9 }}>
            {agents.filter(a => a.status !== "killed").length} active
          </span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
          {agents.length === 0 && (
            <div style={{ fontSize: 9, color: "var(--text2)", padding: "6px 0" }}>
              No agents — start an instrumented swarm
            </div>
          )}
          {agents.map((a) => (
            <AgentRow
              key={a.name}
              agent={a}
              selected={selectedAgent?.name === a.name}
              onClick={() => selectAgent(a)}
            />
          ))}
        </div>
      </div>

      {/* Metrics section */}
      <div style={{ padding: "10px 12px", flex: 1, overflowY: "auto" }}>
        <div style={{
          fontSize: 8, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase",
          color: "var(--text2)", marginBottom: 8,
        }}>
          System Metrics
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
          <MiniCard label="Tokens" value={metrics ? `${((metrics.total_tokens ?? 0)/1000).toFixed(1)}k` : "—"} color="var(--cyan)" />
          <MiniCard label="Calls"  value={metrics ? (metrics.unique_traces ?? 0).toString() : "—"} color="var(--green)" />
          <MiniCard label="Alerts" value={alerts.length.toString()} color={alerts.length > 0 ? "var(--red)" : "var(--text2)"} />
          <MiniCard label="Cost"   value={metrics ? `$${(metrics.total_cost ?? 0).toFixed(2)}` : "—"} color="var(--amber)" />
        </div>

        {/* Active alerts mini-list */}
        {alerts.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div style={{
              fontSize: 8, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase",
              color: "var(--text2)", marginBottom: 6,
            }}>
              Active Alerts
            </div>
            {alerts.slice(0, 4).map((a, i) => (
              <div key={i} style={{
                padding: "4px 6px", borderRadius: 3, marginBottom: 3,
                background: "var(--red-dim)", border: "1px solid rgba(255,69,96,.2)",
                fontSize: 8, lineHeight: 1.4,
              }}>
                <div style={{ color: "var(--red)", fontWeight: 700 }}>{a.rule_id}</div>
                <div style={{ color: "var(--text2)" }}>{a.agent}</div>
              </div>
            ))}
            {alerts.length > 4 && (
              <div style={{ fontSize: 8, color: "var(--text2)", padding: "3px 0" }}>
                +{alerts.length - 4} more alerts…
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function AgentRow({
  agent, selected, onClick,
}: { agent: Agent; selected: boolean; onClick: () => void }) {
  const sc = STATUS_COLOR[agent.status] ?? STATUS_COLOR.idle;
  const isAlert = agent.status === "err" || agent.has_anomaly;

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex", alignItems: "center", gap: 7,
        padding: "5px 7px", borderRadius: 4, cursor: "pointer",
        border: `1px solid ${selected ? "var(--border2)" : isAlert ? "rgba(255,69,96,.2)" : "transparent"}`,
        background: selected
          ? "var(--bg3)"
          : isAlert
          ? STATUS_BG.err
          : "transparent",
        transition: "background .1s",
      }}
      onMouseEnter={(e) => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.background = "var(--bg3)";
      }}
      onMouseLeave={(e) => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.background =
          isAlert ? STATUS_BG.err : "transparent";
      }}
    >
      {/* Icon */}
      <div style={{
        width: 24, height: 24, borderRadius: 3, flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: `${sc}22`, color: sc, fontSize: 8, fontWeight: 700,
      }}>
        {agent.name.substring(0, 2).toUpperCase()}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 10, fontWeight: 500, color: "var(--text0)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {agent.name}
        </div>
        <div style={{
          fontSize: 8, color: "var(--text2)",
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {agent.model || agent.roles?.[0] || "—"}
        </div>
      </div>

      {/* Status dot */}
      <div style={{
        width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
        background: sc,
        boxShadow: agent.status === "err"
          ? `0 0 6px ${sc}`
          : agent.status === "ok" ? `0 0 4px ${sc}` : "none",
        animation: agent.status === "err" ? "blink .8s ease-in-out infinite" : "none",
      }} />
    </div>
  );
}

function MiniCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{
      background: "var(--bg2)", border: "1px solid var(--border)",
      borderRadius: 4, padding: "7px 8px",
    }}>
      <div style={{ fontSize: 7, color: "var(--text2)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 3 }}>
        {label}
      </div>
      <div style={{ fontSize: 15, fontWeight: 700, color, fontFamily: "Syne, sans-serif" }}>
        {value}
      </div>
    </div>
  );
}
