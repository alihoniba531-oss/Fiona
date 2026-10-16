"""Split alternative replies survive the actual offline pilot and HTTP workflows."""

import asyncio
import json
from pathlib import Path
import socket
import time

import pytest

from novel import runner
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.pilot import run_experiment
from novel.report import generate_report
from novel.store_db import get_db
from rate_limit import limiter


DECISIONS = {"adopt": "采纳", "partial": "部分采纳", "reject": "不采纳"}
ROLES = ("plot_architect", "character_advocate", "twist_designer")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("alternative record regressions must use the offline engine")
    monkeypatch.setattr(LLMRouter, "_single_real_call", forbidden)
    for name in ("connect", "connect_ex"):
        original = getattr(socket.socket, name)
        def guarded(sock, address, original=original):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                forbidden()
            return original(sock, address)
        monkeypatch.setattr(socket.socket, name, guarded)


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _pilot_config():
    value = _read(Path(__file__).parents[1] / "novel/pilot_configs/expA2.json")
    value["chapters_per_arm"] = 1
    return value


def _fake_with_three_alternatives(style="new"):
    fake = FakeLLM()
    def script(request, index):
        if request["task"] == "critique_plan":
            result = fake.default_response(request)
            result["alternative"] = f"保留{request['role']}提出的证据核对替代走向。"
            return result
        if request["task"] != "finalize":
            return None
        result = fake.default_response(request)
        for item, decision in zip(result["alternative_responses"], DECISIONS):
            item["decision"] = decision
            item["response"] = f"{item['alternative_id']}的独立理由：先呈现原始记录，再让主角选择公开范围。"
        if style in ("legacy", "mixed"):
            selected = result["alternative_responses"] if style == "legacy" else result["alternative_responses"][:1]
            for item in selected:
                result["objection_responses"].append({
                    "objection_id": item["alternative_id"],
                    "response": DECISIONS[item["decision"]] + "：" + item["response"],
                })
            result["alternative_responses"] = [item for item in result["alternative_responses"] if item not in selected]
            if style == "legacy":
                result.pop("alternative_responses")
        return result
    fake.script = script
    return fake


def test_p0_critique_default_dry_run_persists_split_alternative_responses(tmp_path):
    assert asyncio.run(run_experiment(_pilot_config(), tmp_path, dry_run=True)) == 0
    folder = tmp_path / "arm-panel/ch001"
    record = _read(folder / "chapter_record.json")
    step = _read(folder / "03-finalize-editor.json")
    decision = record["meeting"]["decision"]
    assert decision == step["result"]
    assert decision["alternative_responses"]
    assert all(item["objection_id"].startswith("O") for item in decision["objection_responses"])
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    for item in decision["alternative_responses"]:
        assert "替代走向 " + item["alternative_id"] in report
        assert "主编决定：" + DECISIONS[item["decision"]] in report
        assert item["response"] in report
    solo = _read(tmp_path / "arm-solo/ch001/chapter_record.json")["meeting"]["decision"]
    assert "alternative_responses" not in solo


@pytest.mark.parametrize("style", ["new", "legacy", "mixed"])
def test_critique_report_displays_each_alternative_decision_and_reason_for_both_formats(tmp_path, style):
    fake = _fake_with_three_alternatives(style)
    assert asyncio.run(run_experiment(_pilot_config(), tmp_path, dry_run=True, fake=fake)) == 0
    decision = _read(tmp_path / "arm-panel/ch001/chapter_record.json")["meeting"]["decision"]
    report = generate_report(tmp_path).split("## arm-solo", 1)[0]
    for identifier, label in zip(("A1", "A2", "A3"), DECISIONS.values()):
        line = next(line for line in report.splitlines() if line.startswith("替代走向 " + identifier))
        assert label in line and identifier + "的独立理由" in line
    if style == "new":
        assert {item["decision"] for item in decision["alternative_responses"]} == set(DECISIONS)
    elif style == "legacy":
        assert "alternative_responses" not in decision
        assert {item["objection_id"] for item in decision["objection_responses"] if item["objection_id"].startswith("A")} == {"A1", "A2", "A3"}
    else:
        assert len(decision["alternative_responses"]) == 2


