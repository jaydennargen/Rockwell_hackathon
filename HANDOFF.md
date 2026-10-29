# HANDOFF.md

Each workstream updates its own section when it finishes: what works, how to run it, what's stubbed,
known issues. See AGENTS.md.

## Contract changes
_Proposals to change backend/app/schemas.py, contracts/fixtures, or the API table. The human integrator merges these._

(none)

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
## WS5: Chat agent
## WS6: Databricks data layer
## WS7: Hardware bridge
