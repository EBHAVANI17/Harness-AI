# GCP Setup Guide for Harness-Aware Eval Framework

> **GCP Project:** `190019735002`
> **Time required:** ~15 minutes

---

## Step 1 — Install the gcloud CLI (Windows)

1. Download the installer from:  
   👉 https://cloud.google.com/sdk/docs/install-sdk#windows

2. Run the `.exe` installer and follow the prompts (keep all defaults).

3. Open a **new** PowerShell window and verify:
   ```powershell
   gcloud --version
   ```

4. Initialise and log in:
   ```powershell
   gcloud init
   ```
   - Choose **"Log in with a new account"** when prompted.
   - Select project **`190019735002`** (or enter it manually).

---

## Step 2 — Create a Service Account

A service account is a machine identity the eval framework uses to access GCS.  
Run these commands in PowerShell:

```powershell
# Create the service account
gcloud iam service-accounts create harness-eval `
  --display-name="Harness Eval Framework" `
  --project=190019735002

# Confirm it was created
gcloud iam service-accounts list --project=190019735002
```

---

## Step 3 — Grant Storage Read Permission

```powershell
gcloud projects add-iam-policy-binding 190019735002 `
  --member="serviceAccount:harness-eval@190019735002.iam.gserviceaccount.com" `
  --role="roles/storage.objectViewer"
```

> [!NOTE]
> `roles/storage.objectViewer` allows the framework to **read** GCS objects.
> It cannot delete, write, or modify anything.

---

## Step 4 — Download the Key File

```powershell
gcloud iam service-accounts keys create `
  "c:\Users\Bhavani\OneDrive\Documents\Harness AI\harness-eval-key.json" `
  --iam-account=harness-eval@190019735002.iam.gserviceaccount.com
```

> [!CAUTION]
> **Never commit `harness-eval-key.json` to git.**
> Add it to `.gitignore` immediately:
> ```
> harness-eval-key.json
> ```

---

## Step 5 — Add Credentials to .env

Open `c:\Users\Bhavani\OneDrive\Documents\Harness AI\.env` and add:

```env
GOOGLE_APPLICATION_CREDENTIALS=c:\Users\Bhavani\OneDrive\Documents\Harness AI\harness-eval-key.json
GCP_PROJECT_ID=190019735002
```

---

## Step 6 — Install Python Dependencies

```powershell
cd "c:\Users\Bhavani\OneDrive\Documents\Harness AI"

# Install uv first (if not already installed)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Then install project dependencies
uv sync
```

---

## Step 7 — Discover Your GCS Buckets and Files

This script connects to GCP, lists all your buckets, and auto-samples the schema
of every CSV / JSON / Parquet file it finds:

```powershell
python gcp_discover.py
```

It prints a report like:

```
✅ Connected to project 190019735002
📦 Buckets found: 3

  my-finance-bucket/
    finance/revenue.csv       → columns: date, metric, value, currency  (1,204 rows)
    finance/costs.parquet     → columns: date, category, amount          (892 rows)

  my-eng-bucket/
    eng/deployments.json      → keys: deploy_id, service, status, ts
    eng/bugs.csv              → columns: id, severity, team, created_at  (3,441 rows)
```

It also saves the full schema to `data/gcp_schema_discovery.json`.

---

## Step 8 — Map Your Buckets in gcp_config.yaml

Edit `gcp_config.yaml` using the bucket names and file paths from the discovery output:

```yaml
finance:
  bucket: my-finance-bucket       # ← replace with your actual bucket name
  files:
    - path: finance/revenue.csv
    - path: finance/costs.parquet

engineering:
  bucket: my-eng-bucket
  files:
    - path: eng/deployments.json
    - path: eng/bugs.csv

support:
  bucket: my-support-bucket
  files:
    - path: support/tickets.csv

operations:
  bucket: my-ops-bucket
  files:
    - path: ops/supply_chain.csv
```

---

## Step 9 — Run the Eval Framework with Real Data

```powershell
# Terminal 1 — Start the GCP-backed MCP server
python server_gcp.py

# Terminal 2 — Run evaluations
python level_one.py    # Level 1: deterministic (free, ~1 second)
# (requires Gemini API key in .env)
npx promptfoo eval -c promptfooconfig.yaml --no-cache    # Level 2: Gemini loop
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `403 Forbidden` | Service account lacks permission | Re-run Step 3 with correct IAM role |
| `File not found: harness-eval-key.json` | Key path wrong in `.env` | Use the full absolute path |
| `google.auth.exceptions.DefaultCredentialsError` | No credentials found | Check `GOOGLE_APPLICATION_CREDENTIALS` in `.env` |
| `ModuleNotFoundError: google.cloud.storage` | Deps not installed | Run `uv sync` |
| `Bucket not found` | Wrong bucket name | Re-run `python gcp_discover.py` to list real names |
| `ParquetInvalidHeader` | Corrupt or empty file | Check the file in GCS Console first |
| `server_gcp.py` falls back to fixtures | GCP auth failed | Check the warning printed at startup |

---

## Security Checklist

- [ ] `harness-eval-key.json` is in `.gitignore`
- [ ] `.env` is in `.gitignore`
- [ ] Service account has only `roles/storage.objectViewer` (read-only)
- [ ] Key is stored only on your local machine — not in OneDrive sync if possible

---

## File Reference

| File | Purpose |
|---|---|
| `gcp_adapter.py` | Low-level GCS client (list, read, schema-sample) |
| `gcp_loader.py` | Domain-level loader with in-memory cache |
| `gcp_discover.py` | One-time discovery script → `data/gcp_schema_discovery.json` |
| `gcp_config.yaml` | Maps domain → bucket + file paths |
| `server_gcp.py` | MCP server using real GCS data (falls back to fixtures on auth failure) |

