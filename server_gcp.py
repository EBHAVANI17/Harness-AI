"""
server_gcp.py — FastMCP MCP server backed by real GCP Cloud Storage data.

Identical interface to server.py so the eval framework works unchanged.
Falls back to fixture data if GCS auth is unavailable.

Run with:
    python server_gcp.py          (starts on http://localhost:8000)
"""

from __future__ import annotations

import logging
import os
import re
import warnings
from datetime import date
from typing import Any

from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Load .env early
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try to import GCP modules; degrade to fixture mode on failure
# ---------------------------------------------------------------------------
_GCP_MODE = False
_GCP_WARN: str = ""

try:
    from gcp_adapter import GCSAdapter
    from gcp_loader import load_domain, list_domains

    try:
        import pandas as pd
        _PANDAS_AVAILABLE = True
    except ImportError:
        _PANDAS_AVAILABLE = False
        warnings.warn("pandas not installed — GCP numeric queries may be limited.", stacklevel=1)

    _adapter = GCSAdapter(project_id=os.getenv("GCP_PROJECT_ID"))
    if _adapter.is_available:
        _GCP_MODE = True
        logger.info("server_gcp: GCS authentication successful — using REAL data.")
    else:
        _GCP_WARN = (
            "GCS authentication failed. "
            "Set GOOGLE_APPLICATION_CREDENTIALS and GCP_PROJECT_ID in .env. "
            "Falling back to fixture data."
        )
        logger.warning("server_gcp: %s", _GCP_WARN)
except ImportError as _exc:
    _GCP_WARN = (
        f"GCP dependencies not installed ({_exc}). "
        "Install with: pip install google-cloud-storage pandas pyarrow fastavro pyyaml. "
        "Falling back to fixture data."
    )
    logger.warning("server_gcp: %s", _GCP_WARN)

# ---------------------------------------------------------------------------
# Fixture catalog + values (copied from server.py as fallback)
# ---------------------------------------------------------------------------
METRIC_CATALOG: list[dict[str, Any]] = [
    # ── Finance ──────────────────────────────────────────────────────────────
    {"metric_id": "fin_arr", "title": "Annual Recurring Revenue (ARR)", "domain": "finance",
     "aliases": ["arr", "annual recurring revenue", "annual revenue"],
     "description": "Total annualised value of recurring subscription contracts."},
    {"metric_id": "fin_mrr", "title": "Monthly Recurring Revenue (MRR)", "domain": "finance",
     "aliases": ["mrr", "monthly recurring revenue", "monthly revenue"],
     "description": "Total monthly value of recurring subscription contracts."},
    {"metric_id": "fin_cogs", "title": "Cost of Goods Sold (COGS)", "domain": "finance",
     "aliases": ["cogs", "cost of goods sold", "cost of revenue"],
     "description": "Direct costs attributable to production of goods/services sold."},
    {"metric_id": "fin_opex", "title": "Operating Expenses (OpEx)", "domain": "finance",
     "aliases": ["opex", "operating expenses", "operating costs"],
     "description": "Ongoing costs for running the business (excl. COGS)."},
    {"metric_id": "fin_gross_margin", "title": "Gross Margin %", "domain": "finance",
     "aliases": ["gross margin", "gm", "gross profit margin"],
     "description": "Revenue minus COGS, expressed as a percentage of revenue."},
    {"metric_id": "fin_budget_variance", "title": "Budget Variance", "domain": "finance",
     "aliases": ["budget variance", "variance to budget", "budget vs actuals"],
     "description": "Difference between budgeted and actual spend."},
    # ── Engineering / Product ─────────────────────────────────────────────────
    {"metric_id": "eng_deploy_freq", "title": "Deployment Frequency", "domain": "engineering",
     "aliases": ["deploy frequency", "deployment frequency", "releases per week"],
     "description": "Number of production deployments per week."},
    {"metric_id": "eng_bug_count", "title": "Open Bug Count", "domain": "engineering",
     "aliases": ["bugs", "bug count", "open bugs", "defects"],
     "description": "Number of open bug / defect tickets."},
    {"metric_id": "eng_ticket_cycle", "title": "Ticket Cycle Time (days)", "domain": "engineering",
     "aliases": ["cycle time", "ticket cycle time", "lead time"],
     "description": "Average time from ticket creation to resolution."},
    {"metric_id": "eng_p1_incidents", "title": "P1 Incidents (MTD)", "domain": "engineering",
     "aliases": ["p1 incidents", "critical incidents", "sev1"],
     "description": "Month-to-date count of severity-1 production incidents."},
    # ── Customer Support ─────────────────────────────────────────────────────
    {"metric_id": "sup_sla_compliance", "title": "SLA Compliance Rate", "domain": "support",
     "aliases": ["sla compliance", "sla rate", "sla adherence"],
     "description": "Percentage of support tickets resolved within SLA."},
    {"metric_id": "sup_csat", "title": "Customer Satisfaction (CSAT)", "domain": "support",
     "aliases": ["csat", "customer satisfaction", "satisfaction score"],
     "description": "Average customer satisfaction score (1–5 scale)."},
    {"metric_id": "sup_ticket_volume", "title": "Support Ticket Volume", "domain": "support",
     "aliases": ["ticket volume", "support tickets", "inbound tickets"],
     "description": "Total number of inbound support tickets in the period."},
    {"metric_id": "sup_sentiment", "title": "Support Sentiment Score", "domain": "support",
     "aliases": ["sentiment", "support sentiment", "nps proxy"],
     "description": "ML-derived sentiment score across customer messages (−1 to +1)."},
    # ── Operations / Supply Chain ─────────────────────────────────────────────
    {"metric_id": "ops_inventory_turns", "title": "Inventory Turns", "domain": "ops",
     "aliases": ["inventory turns", "inventory turnover", "stock turns"],
     "description": "Number of times inventory is sold/used per period."},
    {"metric_id": "ops_supplier_lead_time", "title": "Supplier Lead Time (days)", "domain": "ops",
     "aliases": ["lead time", "supplier lead time", "procurement lead time"],
     "description": "Average days from purchase order to delivery."},
    {"metric_id": "ops_on_time_delivery", "title": "On-Time Delivery Rate", "domain": "ops",
     "aliases": ["on time delivery", "otd", "delivery rate"],
     "description": "Percentage of orders delivered on or before the promised date."},
]

