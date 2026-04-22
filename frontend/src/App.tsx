import React from "react";
import { useStore } from "@/store";
import { useWebSocket } from "@/hooks/useWebSocket";
import { AgentListPanel }   from "@/components/AgentListPanel";
import { AgentDetailPanel } from "@/components/AgentDetailPanel";
import { TopologyView }     from "@/views/TopologyView";
import { TimeTravelView }   from "@/views/TimeTravelView";
import { SecurityView }     from "@/views/SecurityView";
import { MetricsView }      from "@/views/MetricsView";

// ── Icons ────────────────────────────────
const IconGraph    = () => <svg width={12} height={12} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/><line x1="7" y1="12" x2="17" y2="7"/><line x1="7" y1="12" x2="17" y2="17"/></svg>;
const IconClock    = () => <svg width={12} height={12} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><polyline points="12,7 12,12 15,15"/></svg>;
const IconShield   = () => <svg width={12} height={12} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>;
const IconChart    = () => <svg width={12} height={12} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24"><polyline points="22,12 18,12 15,21 9,3 6,12 2,12"/></svg>;

export default function App() {
  const { view, setView, alerts, liveMode } = useStore();

  // Connect to live WebSocket feed
  useWebSocket();

  return (
    <>
      {/* Global styles */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Syne:wght@400;600;700;800&display=swap');

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
          --bg0: #080b0f;
          --bg1: #0d1117;
          --bg2: #131920;
          --bg3: #1a2330;
          --bg4: #202c3a;
          --border:  #1e2d3d;
          --border2: #2a3f54;
          --text0: #e8f0f8;
          --text1: #8ba8c4;
          --text2: #4d6a82;
          --green:  #00e5a0;
          --red:    #ff4560;
          --amber:  #ffb347;
          --blue:   #3b9eff;
          --purple: #9b6dff;
          --cyan:   #00d4ff;
          --pink:   #ff6b9d;
          --green-dim:  rgba(0,229,160,0.12);
          --red-dim:    rgba(255,69,96,0.12);
          --amber-dim:  rgba(255,179,71,0.12);
          --blue-dim:   rgba(59,158,255,0.12);
          --purple-dim: rgba(155,109,255,0.12);
          --cyan-dim:   rgba(0,212,255,0.10);
        }

        html, body, #root {
          height: 100%; width: 100%;
          background: var(--bg0);
          color: var(--text0);
          font-family: 'JetBrains Mono', monospace;
          overflow: hidden;
        }

        /* Scrollbars */
        ::-webkit-scrollbar { width: 3px; height: 3px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

        /* Shared button classes */
        .toolbar-btn {
          padding: 4px 10px; border-radius: 3px; font-size: 10px; font-weight: 500;
          cursor: pointer; background: var(--bg3); color: var(--text1);
          border: 1px solid var(--border2); font-family: 'JetBrains Mono', monospace;
          transition: all .15s;
        }
        .toolbar-btn:hover { background: var(--bg4); color: var(--text0); }
        .toolbar-btn.active { background: var(--cyan-dim); color: var(--cyan); border-color: rgba(0,212,255,.3); }

        .toolbar-sep { width: 1px; height: 20px; background: var(--border2); margin: 0 4px; }

        .top-tab {
          display: flex; align-items: center; gap: 6px; padding: 0 16px;
          font-size: 10px; font-weight: 500; letter-spacing: .05em; text-transform: uppercase;
          color: var(--text2); border: none; background: none; cursor: pointer;
          border-bottom: 2px solid transparent; transition: all .15s; white-space: nowrap;
        }
        .top-tab:hover { color: var(--text1); background: var(--bg2); }
        .top-tab.active { color: var(--cyan); border-bottom-color: var(--cyan); }

        @keyframes blink    { 50% { opacity: .3; } }
        @keyframes anomaly-pulse { 50% { border-color: var(--purple); box-shadow: 0 0 8px rgba(155,109,255,.4); } }
        @keyframes pulse-dot { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:.6; transform:scale(.8); } }
      `}</style>

      <div style={{ display: "grid", gridTemplateRows: "48px 1fr", height: "100vh" }}>

        {/* ── TOPBAR ── */}
        <div style={{
          display: "flex", alignItems: "center",
          background: "var(--bg1)", borderBottom: "1px solid var(--border)",
          padding: "0 16px", justifyContent: "space-between",
          position: "relative", zIndex: 100, flexShrink: 0,
        }}>
          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "Syne, sans-serif", fontWeight: 800, fontSize: 15 }}>
            <div style={{
              width: 8, height: 8, borderRadius: "50%", background: "var(--green)",
              boxShadow: "0 0 8px var(--green)",
              animation: "pulse-dot 2s ease-in-out infinite",
            }} />
            <span>DEEP<span style={{ color: "var(--cyan)" }}>TRACE</span></span>
            <span style={{ color: "var(--text2)", fontSize: 10, fontWeight: 400, marginLeft: 4 }}>v2.1.0</span>
          </div>

          {/* Nav tabs */}
          <div style={{ display: "flex", height: 48 }}>
            <NavTab icon={<IconGraph />} label="Topology"    active={view === "topology"}    onClick={() => setView("topology")} />
            <NavTab icon={<IconClock />} label="Time Travel" active={view === "timetravel"}  onClick={() => setView("timetravel")} />
            <NavTab icon={<IconShield/>} label="Security"    active={view === "security"}    onClick={() => setView("security")} />
            <NavTab icon={<IconChart />} label="Metrics"     active={view === "metrics"}     onClick={() => setView("metrics")} />
          </div>

          {/* Status badges */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Badge color="var(--green)" dimColor="rgba(0,229,160,.15)" borderColor="rgba(0,229,160,.3)">
              ● LIVE
            </Badge>
            {alerts.length > 0 && (
              <Badge color="var(--red)" dimColor="rgba(255,69,96,.12)" borderColor="rgba(255,69,96,.3)">
                {alerts.length} ALERT{alerts.length !== 1 ? "S" : ""}
              </Badge>
            )}
          </div>
        </div>

        {/* ── MAIN GRID ── */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "210px 1fr 270px",
          minHeight: 0, overflow: "hidden",
        }}>
          <AgentListPanel />

          {/* Center canvas */}
          <div style={{ display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
            {view === "topology"    && <TopologyView />}
            {view === "timetravel"  && <TimeTravelView />}
            {view === "security"    && <SecurityView />}
            {view === "metrics"     && <MetricsView />}
          </div>

          <AgentDetailPanel />
        </div>

      </div>
    </>
  );
}

function NavTab({
  icon, label, active, onClick,
}: { icon: React.ReactNode; label: string; active: boolean; onClick: () => void }) {
  return (
    <button className={`top-tab ${active ? "active" : ""}`} onClick={onClick}>
      {icon}
      {label}
    </button>
  );
}

function Badge({
  children, color, dimColor, borderColor,
}: { children: React.ReactNode; color: string; dimColor: string; borderColor: string }) {
  return (
    <span style={{
      padding: "3px 8px", borderRadius: 3, fontSize: 9, fontWeight: 700,
      letterSpacing: ".08em", textTransform: "uppercase",
      fontFamily: "JetBrains Mono, monospace",
      background: dimColor, color, border: `1px solid ${borderColor}`,
    }}>
      {children}
    </span>
  );
}
