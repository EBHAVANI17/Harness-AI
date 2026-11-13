"""
gcp_loader.py — Domain-level data loader backed by GCS via GCSAdapter.

Reads gcp_config.yaml, downloads each domain's files, and merges them into
a single pandas DataFrame per domain.  Results are cached in memory and
invalidated on explicit reload.

Usage:
    from gcp_loader import load_domain

    df = load_domain("finance")   # returns pd.DataFrame or None
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports — degrade gracefully
# ---------------------------------------------------------------------------
try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False
    logger.warning("pyyaml is not installed. Run: pip install pyyaml>=6.0")

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False
    logger.warning("pandas is not installed. Run: pip install pandas>=2.2.0")

try:
    from gcp_adapter import GCSAdapter
    _ADAPTER_AVAILABLE = True
except ImportError as _exc:
    _ADAPTER_AVAILABLE = False
    _ADAPTER_IMPORT_ERROR = str(_exc)

# ---------------------------------------------------------------------------
# Config path
# ---------------------------------------------------------------------------
_CONFIG_PATH = Path(__file__).parent / "gcp_config.yaml"

# ---------------------------------------------------------------------------
# In-memory cache  {domain: pd.DataFrame}
# ---------------------------------------------------------------------------
_CACHE: dict[str, "pd.DataFrame | None"] = {}
_ADAPTER: "GCSAdapter | None" = None


def _get_adapter() -> "GCSAdapter | None":
    """Return (and lazily initialise) the shared GCSAdapter instance."""
    global _ADAPTER
    if _ADAPTER is not None:
        return _ADAPTER
    if not _ADAPTER_AVAILABLE:
        logger.error("GCSAdapter not available: %s", _ADAPTER_IMPORT_ERROR)
        return None
    try:
        project_id = os.getenv("GCP_PROJECT_ID")
        _ADAPTER = GCSAdapter(project_id=project_id)
        if not _ADAPTER.is_available:
            logger.error("GCSAdapter authentication failed.")
            return None
        return _ADAPTER
    except Exception as exc:
        logger.error("Failed to create GCSAdapter: %s", exc)
        return None


def _load_config() -> dict[str, Any]:
    """Load gcp_config.yaml from the project root."""
    if not _YAML_AVAILABLE:
        logger.error("pyyaml is not installed; cannot read gcp_config.yaml.")
        return {}
    if not _CONFIG_PATH.is_file():
        logger.error(
            "gcp_config.yaml not found at %s. "
            "Create it by running: python gcp_discover.py",
            _CONFIG_PATH,
        )
        return {}
    try:
        with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception as exc:
        logger.error("Failed to parse gcp_config.yaml: %s", exc)
        return {}


def _load_single_file(
    adapter: "GCSAdapter",
    bucket_name: str,
    file_path: str,
) -> "pd.DataFrame | None":
    """Download and coerce one GCS file to a DataFrame. Logs and returns None on failure."""
    logger.info("Loading gs://%s/%s …", bucket_name, file_path)
    result = adapter.read_file(bucket_name, file_path)

    # Error dict from adapter
    if isinstance(result, dict) and "error" in result:
        logger.warning(
            "Skipping gs://%s/%s — %s", bucket_name, file_path, result["error"]
        )
        return None

    # Already a DataFrame
    if _PANDAS_AVAILABLE and isinstance(result, pd.DataFrame):
        return result

    # list of dicts → DataFrame
    if _PANDAS_AVAILABLE and isinstance(result, list):
        try:
            return pd.DataFrame(result)
        except Exception as exc:
            logger.warning("Could not convert list to DataFrame for %s: %s", file_path, exc)
            return None

    # Plain dict → single-row DataFrame
    if _PANDAS_AVAILABLE and isinstance(result, dict):
        try:
            return pd.DataFrame([result])
        except Exception as exc:
            logger.warning("Could not convert dict to DataFrame for %s: %s", file_path, exc)
            return None

    logger.warning(
        "Unsupported data type %s returned for gs://%s/%s; skipping.",
        type(result).__name__,
        bucket_name,
        file_path,
    )
    return None


def load_domain(domain: str, reload: bool = False) -> "pd.DataFrame | None":
    """
    Load all configured files for a domain and return a merged DataFrame.

    Args:
        domain: One of "finance", "engineering", "support", "operations".
        reload: If True, bypass the cache and re-download from GCS.

    Returns:
        A pandas DataFrame (possibly empty) or None if loading fails entirely.
    """
    if not _PANDAS_AVAILABLE:
        logger.error("pandas is not installed; cannot load domain data.")
        return None

    if not reload and domain in _CACHE:
        logger.debug("Cache hit for domain '%s'.", domain)
        return _CACHE[domain]

    config = _load_config()
    if not config:
        return None

    domain_cfg = config.get(domain)
    if not domain_cfg:
        logger.warning("Domain '%s' not found in gcp_config.yaml.", domain)
        return None

    bucket_name: str = domain_cfg.get("bucket", "")
    files: list[dict] = domain_cfg.get("files", [])

    if not bucket_name or bucket_name == "your-bucket-name":
        logger.warning(
            "Domain '%s' has a placeholder bucket name. "
            "Edit gcp_config.yaml and set the real bucket.",
            domain,
        )
        _CACHE[domain] = None
        return None

    adapter = _get_adapter()
    if adapter is None:
        _CACHE[domain] = None
        return None

    frames: list["pd.DataFrame"] = []
    for file_entry in files:
        file_path = file_entry.get("path", "")
        if not file_path:
            logger.warning("Empty file path in gcp_config.yaml for domain '%s'; skipping.", domain)
            continue
        df = _load_single_file(adapter, bucket_name, file_path)
        if df is not None:
            frames.append(df)

    if not frames:
        logger.warning("No data loaded for domain '%s'.", domain)
        _CACHE[domain] = None
        return None

    merged = pd.concat(frames, ignore_index=True)
    logger.info(
        "Loaded domain '%s': %d rows × %d columns from %d file(s).",
        domain,
        len(merged),
        len(merged.columns),
        len(frames),
    )
    _CACHE[domain] = merged
    return merged


def invalidate_cache(domain: str | None = None) -> None:
    """
    Clear the in-memory cache.

    Args:
        domain: If given, clear only that domain. If None, clear everything.
    """
    global _CACHE
    if domain:
        _CACHE.pop(domain, None)
        logger.info("Cache cleared for domain '%s'.", domain)
    else:
        _CACHE = {}
        logger.info("Full cache cleared.")


def list_domains() -> list[str]:
    """Return all domain names defined in gcp_config.yaml."""
    config = _load_config()
    return list(config.keys())
