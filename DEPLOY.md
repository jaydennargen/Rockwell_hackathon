# Deploying MATE to Databricks Apps

One Databricks App runs everything. On each deployment the platform:

1. runs `npm install` + `npm run build` from the root `package.json` (builds `frontend/` into `frontend/dist`),
2. runs `pip install -r requirements.txt` (which includes `backend/requirements.txt`),
3. starts the `app.yaml` command: `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $DATABRICKS_APP_PORT`.

FastAPI serves both `/api/*` and the built React app from the same URL, so there's no CORS and no
hardcoded host anywhere.

Values you must fill in are marked `<LIKE_THIS>`. Defaults already in the repo: workspace
`https://dbc-45c9154d-c76b.cloud.databricks.com`, warehouse `6e4f969ac71d3b26`, catalog/schema
`infrared.shpe`, LLM endpoint `databricks-meta-llama-3-3-70b-instruct`, app name `mate-triage`.

---

## How authentication works

| Where | Who the app is to Databricks | How |
|---|---|---|
| **Deployed (Databricks Apps)** | The app's **service principal** (created with the app) | Databricks injects `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`; the Databricks SDK uses OAuth M2M automatically |
| **Local dev** | **You** | `databricks auth login` stores an OAuth profile in `~/.databrickscfg`; set `DATABRICKS_CONFIG_PROFILE=mate` in `.env` |

All Databricks calls (SQL warehouse, model serving, Genie) go through `backend/app/dbx.py`, which uses
the SDK's unified authentication. The same code runs in both places; no tokens in code, config files,
or the browser.

**App users** first sign in to Databricks (only workspace users with access to the app get in). Then,
with `AUTH_MODE=demo` (the default in `app.yaml`), MATE shows its role picker with the demo accounts:
Dana Whitfield (field technician) and Luis Ortega (repair specialist). The app adds these accounts to
`app_users` on startup; no demo orders are added. The session cookie is HTTPS-only and signed with a
key derived from the app's own injected secret.

For real per-person identity instead, set `AUTH_MODE=databricks`: the app reads each user's email from
`X-Forwarded-Email` and gives the **specialist** view to emails listed in `SPECIALIST_EMAILS` (real
Databricks logins, comma-separated); everyone else is a **requester**.

This is **app authorization** only. The app doesn't need user authorization (on-behalf-of-user
tokens): all data access uses the service principal, and the app enforces requester/specialist
visibility itself (`backend/app/visibility.py`).

---

## 1. Install the Databricks CLI (once)

Windows (PowerShell):

```powershell
winget install Databricks.DatabricksCLI
databricks --version        # needs v0.250 or newer; v1.x is fine
```

macOS: `brew tap databricks/tap && brew install databricks`.

## 2. Log in to the workspace (once)

```bash
databricks auth login --host https://dbc-45c9154d-c76b.cloud.databricks.com --profile mate
```

A browser window opens for OAuth. This writes a profile to `~/.databrickscfg` (Windows:
`C:\Users\<you>\.databrickscfg`) that looks like this, with no token stored in the file:

```ini
[mate]
host      = https://dbc-45c9154d-c76b.cloud.databricks.com
auth_type = databricks-cli
```

