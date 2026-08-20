.PHONY: install format lint typecheck test test-fast quality synthetic-demo stage1-gate stage1-5-gate stage1-6-gate review-bundle

UV ?= uv

install:
	$(UV) sync --all-groups

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy src

test:
	$(UV) run pytest -q --cov=g2lc --cov-report=term-missing --cov-fail-under=85

test-fast:
	$(UV) run pytest -q tests/unit tests/guidelines

quality: lint typecheck test

synthetic-demo:
	$(UV) run g2lc synthetic run --fixture minimal_dr
	$(UV) run g2lc certificate verify artifacts/synthetic/minimal_dr/certificate.json

stage1-gate: quality synthetic-demo

stage1-5-gate:
	$(UV) run python scripts/stage1_5_gate.py

stage1-6-gate:
	$(UV) run python scripts/stage1_6_gate.py

review-bundle:
	$(UV) run python scripts/review_bundle.py --stage 1.6
