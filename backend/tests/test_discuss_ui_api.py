# -*- coding: utf-8 -*-
"""讨论群详情返回 ``answers``（规格 4.3、6.4）。

全部离线：方案步骤走 ``LLMRouter(dry_run=True, fake=FakeLLM(...))``，
限流器关闭；数据库与网络隔离沿用 ``conftest`` 的 ``client`` 夹具。
"""
import asyncio
import json
import time

import pytest

from discuss import runner
from discuss import store as discuss_store
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from rate_limit import limiter

USER = "discuss_ui_author"
HEADERS = {"X-Dev-User": USER}

PLAN = {
    "title": "讨论群界面测试方案",
    "goal": "确认详情能读回作者的补充回答",
    "deliverable": {"kind": "report", "outline": ["背景", "发现", "建议"]},
    "criteria": ["每个结论有来源", "覆盖两个调研方向", "给出明确建议"],
    "picks": [{"role": "market", "focus": "查市场"},
              {"role": "tech", "focus": "查技术"}],
    "questions": ["你更关心成本还是落地？"],
}
RESPONSES = {"plan": PLAN}

MISSING = object()


@pytest.fixture
def workshop(client, monkeypatch):
    """开关、白名单、限流与离线模型，写法照 ``test_discuss_api.py``。"""
    monkeypatch.setenv("FIONA_DISCUSS", "1")
    monkeypatch.setenv("FIONA_DISCUSS_USERS", USER)
    monkeypatch.setattr(limiter, "enabled", False)
    fake = FakeLLM(dict(RESPONSES))
    monkeypatch.setattr(
        runner, "router_factory",
        lambda store, username, group_id, run_token: LLMRouter(
            store, dry_run=True, fake=fake))
    return client


def create_group(client):
    response = client.post("/discuss/groups", json={
        "request": "帮我研究一下这个方向",
        "budget_strawberries": 500,
        "max_rounds": 2,
        "avatar": False,
    }, headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def ready_group(client):
    """建群并等到主持人出完方案，返回群 ID。"""
    group_id = create_group(client)
    data = None
    for _ in range(600):
        response = client.get(f"/discuss/groups/{group_id}", headers=HEADERS)
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] == "awaiting_start":
            return group_id
        if data["status"] in ("failed", "paused"):
            pytest.fail("群意外停下：" + str(data))
        time.sleep(0.01)
    pytest.fail("等待方案超时：" + str(data))


def stored_config(group_id):
    group = asyncio.run(discuss_store.get_group(USER, group_id))
    assert group is not None
    return dict(group["config"])


def write_config(group_id, config):
    """绕过接口直接更新数据库里的 ``config_json``。"""
    asyncio.run(discuss_store.update_group(
        USER, group_id, config_json=json.dumps(config, ensure_ascii=False)))


def get_answers(client, group_id):
    response = client.get(f"/discuss/groups/{group_id}", headers=HEADERS)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "answers" in data
    return data["answers"]


def test_detail_defaults_answers_to_empty_string(workshop):
    """详情默认返回 ``answers == ""``。"""
    group_id = ready_group(workshop)
    assert get_answers(workshop, group_id) == ""


def test_patch_plan_answers_round_trips_through_detail(workshop):
    """PATCH 写入回答后，接口返回与再次读取的详情都是同样的文字。"""
    client = workshop
    group_id = ready_group(client)
    before = client.get(f"/discuss/groups/{group_id}", headers=HEADERS).json()
    answers = "我更关心成本，预算控制在 500 颗以内。"

    response = client.patch(f"/discuss/groups/{group_id}/plan", json={
        "expected_revision": before["plan_revision"],
        "answers": answers,
    }, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["answers"] == answers
    assert get_answers(client, group_id) == answers


def test_detail_treats_non_string_answers_as_empty(workshop):
    """``config_json.answers`` 缺失或不是字符串时返回空字符串。"""
    client = workshop
    group_id = ready_group(client)
    cases = [
        (MISSING, "缺失"),
        (None, "None"),
        (42, "整数"),
        (True, "布尔"),
        (["一段回答"], "数组"),
        ({"text": "一段回答"}, "对象"),
    ]
    for value, label in cases:
        config = stored_config(group_id)
        if value is MISSING:
            config.pop("answers", None)
        else:
            config["answers"] = value
        write_config(group_id, config)
        assert get_answers(client, group_id) == "", label
