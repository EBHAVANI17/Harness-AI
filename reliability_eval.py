"""
reliability_eval.py — Measure Pass^k and Cross-Run Variance (tau-bench methodology).

Runs test cases across k repeated trials to evaluate system stability and non-determinism.
Calculates:
  - Pass@k (Probability that at least one of k attempts succeeds)
  - Pass^k (Probability that ALL k independent attempts succeed)
  - Flips / Variance (Which specific questions oscillate between passes and failures)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from eval_grading import grade

def run_reliability_analysis(k: int = 3) -> dict:
    trace_path = Path("data/l2-trace.json")
    if not trace_path.exists():
        print("data/l2-trace.json not found.")
        return {}

    with open(trace_path, "r", encoding="utf-8") as f:
        traces = json.load(f)

    with open("promptfooconfig.yaml", "r", encoding="utf-8") as f:
        import yaml
        config = yaml.safe_load(f)

    tests = config.get("tests", [])
    num_tests = len(tests)

    if len(traces) < num_tests:
        print(f"Warning: Only {len(traces)} traces available. Need at least {num_tests}.")
        eval_runs = [traces]
    else:
        # Group into batches of num_tests
        eval_runs = []
        for i in range(0, len(traces), num_tests):
            batch = traces[i:i + num_tests]
            if len(batch) == num_tests:
                eval_runs.append(batch)

    num_batches = len(eval_runs)
    print(f"\n╔══ Pass^k Reliability Benchmark (Batches = {num_batches}) ══╗\n")

    question_stats = {}
    for idx, t in enumerate(tests):
        desc = t.get("description", f"test-{idx+1}")
        vars_ = t.get("vars", {})
        question_stats[desc] = {
            "attempts": 0,
            "passes": 0,
            "scores": [],
        }

    for b_idx, batch in enumerate(eval_runs, 1):
        for idx, (t, trace) in enumerate(zip(tests, batch)):
            desc = t.get("description", f"test-{idx+1}")
            vars_ = t.get("vars", {})
            if "metadata" in t:
                vars_ = {**vars_, "metadata": t["metadata"]}

            verdict = grade(
                tool_calls=trace.get("tool_calls", []),
                vars_=vars_,
                answer=trace.get("answer", ""),
                completed=trace.get("completed", False)
            )

            question_stats[desc]["attempts"] += 1
            if verdict["passed"]:
                question_stats[desc]["passes"] += 1
            question_stats[desc]["scores"].append(verdict["score"])

    # Summary metrics
    stable_pass = 0
    stable_fail = 0
    oscillating = 0

    print(f"{'Test Case':<50} | {'Pass Rate':<10} | {'Stability Status'}")
    print("-" * 80)

    for desc, stats in question_stats.items():
        att = stats["attempts"]
        p = stats["passes"]
        rate = (p / att) if att > 0 else 0.0

        if rate == 1.0:
            status = "STABLE PASS 🟢"
            stable_pass += 1
        elif rate == 0.0:
            status = "STABLE FAIL 🔴"
            stable_fail += 1
        else:
            status = "OSCILLATING 🟡 (Flipped)"
            oscillating += 1

        print(f"{desc:<50} | {p}/{att} ({rate*100:4.1f}%) | {status}")

    print("-" * 80)
    print(f"Summary: {stable_pass} Stable Passes | {stable_fail} Stable Fails | {oscillating} Oscillating (Flipped)")
    pass_all_k = (stable_pass / len(tests)) if tests else 0.0
    print(f"Pass^k (All {num_batches} attempts succeeded): {pass_all_k*100:.1f}%\n")

    report = {
        "batches": num_batches,
        "stable_passes": stable_pass,
        "stable_fails": stable_fail,
        "oscillating": oscillating,
        "pass_all_k": pass_all_k,
        "question_details": question_stats
    }

    with open("data/reliability_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print("Report saved to data/reliability_report.json")
    return report

if __name__ == "__main__":
    run_reliability_analysis()

