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
3. If candidates have a clear winner or once clarified, immediately call the matching domain fetch tool (`fetch_finance`, `fetch_engineering`, `fetch_support`, `fetch_ops`, `fetch_healthcare`, `fetch_bfsi`, `fetch_retail`, `fetch_logistics`, `fetch_saas`).
   - IMPORTANT: Do not stop after resolve_metric. You MUST proceed to call the fetch tool(s) to retrieve the actual numbers for the user.
4. If a query spans multiple domains or industries, call EACH relevant fetch tool and synthesize the final answer.
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
    # ── Industry 1: Healthcare & Life Sciences ────────────────────────────────
    {
        "metric_id": "hc_bed_occupancy",
        "title": "Bed Occupancy Rate",
        "domain": "healthcare",
        "aliases": ["bed occupancy", "bed occupancy rate", "hospital bed occupancy"],
        "description": "Percentage of hospital inpatient beds occupied by patients.",
    },
    {
        "metric_id": "hc_bed_turnover",
        "title": "Bed Turnover Interval",
        "domain": "healthcare",
        "aliases": ["bed turnover", "bed turnover interval", "bed cycle interval"],
        "description": "Average duration in days between discharge and admission to the same bed.",
    },
    {
        "metric_id": "hc_readmission_30d",
        "title": "30-Day Patient Readmission Rate",
        "domain": "healthcare",
        "aliases": ["readmission rate", "30-day readmission", "patient readmission"],
        "description": "Percentage of patients readmitted within 30 days of discharge.",
    },
    {
        "metric_id": "hc_alos",
        "title": "Average Length of Stay (ALOS)",
        "domain": "healthcare",
        "aliases": ["alos", "average length of stay", "patient length of stay"],
        "description": "Average duration in days that admitted patients stay in the facility.",
    },
    {
        "metric_id": "hc_er_wait_time",
        "title": "Emergency Room Wait Time",
        "domain": "healthcare",
        "aliases": ["er wait time", "emergency room wait time", "emergency wait"],
        "description": "Average minutes from patient ER triage to first physician encounter.",
    },
    {
        "metric_id": "hc_nurse_patient_ratio",
        "title": "Nurse-to-Patient Ratio",
        "domain": "healthcare",
        "aliases": ["nurse to patient ratio", "nurse staffing ratio", "nurse ratio"],
        "description": "Ratio of registered nurses on active shift per inpatient bed.",
    },
    # ── Industry 2: Banking, Financial Services & Insurance (BFSI) ─────────────
    {
        "metric_id": "bfsi_car",
        "title": "Capital Adequacy Ratio (CAR)",
        "domain": "bfsi",
        "aliases": ["car", "capital adequacy ratio", "capital adequacy", "basel car"],
        "description": "Ratio of a bank's capital to its risk-weighted credit and market exposure.",
    },
    {
        "metric_id": "bfsi_nim",
        "title": "Net Interest Margin (NIM)",
        "domain": "bfsi",
        "aliases": ["nim", "net interest margin", "interest margin"],
        "description": "Difference between interest received and interest paid out relative to assets.",
    },
    {
        "metric_id": "bfsi_npl_ratio",
        "title": "Non-Performing Loans (NPL) Ratio",
        "domain": "bfsi",
        "aliases": ["npl", "non performing loans", "npl ratio", "bad loan ratio"],
        "description": "Percentage of total loan portfolio in default or close to default (>90 days).",
    },
    {
        "metric_id": "bfsi_ltv",
        "title": "Loan-to-Value (LTV) Ratio",
        "domain": "bfsi",
        "aliases": ["ltv", "loan to value", "ltv ratio", "mortgage ltv"],
        "description": "Ratio of loan principal to the appraised value of the securing collateral.",
    },
    {
        "metric_id": "bfsi_credit_risk",
        "title": "Credit Risk Exposure",
        "domain": "bfsi",
        "aliases": ["credit risk", "credit risk exposure", "portfolio risk exposure"],
        "description": "Total financial exposure vulnerable to counterparty default.",
    },
    {
        "metric_id": "bfsi_market_risk",
        "title": "Market Value at Risk (VaR)",
        "domain": "bfsi",
        "aliases": ["market risk", "value at risk", "market var", "trading var"],
        "description": "Statistical assessment of maximum projected trading loss at 99% confidence.",
    },
    # ── Industry 3: Retail & E-Commerce ────────────────────────────────────────
    {
        "metric_id": "ret_cac",
        "title": "Customer Acquisition Cost (CAC)",
        "domain": "retail",
        "aliases": ["cac", "customer acquisition cost", "shopper acquisition cost"],
        "description": "Total marketing and sales expense divided by new customers acquired.",
    },
    {
        "metric_id": "ret_roas",
        "title": "Return on Ad Spend (ROAS)",
        "domain": "retail",
        "aliases": ["roas", "return on ad spend", "ad spend return", "marketing roas"],
        "description": "Revenue generated for every dollar invested in advertising campaigns.",
    },
    {
        "metric_id": "ret_return_rate",
        "title": "Product Return Rate",
        "domain": "retail",
        "aliases": ["product return rate", "customer returns", "merchandise return rate"],
        "description": "Percentage of fulfilled merchandise units returned by customers.",
    },
    {
        "metric_id": "ret_aov",
        "title": "Average Order Value (AOV)",
        "domain": "retail",
        "aliases": ["aov", "average order value", "order basket size"],
        "description": "Average monetary amount spent each time a customer places an order.",
    },
    {
        "metric_id": "ret_cart_abandonment",
        "title": "Cart Abandonment Rate",
        "domain": "retail",
        "aliases": ["cart abandonment", "cart abandonment rate", "checkout dropoff"],
        "description": "Percentage of shoppers who add items to cart but do not complete purchase.",
    },
    {
        "metric_id": "ret_gmv",
        "title": "Gross Merchandise Value (GMV)",
        "domain": "retail",
        "aliases": ["gmv", "gross merchandise value", "marketplace gmv"],
        "description": "Total sales dollar value for merchandise sold across e-commerce channels.",
    },
    # ── Industry 4: Supply Chain & Freight Logistics ───────────────────────────
    {
        "metric_id": "log_otif",
        "title": "On-Time In-Full (OTIF) Delivery",
        "domain": "logistics",
        "aliases": ["otif", "on time in full", "otif delivery", "freight otif"],
        "description": "Percentage of shipments delivered on the agreed date and with complete quantities.",
    },
    {
        "metric_id": "log_supplier_lead_time",
        "title": "Supplier Procurement Lead Time",
        "domain": "logistics",
        "aliases": ["supplier lead time", "vendor lead time", "procurement lead time"],
        "description": "Calendar days from purchase requisition dispatch to dock arrival.",
    },
    {
        "metric_id": "log_dock_to_stock",
        "title": "Dock-to-Stock Inbound Cycle Time",
        "domain": "logistics",
        "aliases": ["dock to stock", "dock to stock cycle", "inbound receiving time"],
        "description": "Hours taken from truck unlading at warehouse dock to inventory shelf availability.",
    },
    {
        "metric_id": "log_freight_cost",
        "title": "Freight Cost per Ton-Mile",
        "domain": "logistics",
        "aliases": ["freight cost", "freight cost per ton mile", "shipping cost per mile"],
        "description": "Transportation spend incurred per ton of cargo moved one statute mile.",
    },
    {
        "metric_id": "log_doh",
        "title": "Days of Inventory on Hand (DOH)",
        "domain": "logistics",
        "aliases": ["doh", "days of inventory on hand", "inventory days on hand"],
        "description": "Projected days current warehouse inventory will last under prevailing run-rates.",
    },
    {
        "metric_id": "log_capacity_util",
        "title": "Distribution Center Pallet Capacity",
        "domain": "logistics",
        "aliases": ["dc storage capacity", "pallet storage utilization", "dc capacity utilization"],
        "description": "Percentage of total usable DC pallet and racking cubic space occupied.",
    },
    # ── Industry 5: SaaS, Cloud Infrastructure & DevOps ────────────────────────
    {
        "metric_id": "saas_nrr",
        "title": "Net Revenue Retention (NRR)",
        "domain": "saas",
        "aliases": ["nrr", "net revenue retention", "net dollar retention", "ndr"],
        "description": "Percentage of recurring revenue retained from existing customer cohort including expansion.",
    },
    {
        "metric_id": "saas_user_retention",
        "title": "Cohort User Retention",
        "domain": "saas",
        "aliases": ["user retention", "cohort retention", "customer retention rate"],
        "description": "Percentage of active users from a cohort who remain active after 90 days.",
    },
    {
        "metric_id": "saas_cloud_cost",
        "title": "Cloud Compute Cost per API Query",
        "domain": "saas",
        "aliases": ["cloud cost per query", "compute cost per call", "unit economics query"],
        "description": "Infrastructure cloud spend amortized across individual API serverless calls.",
    },
    {
        "metric_id": "saas_p99_latency",
        "title": "API P99 Response Latency",
        "domain": "saas",
        "aliases": ["p99 latency", "api latency", "tail latency", "p99 response time"],
        "description": "99th percentile HTTP server round-trip latency in milliseconds.",
    },
    {
        "metric_id": "saas_uptime_sla",
        "title": "System SLA Availability",
        "domain": "saas",
        "aliases": ["uptime sla", "system availability", "sla uptime", "cloud uptime"],
        "description": "Percentage of time production services meet contractual uptime SLAs (e.g. 99.99%).",
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
    # ── Industry 1: Healthcare ──
    "hc_bed_occupancy": {"value": 88.5, "unit": "%", "period": "2024-Q4"},
    "hc_bed_turnover": {"value": 1.8, "unit": "days", "period": "2024-Q4"},
    "hc_readmission_30d": {"value": 9.2, "unit": "%", "period": "2024-Q4"},
    "hc_alos": {"value": 4.2, "unit": "days", "period": "2024-Q4"},
    "hc_er_wait_time": {"value": 42.0, "unit": "minutes", "period": "2024-Q4"},
    "hc_nurse_patient_ratio": {"value": 1.25, "unit": "RN/bed", "period": "2024-Q4"},
    # ── Industry 2: BFSI ──
    "bfsi_car": {"value": 15.8, "unit": "%", "period": "2024-Q4"},
    "bfsi_nim": {"value": 3.42, "unit": "%", "period": "2024-Q4"},
    "bfsi_npl_ratio": {"value": 1.85, "unit": "%", "period": "2024-Q4"},
    "bfsi_ltv": {"value": 62.4, "unit": "%", "period": "2024-Q4"},
    "bfsi_credit_risk": {"value": 14_200_000, "unit": "USD", "period": "2024-Q4"},
    "bfsi_market_risk": {"value": 4_500_000, "unit": "USD", "period": "2024-Q4"},
    # ── Industry 3: Retail ──
    "ret_cac": {"value": 48.50, "unit": "USD", "period": "2024-Q4"},
    "ret_roas": {"value": 4.6, "unit": "x", "period": "2024-Q4"},
    "ret_return_rate": {"value": 8.2, "unit": "%", "period": "2024-Q4"},
    "ret_aov": {"value": 142.50, "unit": "USD", "period": "2024-Q4"},
    "ret_cart_abandonment": {"value": 68.4, "unit": "%", "period": "2024-Q4"},
    "ret_gmv": {"value": 12_400_000, "unit": "USD", "period": "2024-Q4"},
    # ── Industry 4: Logistics ──
    "log_otif": {"value": 95.2, "unit": "%", "period": "2024-Q4"},
    "log_supplier_lead_time": {"value": 14.5, "unit": "days", "period": "2024-Q4"},
    "log_dock_to_stock": {"value": 6.2, "unit": "hours", "period": "2024-Q4"},
    "log_freight_cost": {"value": 0.182, "unit": "USD/ton-mile", "period": "2024-Q4"},
    "log_doh": {"value": 32.4, "unit": "days", "period": "2024-Q4"},
    "log_capacity_util": {"value": 88.4, "unit": "%", "period": "2024-Q4"},
    # ── Industry 5: SaaS ──
    "saas_nrr": {"value": 124.5, "unit": "%", "period": "2024-Q4"},
    "saas_user_retention": {"value": 94.2, "unit": "%", "period": "2024-Q4"},
    "saas_cloud_cost": {"value": 0.0034, "unit": "USD/call", "period": "2024-Q4"},
    "saas_p99_latency": {"value": 142.0, "unit": "ms", "period": "2024-Q4"},
    "saas_uptime_sla": {"value": 99.992, "unit": "%", "period": "2024-Q4"},
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
    - Security check     → 0.0 (reject injection payloads containing semicolons, shell/SQL keywords)
    - Exact alias match  → 0.95 (unambiguous)
    - Substring match    → 0.78 (partial alias coverage)
    - Token overlap      → up to 0.74 ONLY when the indicator has ≥ 2 tokens
                           AND the overlap fraction is ≥ 0.5.  Single-token
                           indicators must match exactly or via substring to
                           avoid spurious cross-domain matches (e.g. "price"
                           matching "inventory turns" via shared stop-words).
    """
    import re
    ind_lower = indicator.strip().lower()

    # Security check: reject potential SQL injection, command chaining, or delimiter escapes
    if re.search(r"[;`|><\$\{\}]|\b(drop|truncate|delete|exec|system|admin)\b", ind_lower):
        return 0.0

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
# Industry Tools: Healthcare, BFSI, Retail, Logistics, SaaS
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_healthcare(metric_ids: list[str]) -> dict[str, Any]:
    """
    Fetch Healthcare & Clinical Operations metric values (bed occupancy, ALOS, readmission, etc.).

    Args:
        metric_ids: List of canonical metric IDs (must start with 'hc_').
                    Obtain these from `resolve_metric` first.
    """
    return _fetch_domain(metric_ids, domain_prefix="hc_", domain_name="healthcare")


@mcp.tool()
def fetch_bfsi(metric_ids: list[str]) -> dict[str, Any]:
    """
    Fetch Banking, Financial Services & Insurance (BFSI) metric values (CAR, NIM, NPL ratio, VaR, etc.).

    Args:
        metric_ids: List of canonical metric IDs (must start with 'bfsi_').
                    Obtain these from `resolve_metric` first.
    """
    return _fetch_domain(metric_ids, domain_prefix="bfsi_", domain_name="bfsi")


@mcp.tool()
def fetch_retail(metric_ids: list[str]) -> dict[str, Any]:
    """
    Fetch Retail & E-Commerce metric values (CAC, ROAS, AOV, cart abandonment, GMV, return rate).

    Args:
        metric_ids: List of canonical metric IDs (must start with 'ret_').
                    Obtain these from `resolve_metric` first.
    """
    return _fetch_domain(metric_ids, domain_prefix="ret_", domain_name="retail")


@mcp.tool()
def fetch_logistics(metric_ids: list[str]) -> dict[str, Any]:
    """
    Fetch Supply Chain & Freight Logistics metric values (OTIF delivery, dock-to-stock, freight cost, etc.).

    Args:
        metric_ids: List of canonical metric IDs (must start with 'log_').
                    Obtain these from `resolve_metric` first.
    """
    return _fetch_domain(metric_ids, domain_prefix="log_", domain_name="logistics")


@mcp.tool()
def fetch_saas(metric_ids: list[str]) -> dict[str, Any]:
    """
    Fetch SaaS, Cloud Infrastructure & DevOps metric values (NRR, P99 latency, SLA uptime, cloud cost).

    Args:
        metric_ids: List of canonical metric IDs (must start with 'saas_').
                    Obtain these from `resolve_metric` first.
    """
    return _fetch_domain(metric_ids, domain_prefix="saas_", domain_name="saas")


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
