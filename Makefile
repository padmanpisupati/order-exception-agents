PY ?= python3
VENV ?= .venv
BIN = $(VENV)/bin
export PYTHONPATH := src

.PHONY: setup sample demo demo-mini test clean zip
setup:
	$(PY) -m venv $(VENV) && $(BIN)/pip install -q -r requirements.txt
sample:
	$(BIN)/python scripts/generate_sample.py
demo:
	$(BIN)/python -m oea.demo
demo-mini:   ## force the dependency-free graph runner
	$(BIN)/python -m oea.demo --no-langgraph
test:
	$(BIN)/python -m pytest -q
clean:
	rm -rf out .pytest_cache **/__pycache__