FIXTURE_VALUES: dict[str, Any] = {
    "fin_arr":              {"value": 12_400_000, "unit": "USD",          "period": "2024-Q4"},
    "fin_mrr":              {"value": 1_033_333,  "unit": "USD",          "period": "2024-12"},
    "fin_cogs":             {"value": 3_720_000,  "unit": "USD",          "period": "2024-Q4"},
    "fin_opex":             {"value": 5_100_000,  "unit": "USD",          "period": "2024-Q4"},
    "fin_gross_margin":     {"value": 70.0,        "unit": "%",            "period": "2024-Q4"},
    "fin_budget_variance":  {"value": -142_000,   "unit": "USD",          "period": "2024-Q4",
                             "note": "Negative = under budget"},
    "eng_deploy_freq":      {"value": 8.3,         "unit": "deploys/week", "period": "2024-Q4"},
    "eng_bug_count":        {"value": 134,         "unit": "tickets",      "as_of": "2025-01-10"},
    "eng_ticket_cycle":     {"value": 4.7,         "unit": "days",         "period": "2024-Q4"},
    "eng_p1_incidents":     {"value": 2,           "unit": "incidents",    "period": "2024-12"},
    "sup_sla_compliance":   {"value": 91.4,        "unit": "%",            "period": "2024-Q4"},
    "sup_csat":             {"value": 4.2,         "unit": "/5",           "period": "2024-Q4"},
    "sup_ticket_volume":    {"value": 3_817,       "unit": "tickets",      "period": "2024-Q4"},
    "sup_sentiment":        {"value": 0.42,        "unit": "score",        "period": "2024-Q4"},
    "ops_inventory_turns":  {"value": 6.1,         "unit": "turns/year",   "period": "2024-Q4"},
    "ops_supplier_lead_time": {"value": 12.3,      "unit": "days",         "period": "2024-Q4"},
    "ops_on_time_delivery": {"value": 94.7,        "unit": "%",            "period": "2024-Q4"},
}

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

