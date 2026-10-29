# Triage Desk

AI failure-analysis triage for repair orders. Built for the Rockwell Automation Lifecycle Services
challenge at the SHPE AI Hackathon.

A requester submits a SAP repair order and gets a technician-ready triage report: likely cause,
affected areas, troubleshooting steps, and unit history. Orders the system isn't confident about go
to a repair specialist before anything is released. Each order has a chat for follow-up questions.

- **System design:** [ARCHITECTURE.md](ARCHITECTURE.md)
- **How the parallel coding agents work:** [AGENTS.md](AGENTS.md)
- **Databricks data layer:** [docs/databricks_backend_spec.md](docs/databricks_backend_spec.md)
- **Status by workstream:** [HANDOFF.md](HANDOFF.md)

## Run locally (no credentials needed)

```bash
# backend (Python 3.11+)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (Node 20+), in a second terminal
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
```

Sign in with either demo role. Try **New request → Fill with a sample order**; the PanelView sample
shows the escalation path.

Production-style (one server): `cd frontend && npm run build`, then run uvicorn; FastAPI serves `frontend/dist`.

## Tests

```bash
cd backend && pytest -q
cd frontend && npm run lint && npm run build
```

The troubleshooting content comes from a synthetic manual provided for the hackathon. It is not
official Rockwell Automation documentation.
