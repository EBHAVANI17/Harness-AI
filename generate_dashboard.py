"""
Interactive Evaluation Dashboard Generator
Produces a single, standalone, responsive HTML report (reports/index.html)
with Chart.js visuals, KPI cards, filterable results, and step-by-step tool trace explorers.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: could not load {path}: {e}")
        return None


def compute_metrics(l1_data: List[Dict], l2_data: List[Dict], rel_data: Dict, redteam_data: Dict = None) -> Dict:
    l1_total = len(l1_data) if l1_data else 0
    l1_passed = sum(1 for x in l1_data if x.get("passed")) if l1_data else 0
    l1_rate = (l1_passed / l1_total * 100) if l1_total > 0 else 0

    l2_total = len(l2_data) if l2_data else 0
    l2_passed = 0
    l2_scores = []
    category_stats: Dict[str, Dict[str, int]] = {}

    if l2_data:
        for item in l2_data:
            verdict = item.get("verdict", {})
            p = verdict.get("passed", False)
            if p:
                l2_passed += 1
            score = verdict.get("score", 0.0)
            l2_scores.append(score)

            # Categorize by prefix: FIN, ENG, MULTI, etc.
            test_name = item.get("test", "UNKNOWN")
            prefix = test_name.split("-")[0] if "-" in test_name else "OTHER"
            if prefix not in category_stats:
                category_stats[prefix] = {"total": 0, "passed": 0}
            category_stats[prefix]["total"] += 1
            if p:
                category_stats[prefix]["passed"] += 1

    l2_rate = (l2_passed / l2_total * 100) if l2_total > 0 else 0
    avg_score = (sum(l2_scores) / len(l2_scores) * 100) if l2_scores else 0

    rel_k = 0.0
    stable_pass = 0
    stable_fail = 0
    oscillating = 0
    if rel_data:
        rel_k = rel_data.get("pass_all_k", 0.0) * 100
        stable_pass = rel_data.get("stable_passes", 0)
        stable_fail = rel_data.get("stable_fails", 0)
        oscillating = rel_data.get("oscillating", 0)

    rt_total = 0
    rt_passed = 0
    rt_rate = 100.0
    if redteam_data:
        rt_total = redteam_data.get("total", 0)
        rt_passed = redteam_data.get("passed", 0)
        rt_rate = redteam_data.get("pass_rate", 100.0)

    return {
        "l1_total": l1_total,
        "l1_passed": l1_passed,
        "l1_rate": round(l1_rate, 1),
        "l2_total": l2_total,
        "l2_passed": l2_passed,
        "l2_rate": round(l2_rate, 1),
        "avg_score": round(avg_score, 1),
        "rel_k": round(rel_k, 1),
        "stable_pass": stable_pass,
        "stable_fail": stable_fail,
        "oscillating": oscillating,
        "rt_total": rt_total,
        "rt_passed": rt_passed,
        "rt_rate": round(rt_rate, 1),
        "category_stats": category_stats,
    }


def render_html(metrics: Dict, l1_data: List[Dict], l2_data: List[Dict], rel_data: Dict, redteam_data: Dict = None) -> str:
    # Serialize data for client-side filtering and rendering
    l2_json = json.dumps(l2_data or [], indent=2)
    l1_json = json.dumps(l1_data or [], indent=2)

    cat_labels = list(metrics["category_stats"].keys())
    cat_pass_rates = [
        round(metrics["category_stats"][c]["passed"] / metrics["category_stats"][c]["total"] * 100, 1)
        if metrics["category_stats"][c]["total"] > 0 else 0
        for c in cat_labels
    ]

    html = f"""<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Harness AI — Agent Evaluation Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    code, pre {{ font-family: 'JetBrains Mono', monospace; }}
    .glass {{
      background: rgba(15, 23, 42, 0.75);
      backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.08);
    }}
  </style>
