"""
gcp_adapter.py — Unified Google Cloud Storage data adapter.

Authenticates via Service Account JSON key (GOOGLE_APPLICATION_CREDENTIALS env var)
or falls back to Application Default Credentials.

Usage:
    from gcp_adapter import GCSAdapter
    adapter = GCSAdapter()
    df = adapter.read_file("my-bucket", "data/revenue.csv")
"""

from __future__ import annotations

import io
import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional heavy imports — give a helpful message if not installed
# ---------------------------------------------------------------------------

try:
    from google.cloud import storage as gcs
    from google.oauth2 import service_account
    from google.auth import default as google_auth_default
    from google.api_core.exceptions import GoogleAPIError, Forbidden, NotFound
    _GCS_AVAILABLE = True
except ImportError:
    _GCS_AVAILABLE = False
    _GCS_IMPORT_MSG = (
        "google-cloud-storage is not installed. "
        "Run: pip install google-cloud-storage>=2.18.0\n"
        "Or install all GCP deps: pip install google-cloud-storage pandas pyarrow fastavro pyyaml"
    )

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False

try:
    import pyarrow.parquet as pq
    _PYARROW_AVAILABLE = True
except ImportError:
    _PYARROW_AVAILABLE = False

try:
    import fastavro
    _FASTAVRO_AVAILABLE = True
except ImportError:
    _FASTAVRO_AVAILABLE = False


# ---------------------------------------------------------------------------
# GCSAdapter
# ---------------------------------------------------------------------------

