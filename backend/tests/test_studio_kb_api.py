"""WO3e B 块：知识库接口、试拆报价、确认、执行与查询。

全部使用假导演提供方和假知识库函数，不发真实网络请求。
"""
import asyncio
import json

import pytest

import auth
import database
from studio import brain, brain_jobs, cross_review, kb_trial, pricing, recovery, spend, store
from studio.brain_tasks import get_task


def run(coro):
    return asyncio.run(coro)


async def rows(sql, params=()):
    async with store.connection() as db:
        return await store._many(db, sql, params)


SHOTS = [
    {"no": 1, "beat": "建立双方位置", "shot_size": "中景", "angle": "平视侧拍",
     "camera": "固定机位", "action": "叶岚把钥匙放在操作台上，周默看向钥匙",
     "first_frame_prompt": "两人隔着操作台，钥匙在台面中央，侧向平视",
     "video_prompt": "叶岚放下钥匙，周默视线落向钥匙，镜头不动",
     "dialogue": "", "sound_intent": "烤箱底噪", "duration_s": 3.5,
     "sensitive": [], "basis": []},
    {"no": 2, "beat": "关键台词", "shot_size": "近景", "angle": "侧后 45°",
     "camera": "固定机位", "action": "周默说出决定，手指按在台边",
     "first_frame_prompt": "周默侧后 45°，不看镜头，手指按着台边",
     "video_prompt": "周默说完后手指收紧，镜头保持不动",
     "dialogue": "今晚我来收店。", "sound_intent": "台词与轻微环境声", "duration_s": 4.5,
     "sensitive": [], "basis": []},
]

REVIEW = {"verdict": "issues", "summary": "镜 2 的台词可以落到更具体的动作上。",
          "issues": [
              {"severity": "must", "kind": "storyboard", "where": "镜 1",
               "source_ref": None, "problem": "缺少抛钥匙的动作", "suggestion": "补一个手部插入镜"},
              {"severity": "should", "kind": "continuity", "where": "镜 2",
               "source_ref": "第 2 段", "problem": "钥匙位置跨镜不一致", "suggestion": "锁住钥匙在操作台左侧"},
          ]}


@pytest.fixture
def kb(client, monkeypatch):
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", "kb-owner,kb-other")
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "1")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_MONTHLY_USD", "40")
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_DEFAULT", "qwen")

    accounts = {}
    for username in ("kb-owner", "kb-other"):
        user = run(database.get_or_create_user(username))
        accounts[username] = {"Authorization": f"Bearer {auth.create_token(username, user['session_version'])}"}

    state = {"review": "qwen", "calls": [], "scheduled": [], "materials": [], "lint": [],
             "review_error": False, "shot_error": False, "review_calls": 0}

    async def available(username):
        return [{"id": provider, "label": provider, "available": True, "model": model}
                for provider, model in (("claude", "claude-sonnet-5-5"),
                                        ("qwen", "qwen3.8-max"),
                                        ("deepseek", "deepseek-v4-pro"))]

    def select_materials(tags, video_model, owner=None):
        text = f"【scene-{tags['scene_type']}】对话模板：固定空间里交换台词。\n【grammar-shot-size】景别：先中景后近景。"
        state["materials"].append({"tags": dict(tags), "video_model": video_model, "owner": owner,
                                   "text": text})
        return {"template": {"id": "scene-" + tags["scene_type"]},
                "card_ids": ["scene-" + tags["scene_type"], "grammar-shot-size"],
                "text": text, "chars": len(text)}

    def lint_shots(shots, *, video_model, tags):
        state["lint"].append({"shots": [shot["no"] for shot in shots], "video_model": video_model,
                              "tags": dict(tags)})
        return [{"shot_no": 1, "rule_id": "no-looking-at-camera", "level": "warn",
                 "message": "确认视线没有落在镜头上。"}]

    async def get_review_provider(pid, owner):
        return state["review"]

    async def set_review_provider(pid, owner, value):
        state["review"] = value
        return value

    class Adapter:
        def __init__(self, provider, model):
            self.provider, self.model = provider, model

        async def call(self, task, inputs, images=None, repair=None):
            state["calls"].append({"provider": self.provider, "model": self.model, "task": task,
                                   "inputs": inputs})
            if task == "shot_plan":
                has_kb = bool(inputs.get("kb_text"))
                if state["shot_error"] and not has_kb:
                    raise brain.BrainProviderError("rejected", "upstream_rejected",
                                                   "导演调用被拒绝，未扣费")
                shots = [dict(shot) for shot in SHOTS]
                if has_kb:
                    for shot in shots:
                        shot["basis"] = ["scene-dialogue", "grammar-shot-size"]
                return brain.BrainReply(
                    json.dumps({"template_id": "scene-dialogue" if has_kb else None,
                                "deviations": "" if has_kb else "",
                                "shots": shots}, ensure_ascii=False),
                    {"input_tokens": 300, "output_tokens": 200, "cache_read_input_tokens": 0,
                     "cache_creation_input_tokens": 0},
                    self.model, "stop", .01)
            if task == "cross_review":
                state["review_calls"] += 1
                if state["review_error"]:
                    raise brain.BrainProviderError(
                        "uncertain", "response_interrupted",
                        "导演调用结果不确定，可能已扣费，请核对账单后手动释放")
                return brain.BrainReply(
                    json.dumps(REVIEW, ensure_ascii=False),
                    {"input_tokens": 500, "output_tokens": 100, "cache_read_input_tokens": 0,
                     "cache_creation_input_tokens": 0},
                    self.model, "stop", .01)
            raise AssertionError(task)

    async def get_provider(provider, username, images=None):
        model = {"claude": "claude-sonnet-5-5", "qwen": "qwen3.8-max",
                 "deepseek": "deepseek-v4-pro"}[provider]
        return Adapter(provider, model)

    monkeypatch.setattr(brain, "provider_options", available)
    monkeypatch.setattr(brain, "get_provider", get_provider)
    monkeypatch.setattr(kb_trial, "_select_materials", select_materials)
    monkeypatch.setattr(kb_trial, "_lint_shots", lint_shots)
    monkeypatch.setattr(kb_trial, "get_review_provider", get_review_provider)
    monkeypatch.setattr(kb_trial, "set_review_provider", set_review_provider)
    monkeypatch.setattr(kb_trial, "_schedule", lambda trial_id: state["scheduled"].append(trial_id))
    return {"client": client, "headers": accounts, "state": state}


