"""Fixtures must validate against the frozen schemas."""
import json
from pathlib import Path

import pytest

from app import schemas

FIX = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"
CASES = {
    "me_requester.json": schemas.User, "me_specialist.json": schemas.User,
    "order_in.json": schemas.OrderIn,
    "orders_list_requester.json": schemas.OrderList, "orders_list_specialist.json": schemas.OrderList,
    "report_full_auto_released.json": schemas.TriageReport,
    "report_full_needs_review.json": schemas.TriageReport,
    "report_requester_released.json": schemas.TriageReport,
    "report_requester_escalated.json": schemas.TriageReport,
    "chat_history.json": schemas.ChatHistory, "chat_reply.json": schemas.ChatReply,
}


@pytest.mark.parametrize("name,model", CASES.items())
def test_fixture_validates(name, model):
    model.model_validate(json.loads((FIX / name).read_text()))


def test_seed_reports_validate():
    for s in json.loads((FIX / "seed_orders.json").read_text()):
        schemas.OrderIn.model_validate(s["order"])
        schemas.TriageReport.model_validate(s["report"])
