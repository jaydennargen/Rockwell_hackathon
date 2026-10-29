# ARCHITECTURE.md: Failure Analysis Triage App

Rockwell Automation Lifecycle Services: Failure Analysis Triage (SHPE AI Hackathon).

A single web app with role-based views. A **requester** submits SAP repair orders and, for each one, sees the AI triage report (or a notice that a specialist has it) and can chat about it. A **specialist** sees every request, reviews escalated ones, and uses a chat that can query the repair data. Backend: FastAPI deployed as a Databricks App. Data in Delta tables. LLMs on Databricks Model Serving.

Data-layer details (table schemas, category mapping, confidence-model training) are in `docs/databricks_backend_spec.md`. **This file is the source of truth for the API**; it replaces §7 of that spec.

---

## 1. System overview

```
                 ┌──────────────────────────────────────────────┐
 Browser ──────► │ React (Vite, JS, plain CSS)  frontend/        │
                 │  role-aware routes: requester | specialist    │
                 └───────────────┬──────────────────────────────┘
                                 │ /api/* (JSON, cookie session)
                 ┌───────────────▼──────────────────────────────┐
                 │ FastAPI  backend/app/                         │
                 │  auth · orders · review · chat · evidence     │
                 │  visibility.py filters every response by role │
                 └──┬──────────────┬───────────────┬────────────┘
                    │ Repo         │ run_triage()  │ chat_reply()
          ┌─────────▼───┐   ┌──────▼──────┐  ┌─────▼──────┐
          │ backend/    │   │ backend/    │  │ backend/   │
          │ app/repo/   │   │ triage/     │  │ chat/      │
          │ local|dbx   │   │ 2 LLM agents│  │ 1 LLM agent│
          └─────┬───────┘   │ + tools     │  │ + tools    │
                │           └──────┬──────┘  └─────┬──────┘
     ┌──────────▼──────────┐       │ StatsRepo     │
     │ SQLite (local dev)  │◄──────┴───────────────┘
     │ Delta via SQL       │   LLM: FakeLLM | Databricks serving endpoint
     │ warehouse (deployed)│
     └─────────────────────┘
                ▲
     databricks/ notebooks build bronze → silver → gold (nightly)
     hardware/ bench bridge → POST /api/orders/{id}/evidence (stretch)
```

**Every external dependency sits behind a switch**, so all workstreams can run locally without Databricks credentials:

| Env var | Values | Default | Effect |
|---|---|---|---|
| `AUTH_MODE` | `demo` \| `databricks` | `demo` | Demo login picker vs. the identity Databricks Apps passes in |
| `DATA_BACKEND` | `memory` \| `local` \| `databricks` | `memory` | In-memory store seeded from fixtures (WS0) vs. SQLite file (WS3) vs. Delta tables through a SQL warehouse |
| `PIPELINE` | `mock` \| `live` | `mock` | Return fixture reports after a 2 s delay vs. run the real triage pipeline |
| `LLM_MODE` | `fake` \| `databricks` | `fake` | Deterministic fake responses vs. the serving endpoint |
| `CHAT_MODE` | `fake` \| `agent` \| `genie` | `fake` | Chat backend |
| `CONFIDENCE_THRESHOLD` | float | `0.70` | Below this score → `NEEDS_REVIEW` |
| `MOCK_DELAY_SECONDS` | float | `2.5` | Fake processing time in `PIPELINE=mock` |
| `SESSION_SECRET`, `DEVICE_TOKEN` | string | dev values | Cookie signing; bench-device auth |
| `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_HTTP_PATH`, `LLM_ENDPOINT`, `GENIE_SPACE_ID`, `UC_CATALOG`, `UC_SCHEMA` | — | — | Used only in the `databricks` modes |

---

## 2. Roles and what each one sees

Roles live in an `app_users` table (`email`, `name`, `role`, `org`). Demo seed: `requester@vanmeter.demo` (org "Van Meter Inc", a distributor, as in the sample report) and `specialist@rockwell.demo`.

