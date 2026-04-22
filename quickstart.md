# DeepTrace Quickstart Guide

> **Version 2.1.0** · LLM Service Mesh & Agent Observability Platform

---

## Table of Contents

1. [What is DeepTrace?](#1-what-is-deeptrace)
2. [System Requirements](#2-system-requirements)
3. [Project Structure](#3-project-structure)
4. [Infrastructure Setup](#4-infrastructure-setup)
5. [Installing the Collector](#5-installing-the-collector)
6. [Installing the Frontend](#6-installing-the-frontend)
7. [Instrumenting Your Agents](#7-instrumenting-your-agents)
8. [Running the Example Swarm](#8-running-the-example-swarm)
9. [Using the Dashboard](#9-using-the-dashboard)
10. [Zero-Trust Policy Configuration](#10-zero-trust-policy-configuration)
11. [Time-Travel Debugger](#11-time-travel-debugger)
12. [Security & Anomaly Detection](#12-security--anomaly-detection)
13. [Metrics & Token Analytics](#13-metrics--token-analytics)
14. [WebSocket Live Feed](#14-websocket-live-feed)
15. [REST API Reference](#15-rest-api-reference)
16. [Environment Variables](#16-environment-variables)
17. [Production Deployment](#17-production-deployment)
18. [Troubleshooting](#18-troubleshooting)

---

## 1. What is DeepTrace?

DeepTrace is a **Service Mesh for LLMs** — a real-time observability layer that sits between your agent swarm and the underlying infrastructure it touches. It intercepts every inference call and tool invocation, maps them as a live graph, and surfaces anomalies before they become incidents.

**Core capabilities:**

| Capability | Description |
|---|---|
| **Live Topology Graph** | Force-directed agent mesh with token intensity sizing and latency-colored edges |
| **Time-Travel Debugger** | Scrub through the exact execution timeline of any trace, event by event |
| **Security Heatmap** | Agent × Resource permission matrix — anomalies flagged in real time |
| **Zero-Trust Engine** | Policy rules that block unauthorized tool invocations before they execute |
| **Token Analytics** | Token debt ranking, velocity alerts, cost breakdown per agent and model |
| **Merkle Audit Trail** | Tamper-evident hash chain on every tool call — SOC2/ISO 27001 ready |
| **Hot Patching** | Inject system prompt deltas into running agents without a restart |
| **Context Fragmentation** | Alert when >30% of context is lost between a parent agent and its child |

DeepTrace is **framework-agnostic** — the Python SDK wraps LangChain, CrewAI, AutoGen, or any custom agent class with a single decorator.

---

## 2. System Requirements

### Minimum (development)

| Component | Requirement |
|---|---|
| OS | Linux, macOS, or Windows (WSL2) |
| CPU | 2 cores |
| RAM | 4 GB |
| Disk | 8 GB (Docker images + data) |
| Docker | 24.0+ with Compose v2 |
| Python | 3.11+ |
| Node.js | 20 LTS+ |

### Recommended (production single-machine)

| Component | Requirement |
|---|---|
| CPU | 8 cores |
| RAM | 16 GB |
| Disk | 50 GB SSD |
| Network | 1 Gbps internal |

### Port Allocation

| Port | Service |
|---|---|
| `3000` | DeepTrace Dashboard (Frontend) |
| `7474` | Neo4j Browser |
| `7687` | Neo4j Bolt |
| `8080` | Collector API |
| `8123` | ClickHouse HTTP |
| `9000` | ClickHouse Native TCP |
| `9092` | Kafka |
| `6379` | Redis |

---

## 3. Project Structure

```
deeptrace/
├── sdk/                        # Python SDK (instrument your agents)
│   ├── deeptrace.py            #   Core interceptor, decorators, Zero-Trust engine
│   ├── __init__.py
│   └── requirements.txt
│
├── collector/                  # FastAPI ingest server
│   ├── main.py                 #   App factory, WebSocket endpoints, lifespan hooks
│   ├── requirements.txt
│   ├── routers/
│   │   ├── ingest.py           #   POST /ingest/span  POST /ingest/batch
│   │   ├── agents.py           #   GET/POST /agents/*
│   │   ├── traces.py           #   GET /traces/:id  (timeline, diff, Merkle, replay)
│   │   ├── security.py         #   Heatmap, anomalies, violations, prompt injection
│   │   └── metrics.py          #   Summary, token debt, latency percentiles, cost
│   └── services/
│       ├── graph_service.py    #   Neo4j driver — agent nodes, edges, topology
│       ├── clickhouse_service.py # Time-series storage, forensic queries
│       ├── anomaly_engine.py   #   9 real-time detection rules
│       ├── kafka_producer.py   #   High-throughput span streaming
│       ├── redis_pubsub.py     #   Live pub/sub bridge
│       └── ws_manager.py       #   WebSocket room manager
│
├── graph_engine/
│   └── consumer.py             # Standalone Kafka consumer → Neo4j writer
│
├── frontend/                   # React 18 + TypeScript + Vite
│   ├── src/
│   │   ├── App.tsx             #   Root layout, nav, global CSS vars
│   │   ├── types.ts            #   All domain types
│   │   ├── store/index.ts      #   Zustand global store
│   │   ├── utils/api.ts        #   API client + WebSocket factory
│   │   ├── hooks/
│   │   │   ├── useTopology.ts  #   D3 force simulation
│   │   │   └── useWebSocket.ts #   Live feed → store
│   │   ├── views/
│   │   │   ├── TopologyView.tsx
│   │   │   ├── TimeTravelView.tsx
│   │   │   ├── SecurityView.tsx
│   │   │   └── MetricsView.tsx
│   │   └── components/
│   │       ├── AgentListPanel.tsx
│   │       └── AgentDetailPanel.tsx
│   └── ...config files
│
├── docker/
│   ├── docker-compose.yml      # Full stack orchestration
│   ├── Dockerfile.collector
│   ├── Dockerfile.frontend
│   ├── nginx.conf              # SPA + API proxy
│   └── clickhouse/config.xml
│
├── scripts/
│   └── example_swarm.py        # 5-agent demo swarm
│
├── .env.example
├── Makefile
└── README.md
```

---

## 4. Infrastructure Setup

All stateful services (Neo4j, ClickHouse, Kafka, Redis) run in Docker. The collector and frontend can run in Docker or directly on the host — whichever suits your development workflow.

### Step 1 — Clone and configure environment

```bash
git clone https://github.com/your-org/deeptrace.git
cd deeptrace
cp .env.example .env
```

Open `.env` and set at minimum:

```dotenv
JWT_SECRET=<generate with: python -c "import secrets; print(secrets.token_hex(32))">
NEO4J_PASSWORD=deeptrace          # change in production
```

All other defaults work for local development.

### Step 2 — Start the infrastructure

```bash
cd docker
docker compose up -d
```

This starts Zookeeper, Kafka (with topic bootstrap), Neo4j, ClickHouse, and Redis. Docker Compose health checks ensure services start in dependency order — Kafka waits for Zookeeper, the collector waits for all four backing services.

### Step 3 — Verify services are healthy

```bash
docker compose ps
```

All services should show `healthy`. Typical cold-start time is 45–90 seconds due to Neo4j and ClickHouse JVM/native startup.

```bash
# Quick health checks
curl http://localhost:8080/health          # Collector
curl http://localhost:8123/ping            # ClickHouse → "Ok."
curl http://localhost:7474                 # Neo4j Browser (200 OK)
redis-cli -p 6379 ping                    # → PONG
```

### Verify Kafka topics were created

```bash
docker exec -it docker-kafka-1 \
  kafka-topics --bootstrap-server localhost:29092 --list
# Should show: deeptrace-spans, deeptrace-commands, deeptrace-alerts
```

---

## 5. Installing the Collector

The collector is a FastAPI application. Run it directly on the host for hot-reload during development.

```bash
cd collector
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Start with auto-reload:

```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

The OpenAPI docs are available at `http://localhost:8080/api/docs`.

### Running the Graph Engine Consumer (optional)

The graph engine is a standalone Kafka consumer that maintains the Neo4j topology independently of the collector. Start it in a separate terminal:

```bash
cd graph_engine
python -m consumer
```

> **Note:** The collector also writes to Neo4j directly — the standalone consumer is for high-throughput scenarios where you want to decouple graph writes from the ingest path.

---

## 6. Installing the Frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard is served at `http://localhost:3000`. Vite proxies `/api/*` to the collector at `localhost:8080` and `/ws/*` to the WebSocket endpoint.

### Production build

```bash
npm run build        # outputs to frontend/dist/
npm run preview      # serve the production build locally
```

---

## 7. Instrumenting Your Agents

The SDK requires zero changes to your agent logic — you wrap the class or function with a decorator and DeepTrace handles the rest.

### Install the SDK

```bash
pip install httpx pydantic opentelemetry-sdk
# Or from the repo:
pip install -r sdk/requirements.txt
```

### Basic setup

```python
from sdk.deeptrace import DeepTrace, TraceConfig

dt = DeepTrace(TraceConfig(
    endpoint="http://localhost:8080",
    service_name="my-agent-swarm",
    environment="development",
    zero_trust_enabled=True,
))
```

Load from environment variables instead:

```python
dt = DeepTrace(TraceConfig.from_env())
# Reads: DEEPTRACE_ENDPOINT, DEEPTRACE_SERVICE, DEEPTRACE_ENV, DEEPTRACE_API_KEY
```

---

### Instrumenting an agent class

```python
from sdk.deeptrace import DeepTrace, TraceConfig, Permission

dt = DeepTrace(TraceConfig.from_env())

@dt.agent(
    name="SecurityScanner",
    roles=["CodeAudit", "FileSystemRead", "VulnScan"],
    model="claude-3-sonnet",
    permissions=[
        Permission("src/*",    allow=True),
        Permission("db:read",  allow=True),
        Permission("db:write", allow=False),  # explicit deny
    ],
)
class SecurityScanner:
    def run(self, target: str) -> dict:
        # Your agent logic here — fully traced automatically
        results = self.scan_files(target)
        return results

    def scan_files(self, path: str) -> list:
        # This method is also traced (all public methods are wrapped)
        ...
```

Every public method on the class is automatically wrapped. The decorator captures: trace ID, parent span ID, start/end timestamps, token estimates, tool invocations, and status (COMPLETED / FAILED).

---

### Instrumenting a standalone function

```python
from sdk.deeptrace import SpanKind

@dt.trace(
    name="Planner",
    roles=["Orchestration", "TaskDecompose"],
    kind=SpanKind.AGENT,
    model="claude-3-opus",
)
def run_planner(task: str) -> dict:
    ...

# Async agents are supported natively:
@dt.trace(name="AsyncAgent", roles=["DataFetch"])
async def run_async_agent(query: str) -> str:
    result = await some_async_llm_call(query)
    return result
```

---

### Instrumenting tool calls

Wrap individual tools with `@dt.tool()` to enforce Zero-Trust resource boundaries and capture Merkle hashes:

```python
@dt.tool(name="read_file", resource="src/*")
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

@dt.tool(name="query_database", resource="db:read")
def query_db(sql: str) -> list:
    return db.execute(sql).fetchall()

@dt.tool(name="write_config", resource="src/config/*")
def write_config(key: str, value: str) -> bool:
    # If the calling agent's policy denies "src/config/*",
    # this raises PermissionError BEFORE the function body executes.
    config[key] = value
    return True
```

When a Zero-Trust policy blocks a tool call, DeepTrace:
1. Raises `PermissionError` immediately — the function body never runs
2. Emits a `BLOCKED` span to the collector
3. Flags the agent node purple in the topology graph
4. Triggers an anomaly alert in the dashboard

---

### Context manager for fine-grained spans

```python
with dt.span("custom-reasoning-step", roles=["Analysis"]) as span:
    # Manually set token counts if you have them from the API response
    span.token_input  = prompt_tokens
    span.token_output = completion_tokens
    span.model        = "claude-3-opus"
    result = my_llm_call(prompt)
```

---

### LangChain integration

```python
from sdk.deeptrace import DeepTraceLangChainCallback
from langchain.agents import AgentExecutor

callback = DeepTraceLangChainCallback(dt)

agent_executor = AgentExecutor(agent=agent, tools=tools)
result = agent_executor.run(
    "Audit this codebase",
    callbacks=[callback],   # ← drop-in integration
)
```

The callback automatically traces every `on_llm_start`, `on_llm_end`, `on_tool_start`, and `on_tool_end` event with no further code changes.

---

### Context fragmentation detection

When passing context from one agent to another, DeepTrace can detect how much was lost in the handoff:

```python
from sdk.deeptrace import compute_context_fragment

planner_output = run_planner(task)
scanner_input  = prepare_scanner_prompt(planner_output)

# Returns 0.0 (identical) → 1.0 (completely different)
fragment_pct = compute_context_fragment(
    str(planner_output),    # what the parent sent
    scanner_input,          # what the child received
)

if fragment_pct > 0.30:
    print(f"WARNING: {fragment_pct*100:.1f}% context lost in handoff")
    # DeepTrace also surfaces this automatically if the span includes both
```

---

### Flushing before process exit

The SDK batches spans asynchronously. Always call `dt.flush()` before your process exits to ensure all spans are delivered:

```python
import atexit
atexit.register(dt.flush)

# Or explicitly:
dt.flush()
```

---

## 8. Running the Example Swarm

The repo includes a fully instrumented 5-agent security audit swarm that demonstrates all SDK features including Zero-Trust violations and anomaly detection.

```bash
# Make sure the collector is running first
python scripts/example_swarm.py

# Or with a custom task:
python scripts/example_swarm.py "Review the authentication module for privilege escalation risks"
```

**What the example does:**

```
Planner          → decomposes task, spawns 4 sub-agents
SecurityScanner  → reads src/ files, scans dependencies, attempts node_modules/ (policy violation)
CodeAuditor      → AST analysis, reads DB schema (allowed), finds injection vectors
Patcher          → generates diffs for discovered CVEs
Reporter         → synthesizes report, INTENTIONALLY attempts:
                     • src/config/secrets.env  (Zero-Trust BLOCK → purple node)
                     • db:write                 (Zero-Trust BLOCK → anomaly alert)
```

While the swarm runs, open `http://localhost:3000` to watch the topology graph build in real time.

---

## 9. Using the Dashboard

The dashboard has four main views, accessible from the top navigation bar.

### Topology View

The live force-directed graph of your agent mesh.

| Element | Meaning |
|---|---|
| **Node size** | Proportional to total tokens consumed (larger = more token-intensive) |
| **Token ring arc** | Arc around each node shows % of token budget used |
| **Green node** | Agent status: healthy |
| **Amber node** | Agent status: warning (elevated latency or token velocity) |
| **Red node (pulsing)** | Agent status: error or active failure |
| **Purple node** | Zero-Trust anomaly — unauthorized resource access detected |
| **Green edge** | Latency < 200ms |
| **Amber edge** | Latency 200ms – 2s |
| **Red edge** | Latency > 2s |
| **Dashed red edge** | Blocked / denied tool invocation |
| **Animated pulse dot** | Active span in-flight on that edge |

**Interactions:**

- **Click a node** — opens the Agent Detail panel on the right
- **Drag a node** — pin it to a position (releases on mouse-up)
- **Scroll** — zoom in/out
- **Click + drag background** — pan the canvas
- **◉ Live / ◎ Paused** — toggle real-time polling

### Agent Detail Panel (right sidebar)

Clicking any node reveals:

- Runtime info: model, average latency, tool call count, estimated cost
- Token pressure bar with color coding
- 1-hour token history sparkline
- Declared roles and permission badges
- Blocked resources (if any Zero-Trust denials)
- Last 8 spans with status and latency
- Live log stream (updates every ~2 seconds)
- **Kill**, **Patch**, and **Trace** action buttons

### Topology Controls

| Button | Action |
|---|---|
| `◉ Live` | Toggles real-time topology polling (4s interval) |
| `⊡ Reset` | Resets zoom and pan to center |

---

## 10. Zero-Trust Policy Configuration

Policies can be configured in two ways: at instrument time via the SDK, or at runtime via the REST API.

### SDK-level policies

```python
@dt.agent(
    name="DataProcessor",
    roles=["Transform"],
    permissions=[
        Permission("data/input/*",   allow=True),
        Permission("data/output/*",  allow=True,  requires_shadow=True),
        Permission("data/raw/*",     allow=False),          # explicit deny
        Permission("**/.env",        allow=False),          # deny all .env files
        Permission("**/secrets/**",  allow=False),          # deny secrets dir
    ],
)
class DataProcessor:
    ...
```

`requires_shadow=True` means the tool call will first run in a sandbox (Wasm-isolated) to predict its outcome before touching the real resource. This is the pre-flight check for high-risk write operations.

**Pattern syntax** uses Unix shell globbing (`fnmatch`):

| Pattern | Matches |
|---|---|
| `src/*` | Any file directly in `src/` |
| `src/**` | Any file anywhere under `src/` |
| `db:read` | Exact string match — resource named "db:read" |
| `**/.env` | Any `.env` file at any depth |
| `node_modules/*` | Built-in deny — always blocked regardless of policy |

### Built-in deny list

These patterns are always denied regardless of agent configuration:

```
node_modules/*
**/.env
**/secrets/**
**/.git/config
```

### Runtime policy via API

```bash
# Create a new policy rule
curl -X POST http://localhost:8080/security/policies \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "Reporter",
    "resource_pattern": "src/config/*",
    "allow": false,
    "requires_shadow": false,
    "reason": "Reporter should only access synthesized data, not raw config"
  }'

# List all policies for an agent
curl http://localhost:8080/security/policies?agent=Reporter

# Delete a policy
curl -X DELETE http://localhost:8080/security/policies/<policy_id>
```

Policy changes are hot-reloaded — they are published to the `deeptrace:commands` Redis channel and picked up by connected SDK instances within one polling cycle (~1s).

---

## 11. Time-Travel Debugger

The Time Travel view lets you scrub through the complete execution history of any trace.

### Loading a trace

1. Click the **Time Travel** tab in the top nav
2. Paste a Trace ID into the input field and press Enter (or click **Load**)
3. Alternatively: click any agent node in Topology view and click the **Trace** button in the detail panel — this auto-loads that agent's most recent trace

### Using the scrubber

The timeline slider at the bottom replays the trace event-by-event. Drag left to rewind — events dim to show you the state of the system at that exact moment in time.

Each event row shows:

| Column | Content |
|---|---|
| Timestamp | Offset from trace start in seconds (T+0.00s) |
| Agent | Color-coded by agent identity |
| Description | Human-readable event summary |
| Tokens | Token delta for this event |

Events with anomalies are highlighted and tagged with the anomaly type inline.

### Context diff

```bash
# Get the context window diff between two spans in a trace
curl "http://localhost:8080/traces/<trace_id>/diff?span_a=<span_id_a>&span_b=<span_id_b>"
```

Returns:

```json
{
  "context_fragment_pct": 34.2,
  "token_delta": -1840,
  "fragmentation_alert": true,
  "risk": "HIGH"
}
```

A `context_fragment_pct` above 30% triggers a `CONTEXT_FRAGMENTATION` alert.

### Sandbox replay

Replay any failed trace with modified parameters to test fixes without affecting production:

```bash
curl -X POST http://localhost:8080/traces/<trace_id>/replay \
  -H "Content-Type: application/json" \
  -d '{
    "sandbox": true,
    "modifications": {
      "Planner.system_prompt": "You must not scan node_modules directories.",
      "SecurityScanner.model": "claude-3-haiku"
    }
  }'
```

The replay runs in an isolated sandbox. Results are surfaced as a new trace with the `replay_id` attached.

---

## 12. Security & Anomaly Detection

### Anomaly rules

DeepTrace runs 9 real-time detection rules on every span as it arrives:

| Rule ID | Trigger | Severity |
|---|---|---|
| `TOKEN_VELOCITY_HIGH` | > 3,000 tokens/minute | HIGH |
| `TOKEN_VELOCITY_CRITICAL` | > 8,000 tokens/minute | CRITICAL |
| `CONTEXT_FRAGMENTATION` | Context loss > 30% between parent and child | MEDIUM |
| `ZERO_TRUST_VIOLATION` | Tool call blocked by policy | HIGH |
| `RUNAWAY_LOOP` | > 20 spans in 60 seconds for same agent | CRITICAL |
| `TOKEN_SPIKE` | Current span tokens > 3× rolling average | MEDIUM |
| `LATENCY_SPIKE` | Latency > 3× EMA baseline for this agent | MEDIUM |
| `COST_RUNAWAY` | Cost spike > 10× per-minute baseline | HIGH |
| `PROMPT_INJECTION` | Injection keyword or anomalous behavior score ≥ 0.7 | CRITICAL |

### Security Heatmap

Open the **Security** tab to see the full permission matrix. Each cell shows the relationship between one agent and one resource:

| Cell color | Meaning |
|---|---|
| Green `READ` / `WRITE` | Allowed access (observed) |
| Red `DENY` | Access attempted and blocked |
| Purple `ANOM` | Anomalous access pattern — outside declared scope |
| Gray `—` | No interaction observed |

Click any cell to see the full access log for that agent-resource pair.

### Prompt injection detection

```bash
curl http://localhost:8080/security/prompt-injection?hours=6&confidence_threshold=0.7
```

The engine scores each span against three signals:
1. **Token spike after external data ingestion** — large token jump after a web/HTTP tool call
2. **Out-of-scope resource access** — agent touches resources outside its declared roles
3. **Injection keywords in metadata** — phrases like "ignore previous instructions", "new task:", "you are now", etc.

Spans scoring ≥ 0.7 are flagged as suspected injections.

### SOC2 / ISO 27001 audit export

```bash
# Export audit trail as JSON
curl "http://localhost:8080/security/audit-trail?start_ts=1700000000&end_ts=1700086400"

# Export as CSV for compliance tooling
curl "http://localhost:8080/security/audit-trail?start_ts=1700000000&end_ts=1700086400&format=csv" \
  -o audit_trail.csv
```

Every tool invocation in the export includes its Merkle hash. To verify chain integrity:

```bash
# Get the Merkle chain for a specific trace
curl http://localhost:8080/traces/<trace_id>/merkle
```

---

## 13. Metrics & Token Analytics

Open the **Metrics** tab for the analytics dashboard.

### Token Debt ranking

The token debt chart shows which agents are consuming the most tokens in the last 24 hours, sorted high-to-low. This is the primary tool for identifying "verbose" agents whose system prompts can be pruned to reduce cost.

Bars are color-coded:
- **Red** — > 10,000 tokens (high concern)
- **Amber** — 5,000–10,000 tokens (worth reviewing)
- **Green** — < 5,000 tokens (healthy)

### Latency percentiles

```bash
curl http://localhost:8080/metrics/latency-percentiles?window=1h
```

Returns P50, P90, and P99 latency for each agent. The Metrics tab renders these as a grouped bar chart. Use the time window picker (1h / 6h / 24h) to adjust the analysis window.

### Cost breakdown

```bash
curl http://localhost:8080/metrics/cost-breakdown?window=24h
```

Returns cost grouped by `(agent_name, model)`. The cost estimate uses these per-million-token prices:

| Model | Price (per 1M tokens) |
|---|---|
| claude-3-opus | $15.00 |
| claude-3-sonnet | $3.00 |
| claude-3-haiku | $0.25 |
| gpt-4o | $5.00 |
| gpt-4-turbo | $10.00 |
| gpt-3.5-turbo | $0.50 |

> **Note:** These are estimates for budget awareness. Always confirm against your provider's current pricing.

---

## 14. WebSocket Live Feed

The collector exposes two WebSocket endpoints for real-time streaming.

### Global feed — all agents

```javascript
const ws = new WebSocket("ws://localhost:8080/ws/live");

ws.onmessage = (event) => {
  const span = JSON.parse(event.data);
  console.log(span.agent_name, span.status, span.token_total);
};

// Keep-alive
setInterval(() => ws.readyState === 1 && ws.send("ping"), 25000);
```

### Per-agent feed

```javascript
const ws = new WebSocket("ws://localhost:8080/ws/agent/SecurityScanner");
// Receives only spans from the SecurityScanner agent
```

### Message schema

Every message is a JSON-serialized `TraceSpan` object. Key fields:

```json
{
  "trace_id":       "a3f2-8b1c-4e90-cf12",
  "span_id":        "f1e2-d3c4-b5a6-9870",
  "agent_name":     "SecurityScanner",
  "status":         "COMPLETED",
  "kind":           "AGENT",
  "duration_ms":    843.2,
  "token_total":    1240,
  "token_velocity": 882.4,
  "has_anomaly":    false,
  "anomalies":      [],
  "tool_invocations": [
    {
      "tool_name":   "read_file",
      "blocked":     false,
      "duration_ms": 47.1,
      "merkle_hash": "3a9f2c..."
    }
  ]
}
```

---

## 15. REST API Reference

Full interactive docs: `http://localhost:8080/api/docs`

### Ingest

| Method | Path | Description |
|---|---|---|
| `POST` | `/ingest/span` | Ingest a single span |
| `POST` | `/ingest/batch` | Ingest up to 500 spans |
| `POST` | `/ingest/event` | OTEL-compatible raw event ingest |

### Agents

| Method | Path | Description |
|---|---|---|
| `GET` | `/agents/` | List all agents in the mesh |
| `GET` | `/agents/:name` | Get agent detail |
| `GET` | `/agents/:name/spans` | Recent spans for an agent |
| `GET` | `/agents/:name/token_history` | Token usage time-series |
| `POST` | `/agents/:name/kill` | Kill a running agent |
| `POST` | `/agents/:name/hotpatch` | Inject system prompt delta |
| `GET` | `/agents/:name/permissions` | Zero-Trust permission summary |

### Traces

| Method | Path | Description |
|---|---|---|
| `GET` | `/traces/:id` | Full trace with causal tree |
| `GET` | `/traces/:id/timeline` | Chronological event list |
| `GET` | `/traces/:id/diff` | Context window diff between spans |
| `POST` | `/traces/:id/replay` | Sandbox replay with modifications |
| `GET` | `/traces/:id/merkle` | Merkle hash chain audit trail |

### Security

| Method | Path | Description |
|---|---|---|
| `GET` | `/security/heatmap` | Full permission matrix |
| `GET` | `/security/anomalies` | Active anomaly list |
| `POST` | `/security/anomalies/:id/resolve` | Resolve / mark false positive |
| `GET` | `/security/violations` | Zero-Trust violation log |
| `GET` | `/security/policies` | List policy rules |
| `POST` | `/security/policies` | Create / update policy rule |
| `DELETE` | `/security/policies/:id` | Delete policy rule |
| `GET` | `/security/prompt-injection` | Prompt injection scan |
| `GET` | `/security/audit-trail` | SOC2 audit export (JSON or CSV) |

### Metrics

| Method | Path | Description |
|---|---|---|
| `GET` | `/metrics/summary` | Global session metrics |
| `GET` | `/metrics/token-debt` | Token debt ranking |
| `GET` | `/metrics/latency-percentiles` | P50/P90/P99 by agent |
| `GET` | `/metrics/cost-breakdown` | Cost by agent + model |
| `GET` | `/metrics/topology` | Live graph snapshot |

---

## 16. Environment Variables

### Collector

| Variable | Default | Description |
|---|---|---|
| `DEEPTRACE_ENDPOINT` | `http://localhost:8080` | Collector URL (used by SDK) |
| `DEEPTRACE_SERVICE` | `deeptrace-agent` | Service name tag on spans |
| `DEEPTRACE_ENV` | `production` | Environment tag (`dev`, `staging`, `production`) |
| `DEEPTRACE_API_KEY` | *(empty)* | Optional API key for authenticated ingest |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt connection string |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `deeptrace` | Neo4j password |
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse hostname |
| `CLICKHOUSE_PORT` | `9000` | ClickHouse native TCP port |
| `CLICKHOUSE_DB` | `deeptrace` | ClickHouse database name |
| `KAFKA_BROKERS` | `localhost:9092` | Kafka bootstrap servers (comma-separated) |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `JWT_SECRET` | *(required)* | Secret for signing auth tokens |

### Frontend

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8080` | Collector API base URL |
| `VITE_WS_URL` | `ws://localhost:8080` | Collector WebSocket base URL |

---

## 17. Production Deployment

### Single-machine deployment with Docker Compose

The Docker Compose stack is designed to run entirely on one machine. For production, make these changes to `docker/docker-compose.yml`:

**1. Set a strong JWT secret:**

```bash
echo "JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> .env
```

**2. Lock Neo4j credentials:**

Change `NEO4J_PASSWORD` in `.env` and in the compose environment block.

**3. Set Kafka retention for your data volume:**

```yaml
# In docker-compose.yml under kafka environment:
KAFKA_LOG_RETENTION_HOURS: 72      # 3 days (reduce if disk-constrained)
KAFKA_LOG_SEGMENT_BYTES: 104857600  # 100MB per segment
```

**4. Tune ClickHouse memory:**

Edit `docker/clickhouse/config.xml`:
```xml
<max_server_memory_usage_to_ram_ratio>0.4</max_server_memory_usage_to_ram_ratio>
```

**5. Enable Neo4j authentication:**

Already enabled with `NEO4J_AUTH: neo4j/<password>` in the compose file. Open `http://localhost:7474` on first run to complete the password setup.

**6. Scale the collector workers:**

The Dockerfile starts 4 Uvicorn workers. Tune with the `WEB_CONCURRENCY` environment variable:

```yaml
# In docker-compose.yml under collector environment:
WEB_CONCURRENCY: "8"   # Rule of thumb: 2× CPU cores
```

### Reverse proxy with Traefik (optional)

The compose file includes Traefik labels for automatic service discovery if you add Traefik to the stack. To enable:

```bash
# Add traefik to your compose network and enable the labels:
traefik:
  image: traefik:v3.0
  command: --providers.docker --entrypoints.web.address=:80
  ports:
    - "80:80"
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
```

The dashboard will then be served at `http://deeptrace.local` and the API at `http://api.deeptrace.local`.

### Monitoring DeepTrace itself

The collector emits its own OpenTelemetry spans to `http://localhost:4318` (OTLP default). To self-instrument, set:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_SERVICE_NAME=deeptrace-collector
```

---

## 18. Troubleshooting

### No agents appear in the topology graph

**Symptom:** Dashboard shows "No agents detected" after starting the example swarm.

**Check 1 — Collector is running:**

```bash
curl http://localhost:8080/health
# Expected: {"status":"ok","service":"deeptrace-collector","version":"2.1.0"}
```

**Check 2 — Collector can reach its dependencies:**

```bash
curl http://localhost:8080/ready
# Expected: {"ready":true,"checks":{"neo4j":true,"clickhouse":true,"redis":true,"kafka":true}}
```

If any check is `false`, inspect the Docker logs:

```bash
docker compose logs neo4j      # look for "bolt://0.0.0.0:7687"
docker compose logs clickhouse # look for "Ready for connections"
```

**Check 3 — Spans are reaching the collector:**

```bash
# Send a test span manually
curl -X POST http://localhost:8080/ingest/span \
  -H "Content-Type: application/json" \
  -d '{
    "trace_id":"test-001","span_id":"span-001",
    "agent_name":"TestAgent","roles":[],"kind":"AGENT",
    "status":"COMPLETED","timestamp":1700000000,"duration_ms":100
  }'
# Expected: {"accepted":true,...}
```

---

### Purple "anomaly" node appears unexpectedly

A purple node means `ZERO_TRUST_VIOLATION` or another anomaly was detected. Check the Security tab → Anomalies for the specific rule that fired. Common false positives:

- **`TOKEN_VELOCITY_HIGH`** during initial context loading — normal on first span of a long-context agent. Increase the threshold: the anomaly engine thresholds are constants in `collector/services/anomaly_engine.py`.
- **`RUNAWAY_LOOP`** on agents that legitimately emit many short spans — increase the threshold from 20 spans/minute if appropriate.

---

### WebSocket connection drops repeatedly

The frontend auto-reconnects after 3 seconds. Persistent drops usually indicate the Nginx proxy is closing idle connections. Fix by increasing the proxy read timeout:

In `docker/nginx.conf`:
```nginx
location /ws/ {
    proxy_read_timeout 3600;   # increase from 86400s if needed
}
```

---

### ClickHouse insert errors in collector logs

```
ClickHouse insert error: Code: 241. Memory limit exceeded
```

Reduce `max_server_memory_usage_to_ram_ratio` in `docker/clickhouse/config.xml` and restart:

```bash
docker compose restart clickhouse
```

---

### Neo4j runs out of heap

```
Neo4j: java.lang.OutOfMemoryError: Java heap space
```

Increase heap in `docker-compose.yml`:

```yaml
NEO4J_dbms_memory_heap_max__size: "2g"    # increase from 1g
NEO4J_dbms_memory_pagecache_size: "512m"  # increase proportionally
```

---

### Kafka consumer group lag

If the graph engine consumer falls behind under high span volume:

```bash
# Check consumer group lag
docker exec -it docker-kafka-1 \
  kafka-consumer-groups --bootstrap-server localhost:29092 \
  --describe --group deeptrace-graph-engine
```

Increase `max_poll_records` in `graph_engine/consumer.py` and run multiple consumer instances — they will automatically distribute partitions across the 4 Kafka partitions.

---

### Spans are accepted but not visible in Neo4j

The collector writes to Neo4j in background tasks. Under high load, background tasks can be queued. Check the collector logs for `Neo4j upsert failed` warnings. If the graph service can't connect:

```bash
# Test Neo4j connectivity from the collector container
docker exec -it docker-collector-1 \
  python -c "from neo4j import GraphDatabase; d = GraphDatabase.driver('bolt://neo4j:7687', auth=('neo4j','deeptrace')); d.verify_connectivity(); print('OK')"
```

---

*For additional help, open the interactive API docs at `http://localhost:8080/api/docs` or check the collector logs with `docker compose logs -f collector`.*