INSTRUCTIONS = """
You are a business-intelligence assistant connected to a company data catalog.

**Data source**: """ + ("REAL GCP Cloud Storage data" if _GCP_MODE else "FIXTURE data (GCP not connected)") + """

**Workflow (always follow these steps in order)**
1. Call `resolve_metric` with the user's indicator(s) to look up canonical metric IDs.
2. Examine the returned candidates.  If a metric's confidence is < 0.6, warn the user
   that the metric may not be in the catalog before fetching.
3. If multiple candidates are returned for one indicator (a *tie*), ask the user to
   clarify before fetching — do NOT guess.
4. Call the appropriate domain fetch tool (`fetch_finance`, `fetch_engineering`,
   `fetch_support`, `fetch_ops`) using the resolved metric IDs.
5. If a query spans multiple domains (e.g. "SLA compliance by product team") call
   EACH relevant fetch tool and combine the results.
6. Never fabricate metric values.  If a metric is absent from the catalog, say so.

**Tool selection guide**
| Domain          | Fetch tool           | Example metrics                     |
|-----------------|----------------------|-------------------------------------|
| Finance         | fetch_finance        | ARR, MRR, COGS, OpEx, gross_margin  |
| Engineering     | fetch_engineering    | deploy_freq, bug_count, ticket_cycle|
| Customer Support| fetch_support        | sla_compliance, csat, ticket_volume |
| Operations      | fetch_ops            | inventory_turns, supplier_lead_time |

**Ambiguity rules**
- "revenue"  → clarify ARR vs MRR (both confidence 0.75)
- "cost"     → clarify COGS vs OpEx (both confidence 0.85)
- Anything outside the catalog → respond with a coverage-gap explanation.
"""

mcp = FastMCP(
    name="company-data-plugin-gcp",
    instructions=INSTRUCTIONS,
)

# ---------------------------------------------------------------------------
# Dynamic metric catalog from GCS (augments the static catalog)
# ---------------------------------------------------------------------------

def _build_dynamic_catalog() -> list[dict[str, Any]]:
    """
    Scan loaded DataFrames to infer additional metric candidates from column names.
    Returns supplementary entries in METRIC_CATALOG format.
    """
    if not _GCP_MODE or not _PANDAS_AVAILABLE:
        return []

    domain_map = {
        "finance":     ("fin", "finance"),
        "engineering": ("eng", "engineering"),
        "support":     ("sup", "support"),
        "operations":  ("ops", "ops"),
    }
    extra: list[dict[str, Any]] = []
    seen_ids: set[str] = {m["metric_id"] for m in METRIC_CATALOG}

    for domain_name, (prefix, domain_key) in domain_map.items():
        try:
            df = load_domain(domain_name)
        except Exception:
            continue
        if df is None:
            continue
        for col in df.columns:
            safe_col = re.sub(r"[^a-z0-9_]", "_", col.lower())
            metric_id = f"{prefix}_{safe_col}"
            if metric_id in seen_ids:
                continue
            seen_ids.add(metric_id)
            # Build human-readable title from column name
            title = col.replace("_", " ").title()
            extra.append({
                "metric_id": metric_id,
                "title": title,
                "domain": domain_key,
                "aliases": [col.lower(), safe_col, title.lower()],
                "description": f"Column '{col}' from GCS domain '{domain_name}'.",
                "source": "gcs_dynamic",
            })

    if extra:
        logger.info(
            "Dynamic catalog: added %d metric(s) from GCS column names.", len(extra)
        )
    return extra


_DYNAMIC_CATALOG: list[dict[str, Any]] = _build_dynamic_catalog()
_FULL_CATALOG: list[dict[str, Any]] = METRIC_CATALOG + _DYNAMIC_CATALOG

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenise(text: str) -> set[str]:
    _STOP = {
        "the", "a", "an", "of", "in", "by", "for", "and", "or", "to",
        "at", "is", "are", "was", "were", "per",
        "stock", "price", "rate", "count", "total", "average", "avg",
        "number", "time", "cost",
    }
    tokens = set(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())
    return tokens - _STOP


