![DeepTrace](./deeptrace-banner.svg)

<!-- Version & Release -->
![Version](https://img.shields.io/badge/version-2.1.0-00d4ff?style=flat-square&labelColor=080f1a)
![License](https://img.shields.io/badge/license-MIT-00e5a0?style=flat-square&labelColor=080f1a)
![Status](https://img.shields.io/badge/status-production--ready-00e5a0?style=flat-square&labelColor=080f1a)

<!-- Stack -->
![Python](https://img.shields.io/badge/Python-3.11%2B-3b9eff?style=flat-square&logo=python&logoColor=white&labelColor=080f1a)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-00e5a0?style=flat-square&logo=fastapi&logoColor=white&labelColor=080f1a)
![React](https://img.shields.io/badge/React-18-3b9eff?style=flat-square&logo=react&logoColor=white&labelColor=080f1a)
![TypeScript](https://img.shields.io/badge/TypeScript-5.4-3b9eff?style=flat-square&logo=typescript&logoColor=white&labelColor=080f1a)

<!-- Infrastructure -->
![Neo4j](https://img.shields.io/badge/Neo4j-5.19-00e5a0?style=flat-square&logo=neo4j&logoColor=white&labelColor=080f1a)
![ClickHouse](https://img.shields.io/badge/ClickHouse-24.4-ffb347?style=flat-square&logo=clickhouse&logoColor=white&labelColor=080f1a)
![Kafka](https://img.shields.io/badge/Kafka-7.6-ff6b9d?style=flat-square&logo=apachekafka&logoColor=white&labelColor=080f1a)
![Redis](https://img.shields.io/badge/Redis-7.2-ff4560?style=flat-square&logo=redis&logoColor=white&labelColor=080f1a)
![Docker](https://img.shields.io/badge/Docker-Compose-3b9eff?style=flat-square&logo=docker&logoColor=white&labelColor=080f1a)

<!-- Observability & Standards -->
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-compatible-9b6dff?style=flat-square&logo=opentelemetry&logoColor=white&labelColor=080f1a)
![LangChain](https://img.shields.io/badge/LangChain-integrated-00e5a0?style=flat-square&labelColor=080f1a)
![WebSocket](https://img.shields.io/badge/WebSocket-live--feed-00d4ff?style=flat-square&labelColor=080f1a)

<!-- Security & Compliance -->
![Zero-Trust](https://img.shields.io/badge/Zero--Trust-enforced-9b6dff?style=flat-square&labelColor=080f1a)
![SOC2](https://img.shields.io/badge/SOC2-audit--ready-00e5a0?style=flat-square&labelColor=080f1a)
![ISO27001](https://img.shields.io/badge/ISO%2027001-audit--ready-00e5a0?style=flat-square&labelColor=080f1a)
![Merkle](https://img.shields.io/badge/Merkle%20Chain-tamper--evident-ffb347?style=flat-square&labelColor=080f1a)

# DeepTrace — LLM Service Mesh & Observability Platform

> Real-time observability layer for agentic AI systems. Intercept, trace, visualize, and secure every LLM inference and tool invocation across your agent swarm.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        DeepTrace Stack                          │
├──────────────┬───────────────────┬───────────────┬──────────────┤
│  Python SDK  │  FastAPI          │  Neo4j        │  React UI    │
│  (Middleware)│  Collector        │  Graph Engine │  Dashboard   │
│              │  + Kafka Consumer │  + ClickHouse │              │
└──────────────┴───────────────────┴───────────────┴──────────────┘
```

### Components

| Component | Path | Purpose |
|-----------|------|---------|
| **SDK** | `sdk/` | Python decorator/middleware for LangChain, CrewAI, AutoGen |
| **Collector** | `collector/` | FastAPI ingest server + Kafka consumer |
| **Graph Engine** | `graph_engine/` | Neo4j driver, ClickHouse writer, anomaly detection |
| **Frontend** | `frontend/` | React + D3/Canvas topology dashboard |
| **Docker** | `docker/` | Compose stack for all services |

---

## Quick Start

### 1. Start the infrastructure
```bash
cd docker
docker compose up -d
```

### 2. Start the collector
```bash
cd collector
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### 3. Start the frontend
```bash
cd frontend
npm install
npm run dev
```

### 4. Instrument your agents
```python
from deeptrace import DeepTrace, TraceConfig

dt = DeepTrace(TraceConfig(endpoint="http://localhost:8080"))

@dt.agent(name="MyAgent", roles=["CodeAudit", "FileRead"])
class MyAgent:
    def run(self, task: str) -> str:
        ...
```

---

## Features

- **Live Topology Graph** — Force-directed agent mesh with real-time latency coloring
- **Token Intensity** — Node size + ring arc visualizing token budget pressure
- **Time-Travel Debugger** — Scrub through execution history, diff context windows
- **Security Heatmap** — Agent × Resource permission matrix with anomaly detection
- **Zero-Trust Enforcement** — Policy engine blocking unauthorized tool invocations
- **Hot Patching** — Inject system prompt updates to running agents without restart
- **Forensic Tagging** — Merkle tree hashes on every tool invocation for audit trails
- **Context Fragmentation Detection** — Alert when >30% context lost between agents

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPTRACE_ENDPOINT` | `http://localhost:8080` | Collector API URL |
| `NEO4J_URI` | `bolt://localhost:7687` | Graph database |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `deeptrace` | Neo4j password |
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse host |
| `CLICKHOUSE_PORT` | `9000` | ClickHouse port |
| `KAFKA_BROKERS` | `localhost:9092` | Kafka bootstrap servers |
| `REDIS_URL` | `redis://localhost:6379` | Redis for live pub/sub |
| `JWT_SECRET` | *(required)* | Auth token signing secret |

---

## License

MIT — Built for production AI systems requiring enterprise-grade observability.
