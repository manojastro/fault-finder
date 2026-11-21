# On Windows without make, use the same targets via:  py tasks.py <target>
ifeq ($(OS),Windows_NT)
PY := .venv/Scripts/python
else
PY := .venv/bin/python
endif

.PHONY: setup ingest seed test eval baseline run report compare

setup:
	uv venv --python 3.11 .venv || python3.11 -m venv .venv
	uv pip install --python $(PY) -e ".[dev]" || $(PY) -m pip install -e ".[dev]"
	@test -f .env || cp .env.example .env

ingest:
	$(PY) -m app.cli ingest

seed:
	$(PY) -m app.cli seed

test:
	$(PY) -m pytest

eval:
	$(PY) -m evals.run_eval

baseline:
	$(PY) -m evals.run_eval --save-baseline

run:
	$(PY) -m uvicorn app.api:app --reload --port 8000

report:
	$(PY) -m scripts.trace_report

compare:
	$(PY) -m scripts.compare_retrieval