def headers(kb, owner="kb-owner"):
    return kb["headers"][owner]


def project(kb, owner="kb-owner", title="知识库试拆"):
    response = kb["client"].post("/studio/projects", headers=headers(kb, owner), json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def trial_body(**overrides):
    body = {
        "scene_text": "面包房夜班。叶岚把钥匙放在烤盘旁，周默擦净围裙，说今晚他来收店。",
        "tags": {"scene_type": "dialogue", "position": "body", "pace": "mid", "emotion": "克制",
                 "cast_count": 2, "realism": "photoreal", "setting": "interior", "sensitive": []},
        "target_seconds": 15, "video_model": "wan", "modes": ["with_kb", "without_kb"],
    }
    body.update(overrides)
    return body


def quote(kb, p, **overrides):
    return kb["client"].post(f"/studio/projects/{p['id']}/kb/trial/quote",
                             headers=headers(kb), json=trial_body(**overrides))


def start(kb, p, quote_id):
    return kb["client"].post(f"/studio/projects/{p['id']}/kb/trial/start",
                             headers=headers(kb), json={"quote_id": quote_id})


def detail(kb, p, trial_id):
    return kb["client"].get(f"/studio/projects/{p['id']}/kb/trials/{trial_id}", headers=headers(kb))


def test_quote_confirm_once_expiry_and_daily_cap(kb, monkeypatch):
    p = project(kb)
    response = quote(kb, p)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["kind"] == "kb_trial" and data["total"] > 0 and data["expires_at"]
    assert len(data["items"]) == 4
    assert {line["name"] for line in data["items"]} == {
        "导演拆镜（带知识库）", "导演拆镜（不带知识库）",
        "交叉审核（带知识库）", "交叉审核（不带知识库）",
    }

    started = start(kb, p, data["id"])
    assert started.status_code == 200, started.text
    trial_id = started.json()["trial_id"]
    assert trial_id == data["id"] and kb["state"]["scheduled"] == [trial_id]
    assert start(kb, p, data["id"]).status_code == 409
    jobs = run(rows("SELECT kind,status,task FROM studio_jobs WHERE quote_id=?", (data["id"],)))
    assert len(jobs) == 4
    assert sorted(job["kind"] for job in jobs) == ["kb_review", "kb_review", "kb_shot", "kb_shot"]
    assert all(job["status"] == "queued" for job in jobs)

    expired = quote(kb, p).json()

    async def expire(quote_id):
        async with store.connection(transaction=True) as db:
            await db.execute("UPDATE studio_quotes SET expires_at=? WHERE id=?",
                             ("2000-01-01T00:00:00+00:00", quote_id))
    run(expire(expired["id"]))
    assert start(kb, p, expired["id"]).status_code == 409

    capped = quote(kb, p).json()
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "0.00000001")
    assert start(kb, p, capped["id"]).status_code == 409
    assert kb["state"]["scheduled"] == [trial_id]


