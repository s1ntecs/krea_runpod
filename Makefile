.PHONY: test lint check build

test:
	PYTHONPATH=src pytest -q

lint:
	ruff check src scripts tests

check: lint test
	python -m compileall -q src scripts

build:
	docker build -t krea-runpod:local .
