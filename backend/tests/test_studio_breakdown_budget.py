"""WO3c 共用导演额度门禁：离线预检先于任何付费调用。"""
import asyncio

import pytest

import auth
import database
from studio import brain, brain_jobs, sources, store


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def budget_author(client, monkeypatch):
    owner = "wo3c-budget-author"
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", owner)
    account = run(database.get_or_create_user(owner))
    headers = {"Authorization": "Bearer " + auth.create_token(owner, account["session_version"])}
    project = run(store.create_project(owner, "归还旧书", "16:9"))
    calls = []

    async def options(_owner):
        return [{"id": name, "available": True, "label": name, "model": model}
                for name, model in (("qwen", "qwen3.8-max"), ("deepseek", "deepseek-v4-pro"),
                                    ("claude", "claude-sonnet-5-5"))]

    async def forbidden_provider(*args, **kwargs):
        calls.append(args)
        pytest.fail("超限报价不得创建 provider 或发起请求")

    monkeypatch.setattr(brain, "provider_options", options)
    monkeypatch.setattr(brain, "get_provider", forbidden_provider)
    monkeypatch.setattr(brain_jobs, "_schedule", lambda _jid: pytest.fail("超限不得调度"))
    return project, headers, calls


@pytest.mark.parametrize("provider", ["qwen", "deepseek"])
@pytest.mark.parametrize("endpoint", ["quote", "trial"])
def test_existing_director_tasks_enforce_single_quote_cap(client, budget_author, monkeypatch, provider, endpoint):
    project, headers, calls = budget_author
    run(brain_jobs.patch_project(project["id"], project["owner"], provider))
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "0.00000001")
    response = client.post(f"/studio/projects/{project['id']}/brain/{endpoint}", headers=headers,
                           json={"text": "阿宁把借来的旧书放回门边。", "tasks": ["read_through"]})
    assert response.status_code == 409
    assert "单次报价上限" in response.json()["detail"]
    assert "超出" in response.json()["detail"]
    assert calls == []

    async def count():
        async with store.connection() as db:
            return (await store._one(db, "SELECT count(*) AS n FROM studio_jobs"))["n"]
    assert run(count()) == 0


@pytest.mark.parametrize("provider,setting,currency", [
    ("qwen", "FIONA_STUDIO_DAILY_CNY", "¥"),
    ("claude", "FIONA_STUDIO_BRAIN_MONTHLY_USD", "$"),
])
def test_budget_rejection_reports_shortage_before_any_call(client, budget_author, monkeypatch,
                                                          provider, setting, currency):
    project, headers, calls = budget_author
    run(brain_jobs.patch_project(project["id"], project["owner"], provider))
    monkeypatch.setenv(setting, "0.00000001")
    response = client.post(f"/studio/projects/{project['id']}/brain/quote", headers=headers,
                           json={"text": "阿宁归还旧书。", "tasks": ["read_through"]})
    assert response.status_code == 409
    assert "还差 " + currency in response.json()["detail"]
    assert calls == []


@pytest.mark.parametrize('provider,setting,reason', [
    ('qwen', 'FIONA_STUDIO_MAX_QUOTE_CNY', '单次报价上限'),
    ('deepseek', 'FIONA_STUDIO_MAX_QUOTE_CNY', '单次报价上限'),
    ('qwen', 'FIONA_STUDIO_DAILY_CNY', '今日额度不足'),
    ('claude', 'FIONA_STUDIO_BRAIN_MONTHLY_USD', 'Claude 本月额度不足'),
])
def test_breakdown_quote_caps_reject_before_jobs_or_provider(client, budget_author, monkeypatch,
                                                           provider, setting, reason):
    blank, headers, calls = budget_author
    project = run(sources.create_text_project(blank['owner'], 'paste', '门房的旧书', '阿宁来到门房，决定把旧书归还原主。'))
    run(brain_jobs.patch_project(project['id'], blank['owner'], provider))
    monkeypatch.setenv(setting, '0.00000001')
    response = client.post(f"/studio/projects/{project['id']}/breakdown/quote", headers=headers, json={})
    assert response.status_code == 409
    assert reason in response.json()['detail']
    assert calls == []

    async def counts():
        async with store.connection() as db:
            return [(await store._one(db, f'SELECT count(*) AS n FROM {table}'))['n']
                    for table in ('studio_jobs', 'studio_quotes', 'studio_breakdowns')]
    assert run(counts()) == [0, 0, 0]
