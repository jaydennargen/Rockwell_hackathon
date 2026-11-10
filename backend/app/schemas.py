"""API contract: the source of truth for every request/response shape.

FROZEN after WS0. To change anything here, add a proposal under "Contract changes"
in HANDOFF.md (see AGENTS.md §1.2). Example payloads: contracts/fixtures/*.json.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Role = Literal["requester", "specialist"]

Status = Literal[
    "PROCESSING", "AUTO_RELEASED", "NEEDS_REVIEW", "APPROVED", "EDITED", "REJECTED", "FAILED"
]

AreaCategory = Literal[
    "pcba_circuitry", "fan_cooling", "motor_mechanical", "hmi_display", "enclosure_wiring", "other"
]

CauseCategory = Literal[
    "component_failure", "wear_out", "contamination", "physical_damage",
    "configuration_error", "no_problem_found", "external_electrical",
]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---------- auth ----------
class User(BaseModel):
    email: str
    name: str
    role: Role
    org: str


class DemoLoginIn(BaseModel):
    role: Role


# ---------- orders ----------
class OrderIn(BaseModel):
    order_number: str = Field(min_length=1)
    line_number: int = 1000
    catalog: str = Field(min_length=1)
    part_number: str = ""
    part_description: str = ""
    serial_number: Optional[str] = None
    depot: Optional[str] = None
    failure_details: str = ""
    additional_info: Optional[str] = None
    received_date: Optional[date] = None
    purchase_order: Optional[str] = None


class OrderCreated(BaseModel):
    order_id: str
    status: Status


class OrderSummary(BaseModel):
    order_id: str
    catalog: str
    part_description: str
    serial_number: Optional[str] = None
    status: Status
    status_label: str
    submitted_by: str
    created_at: datetime
    confidence_score: Optional[float] = None  # specialist only
    top_reason: Optional[str] = None          # specialist only


class OrderList(BaseModel):
    items: list[OrderSummary]
    total: int


class BulkResult(BaseModel):
    order_ids: list[str]
    errors: list[dict]


# ---------- report ----------
class Header(BaseModel):
    order_number: str
    item: int
    part_number: str
    catalog: str
    serial: Optional[str] = None
    description: str
    depot: Optional[str] = None
    received_date: Optional[date] = None
    purchase_order: Optional[str] = None  # as entered on the order
    sold_to: Optional[str] = None         # submitter's organization (app_users.org)


class CustomerInput(BaseModel):
    text: str
    informative: bool
    raw: Optional[str] = None             # distributor's comments exactly as submitted
    additional_info: Optional[str] = None


class Escalation(BaseModel):
    message: str
    reasons: list[str]


class Area(BaseModel):
    category: AreaCategory
    detail: str


class Predicted(BaseModel):
    areas: list[Area]
    causes: list[CauseCategory]
    rationale: str


class Procedure(BaseModel):
    section: Optional[int] = None  # None = general protocol
    title: str
    synthetic: Literal[True] = True
    loto_required: bool
    steps: list[str]


class HistoryItem(BaseModel):
    order_id: str
    date: date
    causes: list[CauseCategory]


class Review(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    notes: Optional[str] = None
    reviewer: str
    reviewed_at: datetime


class CategoryConfidence(BaseModel):
    """Confidence in one predicted cause or area, with the plain-language signals behind it."""
    kind: Literal["cause", "area"]
    category: str  # a CauseCategory when kind == "cause", an AreaCategory when kind == "area"
    score: float
    reasons: list[str]


class Confidence(BaseModel):
    score: float
    threshold: float
    reasons: list[str]                                   # routing rules that fired
    categories: list[CategoryConfidence] = []            # one per predicted cause and area


class PartPrediction(BaseModel):
    part: str
    freq: float  # share of past orders (same family + cause) that used this part
    n: int       # number of past orders behind that share


class NpfRisk(BaseModel):
    family_rate: float
    flag: bool


class Measurement(BaseModel):
    name: str
    value: float
    unit: str
    spec_min: Optional[float] = None
    spec_max: Optional[float] = None
    pass_: Optional[bool] = Field(default=None, alias="pass")
    source: Optional[str] = None

    model_config = {"populate_by_name": True}


class TriageReport(BaseModel):
    order_id: str
    status: Status
    status_label: str
    created_at: datetime
    updated_at: datetime
    header: Header
    customer_input: CustomerInput
    escalation: Optional[Escalation] = None      # requester view of NEEDS_REVIEW only
    summary: Optional[str] = None
    predicted: Optional[Predicted] = None
    procedure: Optional[Procedure] = None
    unit_history: Optional[list[HistoryItem]] = None
    review: Optional[Review] = None
    # specialist only below
    confidence: Optional[Confidence] = None
    parts_to_prestage: Optional[list[PartPrediction]] = None
    npf_risk: Optional[NpfRisk] = None
    bench_evidence: Optional[list[Measurement]] = None
    trace_id: Optional[str] = None
    error: Optional[str] = None
    pending_sections: list[str] = ["cleaning", "testing"]


# ---------- review / evidence ----------
class Corrections(BaseModel):
    areas: Optional[list[Area]] = None
    causes: Optional[list[CauseCategory]] = None
    parts: Optional[list[str]] = None


class ReviewIn(BaseModel):
    decision: Literal["approve", "edit", "reject"]
    corrections: Optional[Corrections] = None
    notes: Optional[str] = None


class EvidenceIn(BaseModel):
    source: str
    measurements: list[Measurement]


# ---------- chat ----------
class Source(BaseModel):
    label: str
    ref: str


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    sql: Optional[str] = None
    sources: Optional[list[Source]] = None
    created_at: datetime


class ChatHistory(BaseModel):
    messages: list[ChatMessage]


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatReply(BaseModel):
    reply: ChatMessage
