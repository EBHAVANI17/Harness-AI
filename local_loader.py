"""
local_loader.py — Loads synthetic/real data from local sample_data/ directory.
Drop-in replacement for gcp_loader.py when GCS is not available.

Folder structure expected:
  sample_data/
    finance/     *.csv, *.json, *.parquet
    engineering/ *.csv, *.json
    support/     *.csv, *.json
    ops/         *.csv, *.json
"""
from __future__ import annotations

import json
import warnings
from functools import lru_cache
from pathlib import Path

try:
    import pandas as pd
    _PANDAS = True
except ImportError:
    _PANDAS = False

DATA_ROOT = Path(__file__).parent / "sample_data"

DOMAIN_DIRS: dict[str, str] = {
    "finance":     "finance",
    "engineering": "engineering",
    "support":     "support",
    "ops":         "ops",
    "healthcare":  "healthcare",
    "bfsi":        "bfsi",
    "retail":      "retail",
    "logistics":   "logistics",
    "saas":        "saas",
}


def _read_file(path: Path):
    """Read a single file into a DataFrame or list."""
    ext = path.suffix.lower()
    if ext == ".csv":
        if not _PANDAS:
            raise ImportError("pandas required: pip install pandas")
        return pd.read_csv(path)
    if ext == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if _PANDAS and isinstance(data, list):
            return pd.DataFrame(data)
        return data
    if ext == ".jsonl":
        rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
        return pd.DataFrame(rows) if _PANDAS else rows
    if ext == ".parquet":
        if not _PANDAS:
            raise ImportError("pandas + pyarrow required")
        return pd.read_parquet(path)
    warnings.warn(f"Unsupported format: {path.name} — skipping")
    return None


@lru_cache(maxsize=8)
def load_domain(domain: str):
    """Load all files for a domain and return a merged DataFrame."""
    domain = domain.lower()
    folder_name = DOMAIN_DIRS.get(domain)
    if not folder_name:
        return None

    folder = DATA_ROOT / folder_name
    if not folder.exists():
        return None

    frames = []
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() in (".csv", ".json", ".jsonl", ".parquet"):
            try:
                data = _read_file(f)
                if data is not None:
                    if _PANDAS and not isinstance(data, pd.DataFrame):
                        data = pd.DataFrame(data) if isinstance(data, list) else pd.DataFrame([data])
                    frames.append(data)
            except Exception as exc:
                warnings.warn(f"Could not load {f.name}: {exc}")

    if not frames:
        return None
    if _PANDAS:
        import pandas as _pd
        return _pd.concat(frames, ignore_index=True)
    return frames


def get_columns(domain: str) -> list[str]:
    """Return column names for a domain (for metric resolution)."""
    df = load_domain(domain)
    if df is None:
        return []
    if _PANDAS and hasattr(df, "columns"):
        return list(df.columns)
    return []


def query_domain(domain: str, filters: dict | None = None,
                 date_from: str | None = None,
                 date_to: str | None = None,
                 limit: int = 100) -> list[dict]:
    """Query a domain DataFrame with optional filters and date range."""
    df = load_domain(domain)
    if df is None:
        return []
    if not _PANDAS or not hasattr(df, "iterrows"):
        return df[:limit] if isinstance(df, list) else []

    # Date filtering — try common date column names
    for date_col in ("date", "created_at", "timestamp", "created_date"):
        if date_col in df.columns:
            try:
                import pandas as _pd
                df[date_col] = _pd.to_datetime(df[date_col], errors="coerce")
                if date_from:
                    df = df[df[date_col] >= _pd.to_datetime(date_from)]
                if date_to:
                    df = df[df[date_col] <= _pd.to_datetime(date_to)]
            except Exception:
                pass
            break

    # Key=value filters
    if filters:
        for col, val in filters.items():
            if col in df.columns:
                df = df[df[col].astype(str).str.lower() == str(val).lower()]

    return df.head(limit).fillna("").to_dict(orient="records")