</head>
<body class="min-h-full pb-16 selection:bg-indigo-500 selection:text-white">

  <!-- Navigation Bar -->
  <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/25">
          H
        </div>
        <div>
          <h1 class="text-base font-bold tracking-tight text-white flex items-center gap-2">
            Harness-Aware Agent Evals
            <span class="text-xs px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 font-mono">v1.2</span>
          </h1>
          <p class="text-xs text-slate-400">FastMCP Plugin &bull; Level 1 Deterministic &bull; Level 2 Live Agent &bull; Pass^k Stability</p>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <a href="https://github.com/EBHAVANI17/Harness-AI" target="_blank" class="text-xs text-slate-300 hover:text-white px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 flex items-center gap-1.5 transition">
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
          GitHub Repo
        </a>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-8">

    <!-- KPI Metric Cards Grid -->
    <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      
      <!-- Card 1: Level 1 -->
      <div class="glass rounded-2xl p-5 border border-slate-800 shadow-xl relative overflow-hidden group">
        <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-emerald-500/10 rounded-full blur-xl group-hover:bg-emerald-500/20 transition duration-500"></div>
        <div class="flex items-center justify-between text-xs text-slate-400 font-medium mb-2">
          <span>LEVEL 1 DETERMINISTIC</span>
          <span class="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-semibold">Offline</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span class="text-3xl font-extrabold text-white tracking-tight">{metrics['l1_rate']}%</span>
          <span class="text-xs text-emerald-400 font-semibold">{metrics['l1_passed']}/{metrics['l1_total']} tests</span>
        </div>
        <p class="text-xs text-slate-400 mt-2">Zero-shot contract adherence & disambiguation</p>
      </div>

      <!-- Card 2: Level 2 -->
      <div class="glass rounded-2xl p-5 border border-slate-800 shadow-xl relative overflow-hidden group">
        <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-indigo-500/10 rounded-full blur-xl group-hover:bg-indigo-500/20 transition duration-500"></div>
        <div class="flex items-center justify-between text-xs text-slate-400 font-medium mb-2">
          <span>LEVEL 2 LIVE AGENT</span>
          <span class="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-400 font-semibold">Gemini 2.5</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span class="text-3xl font-extrabold text-white tracking-tight">{metrics['l2_rate']}%</span>
          <span class="text-xs text-indigo-400 font-semibold">{metrics['l2_passed']}/{metrics['l2_total']} passed</span>
        </div>
        <p class="text-xs text-slate-400 mt-2">Tool-calling loop over live FastMCP server</p>
      </div>

      <!-- Card 3: LLM Judge Score -->
      <div class="glass rounded-2xl p-5 border border-slate-800 shadow-xl relative overflow-hidden group">
        <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-purple-500/10 rounded-full blur-xl group-hover:bg-purple-500/20 transition duration-500"></div>
        <div class="flex items-center justify-between text-xs text-slate-400 font-medium mb-2">
          <span>JUDGE QUALITY</span>
          <span class="px-2 py-0.5 rounded bg-purple-500/20 text-purple-400 font-semibold">Rubric</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span class="text-3xl font-extrabold text-white tracking-tight">{metrics['avg_score']}%</span>
          <span class="text-xs text-purple-400 font-semibold">Grounding</span>
        </div>
        <p class="text-xs text-slate-400 mt-2">Completeness, ambiguity & conciseness</p>
      </div>

      <!-- Card 4: Pass^k Stability -->
      <div class="glass rounded-2xl p-5 border border-slate-800 shadow-xl relative overflow-hidden group">
        <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-amber-500/10 rounded-full blur-xl group-hover:bg-amber-500/20 transition duration-500"></div>
        <div class="flex items-center justify-between text-xs text-slate-400 font-medium mb-2">
          <span>TAU-BENCH PASS^K</span>
          <span class="px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 font-semibold">Stability</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span class="text-3xl font-extrabold text-white tracking-tight">{metrics['rel_k']}%</span>
          <span class="text-xs text-amber-400 font-semibold">{metrics['stable_pass']} passes</span>
        </div>
        <p class="text-xs text-slate-400 mt-2">{metrics['oscillating']} oscillating tests across seeds</p>
      </div>

      <!-- Card 5: Red-Teaming Defense -->
      <div class="glass rounded-2xl p-5 border border-slate-800 shadow-xl relative overflow-hidden group">
        <div class="absolute -right-4 -bottom-4 w-24 h-24 bg-rose-500/10 rounded-full blur-xl group-hover:bg-rose-500/20 transition duration-500"></div>
        <div class="flex items-center justify-between text-xs text-slate-400 font-medium mb-2">
          <span>RED-TEAM DEFENSE</span>
          <span class="px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 font-semibold">Adversarial</span>
        </div>
        <div class="flex items-baseline gap-2">
          <span class="text-3xl font-extrabold text-white tracking-tight">{metrics['rt_rate']}%</span>
          <span class="text-xs text-rose-400 font-semibold">{metrics['rt_passed']}/{metrics['rt_total']} defended</span>
        </div>
        <p class="text-xs text-slate-400 mt-2">Injection, SQL/delimiters & hallucination safe</p>
      </div>

    </section>

    <!-- Visual Charts Section -->
    <section class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      
      <!-- Chart 1: Domain Success Breakdown -->
      <div class="glass rounded-2xl p-6 border border-slate-800 lg:col-span-2">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-sm font-bold text-white uppercase tracking-wider">Domain Accuracy Breakdown</h2>
            <p class="text-xs text-slate-400">Pass percentage grouped by plugin functional domain</p>
          </div>
          <span class="text-xs font-mono text-slate-500">Level 2 Live Evals</span>
        </div>
        <div class="h-64">
          <canvas id="domainChart"></canvas>
        </div>
      </div>

      <!-- Chart 2: Reliability Distribution -->
      <div class="glass rounded-2xl p-6 border border-slate-800">
        <div class="flex items-center justify-between mb-4">
          <div>
            <h2 class="text-sm font-bold text-white uppercase tracking-wider">Pass^k Reliability</h2>
            <p class="text-xs text-slate-400">Stability classification (tau-bench)</p>
          </div>
        </div>
        <div class="h-64 flex items-center justify-center">
          <canvas id="reliabilityChart"></canvas>
        </div>
      </div>

    </section>

    <!-- Interactive Trace Explorer -->
    <section class="glass rounded-2xl p-6 border border-slate-800 space-y-5">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h2 class="text-base font-bold text-white flex items-center gap-2">
            Interactive Test Trace Explorer
            <span id="testCountBadge" class="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono">10 Cases</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">Click any test case to expand its full conversational trace, tool arguments, and evaluator rationale.</p>
        </div>

        <!-- Filter & Search Controls -->
        <div class="flex items-center gap-2 flex-wrap">
          <div class="relative">
            <input type="text" id="searchInput" placeholder="Search test name or tool..." 
                   class="bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-1.5 pl-8 focus:outline-none focus:border-indigo-500 w-48 sm:w-60">
            <svg class="w-4 h-4 text-slate-500 absolute left-2.5 top-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
          </div>
          <button onclick="setFilter('all')" id="filter-all" class="filter-btn text-xs px-3 py-1.5 rounded-lg bg-indigo-600 text-white font-medium transition">All</button>
          <button onclick="setFilter('pass')" id="filter-pass" class="filter-btn text-xs px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition">Passed</button>
          <button onclick="setFilter('fail')" id="filter-fail" class="filter-btn text-xs px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition">Failed</button>
        </div>
      </div>

      <!-- Test Cases Container -->
      <div id="testCasesContainer" class="space-y-3">
        <!-- Rendered dynamically by JavaScript -->
      </div>
    </section>

    <!-- Architecture & Harness Paper Overview -->
    <section class="glass rounded-2xl p-6 border border-slate-800 grid grid-cols-1 md:grid-cols-3 gap-6">
      <div>
        <div class="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold mb-3 text-sm">1</div>
        <h3 class="text-sm font-semibold text-white mb-1">Contract-Based Schema Evals</h3>
        <p class="text-xs text-slate-400 leading-relaxed">
          Level 1 deterministic tests execute directly against the FastMCP schema without LLM non-determinism, catching coverage gaps, missing parameters, and ambiguous ties instantly.
        </p>
      </div>
      <div>
        <div class="w-8 h-8 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center font-bold mb-3 text-sm">2</div>
        <h3 class="text-sm font-semibold text-white mb-1">Autonomous Function-Calling Loop</h3>
        <p class="text-xs text-slate-400 leading-relaxed">
          Level 2 tests Gemini 2.5 against real MCP sessions over HTTP/SSE, inspecting tool trajectories, disambiguation questions, and hallucination containment.
        </p>
      </div>
      <div>
        <div class="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold mb-3 text-sm">3</div>
        <h3 class="text-sm font-semibold text-white mb-1">Pass^k Flakiness Variance</h3>
        <p class="text-xs text-slate-400 leading-relaxed">
          Based on the Tau-bench methodology, repeated stochastic evaluations identify oscillating edge cases so production prompts are strictly hardened before deployment.
        </p>
      </div>
    </section>

  </main>

  <footer class="text-center text-xs text-slate-600 mt-12">
    Engineered with FastMCP &bull; Google Generative AI &bull; Based on OpenAI Harness-Aware Evaluations paper
  </footer>

  <script>
    // Embedded Data
    const l2Data = {l2_json};
    const l1Data = {l1_json};

    let currentFilter = 'all';
    let searchQuery = '';

    // Render Charts
    window.addEventListener('DOMContentLoaded', () => {{
      // Domain Chart
      const domainCtx = document.getElementById('domainChart').getContext('2d');
      new Chart(domainCtx, {{
        type: 'bar',
        data: {{
          labels: {json.dumps(cat_labels)},
          datasets: [{{
            label: 'Pass Rate (%)',
            data: {json.dumps(cat_pass_rates)},
            backgroundColor: [
              'rgba(99, 102, 241, 0.8)',
              'rgba(168, 85, 247, 0.8)',
              'rgba(14, 165, 233, 0.8)',
              'rgba(245, 158, 11, 0.8)'
            ],
            borderRadius: 8,
            borderWidth: 0
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }}
          }},
          scales: {{
            y: {{
              beginAtZero: true,
              max: 100,
              grid: {{ color: 'rgba(255, 255, 255, 0.05)' }},
              ticks: {{ color: '#94a3b8', font: {{ family: 'JetBrains Mono', size: 10 }} }}
            }},
            x: {{
              grid: {{ display: false }},
              ticks: {{ color: '#94a3b8', font: {{ family: 'Plus Jakarta Sans', weight: '600', size: 11 }} }}
            }}
          }}
        }}
      }});

      // Reliability Chart
      const relCtx = document.getElementById('reliabilityChart').getContext('2d');
      new Chart(relCtx, {{
        type: 'doughnut',
        data: {{
          labels: ['Stable Pass', 'Stable Fail', 'Oscillating'],
          datasets: [{{
            data: [{metrics['stable_pass']}, {metrics['stable_fail']}, {metrics['oscillating']}],
            backgroundColor: [
              '#10b981',
              '#f43f5e',
              '#f59e0b'
            ],
            borderColor: '#0f172a',
            borderWidth: 4
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          cutout: '72%',
          plugins: {{
            legend: {{
              position: 'bottom',
              labels: {{
                color: '#94a3b8',
                font: {{ family: 'Plus Jakarta Sans', size: 11 }},
                padding: 12
              }}
            }}
          }}
        }}
      }});

      renderTestList();
    }});

    function setFilter(filter) {{
      currentFilter = filter;
      document.querySelectorAll('.filter-btn').forEach(btn => {{
        btn.classList.remove('bg-indigo-600', 'text-white');
        btn.classList.add('bg-slate-900', 'text-slate-400');
      }});
      const active = document.getElementById('filter-' + filter);
      if (active) {{
        active.classList.remove('bg-slate-900', 'text-slate-400');
        active.classList.add('bg-indigo-600', 'text-white');
      }}
      renderTestList();
    }}

    document.getElementById('searchInput').addEventListener('input', (e) => {{
      searchQuery = e.target.value.toLowerCase();
      renderTestList();
    }});

    function renderTestList() {{
      const container = document.getElementById('testCasesContainer');
      container.innerHTML = '';

      const filtered = l2Data.filter(item => {{
        const passed = item.verdict ? item.verdict.passed : false;
        if (currentFilter === 'pass' && !passed) return false;
        if (currentFilter === 'fail' && passed) return false;

        if (searchQuery) {{
          const testName = (item.test || '').toLowerCase();
          const answer = (item.answer || '').toLowerCase();
          const reason = (item.verdict && item.verdict.reason || '').toLowerCase();
          const toolCalls = JSON.stringify(item.tool_calls || []).toLowerCase();
          if (!testName.includes(searchQuery) && !answer.includes(searchQuery) && !reason.includes(searchQuery) && !toolCalls.includes(searchQuery)) {{
            return false;
          }}
        }}
        return true;
      }});

      document.getElementById('testCountBadge').textContent = `${{filtered.length}} Cases`;

      if (filtered.length === 0) {{
        container.innerHTML = `<div class="p-8 text-center text-slate-500 text-sm">No test cases match the current filter or search query.</div>`;
        return;
      }}

      filtered.forEach((item, index) => {{
        const passed = item.verdict ? item.verdict.passed : false;
        const score = item.verdict && item.verdict.score !== undefined ? Math.round(item.verdict.score * 100) : (passed ? 100 : 0);
        const reason = item.verdict ? item.verdict.reason : 'No reason provided';
        const toolCalls = item.tool_calls || [];

        const card = document.createElement('div');
        card.className = "border border-slate-800/80 rounded-xl overflow-hidden bg-slate-900/40 hover:bg-slate-900/70 transition";

        card.innerHTML = `
          <button onclick="toggleDetails('detail-${{index}}')" class="w-full text-left px-5 py-4 flex items-center justify-between gap-4 focus:outline-none">
            <div class="flex items-center gap-3 min-w-0">
              <span class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${{passed ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}}">
                ${{passed ? '✓' : '✗'}}
              </span>
              <div class="min-w-0">
                <p class="text-sm font-semibold text-white truncate">${{item.test || 'Untitled Test'}}</p>
                <p class="text-xs text-slate-400 truncate mt-0.5">${{reason}}</p>
              </div>
            </div>
            <div class="flex items-center gap-3 shrink-0">
              <span class="text-xs font-mono px-2 py-0.5 rounded ${{toolCalls.length > 0 ? 'bg-indigo-500/10 text-indigo-300 border border-indigo-500/20' : 'bg-slate-800 text-slate-400'}}">
                ${{toolCalls.length}} tool call${{toolCalls.length === 1 ? '' : 's'}}
              </span>
              <span class="text-xs font-bold font-mono px-2.5 py-1 rounded-md ${{passed ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}}">
                ${{score}}%
              </span>
              <svg id="chevron-detail-${{index}}" class="w-4 h-4 text-slate-500 transition-transform duration-200" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
            </div>
          </button>

          <!-- Collapsible Content -->
          <div id="detail-${{index}}" class="hidden px-5 pb-5 pt-2 border-t border-slate-800/60 bg-slate-950/40 space-y-4">
            
            <!-- Final Answer -->
            <div>
              <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1.5">Agent Response</p>
              <div class="p-3.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 leading-relaxed font-mono whitespace-pre-wrap">${{escapeHtml(item.answer || '(No answer text generated)')}}</div>
            </div>

            <!-- Tool Calls Trace -->
            ${{toolCalls.length > 0 ? `
              <div>
                <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">Tool Execution Trace (${{toolCalls.length}})</p>
                <div class="space-y-2.5">
                  ${{toolCalls.map((tc, tcIdx) => `
                    <div class="p-3 rounded-lg bg-slate-900/90 border border-indigo-900/40 space-y-2">
                      <div class="flex items-center justify-between text-xs">
                        <span class="font-mono font-bold text-indigo-400 flex items-center gap-1.5">
                          <span class="w-2 h-2 rounded-full bg-indigo-500"></span>
                          ${{tc.name || tc.tool || 'unknown_tool'}}
                        </span>
                        <span class="text-slate-500 font-mono text-[10px]">Step ${{tcIdx + 1}}</span>
                      </div>
                      <div class="text-[11px] font-mono text-slate-300">
                        <span class="text-slate-500">Arguments:</span>
                        <pre class="mt-1 p-2 bg-slate-950 rounded text-slate-300 overflow-x-auto text-[11px]">${{escapeHtml(JSON.stringify(tc.arguments || {{}}, null, 2))}}</pre>
                      </div>
                      ${{tc.result ? `
                        <div class="text-[11px] font-mono text-slate-300">
                          <span class="text-slate-500">Output Payload:</span>
                          <pre class="mt-1 p-2 bg-slate-950 rounded text-emerald-400/90 overflow-x-auto text-[11px]">${{escapeHtml(JSON.stringify(tc.result, null, 2))}}</pre>
                        </div>
                      ` : ''}}
                    </div>
                  `).join('')}}
                </div>
              </div>
            ` : '<div class="text-xs text-slate-500 italic">No tools were called (direct conversational response or handled via classification).</div>'}}

            <!-- Grader Verdict Details -->
            <div class="p-3 rounded-lg bg-slate-900/60 border border-slate-800 text-xs">
              <span class="text-slate-400 font-medium">Evaluator Verdict:</span>
              <span class="ml-2 font-semibold ${{passed ? 'text-emerald-400' : 'text-rose-400'}}">${{passed ? 'PASS' : 'FAIL'}}</span>
              <p class="text-slate-400 mt-1">${{escapeHtml(reason)}}</p>
            </div>

          </div>
        `;

        container.appendChild(card);
      }});
    }}

    function toggleDetails(id) {{
      const el = document.getElementById(id);
      const chevron = document.getElementById('chevron-' + id);
      if (el) {{
        el.classList.toggle('hidden');
      }}
      if (chevron) {{
        chevron.classList.toggle('rotate-180');
      }}
    }}

    function escapeHtml(str) {{
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }}
  </script>
</body>
</html>
"""
    return html


def main():
    print("Loading evaluation outputs...")
    l1 = load_json(DATA_DIR / "l1-results.json")
    l2 = load_json(DATA_DIR / "l2-results.json")
    rel = load_json(DATA_DIR / "reliability_report.json")
    rt = load_json(DATA_DIR / "redteam_results.json")

    metrics = compute_metrics(l1 or [], l2 or [], rel or {}, rt or {})
    print(f"Metrics computed:")
    print(f"  Level 1: {metrics['l1_passed']}/{metrics['l1_total']} ({metrics['l1_rate']}%)")
    print(f"  Level 2: {metrics['l2_passed']}/{metrics['l2_total']} ({metrics['l2_rate']}%)")
    print(f"  Judge Average Score: {metrics['avg_score']}%")
    print(f"  Pass^k Reliability: {metrics['rel_k']}% ({metrics['stable_pass']} stable passes)")
    print(f"  Red-Team Defense: {metrics['rt_passed']}/{metrics['rt_total']} ({metrics['rt_rate']}%)")

    html_content = render_html(metrics, l1 or [], l2 or [], rel or {}, rt or {})

    # Write to reports/index.html and reports/dashboard.html
    for filename in ["index.html", "dashboard.html"]:
        out_path = REPORT_DIR / filename
        out_path.write_text(html_content, encoding="utf-8")
        print(f"Generated visual report: {out_path}")

    print("\nDashboard ready! You can open reports/index.html in any browser.")


if __name__ == "__main__":
    main()