| | Requester | Specialist |
|---|---|---|
| Request list | Only their own (`submitted_by = me`) | All requests; filter tabs All / Needs review / Released |
| Submit form + bulk upload | ✅ | ✅ |
| Report: header, status, summary, predicted areas & cause, troubleshooting steps, unit history | ✅ *only once released* (`AUTO_RELEASED`, `APPROVED`, `EDITED`) | ✅ always |
| Report while `NEEDS_REVIEW` | Escalation notice in plain language + reasons, **no predictions** | Full draft |
| Confidence score / threshold numbers | ❌ (plain-language reasons only) | ✅ |
| Parts to pre-stage, NPF risk, bench evidence, trace link | ❌ | ✅ |
| Review panel (approve / edit / reject) | ❌ | ✅ |
| Specialist notes after review | ✅ | ✅ |
| Chat on a request | ✅ scoped to *this* report + its manual section; no SQL | ✅ the report + read-only SQL over gold tables (or Genie) |

The point of the human-in-the-loop design: **a requester never sees predictions the system isn't confident in.** Low confidence → "a specialist is reviewing this", not a guess.

All filtering happens **server-side** in `backend/app/visibility.py` (one dict of field allow-lists per role). The frontend hides UI by role for convenience only; it never receives fields the role can't see. A requester requesting another user's order gets `404`.

### Status labels

| Internal `status` | Requester label | Specialist label |
|---|---|---|
| `PROCESSING` | Processing | Processing |
| `AUTO_RELEASED` | Report ready | Auto-released |
| `NEEDS_REVIEW` | With a specialist | Needs review |
| `APPROVED` | Verified by specialist | Approved |
| `EDITED` | Verified by specialist | Edited |
| `REJECTED` | Closed, see specialist notes | Rejected |
| `FAILED` | Couldn't process, try again | Failed |

The API returns both `status` and `status_label` (already role-specific), so the frontend never maps statuses itself.

---

## 3. Frontend (`frontend/`)

Vite + React 18 + React Router, plain JS, plain CSS (CSS variables in `src/styles/tokens.css`). No UI framework. Archivo (variable width) is self-hosted via `@fontsource-variable/archivo`, so there are no external font requests.

**Visual language:** the report header is drawn as the paper repair tag that travels with a unit through a depot (manila, punched hole, status stamp). That's the one bold element. Everything else is a quiet, form-like sheet that mirrors the printed SAP repair report. Status colors appear only on tags and stamps. Change colors and type in `tokens.css`. Dev server on `:5173`, which proxies `/api` to `:8000`.

### Routes

| Route | Requester | Specialist |
|---|---|---|
| `/login` | Demo picker (two buttons) in `demo` mode; skipped in `databricks` mode | same |
| `/` | → `/requests` | → `/requests?filter=needs_review` |
| `/requests` | My requests + "New request" button | All requests with filter tabs |
| `/requests/new` | Form + bulk upload | same |
| `/requests/:id` | Report (or escalation notice) + Chat panel | Report (full) + Review panel + Chat panel |

### Structure

```
frontend/src/
  main.jsx, App.jsx                 router + <AuthProvider>
  api/client.js                     the ONLY place that calls fetch(); one function per endpoint
  auth/AuthContext.jsx              GET /api/me on load; exposes {user, role, login, logout}
  auth/RequireRole.jsx              route guard
  lib/format.js                     dates, %, category labels, status -> tone
  lib/samples.js                    real orders from the extract for "Fill with a sample order"
  components/
    Layout.jsx, NavBar.jsx, Wordmark.jsx
    StatusTag.jsx                   mini luggage-tag status marker (label from API)
    RepairTag.jsx                   report header: manila tag + status stamp
    Section.jsx                     one label-left/content-right row of the report sheet
    ReportView.jsx                  renders whatever sections the report object contains
    EscalationNotice.jsx            requester view of NEEDS_REVIEW
    ChatPanel.jsx                   transcript + input; GET/POST /orders/:id/chat
    ReviewPanel.jsx                 specialist only: approve / correct / reject
    OrderForm.jsx, BulkUpload.jsx
    specialist/                     ConfidenceSection, PartsSection, BenchEvidence
  pages/
    LoginPage.jsx, RequestListPage.jsx, NewRequestPage.jsx, RequestDetailPage.jsx
  styles/tokens.css, app.css
```