class GCSAdapter:
    """
    Unified adapter for reading data from Google Cloud Storage.

    Authentication priority:
      1. Service Account JSON key pointed to by GOOGLE_APPLICATION_CREDENTIALS
      2. Application Default Credentials (gcloud auth application-default login)
    """

    def __init__(self, project_id: str | None = None) -> None:
        if not _GCS_AVAILABLE:
            raise ImportError(_GCS_IMPORT_MSG)

        self.project_id: str | None = project_id or os.getenv("GCP_PROJECT_ID")
        self._client: gcs.Client | None = None
        self._auth_error: str | None = None
        self._init_client()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        """Initialise the GCS client, trying SA key first then ADC."""
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        try:
            if creds_path and Path(creds_path).is_file():
                credentials = service_account.Credentials.from_service_account_file(
                    creds_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
                self._client = gcs.Client(
                    credentials=credentials,
                    project=self.project_id,
                )
                logger.info("GCSAdapter: authenticated via Service Account key: %s", creds_path)
            else:
                # Fall back to Application Default Credentials
                credentials, detected_project = google_auth_default(
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
                self._client = gcs.Client(
                    credentials=credentials,
                    project=self.project_id or detected_project,
                )
                logger.info("GCSAdapter: authenticated via Application Default Credentials.")
        except Exception as exc:
            self._auth_error = str(exc)
            logger.error("GCSAdapter: authentication failed — %s", exc)

    @property
    def is_available(self) -> bool:
        """True when the client was initialised successfully."""
        return self._client is not None and self._auth_error is None

    def _auth_failure_response(self) -> dict[str, Any]:
        return {
            "error": f"GCS authentication failed: {self._auth_error}",
            "available": False,
            "hint": (
                "Set GOOGLE_APPLICATION_CREDENTIALS to the path of your Service Account JSON key, "
                "or run `gcloud auth application-default login`."
            ),
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_buckets(self) -> list[dict[str, Any]] | dict[str, Any]:
        """
        List all GCS buckets accessible to the authenticated account.

        Returns:
            List of dicts with keys: name, location, storage_class, created.
            Or an error dict if auth failed.
        """
        if not self.is_available:
            return self._auth_failure_response()
        try:
            buckets = []
            for bucket in self._client.list_buckets():  # type: ignore[union-attr]
                buckets.append({
                    "name": bucket.name,
                    "location": getattr(bucket, "location", None),
                    "storage_class": getattr(bucket, "storage_class", None),
                    "created": str(getattr(bucket, "time_created", None)),
                })
            return buckets
        except Forbidden as exc:
            return {"error": f"403 Forbidden listing buckets: {exc}", "available": False}
        except GoogleAPIError as exc:
            return {"error": f"GCS API error: {exc}", "available": False}

    def list_files(
        self, bucket_name: str, prefix: str = ""
    ) -> list[dict[str, Any]] | dict[str, Any]:
        """
        List files in a bucket with metadata.

        Args:
            bucket_name: Name of the GCS bucket.
            prefix:      Optional path prefix to filter results.

        Returns:
            List of dicts with keys: name, size_bytes, content_type, updated.
            Or an error dict on failure.
        """
        if not self.is_available:
            return self._auth_failure_response()
        try:
            bucket = self._client.bucket(bucket_name)  # type: ignore[union-attr]
            blobs = self._client.list_blobs(bucket, prefix=prefix)  # type: ignore[union-attr]
            files = []
            for blob in blobs:
                files.append({
                    "name": blob.name,
                    "size_bytes": blob.size,
                    "content_type": blob.content_type,
                    "updated": str(blob.updated),
                })
            return files
        except NotFound:
            return {"error": f"Bucket '{bucket_name}' not found.", "available": False}
        except Forbidden as exc:
            return {"error": f"403 Forbidden on bucket '{bucket_name}': {exc}", "available": False}
        except GoogleAPIError as exc:
            return {"error": f"GCS API error: {exc}", "available": False}

    def read_file(
        self, bucket_name: str, blob_name: str
    ) -> "pd.DataFrame | dict | list | bytes | dict[str, Any]":
        """
        Download and parse a GCS file into an appropriate Python object.

        Auto-detected formats:
          .csv       → pandas DataFrame
          .json      → dict or list of dicts
          .jsonl     → list of dicts
          .parquet   → pandas DataFrame
          .avro      → list of dicts  (requires fastavro)
          other      → raw bytes (with a warning logged)

        Returns:
            Parsed data or an error dict.
        """
        if not self.is_available:
            return self._auth_failure_response()
        try:
            bucket = self._client.bucket(bucket_name)  # type: ignore[union-attr]
            blob = bucket.blob(blob_name)
            raw: bytes = blob.download_as_bytes()
        except NotFound:
            return {
                "error": f"File '{blob_name}' not found in bucket '{bucket_name}'.",
                "available": False,
            }
        except Forbidden as exc:
            return {"error": f"403 Forbidden reading '{blob_name}': {exc}", "available": False}
        except GoogleAPIError as exc:
            return {"error": f"GCS API error reading '{blob_name}': {exc}", "available": False}

        suffix = Path(blob_name).suffix.lower()
        return self._parse_bytes(raw, suffix, blob_name)

    def sample_schema(
        self, bucket_name: str, blob_name: str, n_rows: int = 5
    ) -> dict[str, Any]:
        """
        Return column names and sample rows for schema discovery.

        Args:
            bucket_name: GCS bucket name.
            blob_name:   Path to the file within the bucket.
            n_rows:      Number of sample rows to return (default 5).

        Returns:
            {
              "columns": [...],
              "sample_rows": [...],   # list of row dicts
              "row_count_approx": int | None,
              "format": str,
            }
            Or an error dict.
        """
        data = self.read_file(bucket_name, blob_name)

        if isinstance(data, dict) and not data.get("available", True) is False:
            # It could be a plain JSON object (not an error); check for error key
            pass
        if isinstance(data, dict) and "error" in data and data.get("available") is False:
            return data  # propagate error

        suffix = Path(blob_name).suffix.lower()

        if _PANDAS_AVAILABLE and isinstance(data, "pd.DataFrame" if False else type(None)):
            pass  # handled below

        try:
            if _PANDAS_AVAILABLE and hasattr(data, "columns"):
                # pandas DataFrame
                df: "pd.DataFrame" = data  # type: ignore[assignment]
                sample = df.head(n_rows).to_dict(orient="records")
                return {
                    "columns": list(df.columns),
                    "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
                    "sample_rows": sample,
                    "row_count_approx": len(df),
                    "format": suffix.lstrip(".") or "unknown",
                }
            elif isinstance(data, list):
                sample = data[:n_rows]
                columns = list(sample[0].keys()) if sample and isinstance(sample[0], dict) else []
                return {
                    "columns": columns,
                    "sample_rows": sample,
                    "row_count_approx": len(data),
                    "format": suffix.lstrip(".") or "unknown",
                }
            elif isinstance(data, dict):
                return {
                    "columns": list(data.keys()),
                    "sample_rows": [data],
                    "row_count_approx": 1,
                    "format": suffix.lstrip(".") or "unknown",
                }
            else:
                return {
                    "columns": [],
                    "sample_rows": [],
                    "row_count_approx": None,
                    "format": suffix.lstrip(".") or "binary",
                    "note": "Binary or unsupported format; schema not available.",
                }
        except Exception as exc:
            return {"error": f"Schema sampling failed: {exc}", "available": False}

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    def _parse_bytes(
        self, raw: bytes, suffix: str, blob_name: str
    ) -> "pd.DataFrame | dict | list | bytes":
        """Dispatch raw bytes to the appropriate parser based on file extension."""
        if suffix == ".csv":
            return self._parse_csv(raw, blob_name)
        elif suffix in (".json",):
            return self._parse_json(raw, blob_name)
        elif suffix == ".jsonl":
            return self._parse_jsonl(raw, blob_name)
        elif suffix == ".parquet":
            return self._parse_parquet(raw, blob_name)
        elif suffix == ".avro":
            return self._parse_avro(raw, blob_name)
        else:
            warnings.warn(
                f"GCSAdapter: unsupported extension '{suffix}' for '{blob_name}'. "
                "Returning raw bytes.",
                stacklevel=3,
            )
            return raw

    def _parse_csv(self, raw: bytes, blob_name: str) -> "pd.DataFrame | dict[str, Any]":
        if not _PANDAS_AVAILABLE:
            return {"error": "pandas is not installed. Run: pip install pandas>=2.2.0", "available": False}
        try:
            return pd.read_csv(io.BytesIO(raw), encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return pd.read_csv(io.BytesIO(raw), encoding="latin-1")
            except Exception as exc:
                return {"error": f"CSV parse error for '{blob_name}': {exc}", "available": False}
        except Exception as exc:
            return {"error": f"CSV parse error for '{blob_name}': {exc}", "available": False}

    def _parse_json(self, raw: bytes, blob_name: str) -> "dict | list | dict[str, Any]":
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            return {"error": f"JSON parse error for '{blob_name}': {exc}", "available": False}

    def _parse_jsonl(self, raw: bytes, blob_name: str) -> "list | dict[str, Any]":
        try:
            lines = raw.decode("utf-8").splitlines()
            return [json.loads(line) for line in lines if line.strip()]
        except Exception as exc:
            return {"error": f"JSONL parse error for '{blob_name}': {exc}", "available": False}

    def _parse_parquet(self, raw: bytes, blob_name: str) -> "pd.DataFrame | dict[str, Any]":
        if not _PANDAS_AVAILABLE:
            return {"error": "pandas is not installed. Run: pip install pandas>=2.2.0", "available": False}
        if not _PYARROW_AVAILABLE:
            return {"error": "pyarrow is not installed. Run: pip install pyarrow>=16.0.0", "available": False}
        try:
            return pd.read_parquet(io.BytesIO(raw))
        except Exception as exc:
            return {"error": f"Parquet parse error for '{blob_name}': {exc}", "available": False}

    def _parse_avro(self, raw: bytes, blob_name: str) -> "list | dict[str, Any]":
        if not _FASTAVRO_AVAILABLE:
            return {"error": "fastavro is not installed. Run: pip install fastavro>=1.9.0", "available": False}
        try:
            reader = fastavro.reader(io.BytesIO(raw))
            return [record for record in reader]
        except Exception as exc:
            return {"error": f"Avro parse error for '{blob_name}': {exc}", "available": False}
