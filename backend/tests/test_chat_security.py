import json
import sqlite3
from types import SimpleNamespace

import pytest

from chat import agent, tools
from triage.stats_repo import LocalStatsRepo


@pytest.mark.parametrize("q", [
    "DELETE FROM gold_part_freq",
    "SELECT * FROM gold_part_freq; DROP TABLE gold_part_freq",
    "UPDATE gold_family_stats SET n_labeled = 0",
    "SELECT * FROM app_users",
    "SELECT * FROM gold_part_freq JOIN app_chat_messages ON 1=1",
    "SELECT * FROM silver_repairs",
    "SELECT * FROM gold_part_freq -- comment",
    "CREATE TABLE x AS SELECT * FROM gold_part_freq",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "SELECT 1",
])
def test_run_sql_rejects(q):
    with pytest.raises(tools.SqlRejected):
        tools.validate_sql(q)


def test_run_sql_forces_limit():
    assert tools.validate_sql("SELECT part FROM gold_part_freq")[0].endswith("LIMIT 200")
    assert tools.validate_sql("SELECT part FROM gold_part_freq LIMIT 5000")[0].endswith("LIMIT 200")
    assert tools.validate_sql("SELECT part FROM hackathon.triage.gold_part_freq LIMIT 3")[0].endswith("LIMIT 3")


def test_run_sql_executes_read_only(tmp_path):
    db = tmp_path / "gold.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE gold_part_freq (product_family, cause_category, part, count, freq)")
        con.execute("INSERT INTO gold_part_freq VALUES ('1394','wear_out','FAN',10,0.5)")
    out = tools.run_sql("SELECT part, count FROM gold_part_freq", LocalStatsRepo(db))
    assert out["rows"] == [["FAN", 10]] and out["sql"].endswith("LIMIT 200")
    assert "error" in tools.run_sql("DELETE FROM gold_part_freq", LocalStatsRepo(db))


class _Client:
    """Records every create() call; answers without tool calls."""
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))])


REPORT = {"order_id": "1-1000", "status": "AUTO_RELEASED", "predicted": {"causes": ["wear_out"], "areas": []},
          "procedure": {"title": "Fan", "steps": ["Check fan"]}}


def test_requester_path_never_gets_tools():
    c = _Client()
    reply = agent._agent_reply(REPORT, [], "what's wrong?", {"role": "requester"}, client=c)
    assert reply["content"] == "ok" and "sql" not in {k for k, v in reply.items() if v}
    assert all("tools" not in kw for kw in c.calls)
    assert "SELECT" not in c.calls[0]["messages"][0]["content"].split("REPORT:")[0]


def test_specialist_tool_loop_runs_sql(tmp_path, monkeypatch):
    call = SimpleNamespace(id="t1", function=SimpleNamespace(
        name="run_sql", arguments=json.dumps({"query": "SELECT part FROM gold_part_freq"})),
        model_dump=lambda: {"id": "t1", "type": "function", "function": {"name": "run_sql", "arguments": "{}"}})
    answers = iter([[call], None])
    c = _Client()
    c.chat.completions.create = lambda **kw: (c.calls.append(kw) or SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content="FAN is most common", tool_calls=next(answers)))]))
    monkeypatch.setattr(agent, "_run_tool", lambda name, args: {"sql": "SELECT part FROM gold_part_freq LIMIT 200",
                                                               "tables": ["gold_part_freq"], "rows": [["FAN"]]})
    reply = agent._agent_reply(REPORT, [], "top part?", {"role": "specialist"}, client=c)
    assert "tools" in c.calls[0] and reply["sql"].endswith("LIMIT 200")
    assert any(s["ref"] == "table:gold_part_freq" for s in reply["sources"])
