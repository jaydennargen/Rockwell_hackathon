# AGENTS.md: Instructions for coding agents (Claude Code / Codex)

Read `ARCHITECTURE.md` before doing anything. Data-layer detail is in `docs/databricks_backend_spec.md`. If this file and a prompt disagree, ask; don't guess.

Several agents work on this repo **at the same time**, each in its own git worktree and branch. Staying inside your file ownership is what keeps merges clean.

---

## 1. Ground rules (all agents)

1. **Stay in your owned paths** (§3). If you need a change outside them, write it as a request in `HANDOFF.md` under your workstream heading and continue with a stub.
2. **Contracts are frozen** once WS0 merges: `backend/app/schemas.py`, `contracts/fixtures/*.json`, and the API table in `ARCHITECTURE.md` §4. To change one, add a proposal to `HANDOFF.md` → "Contract changes" and stop work on that piece. Only the integrator (a human) merges contract changes.
3. **Local first.** Everything must run with the defaults `AUTH_MODE=demo DATA_BACKEND=memory PIPELINE=mock LLM_MODE=fake CHAT_MODE=fake` (WS3 adds `local`) and no Databricks credentials. Databricks code paths go behind the switches in `ARCHITECTURE.md` §1.
4. **Never commit secrets**, `.env`, `backend/.data/`, or the source `.xlsx`. Add new env vars to `.env.example`.
5. **Tests:** backend uses `pytest` (`cd backend && pytest -q`); frontend runs `npm run build` and `npm run lint` with no errors. Run them before every commit.
6. **Commits:** small, prefixed with your workstream (`ws3: add review route`). Never force-push; never rebase someone else's branch.
7. **Honesty rules:** the manual is synthetic (always label it); reports never claim cleaning or testing was done; never hardcode accuracy or other metrics in UI copy.
8. **Stack:** Python 3.11, FastAPI, Pydantic v2, pandas, `databricks-sql-connector`, `openai` (for the Databricks OpenAI-compatible endpoint), `mlflow` (optional import). Frontend: Vite, React 18, React Router 6, plain JS, plain CSS. Don't add other dependencies without noting them in `HANDOFF.md`.
9. When you finish, update your section in `HANDOFF.md`: what works, how to run it, what's stubbed, known issues.

---

## 2. How to run the parallel setup

```bash
# once, after WS0 is merged to main
git worktree add ../ws1-fe-requester  -b ws1/fe-requester
git worktree add ../ws2-fe-specialist -b ws2/fe-specialist
git worktree add ../ws3-api           -b ws3/api
git worktree add ../ws4-triage        -b ws4/triage
git worktree add ../ws5-chat          -b ws5/chat
# then open Claude Code (or Codex) in each folder and paste that workstream's kickoff prompt
```

`databricks/` (WS6) is handled by the Databricks teammate in the workspace and synced through a Git folder. `hardware/` (WS7) goes last.

**Order:** WS0 runs alone and merges first. Then WS1–WS6 run in parallel. Merge in this order: WS3 → WS4 → WS5 → WS1 → WS2, then integrate. WS7 is a stretch goal.

---

## 3. Workstreams

### WS0: Scaffold & contracts ✅ DONE (initial commit)
**Owns:** everything initially; after merge, only `backend/app/schemas.py`, `contracts/`, root config files.
**Deliver:**
- The repo tree from `ARCHITECTURE.md` §3–§4, with empty modules that have docstrings.
- `backend/app/schemas.py`: every Pydantic model from §4.
- `contracts/fixtures/`: `me_requester.json`, `me_specialist.json`, `order_in.json`, `orders_list_requester.json`, `orders_list_specialist.json`, `report_full_auto_released.json`, `report_full_needs_review.json`, `report_requester_released.json`, `report_requester_escalated.json`, `chat_history.json`, `chat_reply.json`. These must validate against the schemas (add a pytest that checks this). Use the realistic values from the sample order 67083053 / R1394CAM75IH/C.
- FastAPI app where **every route in §4 exists** and returns fixture data (demo login works, cookie session works).
- A Vite React app with routing and `api/client.js` implementing every endpoint, plus placeholder pages.
- `.env.example`, `.gitignore`, `app.yaml`, `backend/requirements.txt`, `frontend/package.json`, `HANDOFF.md` with one heading per workstream and a "Contract changes" section.
**Done when:** `uvicorn` + `npm run dev` start; you can log in as each role and see placeholder pages that load fixture data; schema tests pass.

**Kickoff prompt:**
> You are WS0. Read ARCHITECTURE.md and AGENTS.md fully. Scaffold the repo exactly as ARCHITECTURE.md §3–§4 describe and deliver everything listed under WS0 in AGENTS.md. Prioritize correct schemas and fixtures over polish: every other workstream builds against them. Stop when the WS0 "Done when" criteria pass, then update HANDOFF.md.

