"""
server.py — FastMCP MCP server for the Harness-Aware Plugin Evaluation Framework.

Exposes 5 tools across 4 business domains (Finance, Engineering, Support, Ops).
Fixture data is designed to exercise every evaluation failure mode:
  - Ambiguous queries   : "revenue" → ARR vs MRR, "cost" → COGS vs OpEx
  - Coverage gaps       : "stock price", "headcount" — not in catalog
  - Multi-step cases    : "SLA compliance by product team" needs support + engineering
  - Tied confidence     : COGS / OpEx both score 0.85 for "cost"
  - Hallucination traps : plausible-sounding but absent metric IDs

Run with:
    python server.py          (starts on http://localhost:8000)
"""

from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

INSTRUCTIONS = """
You are a business-intelligence assistant connected to a company data catalog.

**Workflow (always follow these steps in order)**
1. Call `resolve_metric` with the user's indicator(s) to look up canonical metric IDs.
2. Examine the returned candidates:
   - If no candidates or low confidence (< 0.6) are returned, state that the data is unavailable. Do NOT call any fetch tools.
   - If candidates are tied (e.g. ARR vs MRR, or COGS vs OpEx), ask the user to clarify which metric they want. Mention both candidates by name and do NOT call fetch tools.
3. If candidates have a clear winner or once clarified, immediately call the matching domain fetch tool (`fetch_finance`, `fetch_engineering`, `fetch_support`, `fetch_ops`).
   - IMPORTANT: Do not stop after resolve_metric. You MUST proceed to call the fetch tool(s) to retrieve the actual numbers for the user.
4. If a query spans multiple domains (e.g. "SLA compliance by product team" or "CSAT and ARR"), call EACH relevant fetch tool and synthesize the final answer.
5. Never fabricate metric values or IDs. Only use IDs returned by resolve_metric.
"""

mcp = FastMCP(
    name="company-data-plugin",
    instructions=INSTRUCTIONS,
)

# ---------------------------------------------------------------------------
# Fixture data — replace these dicts with real DB / API calls
# ---------------------------------------------------------------------------

