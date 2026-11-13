# data/

This directory stores recorded outputs from evaluation runs.  It is **gitignored**
(except for `.gitkeep` and this `README.md`) so that trace files containing
potentially sensitive business data are never committed.

## Files written here

| File | Written by | Contents |
|------|-----------|----------|
| `l1-results.json` | `level_one.py` | Level-1 deterministic test results (one object per test case) |
| `l2-trace.json` | `provider.py` | Level-2 live tool-call traces (one object per provider run) |

## Schema

### `l1-results.json`

```jsonc
[
  {
    "description": "FIN-01 Ambiguous revenue indicator",
    "passed": true,
    "reason": "All tie candidates present: {'fin_arr', 'fin_mrr'}",
    "expected_type": "clarification",
    "candidate_ids": ["fin_arr", "fin_mrr"],
    "high_confidence_ids": ["fin_arr", "fin_mrr"],
    "raw": { /* resolve_metric() return value */ }
  }
]
```

### `l2-trace.json`

```jsonc
[
  {
    "answer": "Your ARR for Q4 2024 was $12.4 M ...",
    "tool_calls": [
      { "tool": "resolve_metric", "args": {"indicators": ["revenue"]}, "result": { ... } },
      { "tool": "fetch_finance",  "args": {"metric_ids": ["fin_arr"]},  "result": { ... } }
    ],
    "completed": true,
    "backend": "gemini"
  }
]
```

## Replaying without API keys

```bash
python replay.py          # re-grades both files
python replay.py --l2-only --fail-only   # only show level-2 failures
```
