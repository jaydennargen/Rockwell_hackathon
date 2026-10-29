"""Demo seed: users + the orders in contracts/fixtures/seed_orders.json (+ one chat transcript)."""
import json

from app import config

DEMO_USERS = {"requester": "requester@vanmeter.demo", "specialist": "specialist@rockwell.demo"}  # demo-login picks these
OTHER_REQUESTER = {"email": "orders@midwestcontrols.demo", "name": "Sam Patel",
                   "role": "requester", "org": "Midwest Controls Supply"}


def demo_data(path=config.FIXTURES):
    users = [json.loads((path / f).read_text()) for f in ("me_requester.json", "me_specialist.json")]
    users.append(OTHER_REQUESTER)
    orders = json.loads((path / "seed_orders.json").read_text())
    released = next(s for s in orders if s["report"]["status"] == "AUTO_RELEASED")
    chat = {(released["report"]["order_id"], released["submitted_by"]):
            json.loads((path / "chat_history.json").read_text())["messages"]}
    return users, orders, chat


def seed_demo(repo) -> None:
    users, orders, chat = demo_data()
    for u in users:
        repo.add_user(u)
    for s in orders:
        if not repo.get_order(s["report"]["order_id"]):
            repo.create_order(s["order"], s["submitted_by"], s["report"])
    for (oid, email), msgs in chat.items():
        if not repo.chat_history(oid, email):
            for m in msgs:
                repo.add_chat(oid, email, m)
