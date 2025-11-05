.PHONY: sync run-week run-week-wc lint format check

# Sync dependencies with uv
sync:
	uv sync

# default weekly run (no wildcard)
run-week:
	uv run run-week --horizon 4 --min_sixty 5

# example with wildcard & 2 FTs
run-week-wc:
	uv run run-week --horizon 4 --min_sixty 5 --use_wildcard --budget 100 --ft 2 --suggest_from_myteam

# Linting: run Ruff on source files
lint:
	uv run ruff check src

# Formatting: apply Ruff + Black to src/
format:
	uv run ruff format src
	uv run black src
