import io
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, Request, Response, UploadFile

from app import config
from app.auth import current_user, require_specialist
from app.errors import ApiError, not_found
from app.jobs import run_triage_job
from app.repo import get_repo
from app.report_pdf import render_pdf
from app.schemas import (BulkResult, EvidenceIn, OrderCreated, OrderIn, OrderList, ReviewIn,
                         TriageReport)
from app.visibility import RELEASED, filter_report, filter_summary
from triage.confidence import rescore_with_evidence

router = APIRouter(prefix="/api/orders")

# SAP extract column -> OrderIn field (bulk upload)
SAP_COLUMNS = {
    "Order Number": "order_number", "Line Number": "line_number", "Catalog": "catalog",
    "Part Number": "part_number", "Part Description": "part_description",
    "Serial Number": "serial_number", "Depot": "depot", "Failure Details": "failure_details",
    "Additional Information": "additional_info", "Received Date": "received_date",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _visible_row(order_id: str, user: dict) -> dict:
    row = get_repo().get_order(order_id)
    if not row or (user["role"] != "specialist" and row["submitted_by"] != user["email"]):
        raise not_found()
    return row


def enrich(row: dict) -> dict:
    """Report plus what the reference repair report shows that the pipeline doesn't store: the
    distributor's comments as submitted, the PO number, and the submitter's organization (Sold To)."""
    r, o = row["report"], row["order"]
    submitter = get_repo().get_user(row["submitted_by"]) or {}
    return {**r,
            "header": {**r["header"], "purchase_order": o.get("purchase_order"), "sold_to": submitter.get("org")},
            "customer_input": {**r["customer_input"], "raw": o.get("failure_details"),
                               "additional_info": o.get("additional_info")}}


def _summary(row: dict) -> dict:
    r = row["report"]
    conf = r.get("confidence") or {}
    return {"order_id": r["order_id"], "catalog": r["header"]["catalog"],
            "part_description": r["header"]["description"], "serial_number": r["header"].get("serial"),
            "status": r["status"], "status_label": r["status"], "submitted_by": row["submitted_by"],
            "created_at": r["created_at"], "confidence_score": conf.get("score"),
            "top_reason": (conf.get("reasons") or [None])[0]}


def _processing_report(order: dict) -> dict:
    order_id = f"{order['order_number']}-{order['line_number']}"
    now = _now()
    return {"order_id": order_id, "status": "PROCESSING", "status_label": "PROCESSING",
            "created_at": now, "updated_at": now,
            "header": {"order_number": order["order_number"], "item": order["line_number"],
                       "part_number": order.get("part_number") or "", "catalog": order["catalog"],
                       "serial": order.get("serial_number"), "description": order.get("part_description") or "",
                       "depot": order.get("depot"), "received_date": order.get("received_date")},
            "customer_input": {"text": order.get("failure_details") or "", "informative": True},
            "pending_sections": ["cleaning", "testing"]}


def _submit(order: OrderIn, user: dict, tasks: BackgroundTasks) -> str:
    data = order.model_dump(mode="json")
    report = _processing_report(data)
    if get_repo().get_order(report["order_id"]):
        raise ApiError(409, "duplicate", f"Order {report['order_id']} was already submitted.")
    get_repo().create_order(data, user["email"], report)
    tasks.add_task(run_triage_job, report["order_id"])
    return report["order_id"]


@router.get("", response_model=OrderList)
def list_orders(filter: Literal["all", "needs_review", "released"] = "all", limit: int = 50,
                offset: int = 0, user: dict = Depends(current_user)):
    mine = None if user["role"] == "specialist" else user["email"]
    rows = get_repo().list_orders(submitted_by=mine)
    if filter == "needs_review":
        rows = [r for r in rows if r["report"]["status"] in ("NEEDS_REVIEW", "FAILED")]  # both need a specialist
    elif filter == "released":
        rows = [r for r in rows if r["report"]["status"] in RELEASED]
    items = [filter_summary(_summary(r), user["role"]) for r in rows[offset: offset + limit]]
    return {"items": items, "total": len(rows)}


@router.post("", response_model=OrderCreated, status_code=201)
def create_order(order: OrderIn, tasks: BackgroundTasks, user: dict = Depends(current_user)):
    return {"order_id": _submit(order, user, tasks), "status": "PROCESSING"}


@router.post("/bulk", response_model=BulkResult)
async def bulk(tasks: BackgroundTasks, file: UploadFile = File(...), user: dict = Depends(current_user)):
    import pandas as pd
    raw = await file.read()
    try:
        df = (pd.read_csv(io.BytesIO(raw)) if file.filename.lower().endswith(".csv")
              else pd.read_excel(io.BytesIO(raw)))
    except Exception:  # noqa: BLE001
        raise ApiError(400, "bad_file", "Upload a .xlsx or .csv with the SAP extract columns.")
    df = df.rename(columns=SAP_COLUMNS)
    ids, errors = [], []
    for i, rec in enumerate(df.to_dict("records"), start=2):
        rec = {k: (None if pd.isna(v) else v) for k, v in rec.items() if k in SAP_COLUMNS.values()}
        try:
            rec["order_number"] = str(rec.get("order_number") or "").split(".")[0]
            rec["line_number"] = int(rec.get("line_number") or 1000)
            if rec.get("received_date") is not None:
                rec["received_date"] = pd.Timestamp(rec["received_date"]).date()
            for k in ("serial_number", "depot", "part_number", "catalog"):
                if rec.get(k) is not None:
                    rec[k] = str(rec[k])
            ids.append(_submit(OrderIn(**rec), user, tasks))
        except Exception as e:  # noqa: BLE001
            msg = e.detail["message"] if isinstance(e, ApiError) else str(e).splitlines()[0]
            errors.append({"row": i, "message": msg})
    return {"order_ids": ids, "errors": errors}


@router.get("/{order_id}", response_model=TriageReport, response_model_exclude_none=True)
def get_order(order_id: str, user: dict = Depends(current_user)):
    return filter_report(enrich(_visible_row(order_id, user)), user["role"])


@router.get("/{order_id}/report.pdf", include_in_schema=True)
def report_pdf(order_id: str, user: dict = Depends(current_user)):
    """The repair report as a PDF in the reference SAP layout, filtered by role like GET /{order_id}."""
    report = TriageReport.model_validate(filter_report(enrich(_visible_row(order_id, user)), user["role"]))
    pdf = render_pdf(report.model_dump(mode="json", by_alias=True))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="repair-report-{order_id}.pdf"'})


@router.post("/{order_id}/review", response_model=TriageReport, response_model_exclude_none=True)
def review(order_id: str, body: ReviewIn, user: dict = Depends(require_specialist)):
    row = _visible_row(order_id, user)
    report = dict(row["report"])
    if report["status"] in ("PROCESSING", "FAILED"):
        raise ApiError(409, "not_ready", "This order hasn't finished processing.")
    c = body.corrections
    if body.decision == "edit" and c:
        pred = dict(report.get("predicted") or {"areas": [], "causes": [], "rationale": ""})
        if c.areas is not None:
            pred["areas"] = [a.model_dump() for a in c.areas]
        if c.causes is not None:
            pred["causes"] = list(c.causes)
        report["predicted"] = pred
        if c.parts is not None:
            report["parts_to_prestage"] = [{"part": p, "freq": 0.0, "n": 0} for p in c.parts]
    report["status"] = {"approve": "APPROVED", "edit": "EDITED", "reject": "REJECTED"}[body.decision]
    report["review"] = {"decision": body.decision, "notes": body.notes, "reviewer": user["email"],
                        "reviewed_at": _now()}
    report["updated_at"] = _now()
    get_repo().save_report(order_id, report)
    get_repo().add_feedback(order_id, {**body.model_dump(mode="json"), "reviewer": user["email"]})
    return filter_report(enrich({**row, "report": report}), user["role"])


@router.post("/{order_id}/evidence", response_model=TriageReport, response_model_exclude_none=True)
def evidence(order_id: str, body: EvidenceIn, request: Request, x_device_token: str | None = Header(default=None)):
    if not config.DEVICE_TOKEN or x_device_token != config.DEVICE_TOKEN:  # unset token = device auth off
        try:
            require_specialist(current_user(request))
        except ApiError:
            raise ApiError(401, "unauthenticated", "Sign in as a specialist or send a valid device token.")
    row = get_repo().get_order(order_id)
    if not row:
        raise not_found()
    ms = []
    for m in body.measurements:
        d = m.model_dump(by_alias=True)
        if d.get("pass") is None and (m.spec_min is not None or m.spec_max is not None):
            d["pass"] = (m.spec_min is None or m.value >= m.spec_min) and (m.spec_max is None or m.value <= m.spec_max)
        d["source"] = body.source
        ms.append(d)
    report = dict(row["report"])
    report["bench_evidence"] = (report.get("bench_evidence") or []) + ms
    report["updated_at"] = _now()
    report = rescore_with_evidence(report)
    get_repo().save_report(order_id, report)
    get_repo().add_evidence(order_id, ms)
    return filter_report(enrich({**row, "report": report}), "specialist")


@router.post("/{order_id}/retry", response_model=OrderCreated)
def retry(order_id: str, tasks: BackgroundTasks, user: dict = Depends(require_specialist)):
    row = _visible_row(order_id, user)
    report = {**row["report"], "status": "PROCESSING", "error": None, "updated_at": _now()}
    get_repo().save_report(order_id, report)
    tasks.add_task(run_triage_job, order_id)
    return {"order_id": order_id, "status": "PROCESSING"}
