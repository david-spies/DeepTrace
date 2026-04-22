import React, { useEffect, useState } from "react";
import { fetchHeatmap, fetchAnomalies, fetchViolations } from "@/utils/api";
import type { PermissionMatrix, AnomalyAlert } from "@/types";

const CELL_CLASS: Record<string, { bg: string; border: string; text: string; label: string }> = {
  ALLOWED: { bg: "rgba(0,229,160,.10)", border: "rgba(0,229,160,.25)", text: "#00e5a0", label: "R/W" },
  BLOCKED: { bg: "rgba(255,69,96,.12)", border: "rgba(255,69,96,.3)",  text: "#ff4560", label: "DENY" },
  ANOMALY: { bg: "rgba(155,109,255,.13)",border:"rgba(155,109,255,.35)",text:"#9b6dff",label: "ANOM" },
  NONE:    { bg: "rgba(255,255,255,.02)", border:"rgba(255,255,255,.07)",text:"#4d6a82",label: "—"   },
};

type Tab = "heatmap" | "anomalies" | "violations";

export function SecurityView() {
  const [tab, setTab] = useState<Tab>("heatmap");
  const [matrix, setMatrix] = useState<PermissionMatrix | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyAlert[]>([]);
  const [violations, setViolations] = useState<any[]>([]);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    fetchHeatmap().then((d: any) => setMatrix(d)).catch(() => {});
    fetchAnomalies().then((d: any) => setAnomalies(d.anomalies ?? [])).catch(() => {});
    fetchViolations().then((d: any) => setViolations(d.violations ?? [])).catch(() => {});
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* Sub-tabs */}
      <div style={{
        display: "flex", background: "var(--bg1)", borderBottom: "1px solid var(--border)",
        padding: "0 12px", flexShrink: 0,
      }}>
        {(["heatmap", "anomalies", "violations"] as Tab[]).map((t) => (
          <button
            key={t}
            className={`top-tab ${tab === t ? "active" : ""}`}
            onClick={() => setTab(t)}
            style={{ fontSize: 10, padding: "0 14px", height: 38 }}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
            {t === "anomalies" && anomalies.length > 0 && (
              <span style={{
                marginLeft: 6, padding: "1px 5px", borderRadius: 3,
                background: "var(--red-dim)", color: "var(--red)", fontSize: 9,
              }}>{anomalies.length}</span>
            )}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflow: "auto" }}>
        {tab === "heatmap" && <HeatmapPanel matrix={matrix} hovered={hovered} setHovered={setHovered} />}
        {tab === "anomalies" && <AnomalyPanel anomalies={anomalies} />}
        {tab === "violations" && <ViolationPanel violations={violations} />}
      </div>

      {/* Legend */}
      {tab === "heatmap" && (
        <div style={{
          display: "flex", gap: 14, padding: "8px 14px",
          borderTop: "1px solid var(--border)", flexShrink: 0,
        }}>
          {Object.entries(CELL_CLASS).map(([k, v]) => (
            <div key={k} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 9, color: "var(--text2)" }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: v.bg, border: `1px solid ${v.border}` }} />
              {k.charAt(0) + k.slice(1).toLowerCase()}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function HeatmapPanel({ matrix, hovered, setHovered }: {
  matrix: PermissionMatrix | null;
  hovered: string | null;
  setHovered: (k: string | null) => void;
}) {
  if (!matrix) return (
    <div style={{ padding: 20, color: "var(--text2)", fontSize: 11 }}>
      Loading permission matrix…
    </div>
  );

  const { agents, resources, cells } = matrix;

  return (
    <div style={{ padding: 14, overflowX: "auto" }}>
      <div style={{ fontSize: 9, color: "var(--text2)", marginBottom: 10, textTransform: "uppercase", letterSpacing: ".1em" }}>
        Permission Matrix — Agent × Resource
      </div>
      <table style={{ borderCollapse: "separate", borderSpacing: 3 }}>
        <thead>
          <tr>
            <th style={{ fontSize: 8, color: "var(--text2)", padding: "4px 8px", textAlign: "left", fontWeight: 400 }}>
              Resource
            </th>
            {agents.map((a) => (
              <th key={a} style={{ fontSize: 8, color: "var(--text1)", padding: "4px 6px", textAlign: "center", fontWeight: 400, minWidth: 70 }}>
                {a.substring(0, 10)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {resources.map((res) => (
            <tr key={res}>
              <td style={{ fontSize: 9, color: "var(--text2)", padding: "3px 8px", whiteSpace: "nowrap" }}>
                {res}
              </td>
              {agents.map((ag) => {
                const key = `${ag}-${res}`;
                const val = (cells[key] || "NONE") as keyof typeof CELL_CLASS;
                const style = CELL_CLASS[val] ?? CELL_CLASS.NONE;
                const isHov = hovered === key;
                return (
                  <td key={ag}>
                    <div
                      onMouseEnter={() => setHovered(key)}
                      onMouseLeave={() => setHovered(null)}
                      title={`${ag} → ${res}: ${val}`}
                      style={{
                        background: style.bg,
                        border: `1px solid ${style.border}`,
                        borderRadius: 3,
                        padding: "5px 4px",
                        textAlign: "center",
                        fontSize: 8,
                        fontWeight: 700,
                        color: style.text,
                        cursor: "pointer",
                        transition: "all .12s",
                        transform: isHov ? "scale(1.08)" : "scale(1)",
                        animation: val === "ANOMALY" ? "anomaly-pulse 2s ease-in-out infinite" : "none",
                        minWidth: 50,
                      }}
                    >
                      {style.label}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: "#ff4560", HIGH: "#ff6b9d", MEDIUM: "#ffb347", LOW: "#8ba8c4",
};

function AnomalyPanel({ anomalies }: { anomalies: AnomalyAlert[] }) {
  if (!anomalies.length) return (
    <div style={{ padding: 20, color: "var(--text2)", fontSize: 11 }}>No active anomalies.</div>
  );
  return (
    <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 6 }}>
      {anomalies.map((a, i) => (
        <div key={i} style={{
          background: "var(--bg2)", border: "1px solid var(--border)",
          borderLeft: `3px solid ${SEVERITY_COLOR[a.severity] ?? "var(--text2)"}`,
          borderRadius: 4, padding: "8px 12px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: SEVERITY_COLOR[a.severity] }}>
              {a.rule_id}
            </span>
            <span style={{ fontSize: 9, color: "var(--text2)" }}>
              {new Date(a.timestamp * 1000).toLocaleTimeString()}
            </span>
          </div>
          <div style={{ fontSize: 10, color: "var(--text1)", marginBottom: 4 }}>{a.description}</div>
          <div style={{ display: "flex", gap: 8, fontSize: 9, color: "var(--text2)" }}>
            <span>Agent: <span style={{ color: "var(--cyan)" }}>{a.agent}</span></span>
            <span>Trace: <span style={{ color: "var(--text1)" }}>{a.trace_id.substring(0, 12)}…</span></span>
          </div>
        </div>
      ))}
    </div>
  );
}

function ViolationPanel({ violations }: { violations: any[] }) {
  if (!violations.length) return (
    <div style={{ padding: 20, color: "var(--text2)", fontSize: 11 }}>No violations in the last 24h.</div>
  );
  return (
    <div style={{ padding: 14 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border)" }}>
            {["Agent","Status","Tokens","Anomalies","Timestamp"].map((h) => (
              <th key={h} style={{ padding: "4px 8px", textAlign: "left", color: "var(--text2)", fontWeight: 400, fontSize: 9 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {violations.map((v, i) => (
            <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,.03)" }}>
              <td style={{ padding: "5px 8px", color: "var(--cyan)" }}>{v.agent_name}</td>
              <td style={{ padding: "5px 8px", color: "var(--red)" }}>{v.status}</td>
              <td style={{ padding: "5px 8px", color: "var(--amber)" }}>{(v.token_total ?? 0).toLocaleString()}</td>
              <td style={{ padding: "5px 8px", color: "var(--purple)" }}>{(v.anomalies ?? []).join(", ") || "—"}</td>
              <td style={{ padding: "5px 8px", color: "var(--text2)", fontSize: 9 }}>
                {new Date((v.timestamp ?? 0) * 1000).toLocaleTimeString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