def test_review_placeholders_are_not_dispatched_before_shots(kb, monkeypatch):
    p = project(kb)
    data = quote(kb, p).json()
    assert start(kb, p, data["id"]).status_code == 200
    scheduled = []
    monkeypatch.setattr(brain_jobs, "_schedule", lambda job_id: scheduled.append(job_id))
    run(brain_jobs.dispatch_queued())
    assert scheduled == []
    assert kb["state"]["calls"] == []
    jobs = run(rows("SELECT kind,status FROM studio_jobs WHERE quote_id=?", (data["id"],)))
    assert sorted(job["kind"] for job in jobs) == ["kb_review", "kb_review", "kb_shot", "kb_shot"]
    assert all(job["status"] == "queued" for job in jobs)


def test_two_modes_each_one_director_call_and_with_kb_basis(kb):
    p = project(kb)
    data = quote(kb, p).json()
    assert start(kb, p, data["id"]).status_code == 200
    run(kb_trial._run_trial(data["id"]))

    tasks = [call["task"] for call in kb["state"]["calls"]]
    assert tasks.count("shot_plan") == 2
    assert tasks.count("cross_review") == 2
    with_inputs = next(call["inputs"] for call in kb["state"]["calls"]
                       if call["task"] == "shot_plan" and "kb_text" in call["inputs"])
    without_inputs = next(call["inputs"] for call in kb["state"]["calls"]
                          if call["task"] == "shot_plan" and "kb_text" not in call["inputs"])
    assert "scene-dialogue" in with_inputs["kb_text"]
    assert "kb_text" not in without_inputs

    body = detail(kb, p, data["id"]).json()
    assert body["status"] == "done"
    with_kb = body["with_kb"]
    without_kb = body["without_kb"]
    assert len(with_kb["shots"]) == 2 and all(shot["basis"] for shot in with_kb["shots"])
    assert len(without_kb["shots"]) == 2 and all(not shot["basis"] for shot in without_kb["shots"])
    assert with_kb["template_id"] == "scene-dialogue"
    assert without_kb["template_id"] is None
    assert with_kb["card_ids"] == ["scene-dialogue", "grammar-shot-size"]
    assert with_kb["injected_chars"] == len(kb["state"]["materials"][0]["text"])
    assert without_kb["injected_chars"] == 0
    assert with_kb["lint"][0]["rule_id"] == "no-looking-at-camera"
    assert body["review"]["with_kb"]["status"] == "succeeded"
    assert body["review"]["without_kb"]["status"] == "succeeded"
    assert body["review"]["with_kb"]["verdict"] == "issues"
    assert [issue["severity"] for issue in body["review"]["with_kb"]["issues"]] == ["must", "should"]


def test_off_sends_no_review_and_quote_has_no_review_fee(kb):
    kb["state"]["review"] = "off"
    p = project(kb)
    data = quote(kb, p).json()
    assert len(data["items"]) == 2
    assert all("交叉审核" not in line["name"] for line in data["items"])
    assert "cross_review" not in {call["task"] for call in kb["state"]["calls"]}
    assert start(kb, p, data["id"]).status_code == 200
    run(kb_trial._run_trial(data["id"]))
    assert [call["task"] for call in kb["state"]["calls"]].count("shot_plan") == 2
    assert [call["task"] for call in kb["state"]["calls"]].count("cross_review") == 0
    body = detail(kb, p, data["id"]).json()
    assert body["review"] == {"with_kb": None, "without_kb": None}
    assert body["with_kb"]["shots"] and body["without_kb"]["shots"]
    jobs = run(rows("SELECT task FROM studio_jobs WHERE quote_id=?", (data["id"],)))
    assert {job.get("task") for job in jobs} == {"shot_plan"}


def test_review_failure_is_recorded_but_trial_result_stays_complete(kb):
    kb["state"]["review_error"] = True
    p = project(kb)
    data = quote(kb, p).json()
    assert start(kb, p, data["id"]).status_code == 200
    run(kb_trial._run_trial(data["id"]))
    body = detail(kb, p, data["id"]).json()
    assert body["status"] == "done"
    assert body["with_kb"]["shots"] and body["without_kb"]["shots"]
    for mode in ("with_kb", "without_kb"):
        review = body["review"][mode]
        assert review["status"] == "uncertain"
        assert review["verdict"] is None and review["issues"] == []
        assert review["summary"]
    shot_jobs = run(rows("SELECT status FROM studio_jobs WHERE quote_id=? AND task='shot_plan'",
                         (data["id"],)))
    assert [job["status"] for job in shot_jobs] == ["succeeded", "succeeded"]