def _score(indicator: str, metric: dict[str, Any]) -> float:
    ind_lower = indicator.strip().lower()
    for alias in metric["aliases"]:
        if ind_lower == alias.lower():
            return 0.95
    for alias in metric["aliases"]:
        if ind_lower in alias.lower() or alias.lower() in ind_lower:
            return 0.78
    ind_tokens = _tokenise(ind_lower)
    if len(ind_tokens) < 2:
        return 0.0
    alias_tokens: set[str] = set()
    for alias in metric["aliases"]:
        alias_tokens |= _tokenise(alias)
    alias_tokens |= _tokenise(metric["title"].lower())
    overlap = len(ind_tokens & alias_tokens)
    if overlap == 0:
        return 0.0
    fraction = overlap / len(ind_tokens)
    if fraction < 0.5:
        return 0.0
    return min(0.60 + 0.08 * overlap, 0.74)


def _apply_date_filter(
    df: "pd.DataFrame",
    date_col: str,
    date_from: str | None,
    date_to: str | None,
) -> "pd.DataFrame":
    """Filter df by date range if date_from / date_to are provided."""
    if not _PANDAS_AVAILABLE or df is None:
        return df
    if date_col not in df.columns:
        return df
    try:
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        if date_from:
            df = df[df[date_col] >= pd.Timestamp(date_from)]
        if date_to:
            df = df[df[date_col] <= pd.Timestamp(date_to)]
    except Exception as exc:
        logger.warning("Date filter failed on column '%s': %s", date_col, exc)
    return df


def _gcs_fetch_domain(
    metric_ids: list[str],
    domain_name: str,
    domain_prefix: str,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Attempt to fetch metrics from GCS DataFrames.
    Falls back to fixtures per metric if GCS data is unavailable.
    """
    data: dict[str, Any] = {}
    missing: list[str] = []
    wrong_domain: list[str] = []
    gcs_warnings: list[str] = []

    if _GCP_WARN:
        gcs_warnings.append(_GCP_WARN)

    for mid in metric_ids:
        if not mid.startswith(domain_prefix):
            wrong_domain.append(mid)
            continue

        # --- Try GCS first ---
        gcs_value = None
        if _GCP_MODE and _PANDAS_AVAILABLE:
            try:
                df = load_domain(domain_name)
                if df is not None and not df.empty:
                    # Detect date column heuristically
                    date_col = next(
                        (c for c in df.columns if "date" in c.lower() or "time" in c.lower()),
                        None,
                    )
                    if date_col:
                        df = _apply_date_filter(df, date_col, date_from, date_to)

                    # Try to find a column matching the metric suffix
                    metric_suffix = mid[len(domain_prefix):]
                    candidate_cols = [
                        c for c in df.columns
                        if metric_suffix in c.lower() or c.lower() in metric_suffix
                    ]
                    if candidate_cols:
                        col = candidate_cols[0]
                        limited = df[col].dropna().head(limit)
                        gcs_value = {
                            "values": limited.tolist(),
                            "column": col,
                            "row_count": len(limited),
                            "source": "gcs",
                        }
                        if date_col and date_col in df.columns:
                            dates = df[date_col].dropna().head(limit).astype(str).tolist()
                            gcs_value["dates"] = dates
            except Exception as exc:
                gcs_warnings.append(f"GCS read error for '{mid}': {exc}")

        if gcs_value is not None:
            data[mid] = gcs_value
        elif mid in FIXTURE_VALUES:
            fixture = dict(FIXTURE_VALUES[mid])
            fixture["source"] = "fixture"
            if _GCP_MODE:
                fixture["note"] = (
                    f"GCS data loaded but column for '{mid}' not found; using fixture."
                )
            data[mid] = fixture
        else:
            missing.append(mid)

    result: dict[str, Any] = {"data": data, "missing": missing}
    if wrong_domain:
        result["wrong_domain"] = wrong_domain
        result["hint"] = (
            f"The following IDs do not belong to the '{domain_name}' domain "
            f"and were skipped: {wrong_domain}.  Use the correct fetch tool."
        )
    if gcs_warnings:
        result["gcs_warnings"] = gcs_warnings
    if date_from or date_to:
        result["date_filter"] = {"from": date_from, "to": date_to}
    return result


# ---------------------------------------------------------------------------
# Tool: resolve_metric
# ---------------------------------------------------------------------------

@mcp.tool()
def resolve_metric(indicators: list[str]) -> dict[str, Any]:
    """
    Resolve one or more business indicators to canonical metric IDs.

    Scans both the static catalog and dynamically discovered GCS column names.

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
              "note": str
            }
          ],
          "data_source": "gcs" | "fixture"
        }
    """
    results: list[dict[str, Any]] = []

    for indicator in indicators:
        scored: list[tuple[float, dict[str, Any]]] = []
        for metric in _FULL_CATALOG:
            score = _score(indicator, metric)
            if score > 0:
                scored.append((score, metric))

        scored.sort(key=lambda x: x[0], reverse=True)

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

        results.append({"indicator": indicator, "candidates": candidates, "note": note})

    return {
        "results": results,
        "data_source": "gcs" if _GCP_MODE else "fixture",
    }


# ---------------------------------------------------------------------------
# Tool: fetch_finance
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_finance(
    metric_ids: list[str],
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Fetch Finance / Accounting metric values from GCS (or fixtures as fallback).

    Args:
        metric_ids: List of canonical metric IDs (must start with 'fin_').
                    Obtain these from `resolve_metric` first.
        date_from:  Optional ISO-8601 date string to filter data from (e.g. "2024-01-01").
        date_to:    Optional ISO-8601 date string to filter data until (e.g. "2024-12-31").
        limit:      Maximum number of rows to return per metric (default 100).

    Returns:
        {"data": {metric_id: value_object, ...}, "missing": [...], "data_source": str}
    """
    return _gcs_fetch_domain(metric_ids, "finance", "fin_", date_from, date_to, limit)


