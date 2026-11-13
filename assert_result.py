"""
assert_result.py — promptfoo assertion script.

promptfoo calls this file for every test case after the provider runs.
It reads the provider output from the context, calls grade() from
eval_grading.py, and returns a promptfoo-compatible verdict.

promptfoo JavaScript assertion interface (file://) expects the module to
export a function that accepts the full test-output context and returns:

    {
        "pass":    bool,
        "score":   float,     # 0.0 – 1.0
        "reason":  str,
    }

Because promptfoo can call Python assertion scripts directly when configured
with ``type: python`` (or via a thin JS shim), this module exposes:
  - ``assert_result(output, context)``  — importable Python entry point
  - ``__call__(output, context)``       — module-level callable alias

It is also runnable as a CLI for quick debugging:

    echo '{"output": "...", "metadata": {...}}' | python assert_result.py vars.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Allow running from any working directory
# ---------------------------------------------------------------------------
_REPO = Path(__file__).parent
sys.path.insert(0, str(_REPO))

from eval_grading import grade  # noqa: E402


# ---------------------------------------------------------------------------
# Core assertion function
# ---------------------------------------------------------------------------

def get_assert(
    output: str | dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    return assert_result(output, context)


def assert_result(
    output: str | dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    Grade the provider's output against the test-case expectations.

    Parameters
    ----------
    output:
        Either the raw string output from the model, or the full provider
        output dict (``{"output": str, "metadata": {...}}``).

    context:
        The promptfoo test context, which includes at minimum:
            - ``vars``  : the test-case vars dict
            - ``test``  : the full test-case object

    Returns
    -------
    dict  with keys ``pass``, ``score``, ``reason``.
    """
    # --- Unpack provider output ---
    if isinstance(output, dict):
        answer: str = output.get("output", "")
        metadata: dict[str, Any] = output.get("metadata", {})
    else:
        answer = str(output)
        metadata = {}

    tool_calls: list[dict[str, Any]] = metadata.get("tool_calls", [])
    completed: bool = metadata.get("completed", False)

    # --- Unpack test vars ---
    vars_: dict[str, Any] = context.get("vars", {})
    test_obj: dict[str, Any] = context.get("test", {})

    # Merge metadata from the test object into vars_ so grade() can see it
    if "metadata" in test_obj and "metadata" not in vars_:
        vars_ = {**vars_, "metadata": test_obj["metadata"]}

    # --- Grade ---
    result = grade(
        tool_calls=tool_calls,
        vars_=vars_,
        answer=answer,
        completed=completed,
    )

    return {
        "pass": result["passed"],
        "score": result["score"],
        "reason": result["reason"],
    }


# ---------------------------------------------------------------------------
# Module-level callable alias (some promptfoo versions call the module directly)
# ---------------------------------------------------------------------------

def __call__(
    output: str | dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    return assert_result(output, context)


# ---------------------------------------------------------------------------
# CLI entrypoint for debugging
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Usage:
        echo '<provider-output-json>' | python assert_result.py <vars-json-file>

    Or pass everything as positional args:
        python assert_result.py output.json vars.json
    """
    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[1])
        vars_path = Path(sys.argv[2])
        output_data = json.loads(output_path.read_text(encoding="utf-8"))
        vars_data = json.loads(vars_path.read_text(encoding="utf-8"))
    elif len(sys.argv) == 2:
        # First arg is vars file; output comes from stdin
        output_data = json.loads(sys.stdin.read())
        vars_data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    else:
        # Everything from stdin as a single JSON object
        raw = json.loads(sys.stdin.read())
        output_data = raw.get("output", raw)
        vars_data = raw.get("vars", {})

    context = {"vars": vars_data}
    verdict = assert_result(output_data, context)
    print(json.dumps(verdict, indent=2))