def test_one_mode_shot_failure_cancels_only_its_review_hold(kb):
    p = project(kb)
    data = quote(kb, p).json()
    assert start(kb, p, data["id"]).status_code == 200
    kb["state"]["shot_error"] = True
    run(kb_trial._run_trial(data["id"]))
    body = detail(kb, p, data["id"]).json()
    assert body["status"] == "partial"
    assert body["with_kb"]["status"] == "succeeded" and body["with_kb"]["shots"]
    assert body["without_kb"]["status"] == "rejected" and body["without_kb"]["shots"] == []
    assert body["review"]["with_kb"]["status"] == "succeeded"
    assert body["review"]["without_kb"] is None
    review_job = run(rows("""SELECT j.* FROM studio_jobs j
        JOIN studio_quotes q ON q.id=j.quote_id WHERE q.id=? AND j.task='cross_review'
        ORDER BY j.created_at""", (data["id"],)))
    cancelled = [job for job in review_job if job["status"] == "cancelled"]
    assert len(cancelled) == 1 and float(cancelled[0]["reserved_amount"] or 0) == 0


def test_review_provider_patch_and_validation(kb):
    p = project(kb)
    url = f"/studio/projects/{p['id']}/review-provider"
    invalid = kb["client"].patch(url, headers=headers(kb), json={"review_provider": "bogus"})
    assert invalid.status_code == 422
    same = kb["client"].patch(url, headers=headers(kb), json={"review_provider": "qwen"})
    assert same.status_code == 200, same.text
    assert same.json() == {"review_provider": "qwen", "brain_provider": "qwen",
                           "same_as_director": True}
    changed = kb["client"].patch(url, headers=headers(kb), json={"review_provider": "deepseek"})
    assert changed.status_code == 200
    assert changed.json() == {"review_provider": "deepseek", "brain_provider": "qwen",
                              "same_as_director": False}
    fetched = kb["client"].get(url, headers=headers(kb))
    assert fetched.status_code == 200 and fetched.json()["review_provider"] == "deepseek"
    other = project(kb, "kb-other")
    assert kb["client"].get(f"/studio/projects/{other['id']}/review-provider",
                            headers=headers(kb, "kb-owner")).status_code == 404


def test_real_review_provider_store(kb):
    p = project(kb)
    url = f"/studio/projects/{p['id']}/review-provider"
    default = kb["client"].get(url, headers=headers(kb))
    assert default.status_code == 200
    assert default.json() == {"review_provider": "qwen", "brain_provider": "qwen",
                              "same_as_director": True}
    changed = kb["client"].patch(url, headers=headers(kb), json={"review_provider": "claude"})
    assert changed.status_code == 200
    assert changed.json() == {"review_provider": "claude", "brain_provider": "qwen",
                              "same_as_director": False}
    assert kb["client"].get(url, headers=headers(kb)).json()["review_provider"] == "claude"
    assert kb["client"].patch(url, headers=headers(kb),
                              json={"review_provider": "bogus"}).status_code == 422


def test_quote_request_validation(kb):
    p = project(kb)
    assert quote(kb, p, scene_text=" ").status_code == 422
    assert quote(kb, p, scene_text="字" * 3001).status_code == 422
    assert quote(kb, p, target_seconds=9).status_code == 422
    assert quote(kb, p, target_seconds=121).status_code == 422
    assert quote(kb, p, modes=["with_kb", "with_kb"]).status_code == 422
    assert quote(kb, p, modes=[]).status_code == 422
    tags = dict(trial_body()["tags"], scene_type="opening-hook")
    assert quote(kb, p, tags=tags).status_code == 422
    tags = dict(trial_body()["tags"], sensitive=["unknown"])
    assert quote(kb, p, tags=tags).status_code == 422


