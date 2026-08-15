.PHONY: build serve

# Prefers the venv's own interpreter regardless of whether it's been
# `source .venv/bin/activate`-d in the current shell — mirrors
# scripts/serve.sh's own fallback, so `make build` works cold.
PYTHON := $(shell test -x .venv/bin/python3 && echo .venv/bin/python3 || echo python3)

build:
	$(PYTHON) build/pipeline.py

serve:
	./scripts/serve.sh
