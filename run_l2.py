import yaml
import json
import time
import sys
from pathlib import Path
from provider import run_case
from eval_grading import grade

def main():
    config_path = Path("promptfooconfig.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tests = config.get("tests", [])
    print(f"Starting Level 2 evaluation ({len(tests)} test cases with rate-limit pacing)...\n")

    results = []
    passed_count = 0

    for idx, t in enumerate(tests, 1):
        desc = t.get("description", f"test-{idx}")
        vars_ = t.get("vars", {})
        query = vars_.get("query", "")
        print(f"[{idx:02d}/{len(tests):02d}] Running: {desc}")
        print(f"     Query: \"{query}\"")

        res = run_case(query)
        answer = res.get("output", "")
        metadata = res.get("metadata", {})
        tool_calls = metadata.get("tool_calls", [])
        completed = metadata.get("completed", False)

        vars_with_meta = {**vars_}
        if "metadata" in t:
            vars_with_meta["metadata"] = t["metadata"]
        verdict = grade(tool_calls=tool_calls, vars_=vars_with_meta, answer=answer, completed=completed)

        status = "PASS ✅" if verdict["passed"] else "FAIL ❌"
        if verdict["passed"]:
            passed_count += 1
        print(f"     Verdict: {status} (Score: {verdict['score']:.2f})")
        if not verdict["passed"]:
            print(f"     Reason : {verdict['reason']}")
        print(f"     Tools called: {[c.get('name') for c in tool_calls]}\n")

        results.append({
            "test": desc,
            "verdict": verdict,
            "answer": answer,
            "tool_calls": tool_calls
        })
        time.sleep(12)  # Respect 5 RPM free tier limits

    print("=" * 50)
    print(f"Level 2 Results: {passed_count}/{len(tests)} passed ({passed_count/len(tests)*100:.1f}%)")
    out_path = Path("data/l2-results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as out_f:
        json.dump(results, out_f, indent=2, default=str)
    print(f"Results saved to {out_path}")

if __name__ == "__main__":
    main()