def test_real_knowledge_base_contract():
    tags = {"scene_type": "dialogue", "position": "body", "pace": "mid", "emotion": "克制",
            "cast_count": 2, "realism": "photoreal", "setting": "interior", "sensitive": []}
    assert len(run(kb_trial.list_cards(type="scene"))) == 19
    card = run(kb_trial.get_card("scene-dialogue"))
    assert card["type"] == "scene" and card["scene_type"] == "dialogue"
    materials = kb_trial._select_materials(tags, "wan", owner=None)
    assert materials["template"]["id"] == "scene-dialogue"
    assert "scene-dialogue" in materials["card_ids"] and materials["chars"] <= 8000
    lint = kb_trial._lint_shots([{"no": 1, "shot_size": "中景", "camera": "固定机位",
                                  "action": "甲放下钥匙", "sensitive": [], "duration_s": 3.2}],
                                video_model="wan", tags=tags)
    assert any(item["rule_id"] == "short-generation" for item in lint)


def test_real_store_exemplars_and_stats(kb):
    async def seed():
        exemplar = await store.create_exemplar("kb-owner", scene_type="dialogue", kind="good",
                                                reason="节奏清楚", shot={"no": 1, "duration_s": 3.5},
                                                tags=["dialogue"])
        return exemplar["id"]

    exemplar_id = run(seed())
    listed = kb["client"].get("/studio/kb/exemplars", headers=headers(kb),
                              params={"scene_type": "dialogue", "kind": "good"})
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["id"] == exemplar_id and listed.json()[0]["shot"] == {"no": 1, "duration_s": 3.5}
    patched = kb["client"].patch(f"/studio/kb/exemplars/{exemplar_id}", headers=headers(kb),
                                 json={"kind": "bad", "reason": "节奏拖沓"})
    assert patched.status_code == 200 and patched.json()["kind"] == "bad"
    assert patched.json()["reason"] == "节奏拖沓"
    archived = kb["client"].patch(f"/studio/kb/exemplars/{exemplar_id}", headers=headers(kb),
                                  json={"archived": True})
    assert archived.status_code == 200 and archived.json()["archived"] is True
    assert kb["client"].get("/studio/kb/exemplars", headers=headers(kb)).json() == []

    async def accumulate():
        from studio.director_kb import stats as kb_stats
        for _ in range(5):
            await kb_stats.accumulate("kb-owner", {"dialogue": [{"shot_size": "中景", "camera": "固定机位",
                                                                  "duration_s": 3.5}]})
    run(accumulate())
    stats = kb["client"].get("/studio/kb/stats", headers=headers(kb)).json()
    assert stats["ready"] is True and stats["episodes"] == 5
    assert stats["scene_types"][0]["scene_type"] == "dialogue"


def test_card_exemplar_and_stats_routes(kb, monkeypatch):
    cards = [
        {"id": "scene-dialogue", "type": "scene", "title": "对话", "summary": "两人静态对话",
         "tags": ["dialogue"], "beats": ["一", "二"]},
        {"id": "grammar-shot-size", "type": "grammar", "title": "景别", "summary": "景别定义",
         "tags": ["shot-size"]},
    ]

    async def all_cards():
        return cards

    async def list_exemplars(owner, *, scene_type=None, kind=None):
        return [{"id": "ex-1", "scene_type": "dialogue", "kind": "good", "reason": "节奏好"}]

    async def patch_exemplar(owner, exemplar_id, fields):
        return {"id": exemplar_id, **fields}

    async def get_stats(owner):
        return {"ready": False, "episodes": 3}

    async def get_card(card_id):
        from fastapi import HTTPException
        for card in cards:
            if card["id"] == card_id:
                return card
        raise HTTPException(404, "Not Found")

    monkeypatch.setattr(kb_trial, "_all_cards", all_cards)
    monkeypatch.setattr(kb_trial, "get_card", get_card)
    monkeypatch.setattr(kb_trial, "list_exemplars", list_exemplars)
    monkeypatch.setattr(kb_trial, "patch_exemplar", patch_exemplar)
    monkeypatch.setattr(kb_trial, "get_stats", get_stats)
    assert kb["client"].get("/studio/kb/cards", headers=headers(kb)).status_code == 200
    listed = kb["client"].get("/studio/kb/cards", params={"type": "scene", "q": "对话"},
                              headers=headers(kb))
    assert listed.status_code == 200
    assert listed.json() == [{"id": "scene-dialogue", "type": "scene", "title": "对话",
                              "summary": "两人静态对话", "tags": ["dialogue"]}]
    assert kb["client"].get("/studio/kb/cards/scene-dialogue", headers=headers(kb)).json()["beats"] == ["一", "二"]
    assert kb["client"].get("/studio/kb/cards/missing", headers=headers(kb)).status_code == 404
    assert kb["client"].get("/studio/kb/exemplars", headers=headers(kb)).json()[0]["id"] == "ex-1"
    patched = kb["client"].patch("/studio/kb/exemplars/ex-1", headers=headers(kb),
                                 json={"kind": "bad", "reason": "节奏拖沓"})
    assert patched.status_code == 200 and patched.json()["kind"] == "bad"
    stats = kb["client"].get("/studio/kb/stats", headers=headers(kb))
    assert stats.json() == {"ready": False, "episodes": 3}


