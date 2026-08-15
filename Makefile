.PHONY: build serve

build:
	python3 build/pipeline.py

serve:
	./scripts/serve.sh
