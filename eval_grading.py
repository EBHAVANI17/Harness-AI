"""
eval_grading.py — Shared grader used by both the standalone provider loop
and the promptfoo assertion script.

The single public function is:

    grade(tool_calls, vars, answer, completed) -> GradeResult

where GradeResult is a TypedDict:

    {
        "pass":   bool,
        "score":  float,   # 0.0 – 1.0
        "reason": str,
    }

Grading criteria (each worth a share of the total score)
---------------------------------------------------------
1. resolve_metric was called            (weight 0.20)
2. All expected fetch tools were called (weight 0.30)
3. All expected metric IDs appeared     (weight 0.30)
4. No unexpected / hallucinated IDs     (weight 0.10)
5. Run completed without error          (weight 0.10)

For 'gap' and 'clarification' expected_types the rubric is adjusted:
- 'gap':           only criterion 1 is required; fetch tools must NOT be called.
- 'clarification': criteria 1 + resolution of all expected_top_ids; no fetch.
"""

from __future__ import annotations

from typing import Any, TypedDict


class GradeResult(TypedDict):
    """Return type of grade()."""
    passed: bool
    score: float
    reason: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def grade(
    tool_calls: list[dict[str, Any]],
    vars_: dict[str, Any],
    answer: str,
    completed: bool,
) -> GradeResult:
    """
    Grade a single model run against the test-case expectations.

    Parameters
    ----------
    tool_calls:
        List of tool-call records produced by the provider, each of the form::

            {
                "tool": str,
                "args": dict,
                "result": Any,   # optional
            }

    vars_:
        The ``vars`` dict from the promptfoo test case.

    answer:
        The model's final natural-language answer.

    completed:
        Whether the tool-calling loop finished without crashing / timing out.

    Returns
    -------
    GradeResult
        ``{"passed": bool, "score": float, "reason": str}``
    """
    expected_type: str = vars_.get("metadata", {}).get("expected_type", "pass")
    # Support vars_ being the top-level test dict or just the vars block
    actual_vars = vars_.get("vars", vars_)

    # Normalise fields if passed as comma-separated strings
    def _to_list(val: Any) -> list[str]:
        if isinstance(val, str):
            return [x.strip() for x in val.split(",") if x.strip()]
        if isinstance(val, list):
            return [str(x) for x in val]
        return []

    expected_tools = _to_list(actual_vars.get("expected_tools", []))
    expected_metric_ids = _to_list(actual_vars.get("expected_metric_ids", []))
    expected_top_ids = _to_list(actual_vars.get("expected_top_ids", []))

    # --- Collect what actually happened ---
    called_tools: list[str] = [tc.get("tool") or tc.get("name", "") for tc in tool_calls]
    called_tools_set: set[str] = set(called_tools)

    # Flatten all metric_ids passed to any tool call
    fetched_ids: set[str] = set()
    resolved_ids: set[str] = set()

    for tc in tool_calls:
        args = tc.get("args") if "args" in tc else tc.get("arguments", {})
        tool_name = tc.get("tool") or tc.get("name", "")

        # IDs passed as arguments to fetch_ tools
        if tool_name.startswith("fetch_"):
            for mid in args.get("metric_ids", []):
                fetched_ids.add(mid)

        # IDs returned by resolve_metric
        if tool_name == "resolve_metric":
            result = tc.get("result", {})
            if isinstance(result, dict):
                for item in result.get("results", []):
                    for c in item.get("candidates", []):
                        resolved_ids.add(c.get("metric_id", ""))

    all_seen_ids = fetched_ids | resolved_ids

    # --- Route by expected_type ---
    if expected_type == "gap":
        return _grade_gap(
            called_tools_set=called_tools_set,
            completed=completed,
        )

    if expected_type == "clarification":
        return _grade_clarification(
            called_tools_set=called_tools_set,
            resolved_ids=resolved_ids,
            expected_top_ids=set(expected_top_ids),
            completed=completed,
            answer=answer,
        )

    # Default: "pass"
    return _grade_pass(
        called_tools_set=called_tools_set,
        expected_tools=expected_tools,
        fetched_ids=fetched_ids,
        expected_metric_ids=set(expected_metric_ids),
        all_seen_ids=all_seen_ids,
        completed=completed,
    )


