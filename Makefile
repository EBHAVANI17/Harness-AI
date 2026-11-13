# Makefile — Harness-Aware Plugin Evaluation Framework
#
# Targets
# -------
#   server   Start the FastMCP server on port 8000
#   l1       Run Level-1 deterministic tests (no API key needed)
#   l2       Run Level-2 live eval via promptfoo
#   replay   Replay recorded runs without API keys
#   all      l1 → l2 → replay in sequence
#   clean    Remove generated data files
#   install  Install dependencies with uv
#
# Windows note: use `nmake /f Makefile` or install GNU Make via
#   winget install GnuWin32.Make
# Alternatively run the commands directly (see README.md).

PYTHON  := python
UV      := uv
PF      := npx promptfoo

.PHONY: server l1 l2 replay all clean install

## Start the MCP server (Ctrl-C to stop)
server:
	$(PYTHON) server.py

## Level-1: deterministic tool tests (no model, no API key)
l1:
	$(PYTHON) level_one.py

## Level-2: live model eval via promptfoo
l2:
	$(PF) eval --config promptfooconfig.yaml

## Replay recorded runs from data/
replay:
	$(PYTHON) replay.py

## Run everything in sequence
all: l1 l2 replay

## Remove generated data files (keeps .gitkeep and README.md)
clean:
	$(PYTHON) -c "import pathlib; [p.unlink() for p in pathlib.Path('data').glob('*.json')]"
	@echo "data/*.json removed."

## Install / sync dependencies with uv
install:
	$(UV) sync