# ---------------------------------------------------------------------------
# R1 返修：混合币种、Claude 月额度、修正后结果、重启续跑、审核预留上界、
# 报价额度与缺失模型卡。以下测试全部使用夹具里的离线 brain，不发真实请求。
# ---------------------------------------------------------------------------

def _patch_brain_provider(kb, project, provider):
    response = kb["client"].patch(f"/studio/projects/{project['id']}", headers=headers(kb),
                                  json={"brain_provider": provider})
    assert response.status_code == 200, response.text
    return response


def _line_map(quote_body):
    return {line["item_id"]: line for line in quote_body["items"]}


def test_mixed_currency_quote_has_line_currency_and_null_total(kb):
    p = project(kb)
    single = quote(kb, p)
    assert single.status_code == 200, single.text
    single = single.json()
    assert single["currency"] == "CNY" and isinstance(single["total"], (int, float))
    assert single["total"] == pytest.approx(
        sum(line["est"] for line in single["items"] if line["currency"] == "CNY"))

    _patch_brain_provider(kb, p, "claude")
    mixed = quote(kb, p)
    assert mixed.status_code == 200, mixed.text
    data = mixed.json()
    lines = _line_map(data)
    assert lines["with_kb:shot_plan"]["currency"] == "USD"
    assert lines["without_kb:shot_plan"]["currency"] == "USD"
    assert lines["with_kb:cross_review"]["currency"] == "CNY"
    assert lines["without_kb:cross_review"]["currency"] == "CNY"
    assert data["total"] is None and data["currency"] == "mixed"
    assert data["totals"]["CNY"] > 0 and data["totals"]["USD"] > 0
    for currency in ("CNY", "USD"):
        expected = sum(line["est"] for line in data["items"] if line["currency"] == currency)
        assert data["totals"][currency] == pytest.approx(expected)


def test_claude_monthly_budget_counts_kb_placeholders(kb, monkeypatch):
    p = project(kb)
    _patch_brain_provider(kb, p, "claude")
    first = quote(kb, p).json()
    second = quote(kb, p).json()
    assert first["totals"]["USD"] > 0
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_MONTHLY_USD",
                       str(first["totals"]["USD"] * 1.05))
    assert start(kb, p, first["id"]).status_code == 200
    assert start(kb, p, second["id"]).status_code == 409
    assert run(spend.brain_month_used("kb-owner")) > 0


def test_repaired_shot_output_is_used_by_detail_and_review(kb, monkeypatch):
    base_get_provider = brain.get_provider
    state = {"invalid": 0}

    class FlakyShot:
        def __init__(self, inner):
            self.inner, self.model = inner, inner.model

        async def call(self, task, inputs, images=None, repair=None):
            if task == "shot_plan" and inputs.get("kb_text") and repair is None:
                state["invalid"] += 1
                shots = [dict(shot) for shot in SHOTS]
                for shot in shots:
                    shot["basis"] = ["scene-dialogue"]
                shots[0]["basis"] = []
                shots[0]["action"] = "第一次输出（会被修正）"
                text = json.dumps({"template_id": "scene-dialogue", "deviations": "",
                                   "shots": shots}, ensure_ascii=False)
                return brain.BrainReply(text, {"input_tokens": 300, "output_tokens": 200,
                                               "cache_read_input_tokens": 0,
                                               "cache_creation_input_tokens": 0},
                                        self.model, "stop", .01)
            return await self.inner.call(task, inputs, images=images, repair=repair)

    async def get_provider(provider, username, images=None):
        return FlakyShot(await base_get_provider(provider, username, images=images))

    monkeypatch.setattr(brain, "get_provider", get_provider)
    p = project(kb)
    data = quote(kb, p).json()
    assert start(kb, p, data["id"]).status_code == 200
    run(kb_trial._run_trial(data["id"]))

    body = detail(kb, p, data["id"]).json()
    assert body["status"] == "done"
    assert body["with_kb"]["status"] == "succeeded"
    assert len(body["with_kb"]["shots"]) == len(SHOTS)
    assert all(shot["basis"] for shot in body["with_kb"]["shots"])
    assert body["with_kb"]["shots"][0]["action"] == SHOTS[0]["action"]
    assert body["review"]["with_kb"]["status"] == "succeeded"
    assert state["invalid"] == 1

    reviews = [call for call in kb["state"]["calls"] if call["task"] == "cross_review"]
    assert len(reviews) == 2
    for call in reviews:
        assert call["inputs"]["shots"][0]["action"] == SHOTS[0]["action"]

    children = run(rows("""SELECT task,status,attempt,parent_job_id FROM studio_jobs
        WHERE quote_id=? AND parent_job_id IS NOT NULL""", (data["id"],)))
    assert len(children) == 1
    assert children[0]["task"] == "shot_plan" and children[0]["status"] == "succeeded"
    assert children[0]["attempt"] == 2
    roots = run(rows("""SELECT * FROM studio_jobs
        WHERE quote_id=? AND task='shot_plan' AND parent_job_id IS NULL""", (data["id"],)))
    assert sorted(job["status"] for job in roots) == ["invalid_output", "succeeded"]


