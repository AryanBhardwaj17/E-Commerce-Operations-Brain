.PHONY: dev dev-worker test seed seed-postgres lint fmt typecheck frontend-check docker-up docker-down clean install check test-unit test-integration test-eval test-cov docker-logs docker-build

# ── Development ──────────────────────────────────────────────────────────────
dev:
	uvicorn --app-dir backend/src api.main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	eob-worker

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	pytest -c backend/pyproject.toml backend/tests/unit backend/tests/integration -v

test-unit:
	pytest -c backend/pyproject.toml backend/tests/unit -v -m unit

test-integration:
	pytest -c backend/pyproject.toml backend/tests/integration -v -m integration

test-eval:
	deepeval test run backend/tests/eval/

test-cov:
	pytest -c backend/pyproject.toml backend/tests/unit backend/tests/integration --cov=backend/src --cov-report=html --cov-report=term-missing

# ── Seeding ───────────────────────────────────────────────────────────────────
seed:
	python backend/scripts/seed_kedb.py
	python backend/scripts/seed_kadb.py

seed-postgres:
	python backend/scripts/seed_postgres.py

# ── Code Quality ──────────────────────────────────────────────────────────────
lint:
	ruff check --config backend/pyproject.toml backend/src backend/tests backend/scripts

fmt:
	ruff format --config backend/pyproject.toml backend/src backend/tests backend/scripts

typecheck:
	python -m mypy --config-file backend/pyproject.toml backend/src

frontend-check:
	npm --prefix frontend run typecheck
	npm --prefix frontend run build

check: lint typecheck frontend-check

# ── Docker ────────────────────────────────────────────────────────────────────
docker-up:
	docker compose -f docker-compose.yml up -d

docker-down:
	docker compose -f docker-compose.yml down

docker-logs:
	docker compose -f docker-compose.yml logs -f

docker-build:
	docker compose -f docker-compose.yml build

# ── Setup ─────────────────────────────────────────────────────────────────────
install:
	pip install -e "./backend[dev]"
	pre-commit install

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
