# Robust imports even if macOS hides the editable-install .pth inside .venv.
export PYTHONPATH := $(CURDIR)/src:$(CURDIR)

.PHONY: install lint typecheck test check up down demo

install:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy src

test:
	uv run pytest --cov

check: lint typecheck test

up:
	docker compose up -d --build --wait

down:
	docker compose down

smoke:
	uv run python scripts/smoke_llm.py

dataroom:
	uv run python scripts/generate_dataroom.py --seed 7

corpus:
	uv run python scripts/fetch_regulatory_corpus.py --slice small

corpus-full:
	uv run python scripts/fetch_regulatory_corpus.py --slice full

roi:
	uv run python scripts/run_roi.py

graph:
	uv run python scripts/build_graph.py
	uv run python -m evals.answer_key_eval

ingest:
	uv run python scripts/ingest.py

eval-retrieval:
	uv run python -m evals.run_retrieval
	uv run python -m evals.temporal_eval
	uv run python evals/guardrail_eval.py
	uv run python -m evals.report
	uv run python scripts/build_readme_metrics.py

eval-ci:
	uv run python evals/guardrail_eval.py
	uv run python -m evals.ci_subset

golden:
	uv run python scripts/generate_golden.py

review:
	uv run python scripts/review_golden.py

# macOS can mark files inside .venv as hidden; Python 3.12 then ignores the editable .pth.
fix-venv:
	chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true

process-db:
	uv run python scripts/build_process_db.py