#: Master metric catalog.  Each entry describes one resolvable business metric.
METRIC_CATALOG: list[dict[str, Any]] = [
    # ── Finance ──────────────────────────────────────────────────────────────
    {
        "metric_id": "fin_arr",
        "title": "Annual Recurring Revenue (ARR)",
        "domain": "finance",
        "aliases": ["arr", "annual recurring revenue", "annual revenue"],
        "description": "Total annualised value of recurring subscription contracts.",
    },
    {
        "metric_id": "fin_mrr",
        "title": "Monthly Recurring Revenue (MRR)",
        "domain": "finance",
        "aliases": ["mrr", "monthly recurring revenue", "monthly revenue"],
        "description": "Total monthly value of recurring subscription contracts.",
    },
    {
        "metric_id": "fin_cogs",
        "title": "Cost of Goods Sold (COGS)",
        "domain": "finance",
        "aliases": ["cogs", "cost of goods sold", "cost of revenue"],
        "description": "Direct costs attributable to production of goods/services sold.",
    },
    {
        "metric_id": "fin_opex",
        "title": "Operating Expenses (OpEx)",
        "domain": "finance",
        "aliases": ["opex", "operating expenses", "operating costs"],
        "description": "Ongoing costs for running the business (excl. COGS).",
    },
    {
        "metric_id": "fin_gross_margin",
        "title": "Gross Margin %",
        "domain": "finance",
        "aliases": ["gross margin", "gm", "gross profit margin"],
        "description": "Revenue minus COGS, expressed as a percentage of revenue.",
    },
    {
        "metric_id": "fin_budget_variance",
        "title": "Budget Variance",
        "domain": "finance",
        "aliases": ["budget variance", "variance to budget", "budget vs actuals"],
        "description": "Difference between budgeted and actual spend.",
    },
    # ── Engineering / Product ─────────────────────────────────────────────────
    {
        "metric_id": "eng_deploy_freq",
        "title": "Deployment Frequency",
        "domain": "engineering",
        "aliases": ["deploy frequency", "deployment frequency", "releases per week"],
        "description": "Number of production deployments per week.",
    },
    {
        "metric_id": "eng_bug_count",
        "title": "Open Bug Count",
        "domain": "engineering",
        "aliases": ["bugs", "bug count", "open bugs", "defects"],
        "description": "Number of open bug / defect tickets.",
    },
    {
        "metric_id": "eng_ticket_cycle",
        "title": "Ticket Cycle Time (days)",
        "domain": "engineering",
        "aliases": ["cycle time", "ticket cycle time", "lead time"],
        "description": "Average time from ticket creation to resolution.",
    },
    {
        "metric_id": "eng_p1_incidents",
        "title": "P1 Incidents (MTD)",
        "domain": "engineering",
        "aliases": ["p1 incidents", "critical incidents", "sev1"],
        "description": "Month-to-date count of severity-1 production incidents.",
    },
    # ── Customer Support ─────────────────────────────────────────────────────
    {
        "metric_id": "sup_sla_compliance",
        "title": "SLA Compliance Rate",
        "domain": "support",
        "aliases": ["sla compliance", "sla rate", "sla adherence"],
        "description": "Percentage of support tickets resolved within SLA.",
    },
    {
        "metric_id": "sup_csat",
        "title": "Customer Satisfaction (CSAT)",
        "domain": "support",
        "aliases": ["csat", "customer satisfaction", "satisfaction score"],
        "description": "Average customer satisfaction score (1–5 scale).",
    },
    {
        "metric_id": "sup_ticket_volume",
        "title": "Support Ticket Volume",
        "domain": "support",
        "aliases": ["ticket volume", "support tickets", "inbound tickets"],
        "description": "Total number of inbound support tickets in the period.",
    },
    {
        "metric_id": "sup_sentiment",
        "title": "Support Sentiment Score",
        "domain": "support",
        "aliases": ["sentiment", "support sentiment", "nps proxy"],
        "description": "ML-derived sentiment score across customer messages (−1 to +1).",
    },
    # ── Operations / Supply Chain ─────────────────────────────────────────────
    {
        "metric_id": "ops_inventory_turns",
        "title": "Inventory Turns",
        "domain": "ops",
        "aliases": ["inventory turns", "inventory turnover", "stock turns"],
        "description": "Number of times inventory is sold/used per period.",
    },
    {
        "metric_id": "ops_supplier_lead_time",
        "title": "Supplier Lead Time (days)",
        "domain": "ops",
        "aliases": ["lead time", "supplier lead time", "procurement lead time"],
        "description": "Average days from purchase order to delivery.",
    },
    {
        "metric_id": "ops_on_time_delivery",
        "title": "On-Time Delivery Rate",
        "domain": "ops",
        "aliases": ["on time delivery", "otd", "delivery rate"],
        "description": "Percentage of orders delivered on or before the promised date.",
    },
]

