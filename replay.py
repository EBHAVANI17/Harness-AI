"""
replay.py — Replay recorded runs from the data/ directory.

Loads previously saved trace files and re-grades them with eval_grading.py
without needing an API key or a running MCP server.  Useful for:

  - CI regression checks against golden recordings
  - Reviewing failures after a provider run
  - Verifying that grading logic changes don't break existing results

Usage
-----
    python replay.py                  # grades both l1-results.json and l2-trace.json
    python replay.py --l1-only        # only level-1 results
    python replay.py --l2-only        # only level-2 traces
    python replay.py --fail-only      # only print failures

Exit codes
----------
    0 — all graded cases passed
    1 — one or more graded cases failed
    2 — no data files found
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Allow running from any working directory
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

from eval_grading import grade  # noqa: E402

import yaml  # noqa: E402

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = REPO_ROOT / "data"
L1_PATH = DATA_DIR / "l1-results.json"
L2_PATH = DATA_DIR / "l2-trace.json"
CONFIG_PATH = REPO_ROOT / "promptfooconfig.yaml"

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty() or os.getenv("FORCE_COLOR")

def _green(s: str) -> str:  return f"\033[32m{s}\033[0m" if _USE_COLOR else s
def _red(s: str) -> str:    return f"\033[31m{s}\033[0m" if _USE_COLOR else s
def _yellow(s: str) -> str: return f"\033[33m{s}\033[0m" if _USE_COLOR else s
def _bold(s: str) -> str:   return f"\033[1m{s}\033[0m"  if _USE_COLOR else s
def _dim(s: str) -> str:    return f"\033[2m{s}\033[0m"  if _USE_COLOR else s


# ---------------------------------------------------------------------------
# Level-1 replay
# ---------------------------------------------------------------------------

def replay_l1(fail_only: bool = False) -> tuple[int, int]:
    """Reload l1-results.json and report pass/fail counts."""
    if not L1_PATH.exists():
        print(_yellow(f"  [skip] {L1_PATH} not found — run `python level_one.py` first."))
        return 0, 0

    results: list[dict[str, Any]] = json.loads(L1_PATH.read_text(encoding="utf-8"))
    passed = failed = 0

    print(_bold(f"\n── Level-1 Replay ({len(results)} cases) ──\n"))
    for i, r in enumerate(results, 1):
        ok: bool = r.get("passed", False)
        if ok:
            passed += 1
        else:
            failed += 1
        if fail_only and ok:
            continue
        status = _green("PASS") if ok else _red("FAIL")
        print(f"  [{i:02d}] {status}  {r.get('description', '(unnamed)')}")
        if not ok:
            print(f"         ↳ {_yellow(r.get('reason', ''))}")

    return passed, failed


# ---------------------------------------------------------------------------
# Level-2 replay
# ---------------------------------------------------------------------------

def _load_test_vars() -> list[dict[str, Any]]:
    """Load test-case vars from promptfooconfig.yaml."""
    if not CONFIG_PATH.exists():
        return []
    with CONFIG_PATH.open(encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("tests", [])


def replay_l2(fail_only: bool = False) -> tuple[int, int]:
    """
    Load l2-trace.json (list of provider run dicts) and re-grade each one
    against the corresponding test case in promptfooconfig.yaml.
    """
    if not L2_PATH.exists():
        print(_yellow(f"  [skip] {L2_PATH} not found — run `python provider.py` first."))
        return 0, 0

    traces: list[dict[str, Any]] = json.loads(L2_PATH.read_text(encoding="utf-8"))
    test_cases = _load_test_vars()

    # Align traces to test cases by index (traces are appended in order)
    if not test_cases:
        print(_yellow("  [warn] promptfooconfig.yaml not found — grading without expected IDs."))

    passed = failed = 0
    print(_bold(f"\n── Level-2 Replay ({len(traces)} recorded runs) ──\n"))

    for i, trace in enumerate(traces):
        tc = test_cases[i] if i < len(test_cases) else {}
        vars_: dict[str, Any] = tc.get("vars", {})
        if "metadata" in tc:
            vars_ = {**vars_, "metadata": tc["metadata"]}

        tool_calls: list[dict[str, Any]] = trace.get("tool_calls", [])
        answer: str = trace.get("answer", "")
        completed: bool = trace.get("completed", False)
        backend: str = trace.get("backend", "?")

        result = grade(
            tool_calls=tool_calls,
            vars_=vars_,
            answer=answer,
            completed=completed,
        )

        ok = result["passed"]
        score = result["score"]
        if ok:
            passed += 1
        else:
            failed += 1

        if fail_only and ok:
            continue

        status = _green("PASS") if ok else _red("FAIL")
        desc = tc.get("description", f"run #{i+1}")
        print(f"  [{i+1:02d}] {status}  {desc}  {_dim(f'(backend={backend}, score={score:.2f})')}")
        if not ok:
            print(f"         ↳ {_yellow(result['reason'])}")

    return passed, failed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Replay recorded evaluation runs.")
    parser.add_argument("--l1-only", action="store_true", help="Only replay level-1 results.")
    parser.add_argument("--l2-only", action="store_true", help="Only replay level-2 traces.")
    parser.add_argument("--fail-only", action="store_true", help="Only print failures.")
    args = parser.parse_args()

    print(_bold("\n╔══ Harness-Aware Plugin Eval — Replay ══╗\n"))

    total_pass = total_fail = 0
    any_data = False

    if not args.l2_only:
        p, f = replay_l1(fail_only=args.fail_only)
        total_pass += p
        total_fail += f
        if p + f > 0:
            any_data = True

    if not args.l1_only:
        p, f = replay_l2(fail_only=args.fail_only)
        total_pass += p
        total_fail += f
        if p + f > 0:
            any_data = True

    if not any_data:
        print(_yellow("\nNo recorded data found in data/. Run level_one.py or provider.py first.\n"))
        return 2

    print(f"\n{'─' * 50}")
    print(
        f"Overall: {_green(str(total_pass))} passed, "
        f"{(_red(str(total_fail)) if total_fail else '0')} failed "
        f"(total {total_pass + total_fail})"
    )
    print()
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