def test_repaired_review_output_is_shown_in_detail(kb, monkeypatch):
    base_get_provider = brain.get_provider
    state = {"invalid": 0}
    wrong_order = {"verdict": "issues", "summary": "第一次顺序错误",
                   "issues": [REVIEW["issues"][1], REVIEW["issues"][0]]}

    class FlakyReview:
        def __init__(self, inner):
            self.inner, self.model = inner, inner.model

        async def call(self, task, inputs, images=None, repair=None):
            if task == "cross_review" and repair is None:
                state["invalid"] += 1
                return brain.BrainReply(json.dumps(wrong_order, ensure_ascii=False),
                                        {"input_tokens": 500, "output_tokens": 100,
                                         "cache_read_input_tokens": 0,
                                         "cache_creation_input_tokens": 0},
                                        self.model, "stop", .01)
            return await self.inner.call(task, inputs, images=images, repair=repair)

    async def get_provider(provider, username, images=None):
        return FlakyReview(await base_get_provider(provider, username, images=images))

    monkeypatch.setattr(brain, "get_provider", get_provider)
    p = project(kb)
    data = quote(kb, p).json()
    assert start(kb, p, data["id"]).status_code == 200
    run(kb_trial._run_trial(data["id"]))

    body = detail(kb, p, data["id"]).json()
    assert body["status"] == "done"
    assert state["invalid"] == 2
    for mode in ("with_kb", "without_kb"):
        review = body["review"][mode]
        assert review["status"] == "succeeded"
        assert review["summary"] == REVIEW["summary"]
        assert [issue["severity"] for issue in review["issues"]] == ["must", "should"]
    roots = run(rows("""SELECT * FROM studio_jobs
        WHERE quote_id=? AND task='cross_review' AND parent_job_id IS NULL""", (data["id"],)))
    assert sorted(job["status"] for job in roots) == ["invalid_output", "invalid_output"]
    children = run(rows("""SELECT task,status,attempt,parent_job_id FROM studio_jobs
        WHERE quote_id=? AND parent_job_id IS NOT NULL""", (data["id"],)))
    assert len(children) == 2
    assert all(job["task"] == "cross_review" and job["status"] == "succeeded"
               and job["attempt"] == 2 for job in children)


def test_recovery_resumes_confirmed_trial_without_duplicate_director_calls(kb):
    p = project(kb)
    data = quote(kb, p).json()
    assert start(kb, p, data["id"]).status_code == 200
    kb["state"]["scheduled"].clear()

    run(recovery.recover_studio_jobs())
    assert kb["state"]["scheduled"] == [data["id"]]

    run(kb_trial._run_trial(data["id"]))
    tasks = [call["task"] for call in kb["state"]["calls"]]
    assert tasks.count("shot_plan") == 2
    assert tasks.count("cross_review") == 2
    body = detail(kb, p, data["id"]).json()
    assert body["status"] == "done"
    assert body["with_kb"]["shots"] and body["without_kb"]["shots"]


def test_resume_after_director_success_only_sends_review(kb, monkeypatch):
    p = project(kb)
    data = quote(kb, p, modes=["with_kb"]).json()
    assert start(kb, p, data["id"]).status_code == 200

    original_activate = kb_trial._activate_review

    async def hold_review(job_id, owner, inputs, input_chars):
        return False

    monkeypatch.setattr(kb_trial, "_activate_review", hold_review)
    run(kb_trial._run_trial(data["id"]))
    tasks = [call["task"] for call in kb["state"]["calls"]]
    assert tasks.count("shot_plan") == 1 and tasks.count("cross_review") == 0
    first = detail(kb, p, data["id"]).json()
    assert first["with_kb"]["status"] == "succeeded"
    assert first["review"]["with_kb"] is None

    monkeypatch.setattr(kb_trial, "_activate_review", original_activate)
    run(kb_trial._run_trial(data["id"]))
    tasks = [call["task"] for call in kb["state"]["calls"]]
    assert tasks.count("shot_plan") == 1
    assert tasks.count("cross_review") == 1
    body = detail(kb, p, data["id"]).json()
    assert body["status"] == "done"
    assert body["review"]["with_kb"]["status"] == "succeeded"