# ---------------------------------------------------------------------------
# Tool: fetch_engineering
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_engineering(
    metric_ids: list[str],
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Fetch Engineering / Product metric values from GCS (or fixtures as fallback).

    Args:
        metric_ids: List of canonical metric IDs (must start with 'eng_').
                    Obtain these from `resolve_metric` first.
        date_from:  Optional ISO-8601 date string to filter data from.
        date_to:    Optional ISO-8601 date string to filter data until.
        limit:      Maximum number of rows to return per metric (default 100).

    Returns:
        {"data": {metric_id: value_object, ...}, "missing": [...], "data_source": str}
    """
    return _gcs_fetch_domain(metric_ids, "engineering", "eng_", date_from, date_to, limit)


# ---------------------------------------------------------------------------
# Tool: fetch_support
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_support(
    metric_ids: list[str],
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Fetch Customer Support metric values from GCS (or fixtures as fallback).

    Args:
        metric_ids: List of canonical metric IDs (must start with 'sup_').
                    Obtain these from `resolve_metric` first.
        date_from:  Optional ISO-8601 date string to filter data from.
        date_to:    Optional ISO-8601 date string to filter data until.
        limit:      Maximum number of rows to return per metric (default 100).

    Returns:
        {"data": {metric_id: value_object, ...}, "missing": [...], "data_source": str}
    """
    return _gcs_fetch_domain(metric_ids, "support", "sup_", date_from, date_to, limit)


# ---------------------------------------------------------------------------
# Tool: fetch_ops
# ---------------------------------------------------------------------------

@mcp.tool()
def fetch_ops(
    metric_ids: list[str],
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Fetch Operations / Supply-Chain metric values from GCS (or fixtures as fallback).

    Args:
        metric_ids: List of canonical metric IDs (must start with 'ops_').
                    Obtain these from `resolve_metric` first.
        date_from:  Optional ISO-8601 date string to filter data from.
        date_to:    Optional ISO-8601 date string to filter data until.
        limit:      Maximum number of rows to return per metric (default 100).

    Returns:
        {"data": {metric_id: value_object, ...}, "missing": [...], "data_source": str}
    """
    return _gcs_fetch_domain(metric_ids, "ops", "ops_", date_from, date_to, limit)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8000"))
    if _GCP_MODE:
        print(f"[server_gcp] ✅  GCS connected — serving REAL data on http://0.0.0.0:{port}")
    else:
        print(f"[server_gcp] ⚠️   GCS unavailable — serving FIXTURE data on http://0.0.0.0:{port}")
        if _GCP_WARN:
            print(f"[server_gcp]     Reason: {_GCP_WARN}")
        print("[server_gcp]     See GCP_SETUP.md to configure authentication.")
    mcp.run(transport="http", host="0.0.0.0", port=port)
