import React, { useEffect, useState } from "react";
import { useStore } from "@/store";
import { fetchAgentSpans, fetchTokenHistory, killAgent, hotpatchAgent } from "@/utils/api";
import { AreaChart, Area, XAxis, Tooltip, ResponsiveContainer } from "recharts";

const STATUS_COLOR: Record<string, string> = {
  ok:     "var(--green)",
  warn:   "var(--amber)",
  err:    "var(--red)",
  idle:   "var(--text2)",
  killed: "var(--text2)",
};

export function AgentDetailPanel() {
  const { selectedAgent, selectAgent, setView, setTimeline } = useStore();
  const [spans, setSpans]       = useState<any[]>([]);
  const [history, setHistory]   = useState<any[]>([]);
  const [patchText, setPatchText] = useState("");
  const [patchOpen, setPatchOpen] = useState(false);
  const [logs, setLogs]           = useState<string[]>([]);

  useEffect(() => {
    if (!selectedAgent) return;
    fetchAgentSpans(selectedAgent.name, 20)
      .then((d: any) => setSpans(d.spans ?? []))
      .catch(() => {});
    fetchTokenHistory(selectedAgent.name, "1h")
      .then((d: any) => setHistory(d.series ?? []))
      .catch(() => {});
    // Simulate live log entries
    const interval = setInterval(() => {
      setLogs((prev) => [
        `${new Date().toLocaleTimeString()} [SPAN] agent=${selectedAgent.name} dur=${Math.round(Math.random() * 400 + 50)}ms`,
        ...prev.slice(0, 29),
      ]);
    }, 2200);
    return () => clearInterval(interval);
  }, [selectedAgent?.name]);

  if (!selectedAgent) {
    return (
      <div style={{
        display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", flex: 1, gap: 10,
        color: "var(--text2)", fontSize: 11, padding: 20, textAlign: "center",
      }}>
        <span style={{ fontSize: 32, opacity: 0.2 }}>◈</span>
        <span>Click any agent node<br />to inspect its telemetry</span>
      </div>
    );
  }

  const a = selectedAgent;
  const tokenPct = a.token_total && 8000 ? Math.min(100, Math.round((a.token_total / 8000) * 100)) : 0;
  const tokenColor = tokenPct > 85 ? "var(--red)" : tokenPct > 60 ? "var(--amber)" : "var(--green)";
  const latColor = (lat: number) => lat < 200 ? "var(--green)" : lat < 2000 ? "var(--amber)" : "var(--red)";
  const avgLat = spans.length
    ? Math.round(spans.reduce((s, sp) => s + (sp.duration_ms ?? 0), 0) / spans.length)
    : 0;

  const handleKill = async () => {
    try {
      await killAgent(a.name, "Killed from dashboard");
      selectAgent({ ...a, status: "killed" });
    } catch { /* silent */ }
  };

  const handlePatch = async () => {
    if (!patchText.trim()) return;
    try {
      await hotpatchAgent(a.name, patchText, "Dashboard hotpatch");
      setPatchOpen(false);
      setPatchText("");
    } catch { /* silent */ }
  };

  const handleTrace = () => {
    setView("timetravel");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* Header */}
      <div style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 4, display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: 9, fontWeight: 700,
            background: `${STATUS_COLOR[a.status]}22`, color: STATUS_COLOR[a.status],
          }}>
            {a.name.substring(0, 2).toUpperCase()}
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text0)", fontFamily: "Syne, sans-serif" }}>
              {a.name}
            </div>
            <div style={{ fontSize: 9, color: "var(--text2)" }}>{a.model || "—"}</div>
          </div>
          <div style={{ flex: 1 }} />
          <span style={{
            fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 3,
            background: `${STATUS_COLOR[a.status]}22`,
            color: STATUS_COLOR[a.status], border: `1px solid ${STATUS_COLOR[a.status]}44`,
          }}>
            {a.status.toUpperCase()}
          </span>
        </div>
        {a.has_anomaly && (
          <div style={{
            fontSize: 9, color: "var(--purple)", background: "var(--purple-dim)",
            border: "1px solid rgba(155,109,255,.3)", borderRadius: 3,
            padding: "3px 8px", marginTop: 4,
          }}>
            ⚠ Anomaly detected — inspect security tab
          </div>
        )}
      </div>

      {/* Body */}
      <div style={{ flex: 1, overflowY: "auto" }}>

        {/* Runtime KVs */}
        <Section title="Runtime">
          <KV k="Roles"      v={a.roles?.join(", ") || "—"} />
          <KV k="Avg Latency" v={`${avgLat}ms`} color={latColor(avgLat)} />
          <KV k="Spans"       v={(a.call_count ?? 0).toLocaleString()} />
          <KV k="Environment" v={a.environment || "—"} />
        </Section>

        {/* Token budget */}
        {a.token_total > 0 && (
          <Section title="Token Budget">
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, marginBottom: 5 }}>
              <span style={{ color: "var(--text2)" }}>Used</span>
              <span style={{ color: tokenColor }}>
                {a.token_total.toLocaleString()} / 8,000
              </span>
            </div>
            <div style={{ background: "var(--bg0)", borderRadius: 3, height: 5, overflow: "hidden", marginBottom: 5 }}>
              <div style={{
                width: `${tokenPct}%`, height: "100%", borderRadius: 3,
                background: tokenColor, transition: "width 0.6s ease",
              }} />
            </div>
            <KV k="Pressure" v={`${tokenPct}%`} color={tokenColor} />
          </Section>
        )}

        {/* Token history sparkline */}
        {history.length > 0 && (
          <Section title="Token History (1h)">
            <ResponsiveContainer width="100%" height={60}>
              <AreaChart data={history} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="tokGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#00e5a0" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#00e5a0" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="minute" hide />
                <Tooltip
                  contentStyle={{ background: "#131920", border: "1px solid #2a3f54", fontSize: 9 }}
                  formatter={(v: any) => [v.toLocaleString(), "Tokens"]}
                />
                <Area
                  type="monotone" dataKey="tokens"
                  stroke="#00e5a0" strokeWidth={1.5}
                  fill="url(#tokGrad)" dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </Section>
        )}

        {/* Permissions */}
        <Section title="Permissions">
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {(a.roles ?? []).map((r) => (
              <span key={r} style={{
                padding: "2px 7px", borderRadius: 3, fontSize: 9,
                border: "1px solid var(--border2)", color: "var(--text1)",
                background: "var(--bg3)",
              }}>{r}</span>
            ))}
            {(a.blocked_resources ?? []).map((r) => (
              <span key={r} style={{
                padding: "2px 7px", borderRadius: 3, fontSize: 9,
                border: "1px solid rgba(255,69,96,.3)", color: "var(--red)",
                background: "var(--red-dim)",
              }}>✕ {r}</span>
            ))}
          </div>
        </Section>

        {/* Recent spans */}
        <Section title="Recent Spans">
          {spans.slice(0, 8).map((sp, i) => (
            <div key={i} style={{
              display: "flex", justifyContent: "space-between",
              padding: "3px 0", borderBottom: "1px solid rgba(255,255,255,.03)",
              fontSize: 9,
            }}>
              <span style={{
                color: sp.status === "FAILED" || sp.status === "BLOCKED"
                  ? "var(--red)" : "var(--text2)",
              }}>{sp.kind}</span>
              <span style={{ color: latColor(sp.duration_ms ?? 0) }}>
                {Math.round(sp.duration_ms ?? 0)}ms
              </span>
              <span style={{ color: "var(--amber)" }}>
                +{(sp.token_total ?? 0).toLocaleString()} tok
              </span>
              <span style={{ color: "var(--text2)" }}>
                {sp.status}
              </span>
            </div>
          ))}
          {spans.length === 0 && (
            <span style={{ fontSize: 9, color: "var(--text2)" }}>No spans yet</span>
          )}
        </Section>

        {/* Log stream */}
        <Section title="Live Log Stream">
          <div style={{
            maxHeight: 110, overflowY: "auto",
            display: "flex", flexDirection: "column-reverse",
          }}>
            {logs.map((l, i) => (
              <div key={i} style={{
                fontSize: 8, lineHeight: 1.6, color: "var(--text2)",
                borderBottom: "1px solid rgba(255,255,255,.02)", fontFamily: "monospace",
              }}>
                {l}
              </div>
            ))}
            {logs.length === 0 && (
              <div style={{ fontSize: 8, color: "var(--text2)" }}>Waiting for spans…</div>
            )}
          </div>
        </Section>

        {/* Hotpatch UI */}
        {patchOpen && (
          <Section title="Hot Patch — System Prompt Delta">
            <textarea
              value={patchText}
              onChange={(e) => setPatchText(e.target.value)}
              placeholder="Enter instructions to append to this agent's system prompt…"
              style={{
                width: "100%", background: "var(--bg0)", border: "1px solid var(--border2)",
                borderRadius: 3, padding: "6px 8px", fontSize: 9, color: "var(--text0)",
                fontFamily: "JetBrains Mono, monospace", resize: "vertical", minHeight: 70,
                outline: "none",
              }}
            />
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              <button
                onClick={handlePatch}
                style={{
                  flex: 1, padding: "5px 0", borderRadius: 3, fontSize: 9, fontWeight: 700,
                  cursor: "pointer", background: "var(--amber-dim)", color: "var(--amber)",
                  border: "1px solid rgba(255,179,71,.3)", fontFamily: "JetBrains Mono, monospace",
                  letterSpacing: ".06em", textTransform: "uppercase",
                }}
              >
                Inject Patch
              </button>
              <button
                onClick={() => setPatchOpen(false)}
                style={{
                  padding: "5px 10px", borderRadius: 3, fontSize: 9, cursor: "pointer",
                  background: "var(--bg3)", color: "var(--text2)",
                  border: "1px solid var(--border2)", fontFamily: "JetBrains Mono, monospace",
                }}
              >
                Cancel
              </button>
            </div>
          </Section>
        )}
      </div>

      {/* Action row */}
      <div style={{
        display: "flex", gap: 6, padding: "10px 12px",
        borderTop: "1px solid var(--border)", flexShrink: 0,
      }}>
        <ActionBtn
          label="Kill"
          color="var(--red)"
          dimColor="var(--red-dim)"
          borderColor="rgba(255,69,96,.3)"
          onClick={handleKill}
          disabled={a.status === "killed" || a.status === "idle"}
        />
        <ActionBtn
          label="Patch"
          color="var(--amber)"
          dimColor="var(--amber-dim)"
          borderColor="rgba(255,179,71,.3)"
          onClick={() => setPatchOpen(!patchOpen)}
        />
        <ActionBtn
          label="Trace"
          color="var(--cyan)"
          dimColor="var(--cyan-dim)"
          borderColor="rgba(0,212,255,.3)"
          onClick={handleTrace}
        />
      </div>

    </div>
  );
}