---

### WS1: Frontend, requester flow + shared components
**Owns:** `frontend/src/{auth,lib,components/*.jsx except ReviewPanel.jsx,pages/*,styles/*}`
**Starting point:** WS0 shipped working, designed versions of all of these. Your job is to finish and harden them, not rebuild them. Keep the visual language in ARCHITECTURE.md §3.
**Must not touch:** `components/ReviewPanel.jsx`, `api/client.js` (request changes via HANDOFF.md).
**Deliver (remaining):** client-side validation messages per field; pagination on the list; a polished processing state; keyboard and screen-reader pass; empty/error states checked against the live API. Already working: login picker; request list (mine); new request form with "Fill with a sample order" + bulk upload; request detail with polling, `ReportView` (data-driven, renders only the sections present), `EscalationNotice`, and `ChatPanel`; the synthetic-manual label; the "Cleaning / Testing: to be completed by technician" section; empty, loading, and error states. Layout should be minimal, clean, and responsive. Jayden owns the visual design, so keep styling in CSS variables in `tokens.css`.
**Done when:** against the WS0 mock API, a requester can log in, submit, watch the order go from Processing → Report ready / With a specialist, open it, and chat.

**Kickoff prompt:**
> You are WS1. Read ARCHITECTURE.md (§2, §3) and AGENTS.md. The requester flow already works against the mock API; finish and harden it as listed under WS1, working only in your owned paths and only against the existing api/client.js and contracts/fixtures. ReportView must render sections based on which keys exist in the report, so the specialist view works without changes. Keep styling in CSS variables. Update HANDOFF.md when done.

---

### WS2: Frontend, specialist additions
**Owns:** `frontend/src/components/ReviewPanel.jsx`, `frontend/src/components/specialist/*`, `frontend/src/pages/specialist/*` (if needed).
**Starting point:** WS0 shipped working versions of the filter tabs, ReviewPanel, and the specialist sections. Finish and harden them.
**Coordinate:** filter tabs on `RequestListPage` and mounting `ReviewPanel` on `RequestDetailPage` are one-line insertions into WS1 files. Make them in a final commit after WS1 merges, or ask in HANDOFF.md.
**Deliver:** filter tabs (All / Needs review / Released) with confidence and top-reason columns; `ReviewPanel` (approve; edit with dropdowns for area/cause from the categories in `docs/databricks_backend_spec.md` §2 + a parts list; reject with notes); display of specialist-only report sections (confidence numbers, parts to pre-stage, NPF risk, bench evidence, trace link) as small components that `ReportView` can render by key.
**Done when:** a specialist can open an escalated order from the mock API, edit it, and see the status change.

**Kickoff prompt:**
> You are WS2. Read ARCHITECTURE.md (§2, §3) and AGENTS.md. The specialist UI already works against the mock API; finish and harden it as listed under WS2 in your owned paths. Write specialist report sections as standalone components keyed by report field name so WS1's ReportView can render them. Don't edit WS1 files until WS1 has merged; then make only the minimal insertions. Update HANDOFF.md when done.

---

### WS3: Backend API, auth, visibility, repo
**Owns:** `backend/app/**` except `schemas.py`; `backend/scripts/seed_demo.py`; `backend/tests/test_api_*.py`, `test_visibility.py`.
**Starting point:** WS0 shipped every route on an in-memory repo (`repo/memory.py`), demo auth, `visibility.py`, background mock triage, and 27 passing tests.
**Deliver (remaining):** `repo/local.py` (SQLite) and `repo/databricks.py`, then make `local` the default; databricks auth mode; evidence re-scoring; seed script. Already working: demo auth; `visibility.py` with server-side field filtering and role-specific `status_label`; `repo/local.py` (SQLite) and `repo/databricks.py`; background `jobs.run_triage_job` calling `triage.mock` or `triage.pipeline` depending on `PIPELINE`; review (writes feedback, updates status); evidence (stores it, calls a confidence re-score hook); chat routes delegating to `chat.agent.chat_reply`; bulk upload parsing the SAP extract's column names; seed script; static file serving for production.
**Tests that must exist:** a requester can't see another user's order (404); requester responses never contain `confidence`, `parts_to_prestage`, `npf_risk`, `bench_evidence`, `trace_id`; a requester sees `escalation` and no `predicted` while `NEEDS_REVIEW`; review endpoint is specialist-only (403).
**Done when:** all routes are backed by the local repo, tests pass, and the WS0 fixture responses are replaced by real stored data.

