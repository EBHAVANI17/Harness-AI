"""
gcp_discover.py — CLI tool to discover GCS buckets and auto-sample schemas.

Usage:
    python gcp_discover.py

Loads GOOGLE_APPLICATION_CREDENTIALS and GCP_PROJECT_ID from .env,
then walks all accessible buckets, samples CSV/JSON/Parquet files,
and saves a report to data/gcp_schema_discovery.json.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# Load .env before anything else
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[warn] python-dotenv not installed — reading environment variables directly.")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Check that google-cloud-storage is installed before proceeding
# ---------------------------------------------------------------------------
try:
    from gcp_adapter import GCSAdapter
except ImportError as exc:
    print(f"\n[ERROR] Cannot import gcp_adapter: {exc}")
    print("Make sure you are running from the project directory and dependencies are installed.")
    print("Install with:  pip install google-cloud-storage pandas pyarrow fastavro pyyaml")
    sys.exit(1)

# File formats that support schema sampling
_SAMPLE_EXTENSIONS = {".csv", ".json", ".jsonl", ".parquet"}


def _hr(char: str = "─", width: int = 70) -> str:
    return char * width


def discover() -> dict:
    """Run full bucket/file discovery and return structured report."""
    project_id = os.getenv("GCP_PROJECT_ID", "")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

    print(_hr("═"))
    print("  GCS Schema Discovery")
    print(_hr("═"))
    print(f"  Project ID : {project_id or '(not set — using default from credentials)'}")
    print(f"  Credentials: {creds_path or '(not set — will try Application Default Credentials)'}")
    print(_hr())

    adapter = GCSAdapter(project_id=project_id or None)

    if not adapter.is_available:
        print("\n[ERROR] GCS authentication failed.")
        print("  → Check that GOOGLE_APPLICATION_CREDENTIALS points to a valid Service Account JSON key.")
        print("  → Or run: gcloud auth application-default login")
        return {"error": "Authentication failed", "buckets": []}

    # ------------------------------------------------------------------
    # List buckets
    # ------------------------------------------------------------------
    print("\nFetching bucket list …")
    buckets_result = adapter.list_buckets()

    if isinstance(buckets_result, dict) and "error" in buckets_result:
        print(f"\n[ERROR] {buckets_result['error']}")
        return {"error": buckets_result["error"], "buckets": []}

    buckets: list[dict] = buckets_result  # type: ignore[assignment]
    print(f"  Found {len(buckets)} bucket(s).\n")

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "bucket_count": len(buckets),
        "buckets": [],
    }

    yaml_hints: list[str] = []

    for bucket_info in buckets:
        bucket_name = bucket_info["name"]
        print(_hr())
        print(f"  Bucket: gs://{bucket_name}")
        print(f"          location={bucket_info.get('location')}  "
              f"class={bucket_info.get('storage_class')}")

        # List files
        files_result = adapter.list_files(bucket_name)
        if isinstance(files_result, dict) and "error" in files_result:
            print(f"  [WARN] Could not list files: {files_result['error']}")
            report["buckets"].append({
                "name": bucket_name,
                "error": files_result["error"],
                "files": [],
            })
            continue

        files: list[dict] = files_result  # type: ignore[assignment]
        print(f"  Files found: {len(files)}")

        bucket_entry: dict = {
            "name": bucket_name,
            "location": bucket_info.get("location"),
            "storage_class": bucket_info.get("storage_class"),
            "files": [],
        }

        for file_info in files:
            blob_name: str = file_info["name"]
            size_kb = round((file_info.get("size_bytes") or 0) / 1024, 1)
            suffix = Path(blob_name).suffix.lower()

            file_entry: dict = {
                "path": blob_name,
                "size_kb": size_kb,
                "content_type": file_info.get("content_type"),
            }

            if suffix in _SAMPLE_EXTENSIONS:
                print(f"    Sampling schema: {blob_name}  ({size_kb} KB) …")
                schema = adapter.sample_schema(bucket_name, blob_name, n_rows=5)
                file_entry["schema"] = schema
                if "columns" in schema:
                    print(f"      columns ({len(schema['columns'])}): {schema['columns']}")
                    if schema.get("sample_rows"):
                        print(f"      sample row: {schema['sample_rows'][0]}")
                    # Collect YAML hints
                    yaml_hints.append(
                        f"      # gs://{bucket_name}/{blob_name}\n"
                        f"      # columns: {schema['columns']}\n"
                        f"      - path: {blob_name}"
                    )
                else:
                    print(f"      [WARN] Schema sampling failed: {schema.get('error')}")
            else:
                print(f"    Skipping (unsupported format): {blob_name}")
                file_entry["schema"] = None

            bucket_entry["files"].append(file_entry)

        report["buckets"].append(bucket_entry)

    # ------------------------------------------------------------------
    # Save report
    # ------------------------------------------------------------------
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "gcp_schema_discovery.json"
    output_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("\n" + _hr("═"))
    print(f"  Report saved to: {output_path.resolve()}")
    print(_hr("═"))

    # ------------------------------------------------------------------
    # Print gcp_config.yaml hints
    # ------------------------------------------------------------------
    if yaml_hints:
        print("\n📋  Copy the paths below into gcp_config.yaml:\n")
        for hint in yaml_hints:
            print(hint)
    else:
        print("\n[INFO] No CSV/JSON/Parquet files found to sample.")

    print("\n✅  Next step: edit gcp_config.yaml with the bucket names and file paths above,")
    print("    then run:  python server_gcp.py")
    print()

    return report


if __name__ == "__main__":
    discover()