# ---------------------------------------------------------------------------
# Internal graders
# ---------------------------------------------------------------------------

def _grade_gap(
    called_tools_set: set[str],
    completed: bool,
) -> GradeResult:
    """Coverage-gap: model must call resolve_metric and NOT call any fetch_ tool."""
    issues: list[str] = []
    score = 0.0

    if "resolve_metric" in called_tools_set:
        score += 0.50
    else:
        issues.append("resolve_metric was not called")

    fetch_tools_called = {t for t in called_tools_set if t.startswith("fetch_")}
    if not fetch_tools_called:
        score += 0.40
    else:
        issues.append(
            f"fetch tools called despite coverage gap: {fetch_tools_called}"
        )

    if completed:
        score += 0.10
    else:
        issues.append("run did not complete")

    passed = not issues
    reason = "Coverage-gap handling correct." if passed else "; ".join(issues)
    return GradeResult(passed=passed, score=round(score, 3), reason=reason)


def _grade_clarification(
    called_tools_set: set[str],
    resolved_ids: set[str],
    expected_top_ids: set[str],
    completed: bool,
    answer: str,
) -> GradeResult:
    """Ambiguous: model must resolve the tie candidates and ask for clarification."""
    issues: list[str] = []
    score = 0.0

    # 1. resolve_metric called
    if "resolve_metric" in called_tools_set:
        score += 0.30
    else:
        issues.append("resolve_metric was not called")

    # 2. All tie candidates were resolved
    missing_top = expected_top_ids - resolved_ids
    if not missing_top:
        score += 0.30
    else:
        issues.append(f"tie candidates not resolved: {missing_top}")

    # 3. No fetch_ tools called (model should ask, not guess)
    fetch_tools = {t for t in called_tools_set if t.startswith("fetch_")}
    if not fetch_tools:
        score += 0.30
    else:
        issues.append(
            f"model should ask for clarification but called fetch tools: {fetch_tools}"
        )

    # 4. Answer contains some hedging language (heuristic)
    hedge_words = {"clarify", "unclear", "ambiguous", "which", "do you mean",
                   "could you", "please specify", "both"}
    if any(w in answer.lower() for w in hedge_words):
        score += 0.10
    else:
        issues.append("answer lacks clarification language")

    if not completed:
        issues.append("run did not complete")

    passed = len(issues) == 0
    reason = "Clarification handled correctly." if passed else "; ".join(issues)
    return GradeResult(passed=passed, score=round(score, 3), reason=reason)


def _grade_pass(
    called_tools_set: set[str],
    expected_tools: list[str],
    fetched_ids: set[str],
    expected_metric_ids: set[str],
    all_seen_ids: set[str],
    completed: bool,
) -> GradeResult:
    """Standard pass: correct tools called, correct IDs fetched, no extras."""
    issues: list[str] = []
    score = 0.0

    # 1. resolve_metric called (weight 0.20)
    if "resolve_metric" in called_tools_set:
        score += 0.20
    else:
        issues.append("resolve_metric was not called")

    # 2. All expected fetch tools called (weight 0.30)
    expected_fetch = {t for t in expected_tools if t != "resolve_metric"}
    missing_tools = expected_fetch - called_tools_set
    if not missing_tools:
        score += 0.30
    else:
        issues.append(f"missing expected tools: {missing_tools}")

    # 3. All expected metric IDs fetched (weight 0.30)
    missing_ids = expected_metric_ids - fetched_ids
    if not missing_ids:
        score += 0.30
    else:
        issues.append(f"missing expected metric IDs: {missing_ids}")

    # 4. No unexpected / hallucinated IDs fetched (weight 0.10)
    extra_ids = fetched_ids - expected_metric_ids
    if not extra_ids:
        score += 0.10
    else:
        # Extra IDs are a soft penalty but not necessarily a hard fail
        issues.append(f"unexpected IDs fetched (possible hallucination): {extra_ids}")

    # 5. Run completed (weight 0.10)
    if completed:
        score += 0.10
    else:
        issues.append("run did not complete")

    passed = len(issues) == 0
    reason = "All checks passed." if passed else "; ".join(issues)
    return GradeResult(passed=passed, score=round(score, 3), reason=reason)
