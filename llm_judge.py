"""
llm_judge.py — Advanced LLM-as-a-Judge Evaluation Module.

Evaluates AI agent responses using a structured multi-criteria rubric:
1. Tool Grounding (Are answers strictly grounded in retrieved data without hallucination?)
2. Ambiguity Handling (Does the model ask clarifying questions when inputs are ambiguous?)
3. Completeness & Helpfulness (Did it solve the user's intent concisely?)
4. Tone & Professionalism (Is the output structured clearly for a business stakeholder?)

Can evaluate live using Gemini, or use deterministic heuristic fallback
when API quota is throttled/offline.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from dotenv import load_dotenv

load_dotenv()

JUDGE_RUBRIC_PROMPT = """
You are an expert AI Evaluation Judge assessing a business intelligence assistant.

Evaluate the Assistant's final answer and tool calls against the User's query and Test Expectations.

Criteria to grade (score each 1 to 5):
1. Grounding (1-5): Did the model avoid fabricating metrics or values not present in tools?
2. Ambiguity & Gaps (1-5): Did it handle ties/missing data appropriately (e.g. asking for clarification or noting data is unavailable)?
3. Completeness (1-5): Did the response answer what was asked without leaving out necessary steps?
4. Conciseness (1-5): Was the explanation direct, professional, and free of unnecessary fluff?

Input Data:
- Query: {query}
- Expected Mechanism: {mechanism}
- Expected Action: {expected_type}
- Tool Calls Made: {tool_calls}
- Assistant Answer: {answer}

Provide your evaluation strictly as a valid JSON object matching this schema:
{{
  "grounding_score": int,
  "ambiguity_score": int,
  "completeness_score": int,
  "conciseness_score": int,
  "overall_score": float,
  "passed": bool,
  "critique": "short summary explaining why"
}}
"""


def heuristic_judge_fallback(
    query: str,
    tool_calls: list[dict[str, Any]],
    answer: str,
    mechanism: str = "",
    expected_type: str = "",
) -> dict[str, Any]:
    """Deterministic rubric scoring when LLM Judge API is offline or throttled."""
    score_grounding = 5
    score_ambiguity = 5
    score_completeness = 5
    score_conciseness = 5
    critique_points = []

    answer_lower = answer.lower()
    tool_names = [tc.get("name") or tc.get("tool", "") for tc in tool_calls]

    # Check for hallucination/grounding
    if "unavailable" in answer_lower or "not in our catalog" in answer_lower:
        if mechanism in ("coverage_gap", "hallucination_trap"):
            score_grounding = 5
            score_ambiguity = 5
            critique_points.append("Correctly identified catalog gap without guessing.")
    elif mechanism in ("coverage_gap", "hallucination_trap") and any(t.startswith("fetch_") for t in tool_names):
        score_grounding = 2
        critique_points.append("Attempted to fetch data for metric that does not exist in catalog.")

    # Check for ambiguity handling
    if mechanism == "ambiguous_concept" or expected_type == "clarify":
        if any(w in answer_lower for w in ["which", "clarify", "mean", "arr or mrr", "cogs or opex"]):
            score_ambiguity = 5
            critique_points.append("Correctly surfaced clarification prompt for tied candidates.")
        else:
            score_ambiguity = 2
            score_completeness = 3
            critique_points.append("Failed to clearly ask user for clarification on ambiguous metric.")

    # Check completeness
    if not answer.strip() or answer.startswith("[ERROR]"):
        score_completeness = 1
        critique_points.append("No response or error encountered.")

    avg_score = round((score_grounding + score_ambiguity + score_completeness + score_conciseness) / 4.0, 2)
    passed = avg_score >= 3.5

    return {
        "grounding_score": score_grounding,
        "ambiguity_score": score_ambiguity,
        "completeness_score": score_completeness,
        "conciseness_score": score_conciseness,
        "overall_score": avg_score,
        "passed": passed,
        "judge_mode": "heuristic-fallback",
        "critique": " ".join(critique_points) or "Answer met expected behavioral guidelines.",
    }


def judge_response(
    query: str,
    tool_calls: list[dict[str, Any]],
    answer: str,
    mechanism: str = "",
    expected_type: str = "",
) -> dict[str, Any]:
    """Judge a model turn with an LLM rubric, falling back to heuristics if throttled."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return heuristic_judge_fallback(query, tool_calls, answer, mechanism, expected_type)

    prompt = JUDGE_RUBRIC_PROMPT.format(
        query=query,
        mechanism=mechanism,
        expected_type=expected_type,
        tool_calls=json.dumps(tool_calls, default=str),
        answer=answer,
    )

    try:
        import google.generativeai as genai  # type: ignore
        genai.configure(api_key=api_key)
        judge_model = genai.GenerativeModel("gemini-2.5-flash-lite")
        resp = judge_model.generate_content(prompt)
        text = resp.text.strip()

        # Extract JSON from potential code fences
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            data["judge_mode"] = "llm-judge"
            return data
    except Exception:
        pass

    return heuristic_judge_fallback(query, tool_calls, answer, mechanism, expected_type)


if __name__ == "__main__":
    test_result = judge_response(
        query="What is our current stock price?",
        tool_calls=[{"name": "resolve_metric", "arguments": {"indicators": ["stock price"]}}],
        answer="I checked our company data catalog and stock price is not available in our records.",
        mechanism="coverage_gap",
        expected_type="gap",
    )
    print("Judge Evaluation Output:")
    print(json.dumps(test_result, indent=2))

