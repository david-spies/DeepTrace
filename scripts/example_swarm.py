"""
DeepTrace SDK — Example: Multi-Agent Security Audit Swarm
=========================================================
Run this to see DeepTrace in action with simulated agent telemetry.

Prerequisites:
    pip install -r sdk/requirements.txt
    # Collector must be running on localhost:8080
    # OR set DEEPTRACE_ENDPOINT=http://your-collector:8080

Usage:
    python scripts/example_swarm.py
"""

import asyncio
import random
import time
import sys
import os

# Add sdk to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sdk.deeptrace import (
    DeepTrace, TraceConfig, SpanKind, Permission,
    compute_context_fragment,
)


# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────

config = TraceConfig(
    endpoint=os.getenv("DEEPTRACE_ENDPOINT", "http://localhost:8080"),
    service_name="security-audit-swarm",
    environment="development",
    zero_trust_enabled=True,
    shadow_tool_execution=False,
)

dt = DeepTrace(config)


# ─────────────────────────────────────────
# TOOL DEFINITIONS
# ─────────────────────────────────────────

@dt.tool(name="read_file", resource="src/*")
def read_file(path: str) -> str:
    """Simulated file read."""
    time.sleep(random.uniform(0.05, 0.2))
    return f"<file content of {path}: {random.randint(100, 500)} lines>"


@dt.tool(name="scan_dependencies", resource="package.json")
def scan_dependencies(lockfile: str) -> dict:
    """Simulated dependency scan."""
    time.sleep(random.uniform(0.3, 0.9))
    vulns = random.randint(0, 5)
    return {
        "vulnerabilities": vulns,
        "critical": random.randint(0, vulns),
        "cve_ids": [f"CVE-2024-{random.randint(1000, 9999)}" for _ in range(min(3, vulns))],
    }


@dt.tool(name="query_db", resource="db:read")
def query_db(sql: str) -> list:
    """Simulated DB read (allowed)."""
    time.sleep(random.uniform(0.01, 0.05))
    return [{"id": i, "data": f"row_{i}"} for i in range(3)]


@dt.tool(name="write_db", resource="db:write")
def write_db(table: str, data: dict) -> bool:
    """Simulated DB write — will be blocked for Reporter agent."""
    time.sleep(0.01)
    return True


@dt.tool(name="read_config", resource="src/config/secrets.env")
def read_config() -> dict:
    """Reads sensitive config — should trigger Zero-Trust alert for most agents."""
    time.sleep(0.05)
    return {"api_key": "sk-REDACTED", "db_pass": "REDACTED"}


@dt.tool(name="generate_patch", resource="src/*")
def generate_patch(finding: dict) -> str:
    """Generate a code patch for a vulnerability."""
    time.sleep(random.uniform(0.2, 0.6))
    return f"diff --git a/{finding.get('file', 'src/auth.ts')} b/{finding.get('file', 'src/auth.ts')}\n+// PATCH: {finding.get('type', 'SQLi')} fix applied"


@dt.tool(name="call_external_api", resource="ext-api")
def call_external_api(endpoint: str, payload: dict) -> dict:
    """Simulated external API call."""
    time.sleep(random.uniform(0.1, 0.5))
    return {"status": "ok", "result": f"Response from {endpoint}"}


# ─────────────────────────────────────────
# AGENTS
# ─────────────────────────────────────────

@dt.trace(
    name="Planner",
    roles=["Orchestration", "TaskDecompose", "SubAgentSpawn"],
    kind=SpanKind.AGENT,
    model="claude-3-opus",
)
def run_planner(task: str) -> dict:
    """Orchestrator: decomposes the task and coordinates sub-agents."""
    print(f"[Planner] Starting task: {task[:60]}…")

    # Simulate chain-of-thought reasoning
    time.sleep(random.uniform(0.3, 0.8))

    subtasks = [
        {"type": "dependency_scan",  "agent": "SecurityScanner", "priority": "HIGH"},
        {"type": "static_analysis",  "agent": "CodeAuditor",     "priority": "HIGH"},
        {"type": "report_synthesis", "agent": "Reporter",        "priority": "MEDIUM"},
    ]

    print(f"[Planner] Decomposed into {len(subtasks)} subtasks")
    return {"subtasks": subtasks, "trace_context": "Analyze repo for CVEs and generate patches"}


@dt.trace(
    name="SecurityScanner",
    roles=["CodeAudit", "FileSystemRead", "VulnScan"],
    kind=SpanKind.AGENT,
    model="claude-3-sonnet",
)
def run_security_scanner(context: str) -> dict:
    """Scans the codebase for vulnerabilities."""
    print("[SecurityScanner] Starting scan…")

    findings = []

    # Read source files
    for path in ["src/auth/login.ts", "src/api/routes.ts", "src/utils/query.ts"]:
        content = read_file(path)
        if random.random() > 0.5:
            findings.append({
                "file": path,
                "type": random.choice(["SQLi", "XSS", "IDOR", "AuthBypass"]),
                "severity": random.choice(["HIGH", "CRITICAL", "MEDIUM"]),
                "line": random.randint(10, 200),
            })

    # Scan dependencies
    dep_result = scan_dependencies("package-lock.json")
    if dep_result["vulnerabilities"] > 0:
        findings.append({
            "type": "DEP_VULN",
            "cves": dep_result["cve_ids"],
            "severity": "HIGH",
        })

    # Simulate runaway: occasionally try to access node_modules (will be allowed since
    # no explicit deny rule in this demo — in production Zero-Trust would block it)
    if random.random() > 0.8:
        try:
            content = read_file("node_modules/.bin/something")
            print("[SecurityScanner] WARNING: Scanned node_modules — exclusion zone violation!")
        except PermissionError as e:
            print(f"[SecurityScanner] BLOCKED: {e}")

    print(f"[SecurityScanner] Found {len(findings)} issues")
    return {"findings": findings, "scan_complete": True}


