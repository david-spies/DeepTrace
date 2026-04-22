.PHONY: up down dev sdk-install collector-install fe-install fe-dev test lint clean

# ── Infrastructure ─────────────────────────────────────────
up:
	cd docker && docker compose up -d
	@echo "DeepTrace infrastructure started."
	@echo "  Neo4j browser:   http://localhost:7474"
	@echo "  Collector API:   http://localhost:8080/api/docs"
	@echo "  Dashboard:       http://localhost:3000"

down:
	cd docker && docker compose down

logs:
	cd docker && docker compose logs -f --tail=100

# ── Development ────────────────────────────────────────────
dev: up
	@echo "Starting collector + frontend in parallel..."
	@$(MAKE) -j2 collector-dev fe-dev

collector-dev:
	cd collector && uvicorn main:app --host 0.0.0.0 --port 8080 --reload

fe-dev:
	cd frontend && npm run dev

graph-engine:
	cd graph_engine && python -m consumer

# ── Install ────────────────────────────────────────────────
install: sdk-install collector-install fe-install

sdk-install:
	pip install -r sdk/requirements.txt

collector-install:
	pip install -r collector/requirements.txt

fe-install:
	cd frontend && npm install

# ── Example ────────────────────────────────────────────────
example:
	python scripts/example_swarm.py

# ── Tests ──────────────────────────────────────────────────
test:
	pytest tests/ -v

lint:
	cd frontend && npm run lint
	ruff check collector/ sdk/ graph_engine/

type-check:
	cd frontend && npm run type-check
	mypy collector/ sdk/ --ignore-missing-imports

# ── Clean ──────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	cd frontend && rm -rf node_modules dist 2>/dev/null || true
