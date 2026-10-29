"""In-memory repo seeded from contracts/fixtures (WS0). Resets on restart.
WS3 adds local.py (SQLite) and databricks.py with the same interface."""
import copy
import json
from pathlib import Path
from typing import Optional


class MemoryRepo:
    def __init__(self, users: list[dict], seed: list[dict], chat: dict):
        self.users = {u["email"]: u for u in users}
        self.orders: dict[str, dict] = {}
        for s in seed:
            self.orders[s["report"]["order_id"]] = copy.deepcopy(s)
        self.chat = chat
        self.feedback: list[dict] = []
        self.evidence: list[dict] = []

    @classmethod
    def from_fixtures(cls, path: Path) -> "MemoryRepo":
        users = [json.loads((path / f).read_text()) for f in ("me_requester.json", "me_specialist.json")]
        users.append({"email": "orders@midwestcontrols.demo", "name": "Sam Patel",
                      "role": "requester", "org": "Midwest Controls Supply"})
        seed = json.loads((path / "seed_orders.json").read_text())
        released = next(s for s in seed if s["report"]["status"] == "AUTO_RELEASED")
        history = json.loads((path / "chat_history.json").read_text())["messages"]
        chat = {(released["report"]["order_id"], released["submitted_by"]): history}
        return cls(users, seed, chat)

    # users
    def get_user(self, email: str) -> Optional[dict]:
        return self.users.get(email)

    def user_for_role(self, role: str) -> dict:
        return next(u for u in self.users.values() if u["role"] == role)

    # orders
    def create_order(self, order, submitted_by, report):
        self.orders[report["order_id"]] = {"submitted_by": submitted_by, "order": order, "report": report}

    def get_order(self, order_id):
        return self.orders.get(order_id)

    def list_orders(self, submitted_by=None):
        rows = [o for o in self.orders.values() if submitted_by in (None, o["submitted_by"])]
        return sorted(rows, key=lambda o: o["report"]["created_at"], reverse=True)

    def save_report(self, order_id, report):
        self.orders[order_id]["report"] = report

    def add_feedback(self, order_id, feedback):
        self.feedback.append({"order_id": order_id, **feedback})

    def add_evidence(self, order_id, measurements):
        self.evidence.extend({"order_id": order_id, **m} for m in measurements)

    # chat
    def chat_history(self, order_id, email):
        return list(self.chat.get((order_id, email), []))

    def add_chat(self, order_id, email, message):
        self.chat.setdefault((order_id, email), []).append(message)
