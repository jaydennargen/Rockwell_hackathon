# HANDOFF.md

Each workstream updates its own section when it finishes: what works, how to run it, what's stubbed,
known issues. See AGENTS.md.

## Contract changes
_Proposals to change backend/app/schemas.py, contracts/fixtures, or the API table. The human integrator merges these._

- **Merged (2026-10-29, approved by the user): per-category confidence.** `Confidence` gains
  `categories: [CategoryConfidence{kind: "cause"|"area", category, score, reasons[]}]`, one entry per
  predicted cause and area (default `[]`, so older payloads still validate). Specialist-only like the rest
  of `confidence`. Fixtures regenerated; ARCHITECTURE.md §4 updated.
- **For WS6: `gold_family_stats.area_dist`** (map area_category -> share of labeled orders) is a new column
  next to `cause_dist`; per-area confidence needs it. `product_family` rule is in `triage/tools.py`
  (`product_family()`) and must match the silver notebook.

## Build/local-mvp (2026-10-29): WS3 + WS4 + WS5 + UI pass in one branch
- **Run:** defaults now `DATA_BACKEND=local PIPELINE=mock LLM_MODE=fake CHAT_MODE=fake`. First start creates
  `backend/.data/app.db` and seeds it from the fixtures (`python scripts/seed_demo.py --reset` to start over).
  `PIPELINE=live` runs the real pipeline; without `gold.db` every order escalates with
  "little repair history", which is the honest answer.
- **The SAP extract lives in Databricks**, not locally. Once linked: `DATA_BACKEND=databricks` reads stats
  from Delta (`DatabricksStatsRepo`), or export the xlsx and run
  `python scripts/build_local_gold.py --xlsx <file>` to get a local `gold.db`. Then run
  `python scripts/eval_holdout.py --n 300` for accuracy vs. coverage (the only source of numbers for the pitch).
- **Triage (WS4):** `tools.py`, `agents.py` (Extraction validated with one retry), `llm.py` (FakeLLM keyword
  rules / DatabricksLLM), `confidence.py`, `pipeline.py`, `gold.py` (silver + gold build shared by both
  scripts), prompts. Confidence is hand-weighted (weights at the top of `confidence.py` are starting values,
  not measured); `CONFIDENCE_MODEL_URI` plugs in the MLflow model. Per-category reasons quote the text
  phrase and the family share ("48% of 320 past MPLB repairs had this cause").
- **Mock (`PIPELINE=mock`)** also emits per-category confidence; its reasons say
  "Mock pipeline: template score, not computed from repair history."
- **API/repo (WS3):** `repo/local.py` (SQLite, shared `SqlRepo`), `repo/databricks.py` (same SQL on Delta +
  bronze append), seed, evidence endpoint accepts specialist session or `X-Device-Token` and re-scores
  (re-routes only if not reviewed).
- **Chat (WS5):** `run_sql` guard (single SELECT, gold tables only, no `;`/comments/DDL/DML, LIMIT ≤ 200),
  `get_report`, `get_procedure`, agent tool loop (max 4 tool calls; requester gets no tools), Genie client.
  Fake mode answers from the report and, for specialists, explains routing + the weakest category.
- **UI:** plain mobile-first layout (no repair-tag styling), 44px touch targets, status pills. Specialist
  report shows "AI confidence": overall vs. threshold, why it escalated, and each cause/area with a bar
  and its reasons.
- **Not run against a workspace yet:** `DatabricksRepo`, `DatabricksStatsRepo`, `DatabricksLLM`, agent chat,
  Genie. Verify the `:param` binding, the bronze column names, and the Genie response fields on first connect.
- **Tests:** `cd backend && pytest -q` (65). Frontend lint + build clean.

## WS0: Scaffold & contracts (done)
- **Works:** every API route in ARCHITECTURE.md §4 on an in-memory repo seeded from
  `contracts/fixtures/seed_orders.json` (5 real orders from the SAP extract: 1 auto-released,
  3 needs review, 1 approved; 1 belongs to a second requester to test isolation). Demo auth with a
  signed cookie. Server-side role filtering (`app/visibility.py`). Background mock triage
  (`triage/mock.py`): uninformative text or no manual match escalates. Fake chat. Bulk upload parses
  the SAP extract's column names.
- **Frontend:** all four views working against the API for both roles, designed (repair-tag header,
  report sheet, transcript chat, review panel). Self-hosted Archivo font.
- **Tests:** `cd backend && pytest -q` (27 tests: contracts, visibility, flow, clean_text).
- **Regenerate fixtures:** `python contracts/make_fixtures.py` (from the repo root).
- **Stubbed:** `repo/local.py`, `repo/databricks.py` (WS3); `triage/pipeline.py` and friends (WS4);
  chat agent/genie modes (WS5); evidence re-scoring (TODO in `routes/orders.py`).
- **Known:** the in-memory repo resets on restart. Mock part frequencies and NPF rates were computed
  from the extract per product family but are template values, not model output.

## WS1: Frontend, requester
## WS2: Frontend, specialist
## WS3: Backend API
## WS4: Triage pipeline
- **Testbench (2026-10-29):** `python scripts/testbench.py <cases> [--history <extract>]` runs a file of test
  orders through the live pipeline and prints PASS/FAIL per case (exit 0/1/2). Cases: CSV/xlsx/JSON/SQLite with
  optional `expected_cause/area/status`, `min/max_confidence`; or a full SAP extract / gold.db graded against the
  technician labels. Test orders are removed from `--history`. `tests/test_triage_testbench.py` runs every
  `tests/cases/*_cases.*` file under pytest. Columns: `tests/cases/README.md`. `sample_history.csv` is synthetic.
## WS5: Chat agent
## WS6: Databricks data layer
## WS7: Hardware bridge