def _wait(client, novel_id, state, headers):
    for _ in range(500):
        response = client.get(f"/novels/{novel_id}", headers=headers)
        assert response.status_code == 200, response.text
        book = response.json()
        if book["status"] == state:
            return book
        assert book["status"] not in ("failed", "paused"), book
        time.sleep(.01)
    pytest.fail(f"workshop did not reach {state}")


@pytest.mark.parametrize("style,automation", [
    ("new", "full_auto"), ("legacy", "full_auto"), ("new", "per_chapter"),
])
def test_chapter_http_endpoint_returns_alternative_replies_saved_by_the_engine(client, monkeypatch, style, automation):
    username = "alternative_records_author"
    headers = {"X-Dev-User": username}
    monkeypatch.setenv("FIONA_NOVEL", "1")
    monkeypatch.setenv("FIONA_NOVEL_USERS", username)
    monkeypatch.setattr(limiter, "enabled", False)
    fake = _fake_with_three_alternatives(style)
    monkeypatch.setattr(runner, "router_factory", lambda store, *args: LLMRouter(store, dry_run=True, fake=fake))
    agents = {role: "dashscope:qwen3.8-max" for role in ("editor", "archivist", "reviewer", *ROLES)}
    agents["writer"] = "deepseek:deepseek-flash"
    response = client.post("/novels", headers=headers, json={
        "seed_idea": "核对旧案档案，并决定如何保护证人。", "agents": agents,
        "panel_mode": "critique", "automation": automation, "budget_strawberries": 100000,
        "target": {"min_chapters": 1, "max_chapters": 1, "chapter_words": 1000},
    })
    assert response.status_code == 201, response.text
    novel_id = response.json()["id"]
    _wait(client, novel_id, "awaiting_setup", headers)
    response = client.post(f"/novels/{novel_id}/setup/approve", headers=headers, json={})
    assert response.status_code == 200, response.text
    if automation == "per_chapter":
        _wait(client, novel_id, "awaiting_plan", headers)
        planned = client.get(f"/novels/{novel_id}/chapters/1", headers=headers)
        assert planned.status_code == 200, planned.text
        pending = planned.json()["meeting"]
        assert [item["id"] for item in pending["objections"]] == ["O1", "O2", "O3", "A1", "A2", "A3"]
        before = pending["decision"]["alternative_responses"]
        assert [item["decision"] for item in before] == list(DECISIONS)
        async def saved_plan():
            async with get_db() as db:
                async with db.execute("SELECT meeting_json FROM novel_chapters WHERE novel_id=? AND chapter=1 AND status='awaiting_plan_approval'", (novel_id,)) as cursor:
                    return json.loads((await cursor.fetchone())[0])
        assert pending == asyncio.run(saved_plan())
        beat = pending["decision"]["beat_sheet"]
        beat["title"] = "作者确认的交接记录"
        response = client.post(f"/novels/{novel_id}/plan/approve", headers=headers, json={"beat_sheet": beat})
        assert response.status_code == 200, response.text
    _wait(client, novel_id, "awaiting_end", headers)
    response = client.get(f"/novels/{novel_id}/chapters/1", headers=headers)
    assert response.status_code == 200, response.text
    meeting = response.json()["meeting"]
    async def persisted():
        async with get_db() as db:
            async with db.execute("SELECT meeting_json FROM novel_chapters WHERE novel_id=? AND chapter=1", (novel_id,)) as cursor:
                return json.loads((await cursor.fetchone())[0])
    assert meeting == asyncio.run(persisted())
    decision = meeting["decision"]
    if automation == "per_chapter":
        assert decision["alternative_responses"] == before
        assert decision["beat_sheet"]["title"] == "作者确认的交接记录"
        assert response.json()["title"] == "作者确认的交接记录"
    if style == "new":
        assert decision["alternative_responses"] == [
            {"alternative_id": identifier, "decision": choice,
             "response": f"{identifier}的独立理由：先呈现原始记录，再让主角选择公开范围。"}
            for identifier, choice in zip(("A1", "A2", "A3"), DECISIONS)
        ]
        assert {item["objection_id"] for item in decision["objection_responses"]} == {"O1", "O2", "O3"}
    else:
        assert "alternative_responses" not in decision
        assert {item["objection_id"] for item in decision["objection_responses"] if item["objection_id"].startswith("A")} == {"A1", "A2", "A3"}
    assert any(call["task"] == "write" for call in fake.calls)
    assert any(call["task"] == "archive" for call in fake.calls)