// ── Sub-components ──────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--border)" }}>
      <div style={{
        fontSize: 8, fontWeight: 700, letterSpacing: ".1em",
        textTransform: "uppercase", color: "var(--text2)", marginBottom: 7,
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function KV({ k, v, color = "var(--text0)" }: { k: string; v: string; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, gap: 8 }}>
      <span style={{ fontSize: 9, color: "var(--text2)", flexShrink: 0 }}>{k}</span>
      <span style={{ fontSize: 9, color, textAlign: "right", wordBreak: "break-all" }}>{v}</span>
    </div>
  );
}

function ActionBtn({
  label, color, dimColor, borderColor, onClick, disabled = false,
}: {
  label: string; color: string; dimColor: string; borderColor: string;
  onClick: () => void; disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        flex: 1, padding: "6px 0", borderRadius: 3, fontSize: 9, fontWeight: 700,
        cursor: disabled ? "not-allowed" : "pointer",
        background: disabled ? "var(--bg3)" : dimColor,
        color: disabled ? "var(--text2)" : color,
        border: `1px solid ${disabled ? "var(--border)" : borderColor}`,
        fontFamily: "JetBrains Mono, monospace",
        textTransform: "uppercase", letterSpacing: ".06em",
        transition: "all .12s",
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {label}
    </button>
  );
}