def test_review_quote_covers_shot_plan_output_upper_bound(kb):
    p = project(kb)
    shot = {"no": 1, "beat": "建立位置", "shot_size": "中景", "angle": "平视侧拍",
            "camera": "固定机位", "action": "叶岚把钥匙放在操作台上，周默看向钥匙",
            "first_frame_prompt": "两人隔着操作台，钥匙在台面中央，侧向平视",
            "video_prompt": "叶岚放下钥匙，周默视线落向钥匙，镜头不动",
            "dialogue": "今晚我来收店。", "sound_intent": "烤箱底噪", "duration_s": 3.5,
            "sensitive": [], "basis": ["scene-dialogue"]}
    target = get_task("shot_plan").max_tokens / 1.5
    shots = []
    while True:
        candidate = [*shots, {**shot, "no": len(shots) + 1}]
        if len(json.dumps(candidate, ensure_ascii=False)) > target * 1.05:
            break
        shots = candidate
    assert shots
    data = quote(kb, p).json()
    payload = run(rows("SELECT items_json FROM studio_quotes WHERE id=?", (data["id"],)))[0]["items"]
    review = next(item for item in payload["items"]
                  if item["mode"] == "with_kb" and item["role"] == "cross_review")
    inputs = cross_review.build_inputs(trial_body()["scene_text"], shots)
    chars = brain.estimate_input_chars("cross_review", inputs)
    expected = pricing.estimate_brain("qwen3.8-max", chars,
                                      get_task("cross_review").max_tokens)
    assert review["first_max"] >= expected["amount"]
    assert review["amount"] >= review["first_max"]
    assert review["repair_max"] > 0
    assert review["currency"] == expected["currency"] == "CNY"
    assert review["input_chars"] > len(trial_body()["scene_text"])


def test_quote_max_cny_cap_blocks_before_and_after_quote(kb, monkeypatch):
    p = project(kb)
    before = len(run(rows("SELECT id FROM studio_quotes")))
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "0.00000001")
    blocked = quote(kb, p)
    assert blocked.status_code == 409
    assert len(run(rows("SELECT id FROM studio_quotes"))) == before

    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    data = quote(kb, p).json()
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "0.00000001")
    assert start(kb, p, data["id"]).status_code == 409


def test_trial_detail_reports_missing_model_card_for_3d(kb):
    p = project(kb)
    tags = dict(trial_body()["tags"], realism="3d")
    data = quote(kb, p, tags=tags).json()
    body = detail(kb, p, data["id"]).json()
    assert body["with_kb"]["model_card_missing"] is True
    assert body["without_kb"]["model_card_missing"] is True

    only = quote(kb, p, tags=tags, modes=["without_kb"]).json()
    one_mode = detail(kb, p, only["id"]).json()
    assert one_mode["with_kb"] is None
    assert one_mode["without_kb"]["model_card_missing"] is True

    normal = quote(kb, p).json()
    normal_body = detail(kb, p, normal["id"]).json()
    assert normal_body["with_kb"]["model_card_missing"] is False
    assert normal_body["without_kb"]["model_card_missing"] is False


def test_recovery_cancels_placeholders_for_archived_project(kb):
    p = project(kb)
    data = quote(kb, p).json()
    assert start(kb, p, data["id"]).status_code == 200
    kb["state"]["scheduled"].clear()

    async def archive():
        async with store.connection(transaction=True) as db:
            await db.execute("UPDATE studio_projects SET archived=1 WHERE id=?", (p["id"],))
    run(archive())
    run(recovery.recover_studio_jobs())

    assert kb["state"]["scheduled"] == []
    jobs = run(rows("""SELECT kind,status,reserved_amount FROM studio_jobs
        WHERE quote_id=? ORDER BY kind""", (data["id"],)))
    assert len(jobs) == 4
    assert all(job["status"] == "cancelled" for job in jobs)
    assert all(float(job["reserved_amount"] or 0) == 0 for job in jobs)
