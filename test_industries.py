"""
Multi-Industry Evaluation Runner for 5 Distinct Enterprise Industries:
1. Healthcare & Clinical Operations
2. Banking, Financial Services & Insurance (BFSI)
3. Retail & E-Commerce
4. Supply Chain & Freight Logistics
5. SaaS, Cloud Infrastructure & DevOps

Executes contract verification, ambiguity detection, coverage gaps, and tool execution.
Saves comprehensive results to data/industries_results.json.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
import yaml

REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

from server import (
    resolve_metric,
    fetch_healthcare,
    fetch_bfsi,
    fetch_retail,
    fetch_logistics,
    fetch_saas,
)

CONFIG_PATH = REPO_ROOT / "data" / "industries_config.yaml"
RESULTS_PATH = REPO_ROOT / "data" / "industries_results.json"


def evaluate_test(test: Dict[str, Any]) -> Dict[str, Any]:
    test_id = test.get("id", "UNKNOWN")
    industry = test.get("industry", "general")
    description = test.get("description", "")
    vars_dict = test.get("vars", {})
    metadata = test.get("metadata", {})

    indicators_raw = vars_dict.get("indicator", "")
    indicators = [i.strip() for i in indicators_raw.split(",") if i.strip()]
    expected_type = metadata.get("expected_type", "pass")
    expected_ids = set(vars_dict.get("expected_metric_ids", []))
    expected_top_ids = set(vars_dict.get("expected_top_ids", []))

    # 1. Call resolve_metric
    raw = resolve_metric(indicators=indicators)
    res_list = raw.get("results", [])

    all_candidate_ids = set()
    high_conf_ids = set()
    top_tied_ids = set()

    for item in res_list:
        cands = item.get("candidates", [])
        for c in cands:
            mid = c.get("metric_id")
            all_candidate_ids.add(mid)
            if c.get("confidence", 0) >= 0.70:
                high_conf_ids.add(mid)

        if len(cands) >= 2 and cands[0]["confidence"] == cands[1]["confidence"]:
            top_score = cands[0]["confidence"]
            for c in cands:
                if c["confidence"] == top_score:
                    top_tied_ids.add(c["metric_id"])

    # 2. Grade according to expected_type
    passed = False
    reason = ""

    if expected_type == "gap":
        if len(high_conf_ids) == 0:
            passed = True
            reason = "Coverage gap correctly identified (0 high-confidence candidates)."
        else:
            passed = False
            reason = f"Expected coverage gap, but found high-confidence matches: {high_conf_ids}"

    elif expected_type == "clarification":
        # Check that ambiguous candidates are present
        if expected_ids.issubset(all_candidate_ids):
            passed = True
            reason = f"All ambiguous candidate options present ({expected_ids}) enabling agent clarification."
        else:
            passed = False
            missing = expected_ids - all_candidate_ids
            reason = f"Missing expected ambiguity candidates: {missing}"

    elif expected_type == "pass":
        if expected_ids.issubset(all_candidate_ids):
            passed = True
            reason = f"Successfully resolved expected metric IDs: {expected_ids}"
        else:
            passed = False
            missing = expected_ids - all_candidate_ids
            reason = f"Failed to resolve required metric IDs: {missing}"

    # 3. Test execution against domain fetch tool
    tool_executed = False
    tool_output = None
    if passed and expected_type == "pass":
        fetch_map = {
            "healthcare": fetch_healthcare,
            "bfsi": fetch_bfsi,
            "retail": fetch_retail,
            "logistics": fetch_logistics,
            "saas": fetch_saas,
        }
        tool_fn = fetch_map.get(industry)
        if tool_fn and expected_ids:
            try:
                tool_output = tool_fn(list(expected_ids))
                tool_executed = True
            except Exception as e:
                tool_output = {"error": str(e)}

    return {
        "id": test_id,
        "industry": industry,
        "description": description,
        "query": vars_dict.get("query", ""),
        "passed": passed,
        "expected_type": expected_type,
        "reason": reason,
        "resolved_candidates": list(all_candidate_ids),
        "tool_executed": tool_executed,
        "sample_output": tool_output,
    }


def main():
    print("=" * 70)
    print("HARNESS-AI MULTI-INDUSTRY EVALUATION SUITE (5 ENTERPRISE SECTORS)")
    print("=" * 70)

    if not CONFIG_PATH.exists():
        print(f"Error: {CONFIG_PATH} not found.")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    industries = cfg.get("industries", [])
    tests = cfg.get("tests", [])

    results = []
    by_industry: Dict[str, Dict[str, Any]] = {}
    for ind in industries:
        by_industry[ind["id"]] = {
            "name": ind["name"],
            "total": 0,
            "passed": 0,
            "cases": [],
        }

    for test in tests:
        res = evaluate_test(test)
        results.append(res)
        ind_id = res["industry"]
        if ind_id in by_industry:
            by_industry[ind_id]["total"] += 1
            if res["passed"]:
                by_industry[ind_id]["passed"] += 1
            by_industry[ind_id]["cases"].append(res)

    # Print Report
    total_tests = len(results)
    total_passed = sum(1 for r in results if r["passed"])
    overall_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

    print("\nINDUSTRY BREAKDOWN:")
    print("-" * 70)
    for ind_id, stats in by_industry.items():
        t = stats["total"]
        p = stats["passed"]
        rate = (p / t * 100) if t > 0 else 0
        icon = "✓" if rate == 100 else ("!" if rate >= 70 else "✗")
        print(f"[{icon}] {stats['name']} ({ind_id.upper()}): {p}/{t} ({rate:.1f}%)")
        for c in stats["cases"]:
            status_str = "PASS" if c["passed"] else "FAIL"
            print(f"    • [{status_str}] {c['id']} — {c['description']}")
            print(f"        ↳ {c['reason']}")

    print("-" * 70)
    print(f"OVERALL 5-INDUSTRY BENCHMARK: {total_passed}/{total_tests} ({overall_rate:.1f}%)")
    print("=" * 70)

    # Save to JSON
    output_payload = {
        "benchmark": "5-Industry Enterprise Evaluation",
        "total_tests": total_tests,
        "total_passed": total_passed,
        "overall_pass_rate": round(overall_rate, 1),
        "industries": by_industry,
        "all_cases": results,
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, indent=2)

    print(f"\nResults successfully saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
