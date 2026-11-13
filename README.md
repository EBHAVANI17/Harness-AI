# Harness-Aware Plugin Evaluation Framework

A production-ready, reusable scaffold for evaluating company-data MCP plugins
across **Finance**, **Engineering**, **Customer Support**, and **Operations**
domains — inspired by the OpenAI Cookbook article
*"Harness-Aware Evaluation of Plugins"*.

---

## Table of Contents

1. [What This Is](#what-this-is)
2. [Prerequisites](#prerequisites)
3. [Quick Start](#quick-start)
4. [Project Layout](#project-layout)
5. [The Three Evaluation Levels](#the-three-evaluation-levels)
   - [Level 1 — Deterministic Tool Tests](#level-1--deterministic-tool-tests)
   - [Level 2 — Live Model Eval (promptfoo)](#level-2--live-model-eval-promptfoo)
   - [Replay — Offline Re-grading](#replay--offline-re-grading)
6. [Test Case Reference](#test-case-reference)
7. [Adding New Test Cases](#adding-new-test-cases)
8. [Adapting to Real Data Sources](#adapting-to-real-data-sources)
9. [Decision Guide — When to Use Each Level](#decision-guide--when-to-use-each-level)
10. [Environment Variables](#environment-variables)
11. [Troubleshooting](#troubleshooting)

---

## What This Is

This framework lets you answer the question:

> *"Does my MCP plugin behave correctly when a language model uses it?"*

It evaluates **five failure modes** that commonly break production plugins:

| Failure mode | Example |
|---|---|
| **Ambiguous queries** | "revenue" → ARR or MRR? Model must ask. |
| **Coverage gaps** | "stock price" is not in the catalog. Model must say so. |
| **Tool-selection errors** | Using `fetch_ops` for a finance metric. |
| **Multi-step reasoning** | "SLA compliance by product team" needs both `fetch_support` AND `fetch_engineering`. |
| **Hallucination prevention** | Model invents a metric ID like `eng_velocity_points`. |

The scaffold ships with **synthetic fixture data** so you can run everything
without connecting to a real database.  Swapping in real data takes
[~10 lines of code](#adapting-to-real-data-sources).

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | `python --version` |
| [uv](https://docs.astral.sh/uv/) | latest | Fast Python package manager |
| Node.js | ≥ 18 | Needed for `npx promptfoo` (Level 2 only) |
| Gemini API key | — | Free tier works; get one at [aistudio.google.com](https://aistudio.google.com) |
| Ollama + llama3 | optional | Fallback when Gemini is unavailable |

> **Windows users:** GNU Make is optional.  All `make` targets have equivalent
> `python` commands listed in this README.

---

## Quick Start

```bash
# 1. Clone / download this repository
cd "Harness AI"

# 2. Install dependencies
uv sync

# 3. Copy the environment template and add your Gemini key
copy .env.example .env
# Edit .env and set GEMINI_API_KEY=...

# 4. Start the MCP server (leave this terminal open)
python server.py
# Server is now running at http://localhost:8000

# 5. In a new terminal — run Level-1 tests (no API key needed)
python level_one.py

# 6. Run Level-2 live eval (requires Gemini key + Node.js)
npx promptfoo eval --config promptfooconfig.yaml

# 7. Replay recorded results without API keys
python replay.py
```

Using `make`:

```bash
make install      # uv sync
make server       # start MCP server
make l1           # level-1 tests
make l2           # level-2 live eval
make replay       # offline replay
make all          # l1 → l2 → replay
```

---

## Project Layout

```
Harness AI/
├── server.py              FastMCP MCP server (5 tools, 4 domains)
├── promptfooconfig.yaml   10 test cases for promptfoo
├── level_one.py           Level-1 deterministic tests
├── eval_grading.py        Shared grader (used by all levels)
├── provider.py            Standalone model loop (Gemini + Ollama fallback)
├── assert_result.py       promptfoo assertion script
├── replay.py              Offline replay of recorded runs
├── notebook_setup.py      Jupyter notebook helper
├── pyproject.toml         uv project file
├── Makefile               Convenience targets
├── .env.example           Environment variable template
├── .env                   Your secrets (gitignored)
└── data/
    ├── .gitkeep
    ├── README.md          Schema docs for data files
    ├── l1-results.json    Written by level_one.py
    └── l2-trace.json      Written by provider.py
```

---

## The Three Evaluation Levels

### Level 1 — Deterministic Tool Tests

**What it does:** Calls `resolve_metric()` directly from `server.py`
(no model, no API key, no network) and checks that the fixture data
returns the expected candidates.

**When to run:** On every commit.  Fast (~1 s), zero external dependencies.

```bash
python level_one.py
# or
make l1
```

Sample output:

```
══ Level-1 Deterministic Tool Tests ══

[01] PASS  FIN-01 Ambiguous revenue indicator
       ↳ All tie candidates present: {'fin_arr', 'fin_mrr'} — model can present clarification.
[02] PASS  FIN-02 Coverage gap — stock price not in catalog
       ↳ Correctly returned no high-confidence candidates (coverage gap).
...
Results: 10 passed, 0 failed  (total 10)

Results saved → data/l1-results.json
```

**Exit codes:** `0` = all pass, `1` = any failure.

---

### Level 2 — Live Model Eval (promptfoo)

**What it does:** Uses [promptfoo](https://promptfoo.dev) to run each of the
10 test cases through a live model (Gemini or Ollama).  The model receives the
natural-language `query`, calls tools on the running MCP server, and the
grader checks the tool-call trace against expectations.

**When to run:** Before releasing a new plugin version.  Requires the MCP
server to be running and either a Gemini API key or Ollama.

```bash
# Terminal 1 — keep running
python server.py

# Terminal 2
npx promptfoo eval --config promptfooconfig.yaml

# View results in the browser
npx promptfoo view
```

**How grading works** (`eval_grading.py`):

| Check | Weight | Description |
|---|---|---|
| `resolve_metric` called | 0.20 | Model used the resolver before fetching |
| All fetch tools called | 0.30 | Correct domain fetch tools invoked |
| All expected IDs fetched | 0.30 | Required metric IDs in tool arguments |
| No unexpected IDs | 0.10 | No hallucinated metric IDs |
| Run completed | 0.10 | Loop finished without crashing |

For `gap` and `clarification` expected types the rubric is adjusted
automatically (see `eval_grading.py` for details).

---

### Replay — Offline Re-grading

**What it does:** Re-runs the grader against `data/l1-results.json` and
`data/l2-trace.json` without touching the model or the MCP server.
Useful for CI regression checks or reviewing failures after a provider run.

```bash
python replay.py                     # both levels
python replay.py --l1-only           # only level-1
python replay.py --l2-only           # only level-2
python replay.py --fail-only         # only print failures
```

**Exit codes:** `0` = all pass, `1` = any failure, `2` = no data files found.

---

## Test Case Reference

| ID | Domain | Failure Mode | Expected Type |
|---|---|---|---|
| FIN-01 | Finance | Ambiguous: revenue = ARR vs MRR | `clarification` |
| FIN-02 | Finance | Coverage gap: stock price | `gap` |
| FIN-03 | Finance | Tool selection: gross margin | `pass` |
| FIN-04 | Finance | Ambiguous: cost = COGS vs OpEx | `clarification` |
| MULTI-01 | Support + Engineering | Multi-step: SLA by team | `pass` |
| MULTI-02 | Support + Finance | Multi-step: CSAT + ARR | `pass` |
| ENG-01 | Engineering | Hallucination: eng_velocity_points | `gap` |
| ENG-02 | Engineering | Tool selection: deploy frequency | `pass` |
| OPS-01 | Ops | Coverage gap: headcount | `gap` |
| OPS-02 | Ops | Hallucination: ops_warehouse_utilization | `gap` |

---

## Adding New Test Cases

### 1. Add a fixture metric (if needed)

In `server.py`, append to `METRIC_CATALOG`:

```python
{
    "metric_id": "fin_cac",
    "title": "Customer Acquisition Cost (CAC)",
    "domain": "finance",
    "aliases": ["cac", "customer acquisition cost", "acquisition cost"],
    "description": "Average cost to acquire one new customer.",
},
```

Add a fixture value to `FIXTURE_VALUES`:

```python
"fin_cac": {"value": 1_250, "unit": "USD", "period": "2024-Q4"},
```

### 2. Add a test case to `promptfooconfig.yaml`

```yaml
- description: "FIN-05 Customer acquisition cost"
  vars:
    indicator: "cac"
    query: "What was our CAC last quarter?"
    expected_tools:
      - "resolve_metric"
      - "fetch_finance"
    expected_metric_ids:
      - "fin_cac"
    expected_top_ids: []
  metadata:
    mechanism: "tool_selection"
    expected_type: "pass"
    notes: >
      CAC resolves cleanly to fin_cac.  fetch_finance should be called.
```

### 3. Run Level 1 to verify the resolver

```bash
python level_one.py
```

### 4. Run Level 2 to verify the full model loop

```bash
python server.py &   # background
npx promptfoo eval --config promptfooconfig.yaml
```

---

## Adapting to Real Data Sources

The fixture data lives in two dicts inside `server.py`:

| Dict | Purpose |
|---|---|
| `METRIC_CATALOG` | Metric metadata and aliases used by `resolve_metric` |
| `FIXTURE_VALUES` | Values returned by the four fetch tools |

To connect to a real database or API, replace the body of each `_fetch_domain`
call.  Example for a SQL database:

```python
# server.py — replace FIXTURE_VALUES lookup with a real query
import psycopg2

def _fetch_domain(metric_ids, domain_prefix, domain_name):
    conn = psycopg2.connect(os.getenv("DB_URL"))
    cur = conn.cursor()
    data = {}
    for mid in metric_ids:
        cur.execute("SELECT value, unit, period FROM metrics WHERE id = %s", (mid,))
        row = cur.fetchone()
        if row:
            data[mid] = {"value": row[0], "unit": row[1], "period": row[2]}
    conn.close()
    return {"data": data, "missing": [m for m in metric_ids if m not in data]}
```

The `resolve_metric` tool is similarly easy to swap — replace `_score()` with
a call to a vector database (Pinecone, pgvector, Weaviate) for semantic search
over your real metric catalog.

---

## Decision Guide — When to Use Each Level

```
                 ┌─────────────────────────────────────────────────┐
                 │            Which level should I run?            │
                 └───────────────────────┬─────────────────────────┘
                                         │
              ┌──────────────────────────▼──────────────────────────┐
              │  Did I change fixture data, metric catalog,         │
              │  or the resolve_metric logic?                       │
              └──────────────────────────┬──────────────────────────┘
                         YES             │            NO
                          │              │             │
                          ▼              │             ▼
                    Run Level 1          │    Skip Level 1
                    (always fast)        │
                                         │
              ┌──────────────────────────▼──────────────────────────┐
              │  Am I about to cut a release, or did I change       │
              │  the system prompt / tool descriptions?             │
              └──────────────────────────┬──────────────────────────┘
                         YES             │            NO
                          │              │             │
                          ▼              │             ▼
                    Run Level 2          │   Run Replay only
                    (needs API key)      │   (no API key needed)
```

| Situation | Recommended level |
|---|---|
| Local development, quick sanity check | Level 1 |
| PR / merge-request gate | Level 1 + Replay |
| Pre-release regression suite | Level 1 + Level 2 |
| CI without API keys (secrets not available) | Level 1 + Replay |
| Debugging a specific failure after a provider run | Replay `--fail-only` |
| Notebook / exploratory analysis | `notebook_setup.prepare()` → provider directly |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required for Level 2)* | Google AI Studio API key |
| `EVAL_MODEL` | `gemini-2.0-flash` | Gemini model name |
| `MCP_URL` | `http://localhost:8000/mcp` | MCP server endpoint |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server base URL |
| `MCP_PORT` | `8000` | Port the server binds to |
| `FORCE_COLOR` | *(unset)* | Set to `1` for ANSI colours in CI |

Copy `.env.example` → `.env` and fill in your values.  The `.env` file is
listed in `.gitignore` and will never be committed.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'fastmcp'`

```bash
uv sync          # installs all dependencies from pyproject.toml
```

### MCP server not reachable

Make sure `python server.py` is running in another terminal before running
Level 2 or the provider.  Check that port 8000 is not already in use:

```powershell
netstat -ano | findstr :8000
```

### Gemini quota exceeded

The free tier allows ~15 requests per minute.  Either wait a minute or start
Ollama and let the provider fall back automatically:

```bash
ollama pull llama3
ollama serve
```

### promptfoo not found

```bash
npm install -g promptfoo
# or use npx (no install needed):
npx promptfoo eval --config promptfooconfig.yaml
```

### Level-1 tests fail on Windows (colour codes)

Set `FORCE_COLOR=1` or pipe output to a file:

```powershell
$env:FORCE_COLOR = "1"; python level_one.py
```
