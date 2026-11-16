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