**`ReportView` is data-driven:** it renders a section only if that key exists in the response. Role differences come from the server, so a single component serves both roles.

**Polling:** `RequestDetailPage` polls `GET /api/orders/:id` every 2 s while `status == "PROCESSING"`, then stops.

---

## 4. Backend API (`backend/app/`)

FastAPI. All routes under `/api`. JSON in and out. Errors: `{"error": {"code": "string", "message": "string"}}` with the matching HTTP status. Pydantic models in `backend/app/schemas.py` are the source of truth; example payloads live in `contracts/fixtures/`.

### Auth

| Method | Path | Body → Response | Notes |
|---|---|---|---|
| `POST` | `/api/auth/demo-login` | `{role: "requester"\|"specialist"}` → `User` | `demo` mode only; sets an httpOnly `session` cookie |
| `POST` | `/api/auth/logout` | → `{}` | |
| `GET` | `/api/me` | → `User` | `401` if not signed in |

`User = {email, name, role, org}`.

In `databricks` mode, identity comes from the user headers Databricks Apps forwards to the app (`X-Forwarded-Email`; check the header name in the Databricks Apps docs when wiring it), looked up in `app_users`. Unknown users default to `requester`.

### Orders

| Method | Path | Who | Body → Response |
|---|---|---|---|
| `GET` | `/api/orders?filter=all\|needs_review\|released&limit=50&offset=0` | both | → `{items: OrderSummary[], total}`. Requesters always get only their own |
| `POST` | `/api/orders` | both | `OrderIn` → `{order_id, status}` (`201`); triage starts in the background |
| `POST` | `/api/orders/bulk` | both | multipart `file` (.xlsx/.csv with the SAP extract's column names) → `{order_ids: string[], errors: [{row, message}]}` |
| `GET` | `/api/orders/{order_id}` | both | → `TriageReport` (role-filtered) |
| `POST` | `/api/orders/{order_id}/review` | specialist | `ReviewIn` → `TriageReport` |
| `POST` | `/api/orders/{order_id}/evidence` | specialist or `X-Device-Token` | `EvidenceIn` → `TriageReport` (re-scores confidence) |
| `POST` | `/api/orders/{order_id}/retry` | specialist | → `{order_id, status}` |

### Chat (per request)

| Method | Path | Body → Response |
|---|---|---|
| `GET` | `/api/orders/{order_id}/chat` | → `{messages: ChatMessage[]}` |
| `POST` | `/api/orders/{order_id}/chat` | `{message: string}` → `{reply: ChatMessage}` |

Chat history is stored per (`order_id`, `user_email`).

### Schemas

```text
OrderIn        { order_number: str, line_number: int = 1000, catalog: str, part_number: str,
                 part_description: str, serial_number: str?, depot: str?,
                 failure_details: str, additional_info: str?, received_date: date? }

OrderSummary   { order_id, catalog, part_description, serial_number, status, status_label,
                 submitted_by, created_at,
                 confidence_score?  (specialist only), top_reason? (specialist only) }

TriageReport   { order_id, status, status_label, created_at, updated_at,
                 header:          { order_number, item, part_number, catalog, serial,
                                    description, depot, received_date },
                 customer_input:  { text, informative },
                 escalation?:     { message, reasons: str[] }              // requester, NEEDS_REVIEW only
                 summary?:        str                                      // Agent 2 narrative
                 predicted?:      { areas: [{category, detail}], causes: str[], rationale }
                 procedure?:      { section, title, synthetic: true, loto_required, steps: str[] }
                 unit_history?:   [{ order_id, date, causes: str[] }]
                 review?:         { decision, notes, reviewer, reviewed_at }
                 // specialist only ↓
                 confidence?:     { score, threshold, reasons: str[] }
                 parts_to_prestage?: [{ part, freq, n }]
                 npf_risk?:       { family_rate, flag }
                 bench_evidence?: [{ name, value, unit, spec_min, spec_max, pass, source }]
                 trace_id?:       str
                 pending_sections: ["cleaning", "testing"] }

ReviewIn       { decision: "approve"|"edit"|"reject",
                 corrections?: { areas?: [{category, detail}], causes?: str[], parts?: str[] },
                 notes?: str }

EvidenceIn     { source: str, measurements: [{ name, value, unit, spec_min?, spec_max? }] }

ChatMessage    { id, role: "user"|"assistant", content, sql?: str, sources?: [{label, ref}],
                 created_at }
```

`order_id` = `"{order_number}-{line_number}"`. A duplicate submission returns `409`.

### Backend layout

```
backend/
  app/
    main.py            FastAPI app, routers, static files (serves frontend/dist in prod), startup seed
    config.py          env vars (§1)
    auth.py            session cookie (demo) / forwarded headers (databricks); current_user dependency
    visibility.py      ROLE_FIELDS + status_label(); filter_report(report, user)
    schemas.py         Pydantic models (§4)
    routes/            auth.py, orders.py, chat.py, evidence.py
    repo/
      base.py          Repo protocol: users, orders, reports, reviews, chat, evidence
      local.py         SQLite implementation (file: backend/.data/app.db)
      databricks.py    databricks-sql-connector implementation (Delta tables)
    jobs.py            run_triage_job(order_id): calls triage.pipeline or the mock; writes report
  triage/
    pipeline.py        triage(order: dict, stats: StatsRepo, llm: LLM) -> dict   (full report, unfiltered)
    agents.py          triage_extractor(), report_writer()   (the 2 pipeline LLM agents)
    tools.py           clean_text, history_lookup, repeat_return_check, procedure_lookup,
                       parts_predictor, loto_rule
    confidence.py      score(features) -> (score, reasons); route(...) -> status
    stats_repo.py      StatsRepo protocol + LocalStatsRepo (SQLite built from the xlsx) + DatabricksStatsRepo
    llm.py             LLM protocol + FakeLLM + DatabricksLLM (OpenAI-compatible client)
    prompts/           extractor.md, report_writer.md
    mock.py            fixture-based reports for PIPELINE=mock
  chat/
    agent.py           chat_reply(order_report, history, message, user) -> ChatMessage
    tools.py           get_report, get_procedure, run_sql (read-only, gold tables, specialist only)
    genie.py           Genie Conversation API client (CHAT_MODE=genie)
  scripts/
    build_local_gold.py   xlsx + manual → backend/.data/gold.db (silver + gold tables, same names as Delta)
    seed_demo.py          demo users + ~6 requester orders (mix of released / escalated)
  tests/
```

---

## 5. Triage pipeline

Fixed sequence of steps, no LLM planner. **3 LLM agents in total** (2 here, 1 in chat); everything else is plain code. Full logic in `docs/databricks_backend_spec.md` §4–§6.

```
clean_text → triage_extractor (LLM) → history_lookup → repeat_return_check
→ procedure_lookup → parts_predictor → confidence.score → confidence.route
→ report_writer (LLM) → full report dict
```

- `jobs.run_triage_job` writes `PROCESSING`, calls the pipeline, and stores the **full** report. `visibility.filter_report` trims it per request. Any exception → `FAILED` with the error stored.
- Every step is wrapped in `@mlflow.trace` when `mlflow` is importable and a tracking URI is set; otherwise it's a no-op decorator.
- `StatsRepo` hides where gold stats come from: the local SQLite built by `build_local_gold.py`, or Delta. Same table and column names in both.
- `PIPELINE=mock` picks a fixture by a simple rule (e.g. empty/uninformative text → escalated fixture) so the demo and frontend dev show both paths.

### Confidence and routing

`NEEDS_REVIEW` if: score < threshold, **or** repeat return ≤ 180 days, **or** (uninformative text **and** family history has < 30 labeled orders), **or** no manual section matches. Every rule that fires adds a reason string written for a non-expert ("The failure description didn't include usable details"). Requesters see these reasons; specialists also see the numbers.

### Chat agent

- **Requester:** the system prompt contains only the filtered report + its procedure section. Tools: none. Instruction: answer only about this order; if asked anything else, say a specialist can help.
- **Specialist:** full report in context + tools `get_report(order_id)`, `get_procedure(section)`, `run_sql(query)`. `run_sql` allows only `SELECT` on the gold tables, with a `LIMIT 200` appended. Answers include the SQL they used. `CHAT_MODE=genie` sends data questions to the Genie space instead.

---

## 6. Data

| Store | Local (`DATA_BACKEND=local`) | Deployed (`databricks`) |
|---|---|---|
| App tables (`app_users`, `app_orders`, `gold_triage_reports`, `gold_review_feedback`, `app_chat_messages`, `gold_bench_evidence`) | `backend/.data/app.db` | Delta in `{UC_CATALOG}.{UC_SCHEMA}` |
| Gold stats (`gold_family_stats`, `gold_part_freq`, `gold_repeat_returns`, `gold_depot_patterns`), `silver_repairs`, `silver_manual_sops` | `backend/.data/gold.db` from `build_local_gold.py` | Built by `databricks/` notebooks |

New submissions are also appended to `bronze_sap_repairs` (`source = 'app_submission'`, `submitted_by`) in Databricks mode, so there is one master table.

---

## 7. Deployment (Databricks App)

- `npm run build` → `frontend/dist`. FastAPI serves it as static files, with every unknown non-`/api` path falling back to `index.html`.
- `app.yaml` at the repo root runs `uvicorn backend.app.main:app` on the port Databricks Apps provides (check the env var name in the Apps docs). Env vars come from the App config; secrets via Databricks secrets, never committed.
- The App's service principal needs: `USE`/`SELECT`/`MODIFY` on the schema, `CAN USE` on the SQL warehouse, `CAN QUERY` on the serving endpoint (and on the Genie space, if used).
- Local dev: `cd backend && uvicorn app.main:app --reload --port 8000` and `cd frontend && npm run dev`.

---

## 8. Hardware hook (stretch)

`hardware/bridge/bridge.py` reads JSON lines from the FPGA over UART (`{"name":"fan_rpm","value":3120,"unit":"rpm"}`), attaches the spec limits for the selected order, and POSTs to `/api/orders/{id}/evidence` with `X-Device-Token`. The backend stores the evidence, recomputes confidence (`bench_evidence_supports` = +1 if it supports the predicted cause, −1 if it contradicts it), and may move the order between `NEEDS_REVIEW` and `AUTO_RELEASED` **only if no specialist has reviewed it yet**. Spartan-7 Urbana fan tach counter; the tach line is open-collector, so pull it up to 3.3 V and never connect 12 V to an FPGA pin.

---

## 9. Non-negotiables

1. Troubleshooting content comes from a **synthetic** manual. Always `synthetic: true`, always labeled in the UI.
2. The pre-repair report never claims cleaning or testing happened (`pending_sections`).
3. Requesters never receive specialist-only fields or unreleased predictions. This is enforced in `visibility.py` and covered by tests.
4. No secrets in the repo. `.env.example` lists every variable.
5. No numbers in the UI or pitch that weren't computed from the data or the holdout evaluation.