**Kickoff prompt:**
> You are WS3. Read ARCHITECTURE.md (§1, §2, §4, §6, §7) and AGENTS.md. Implement the FastAPI backend in your owned paths against the frozen schemas. Role filtering must happen server-side in visibility.py and be covered by the required tests. Call triage and chat only through their public functions (triage.pipeline.triage, triage.mock, chat.agent.chat_reply); stub them if they don't exist yet. Update HANDOFF.md when done.

---

### WS4: Triage pipeline (2 LLM agents + tools + confidence)
**Owns:** `backend/triage/**`, `backend/scripts/build_local_gold.py`, `backend/tests/test_triage_*.py`.
**Deliver:**
- WS0 left a starting `clean_text` and the 8 manual sections as JSON (`triage/data/manual_sops.json`) in `triage/`; reuse them.
- `build_local_gold.py` (xlsx + manual → `gold.db`, with the same tables and columns as `docs/databricks_backend_spec.md` §3; includes the category mapping from §2 and the `^~` parts split).
- Tools, `confidence.py` (start with hand-weighted scoring + the routing rules; leave a `load_model()` hook for the MLflow model), `FakeLLM` and `DatabricksLLM`, prompts, `pipeline.triage()` returning the full report dict that matches `TriageReport`, and `mock.py`.
- A script `scripts/eval_holdout.py` that runs the pipeline over N labeled orders from the newest 20% and prints accuracy vs. coverage at several thresholds.
**Done when:** `triage()` runs end to end locally with `FakeLLM`; with `LLM_MODE=databricks` it runs on a real order; `eval_holdout.py` prints a table; tests cover clean_text, the category mapping, routing rules, and that the output validates against `TriageReport`.

**Kickoff prompt:**
> You are WS4. Read ARCHITECTURE.md §5 and docs/databricks_backend_spec.md §0–§6 and AGENTS.md. Build the triage pipeline in backend/triage exactly as specified: a fixed sequence of steps, 2 LLM agents, everything else plain code, behind the StatsRepo and LLM interfaces so it runs locally on gold.db with FakeLLM. The output must validate against the TriageReport schema. Don't invent metrics; eval_holdout.py computes them. Update HANDOFF.md when done.

---

### WS5: Chat agent
**Owns:** `backend/chat/**`, `backend/tests/test_chat_*.py`.
**Deliver:** `chat_reply(report, history, message, user) -> ChatMessage` with role-specific behavior (ARCHITECTURE.md §5); a fake mode; an agent mode (tool-calling loop over the OpenAI-compatible endpoint, max 4 tool calls); a read-only `run_sql` guard (single `SELECT`, gold tables only, forced `LIMIT`, rejects `;`, DDL, and DML); Genie mode.
**Tests:** `run_sql` rejects writes and non-gold tables; the requester path never calls tools.
**Done when:** fake and agent modes work locally against `gold.db`; five scripted specialist questions return answers with SQL.

**Kickoff prompt:**
> You are WS5. Read ARCHITECTURE.md §5 (Chat agent) and AGENTS.md. Implement backend/chat in your owned paths. Requester chat is context-only with no tools; specialist chat may use get_report, get_procedure, and a strictly read-only run_sql over gold tables. Security tests are required. Update HANDOFF.md when done.

---

### WS6: Databricks data layer (Databricks teammate)
**Owns:** `databricks/**`.
**Deliver:** notebooks `01_bronze`, `02_silver`, `03_gold_stats`, `04_confidence_model`, `05_app_tables` per `docs/databricks_backend_spec.md` §3–§5 and §9; a Genie space over the gold tables; the serving-endpoint name and SQL warehouse HTTP path recorded in `HANDOFF.md`. Table and column names must match what `build_local_gold.py` produces (coordinate with WS4 through HANDOFF.md).

---

### WS7: Hardware bench bridge (stretch)
**Owns:** `hardware/**`.
**Deliver:** FPGA fan-tach counter (Spartan-7 Urbana) emitting JSON lines over UART; `bridge.py` posting to `/api/orders/{id}/evidence` with `X-Device-Token`. See ARCHITECTURE.md §8.

---

## 4. Integration checklist (human integrator)

1. Merge WS3 → WS4 → WS5 → WS1 → WS2; run `pytest` and `npm run build` after each merge.
2. `PIPELINE=live LLM_MODE=fake`: submit 3 orders, check both routing paths.
3. `LLM_MODE=databricks`: same, with a real endpoint.
4. `DATA_BACKEND=databricks`: point at WS6's tables, then rerun step 3.
5. Deploy as a Databricks App and run the demo script: requester submits → auto-released; requester submits an uninformative order → escalated; specialist edits it → requester sees "specialist verified"; chat in both roles.