#: Synthetic values returned by the fetch tools (replace with real queries).
FIXTURE_VALUES: dict[str, Any] = {
    # Finance
    "fin_arr": {"value": 12_400_000, "unit": "USD", "period": "2024-Q4"},
    "fin_mrr": {"value": 1_033_333, "unit": "USD", "period": "2024-12"},
    "fin_cogs": {"value": 3_720_000, "unit": "USD", "period": "2024-Q4"},
    "fin_opex": {"value": 5_100_000, "unit": "USD", "period": "2024-Q4"},
    "fin_gross_margin": {"value": 70.0, "unit": "%", "period": "2024-Q4"},
    "fin_budget_variance": {"value": -142_000, "unit": "USD", "period": "2024-Q4",
                             "note": "Negative = under budget"},
    # Engineering
    "eng_deploy_freq": {"value": 8.3, "unit": "deploys/week", "period": "2024-Q4"},
    "eng_bug_count": {"value": 134, "unit": "tickets", "as_of": "2025-01-10"},
    "eng_ticket_cycle": {"value": 4.7, "unit": "days", "period": "2024-Q4"},
    "eng_p1_incidents": {"value": 2, "unit": "incidents", "period": "2024-12"},
    # Support
    "sup_sla_compliance": {"value": 91.4, "unit": "%", "period": "2024-Q4"},
    "sup_csat": {"value": 4.2, "unit": "/5", "period": "2024-Q4"},
    "sup_ticket_volume": {"value": 3_817, "unit": "tickets", "period": "2024-Q4"},
    "sup_sentiment": {"value": 0.42, "unit": "score", "period": "2024-Q4"},
    # Ops
    "ops_inventory_turns": {"value": 6.1, "unit": "turns/year", "period": "2024-Q4"},
    "ops_supplier_lead_time": {"value": 12.3, "unit": "days", "period": "2024-Q4"},
    "ops_on_time_delivery": {"value": 94.7, "unit": "%", "period": "2024-Q4"},
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> set[str]:
    """
    Lower-case word-tokenise, removing common stop-words that are too broad
    to be useful for metric matching (e.g. "stock" appears in both
    "stock price" and "inventory stock turns", causing false positives).
    """
    import re
    _STOP = {
        "the", "a", "an", "of", "in", "by", "for", "and", "or", "to",
        "at", "is", "are", "was", "were", "per",
        # domain-ambiguous words whose presence alone is not diagnostic
        "stock", "price", "rate", "count", "total", "average", "avg",
        "number", "time", "cost",
    }
    tokens = set(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())
    return tokens - _STOP


def _score(indicator: str, metric: dict[str, Any]) -> float:
    """
    Simple alias + token overlap scorer (0.0 – 1.0).
    Real systems would use embeddings; this is intentionally lightweight so the
    fixture data drives interesting evaluation scenarios.

    Design decisions
    ----------------
    - Exact alias match  → 0.95 (unambiguous)
    - Substring match    → 0.78 (partial alias coverage)
    - Token overlap      → up to 0.74 ONLY when the indicator has ≥ 2 tokens
                           AND the overlap fraction is ≥ 0.5.  Single-token
                           indicators must match exactly or via substring to
                           avoid spurious cross-domain matches (e.g. "price"
                           matching "inventory turns" via shared stop-words).
    """
    ind_lower = indicator.strip().lower()

    # Exact alias match → high confidence
    for alias in metric["aliases"]:
        if ind_lower == alias.lower():
            return 0.95

    # Substring match (indicator is a sub-string of an alias, or vice-versa)
    for alias in metric["aliases"]:
        if ind_lower in alias.lower() or alias.lower() in ind_lower:
            return 0.78

    # Token-overlap — only meaningful for multi-token indicators
    ind_tokens = _tokenise(ind_lower)
    if len(ind_tokens) < 2:
        # Single-word indicator with no alias match → no confidence
        return 0.0

    alias_tokens: set[str] = set()
    for alias in metric["aliases"]:
        alias_tokens |= _tokenise(alias)
    alias_tokens |= _tokenise(metric["title"].lower())

    overlap = len(ind_tokens & alias_tokens)
    if overlap == 0:
        return 0.0

    # Require at least 50% of the indicator tokens to match
    fraction = overlap / len(ind_tokens)
    if fraction < 0.5:
        return 0.0

    return min(0.60 + 0.08 * overlap, 0.74)


# ---------------------------------------------------------------------------
# Tool: resolve_metric
# ---------------------------------------------------------------------------

@mcp.tool()
def resolve_metric(indicators: list[str]) -> dict[str, Any]:
    """
    Resolve one or more business indicators to canonical metric IDs.

    For each indicator string the tool returns an ordered list of candidate
    metrics with confidence scores.  Candidates with confidence < 0.6 indicate
    a *coverage gap* (the metric may not exist in the catalog).

    Args:
        indicators: Natural-language or abbreviated indicator names.
                    E.g. ["revenue", "cost", "SLA compliance"].

    Returns:
        {
          "results": [
            {
              "indicator": str,
              "candidates": [
                {"metric_id": str, "title": str, "domain": str, "confidence": float}
              ],
              "note": str   # human-readable hint (gap / ambiguity / ok)
            }
          ]
        }
    """
    results: list[dict[str, Any]] = []

    for indicator in indicators:
        scored: list[tuple[float, dict[str, Any]]] = []
        for metric in METRIC_CATALOG:
            score = _score(indicator, metric)
            if score > 0:
                scored.append((score, metric))

        # Sort descending by confidence
        scored.sort(key=lambda x: x[0], reverse=True)

        # Keep only candidates with score ≥ 0.5 (up to top 5)
        candidates = [
            {
                "metric_id": m["metric_id"],
                "title": m["title"],
                "domain": m["domain"],
                "confidence": round(s, 3),
            }
            for s, m in scored[:5]
            if s >= 0.5
        ]

        # --- Craft the note ---
        if not candidates:
            note = (
                f"No metric found for '{indicator}'. "
                "This indicator is not in the catalog — it may be a coverage gap."
            )
        elif len(candidates) > 1 and candidates[0]["confidence"] == candidates[1]["confidence"]:
            note = (
                f"Ambiguous: '{indicator}' matches multiple metrics with equal confidence. "
                "Please clarify which metric the user wants before fetching."
            )
        elif len(candidates) > 1:
            note = (
                f"Multiple candidates for '{indicator}'. "
                "Top match is recommended, but confirm with user if context is unclear."
            )
        else:
            note = "Resolved."

        results.append(
            {
                "indicator": indicator,
                "candidates": candidates,
                "note": note,
            }
        )

    return {"results": results}


# ---------------------------------------------------------------------------
# Tool: fetch_finance
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_finance(metric_ids: list[str]) -> dict[str, Any]:
    """
    Fetch Finance / Accounting metric values.

    Args:
        metric_ids: List of canonical metric IDs (must start with 'fin_').
                    Obtain these from `resolve_metric` first.

    Returns:
        {"data": {metric_id: value_object, ...}, "missing": [metric_id, ...]}
    """
    return _fetch_domain(metric_ids, domain_prefix="fin_", domain_name="finance")


# ---------------------------------------------------------------------------
# Tool: fetch_engineering
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_engineering(metric_ids: list[str]) -> dict[str, Any]:
    """
    Fetch Engineering / Product metric values.

    Args:
        metric_ids: List of canonical metric IDs (must start with 'eng_').
                    Obtain these from `resolve_metric` first.

    Returns:
        {"data": {metric_id: value_object, ...}, "missing": [metric_id, ...]}
    """
    return _fetch_domain(metric_ids, domain_prefix="eng_", domain_name="engineering")


# ---------------------------------------------------------------------------
# Tool: fetch_support
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_support(metric_ids: list[str]) -> dict[str, Any]:
    """
    Fetch Customer Support metric values.

    Args:
        metric_ids: List of canonical metric IDs (must start with 'sup_').
                    Obtain these from `resolve_metric` first.

    Returns:
        {"data": {metric_id: value_object, ...}, "missing": [metric_id, ...]}
    """
    return _fetch_domain(metric_ids, domain_prefix="sup_", domain_name="support")


# ---------------------------------------------------------------------------
# Tool: fetch_ops
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_ops(metric_ids: list[str]) -> dict[str, Any]:
    """
    Fetch Operations / Supply-Chain metric values.

    Args:
        metric_ids: List of canonical metric IDs (must start with 'ops_').
                    Obtain these from `resolve_metric` first.

    Returns:
        {"data": {metric_id: value_object, ...}, "missing": [metric_id, ...]}
    """
    return _fetch_domain(metric_ids, domain_prefix="ops_", domain_name="ops")


# ---------------------------------------------------------------------------
# Shared fetch helper
# ---------------------------------------------------------------------------

def _fetch_domain(
    metric_ids: list[str],
    domain_prefix: str,
    domain_name: str,
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    missing: list[str] = []
    wrong_domain: list[str] = []

    for mid in metric_ids:
        if not mid.startswith(domain_prefix):
            wrong_domain.append(mid)
            continue
        if mid in FIXTURE_VALUES:
            data[mid] = FIXTURE_VALUES[mid]
        else:
            missing.append(mid)

    result: dict[str, Any] = {"data": data, "missing": missing}
    if wrong_domain:
        result["wrong_domain"] = wrong_domain
        result["hint"] = (
            f"The following IDs do not belong to the '{domain_name}' domain "
            f"and were skipped: {wrong_domain}.  Use the correct fetch tool."
        )
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8000"))
    mcp.run(transport="http", host="0.0.0.0", port=port)