@dt.trace(
    name="CodeAuditor",
    roles=["StaticAnalysis", "FileSystemRead"],
    kind=SpanKind.AGENT,
    model="claude-3-haiku",
)
def run_code_auditor(context: str) -> dict:
    """Performs static analysis on the codebase."""
    print("[CodeAuditor] Starting static analysis…")

    # Read and analyze source
    sources = {}
    for path in ["src/auth/query.ts", "src/middleware/validate.ts"]:
        sources[path] = read_file(path)
        time.sleep(random.uniform(0.1, 0.3))

    # DB read (allowed)
    schema = query_db("SELECT * FROM information_schema.tables LIMIT 5")

    findings = []
    for path, content in sources.items():
        if random.random() > 0.4:
            findings.append({
                "file": path,
                "line": random.randint(1, 100),
                "rule": random.choice(["no-raw-sql", "require-auth", "validate-input"]),
                "severity": "MEDIUM",
                "message": "Potential injection vector in parameterized query",
            })

    print(f"[CodeAuditor] Static analysis complete: {len(findings)} findings")
    return {"findings": findings, "lines_analyzed": 2847}


@dt.trace(
    name="Patcher",
    roles=["CodeGenerate", "FileWrite", "DiffApply"],
    kind=SpanKind.AGENT,
    model="claude-3-haiku",
)
def run_patcher(findings: list) -> dict:
    """Generates and applies patches for discovered vulnerabilities."""
    print(f"[Patcher] Generating patches for {len(findings)} findings…")

    patches = []
    for finding in findings[:3]:  # limit for demo
        patch = generate_patch(finding)
        patches.append({
            "finding": finding,
            "patch": patch,
            "applied": True,
        })
        time.sleep(random.uniform(0.1, 0.4))

    print(f"[Patcher] Generated {len(patches)} patches")
    return {"patches": patches, "status": "ready_for_review"}


@dt.trace(
    name="Reporter",
    roles=["ReportGenerate", "ExternalAPI"],
    kind=SpanKind.AGENT,
    model="claude-3-opus",
)
def run_reporter(audit_results: dict) -> dict:
    """
    Synthesizes audit results into a report.
    INTENTIONALLY attempts out-of-scope actions to demonstrate Zero-Trust.
    """
    print("[Reporter] Synthesizing report…")

    # Allowed: call external API
    ext = call_external_api("https://api.nvd.nist.gov/vuln/enrichment", audit_results)

    # ANOMALY: Try to read secrets config (outside role boundary)
    print("[Reporter] Attempting to read src/config/secrets.env (should be blocked)…")
    try:
        secrets = read_config()
        print(f"[Reporter] WARNING: Read secrets — {secrets}")
    except PermissionError as e:
        print(f"[Reporter] BLOCKED by Zero-Trust: {e}")

    # ANOMALY: Try to write to DB (outside role boundary)
    print("[Reporter] Attempting db:write (should be blocked)…")
    try:
        write_db("audit_log", {"results": "data"})
        print("[Reporter] WARNING: DB write succeeded — policy misconfiguration!")
    except PermissionError as e:
        print(f"[Reporter] BLOCKED by Zero-Trust: {e}")

    # Simulate high token usage (verbose LLM output)
    time.sleep(random.uniform(1.0, 2.5))

    total_findings = (
        len(audit_results.get("scanner_findings", [])) +
        len(audit_results.get("auditor_findings", []))
    )

    report = {
        "summary": f"Security audit complete. {total_findings} findings identified.",
        "risk_score": "HIGH" if total_findings > 3 else "MEDIUM",
        "patches_ready": len(audit_results.get("patches", [])),
        "requires_immediate_action": total_findings > 2,
    }

    print(f"[Reporter] Report generated: {report['summary']}")
    return report


# ─────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────

async def run_swarm(task: str):
    print("=" * 60)
    print(f"DeepTrace Example Swarm")
    print(f"Task: {task}")
    print(f"Collector: {config.endpoint}")
    print("=" * 60)

    # Run agents (in a real system these would be parallel + async)
    plan = run_planner(task)

    scanner_result = run_security_scanner(
        context="Analyze codebase at ./src/ for security vulnerabilities"
    )

    auditor_result = run_code_auditor(
        context="Static analysis of TypeScript source — focus on injection risks"
    )

    # Detect context fragmentation
    planner_ctx = str(plan)
    scanner_ctx = str(scanner_result)
    frag = compute_context_fragment(planner_ctx, scanner_ctx)
    if frag > 0.3:
        print(f"[Orchestrator] ⚠ Context fragmentation detected: {frag*100:.1f}%")

    patch_result = run_patcher(
        findings=scanner_result.get("findings", []) + auditor_result.get("findings", [])
    )

    report = run_reporter(audit_results={
        "scanner_findings": scanner_result.get("findings", []),
        "auditor_findings":  auditor_result.get("findings", []),
        "patches":           patch_result.get("patches", []),
    })

    print("\n" + "=" * 60)
    print("Swarm complete. Open DeepTrace dashboard to inspect the trace.")
    print(f"  Risk Score:   {report.get('risk_score', '?')}")
    print(f"  Patches Ready: {report.get('patches_ready', 0)}")
    print("=" * 60)

    # Flush remaining spans
    dt.flush()


if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or "Analyze this repository and generate security patches for all vulnerabilities found."
    asyncio.run(run_swarm(task))