Check it: `databricks current-user me -p mate`. Never commit this file or copy it into the repo
(it's gitignored).

## 3. Fill in the app settings

Edit **`app.yaml`**:

- `AUTH_MODE`: `demo` (role picker with the demo accounts). Nothing to fill in.
- `UC_CATALOG` / `UC_SCHEMA` / `CONFIDENCE_THRESHOLD`: already set to `infrared` / `shpe` / `0.825`.

Edit **`databricks.yml`** only if these differ in your workspace:

- `warehouse_id` default: your SQL warehouse ID (SQL Warehouses → your warehouse → Connection details;
  the ID is the last part of the HTTP path).
- `llm_endpoint` default: the serving endpoint name (Serving → endpoint name).
- `name: mate-triage`: app names are lowercase letters, numbers, and dashes, unique in the workspace.
- To let every workspace user open the app, uncomment the `permissions` block.

## 4. Deploy

From the repo root:

```bash
databricks bundle validate -p mate
databricks bundle deploy   -p mate     # creates the app, attaches the warehouse + endpoint, uploads the code
databricks bundle run mate -p mate     # builds and starts it (first run takes a few minutes)
```

`bundle deploy` uploads every file not in `.gitignore` (so no `.env`, `node_modules`, `.venv`,
`backend/.data`, or `frontend/dist`; the build happens in Databricks).

## 5. Grant data permissions (once, after the first deploy)

Attached resources (`sql-warehouse` → CAN USE, `llm-endpoint` → CAN QUERY) are granted by
`bundle deploy`. Unity Catalog schemas can't be attached as app resources, so grant those yourself.

Get the service principal's ID:

```bash
databricks apps get mate-triage -p mate -o json
# copy "service_principal_client_id" (a UUID)
```

Then run this in the SQL editor as the owner of `infrared.shpe` (or a metastore admin):

```sql
GRANT USE CATALOG ON CATALOG infrared TO `<SERVICE_PRINCIPAL_CLIENT_ID>`;
GRANT USE SCHEMA, SELECT, MODIFY, CREATE TABLE ON SCHEMA infrared.shpe TO `<SERVICE_PRINCIPAL_CLIENT_ID>`;
```

- `CREATE TABLE` + `MODIFY`: the app creates and writes its own tables on first use (`app_users`,
  `app_orders`, `gold_triage_reports`, `gold_review_feedback`, `app_chat_messages`,
  `gold_bench_evidence`) and appends to `bronze_sap_repairs`.
- `SELECT`: the live pipeline and specialist chat read `gold_family_stats`, `gold_part_freq`,
  `gold_repeat_returns`, `gold_depot_patterns`, `silver_repairs`.

No restart is needed after granting.

## 6. Open and check it

```bash
databricks apps get mate-triage -p mate      # prints the app URL
```

Open the URL (you'll sign in with Databricks SSO). Then check the backend can reach Databricks:

```
https://<APP_URL>/api/health?deep=1
```

Expect `"ok": true`, `"auth_type": "oauth-m2m"`, `"warehouse": true`. If `warehouse` is false, the
`error` field says why (warehouse stopped, missing grant, wrong ID).

## 7. Logs

```bash
databricks apps logs mate-triage -p mate               # recent logs
databricks apps logs mate-triage -p mate --follow      # stream
```

Or in the UI: **Compute → Apps → mate-triage → Logs**. Build output (npm/pip) and Python errors
both show up there.

## 8. Redeploy after code changes

```bash
databricks bundle deploy -p mate && databricks bundle run mate -p mate
```

---

## Alternative: deploy without the bundle (UI + CLI)

1. **Compute → Apps → Create app → Custom**, name `mate-triage`.
2. Under **App resources**, add a **SQL warehouse** with key `sql-warehouse` (Can use) and a
   **Serving endpoint** with key `llm-endpoint` (Can query). The keys must match `app.yaml`.
3. Upload and deploy:
   ```bash
   databricks sync . /Workspace/Users/<YOUR_EMAIL>/mate-triage -p mate
   databricks apps deploy mate-triage --source-code-path /Workspace/Users/<YOUR_EMAIL>/mate-triage -p mate
   ```
4. Do step 5 (grants) and step 6 above.

## Optional: Genie chat

Create a Genie space over the gold tables, then uncomment the `genie-space` resource in
`databricks.yml` (fill in `space_id`) and the `GENIE_SPACE_ID` lines in `app.yaml`, set
`CHAT_MODE` to `genie`, and redeploy.

## Optional: MLflow tracing

Set `MLFLOW_TRACKING_URI=databricks` and `MLFLOW_EXPERIMENT_NAME=/Users/<YOUR_EMAIL>/mate-traces` in
`app.yaml`, and give the service principal CAN EDIT on that experiment. Off by default.

## Optional: bench device (hardware/)

The evidence endpoint's device token is off in deployment unless `DEVICE_TOKEN` is set. Store it in a
secret scope, add it as a **Secret** resource with key `device-token`, and add
`- name: DEVICE_TOKEN` / `valueFrom: device-token` to `app.yaml`.

---

## Running locally against Databricks

```bash
cp .env.example .env
# in .env: DATABRICKS_CONFIG_PROFILE=mate, then switch the modes you want, e.g.
#   DATA_BACKEND=databricks  PIPELINE=live  LLM_MODE=databricks  CHAT_MODE=agent
# keep AUTH_MODE=demo locally (the forwarded identity header only exists behind Databricks Apps)
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

The fully local defaults (`DATA_BACKEND=local`, `PIPELINE=mock`, fakes) need no Databricks access.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Build fails at `npm` or `pip` | Check the Logs tab. If the workspace blocks internet access to npm/PyPI, ask an admin to allow it. |
| `/api/health?deep=1` shows `warehouse: false` with a permission error | Step 5 grants, or the warehouse resource is missing or stopped. |
| Orders go to **Failed** with `TABLE_OR_VIEW_NOT_FOUND` | The gold tables don't exist in `infrared.shpe` yet (databricks/ notebooks). |
| Chat or triage returns 503 `databricks_unavailable` | The LLM endpoint name is wrong, or the service principal lacks CAN QUERY. |
| (`AUTH_MODE=databricks`) Everyone gets the requester view | Add their Databricks emails to `SPECIALIST_EMAILS` in `app.yaml` and redeploy. |
