"""
level_one.py — Level-1 deterministic tool tests (no model, no API key needed).

Loads test cases from promptfooconfig.yaml, calls resolve_metric() directly
from server.py, and verifies the expected metric IDs appear in the candidates.

Usage
-----
    python level_one.py

Exit codes
----------
    0 — all tests passed
    1 — one or more tests failed
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Allow running from any working directory
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

from server import resolve_metric  # noqa: E402  (after sys.path tweak)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CONFIG_PATH = REPO_ROOT / "promptfooconfig.yaml"
DATA_DIR = REPO_ROOT / "data"
RESULTS_PATH = DATA_DIR / "l1-results.json"

# ---------------------------------------------------------------------------
# ANSI helpers (Windows-safe: set FORCE_COLOR=1 to enable, or pipe to file)
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty() or os.getenv("FORCE_COLOR")

def _green(s: str) -> str:  return f"\033[32m{s}\033[0m" if _USE_COLOR else s
def _red(s: str) -> str:    return f"\033[31m{s}\033[0m" if _USE_COLOR else s
def _yellow(s: str) -> str: return f"\033[33m{s}\033[0m" if _USE_COLOR else s
def _bold(s: str) -> str:   return f"\033[1m{s}\033[0m"  if _USE_COLOR else s


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _indicators_from_vars(vars_: dict[str, Any]) -> list[str]:
    """
    Split the 'indicator' var (may be comma-separated for multi-step cases).
    """
    raw: str = vars_.get("indicator", "")
    return [i.strip() for i in raw.split(",") if i.strip()]


def _all_candidate_ids(result_obj: dict[str, Any]) -> set[str]:
    """Return flat set of all metric_ids across all resolved indicators."""
    ids: set[str] = set()
    for item in result_obj.get("results", []):
        for c in item.get("candidates", []):
            ids.add(c["metric_id"])
    return ids


def evaluate_case(test: dict[str, Any]) -> dict[str, Any]:
    """
    Run a single level-1 evaluation.

    Rules
    -----
    - For 'pass' expected_type   : all expected_metric_ids must appear as candidates.
    - For 'clarification'        : all expected_top_ids must appear, implying a tie.
    - For 'gap'                  : expected_metric_ids must be EMPTY and no candidates
                                   with confidence ≥ 0.6 should be returned.
    """
    desc = test.get("description", "(unnamed)")
    vars_ = test.get("vars", {})
    metadata = test.get("metadata", {})
    expected_type: str = metadata.get("expected_type", "pass")
    expected_metric_ids: list[str] = vars_.get("expected_metric_ids", [])
    expected_top_ids: list[str] = vars_.get("expected_top_ids", [])

    indicators = _indicators_from_vars(vars_)
    if not indicators:
        return {
            "description": desc,
            "passed": False,
            "reason": "No indicators found in test vars.",
            "raw": None,
        }

    # --- Call the tool ---
    try:
        raw = resolve_metric(indicators)
    except Exception as exc:
        return {
            "description": desc,
            "passed": False,
            "reason": f"resolve_metric raised exception: {exc}",
            "raw": None,
        }

    candidate_ids = _all_candidate_ids(raw)
    high_confidence_ids = {
        c["metric_id"]
        for item in raw.get("results", [])
        for c in item.get("candidates", [])
        if c.get("confidence", 0) >= 0.6
    }

    passed = False
    reason = ""

    if expected_type == "gap":
        # Must NOT resolve any confident candidates
        if not high_confidence_ids:
            passed = True
            reason = "Correctly returned no high-confidence candidates (coverage gap)."
        else:
            reason = (
                f"Expected no high-confidence candidates, but got: {high_confidence_ids}"
            )

    elif expected_type == "clarification":
        # All expected_top_ids must appear as candidates (enabling a clarification prompt)
        missing = set(expected_top_ids) - candidate_ids
        if not missing:
            passed = True
            reason = (
                f"All tie candidates present: {set(expected_top_ids)} — "
                "model can present clarification."
            )
        else:
            reason = f"Missing tie candidates: {missing}"

    else:  # "pass"
        missing = set(expected_metric_ids) - candidate_ids
        if not missing:
            passed = True
            reason = f"All expected IDs found: {set(expected_metric_ids)}"
        else:
            reason = f"Missing expected IDs: {missing}"

    return {
        "description": desc,
        "passed": passed,
        "reason": reason,
        "raw": raw,
        "expected_type": expected_type,
        "candidate_ids": sorted(candidate_ids),
        "high_confidence_ids": sorted(high_confidence_ids),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(_bold("\n══ Level-1 Deterministic Tool Tests ══\n"))

    if not CONFIG_PATH.exists():
        print(_red(f"ERROR: config not found at {CONFIG_PATH}"))
        return 1

    with CONFIG_PATH.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tests: list[dict[str, Any]] = config.get("tests", [])
    if not tests:
        print(_yellow("No tests found in promptfooconfig.yaml"))
        return 0

    results: list[dict[str, Any]] = []
    passed_count = 0

    for i, test in enumerate(tests, start=1):
        result = evaluate_case(test)
        results.append(result)
        status = _green("PASS") if result["passed"] else _red("FAIL")
        print(f"[{i:02d}] {status}  {result['description']}")
        if not result["passed"]:
            print(f"       ↳ {_yellow(result['reason'])}")
        else:
            print(f"       ↳ {result['reason']}")
        if result.get("passed"):
            passed_count += 1

    total = len(tests)
    failed = total - passed_count
    print(f"\n{'─' * 50}")
    print(
        f"Results: {_green(str(passed_count))} passed, "
        f"{_red(str(failed)) if failed else '0'} failed  "
        f"(total {total})"
    )

    # --- Persist results ---
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved → {RESULTS_PATH}\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
