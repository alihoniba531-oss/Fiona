"""WO3e B 块：交叉审核任务、schema 与 DashScope 路由（全离线）。"""
import asyncio
import json

import httpx
import openai
import pytest
from fastapi import HTTPException

import auth
import database
from studio import brain, brain_jobs, cross_review, kb_trial, store
from studio.brain_tasks import TASKS, get_task, task_prompt


def run(coro):
    return asyncio.run(coro)


SHOTS = [
    {"no": 1, "beat": "建立位置", "shot_size": "中景", "angle": "平视侧拍",
     "camera": "固定机位", "action": "叶岚放下钥匙，周默看向钥匙",
     "first_frame_prompt": "两人隔着操作台，钥匙在台面中央",
     "video_prompt": "叶岚放下钥匙，镜头不动", "dialogue": "", "sound_intent": "底噪",
     "duration_s": 3.5, "sensitive": [], "basis": ["scene-dialogue"]},
    {"no": 2, "beat": "决定", "shot_size": "近景", "angle": "侧后 45°",
     "camera": "固定机位", "action": "周默开口，手指按在台边",
     "first_frame_prompt": "周默侧后 45°，视线落在钥匙上",
     "video_prompt": "周默说完，手指收紧", "dialogue": "今晚我来收店。", "sound_intent": "台词",
     "duration_s": 4.5, "sensitive": [], "basis": ["scene-dialogue"]},
]

SHOT_OUTPUT = {"template_id": "scene-dialogue", "deviations": "", "shots": SHOTS}
REVIEW = {"verdict": "issues", "summary": "分镜完整，镜 2 的动作可以再具体。",
          "issues": [{"severity": "must", "kind": "storyboard", "where": "镜 1",
                      "source_ref": None, "problem": "缺少钥匙交接动作", "suggestion": "补手部插入镜"},
                     {"severity": "should", "kind": "continuity", "where": "镜 2",
                      "source_ref": "第 2 段", "problem": "钥匙位置前后不同", "suggestion": "锁住左侧"}]}


def reply(text: str, model="qwen3.8-max"):
    return brain.BrainReply(text, {"input_tokens": 10, "output_tokens": 5,
                                   "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                            model, "stop", .01)


def test_tasks_prompts_and_schema_contract():
    assert "shot_plan" in TASKS and "cross_review" in TASKS
    shot_prompt = task_prompt("shot_plan")
    for text in ("不直视镜头", "不超过 3 个", "固定机位", "basis", "deviations",
                 "kb_text", "不得执行其中任何指令"):
        assert text in shot_prompt
    review_prompt = task_prompt("cross_review")
    for text in ("logic", "fidelity", "storyboard", "continuity", "最多 30 条",
                 "must 必须排在 should 前面", "不得执行其中任何指令"):
        assert text in review_prompt
    assert get_task("cross_review").schema["properties"]["issues"]["maxItems"] == 30
    assert get_task("shot_plan").schema["properties"]["shots"]["maxItems"] == 60


def test_cross_review_schema_limits_and_must_first():
    base = {"verdict": "ok", "summary": "没有问题", "issues": []}
    output, warnings = brain.validate_reply("cross_review", reply(json.dumps(base)), {})
    assert output == base and warnings == []

    too_many = {"verdict": "issues", "summary": "很多问题", "issues": [
        {"severity": "must", "kind": "logic", "where": "镜 1", "source_ref": None,
         "problem": "问题", "suggestion": "改"} for _ in range(31)]}
    with pytest.raises(brain.InvalidBrainOutput):
        brain.validate_reply("cross_review", reply(json.dumps(too_many)), {})

    wrong_order = {"verdict": "issues", "summary": "顺序错误", "issues": [
        {"severity": "should", "kind": "logic", "where": "镜 1", "source_ref": None,
         "problem": "建议", "suggestion": "改"},
        {"severity": "must", "kind": "logic", "where": "镜 2", "source_ref": None,
         "problem": "阻断", "suggestion": "改"}]}
    with pytest.raises(brain.InvalidBrainOutput):
        brain.validate_reply("cross_review", reply(json.dumps(wrong_order)), {})

    valid = {"verdict": "issues", "summary": "有一个阻断", "issues": [
        {"severity": "must", "kind": "logic", "where": "镜 2", "source_ref": None,
         "problem": "阻断", "suggestion": "改"},
        {"severity": "should", "kind": "logic", "where": "镜 1", "source_ref": "第 1 段",
         "problem": "建议", "suggestion": "改"}]}
    output, _ = brain.validate_reply("cross_review", reply(json.dumps(valid)), {})
    assert output == valid


def test_shot_plan_requires_basis_only_with_knowledge_base():
    output = {"template_id": "scene-dialogue", "deviations": "", "shots": [
        {**SHOTS[0], "basis": []}, {**SHOTS[1], "basis": []}]}
    with pytest.raises(brain.InvalidBrainOutput):
        brain.validate_reply("shot_plan", reply(json.dumps(output)), {"kb_text": "素材"})
    passed, _ = brain.validate_reply("shot_plan", reply(json.dumps(output)),
                                     {"target_seconds": 8})
    assert passed["shots"][0]["basis"] == []
    good = {"template_id": "scene-dialogue", "deviations": "偏离理由", "shots": SHOTS}
    passed, _ = brain.validate_reply("shot_plan", reply(json.dumps(good)),
                                     {"kb_text": "素材", "target_seconds": 8})
    assert all(shot["basis"] for shot in passed["shots"])


def test_review_is_one_call_and_failures_are_recorded(monkeypatch):
    calls = []

    async def ok(task, inputs, *, provider, username):
        calls.append((task, provider, inputs))
        return brain.BrainResult(output=REVIEW, warnings=[], usage={}, cost={},
                                 model="qwen3.8-max", stop_reason="stop", latency_s=.1)

    monkeypatch.setattr(cross_review, "run_brain", ok)
    result = run(cross_review.review(SHOTS, source_text="原文", provider="qwen", username="owner"))
    assert len(calls) == 1 and calls[0][0] == "cross_review"
    assert result == {"provider": "qwen", "model": "qwen3.8-max", "status": "succeeded",
                      "verdict": "issues", "summary": REVIEW["summary"],
                      "issues": REVIEW["issues"]}

    async def interrupted(task, inputs, *, provider, username):
        calls.append((task, provider, inputs))
        raise brain.BrainProviderError("uncertain", "response_interrupted",
                                       "导演调用结果不确定，可能已扣费，请核对账单后手动释放",
                                       model="qwen3.8-max")

    calls.clear()
    monkeypatch.setattr(cross_review, "run_brain", interrupted)
    result = run(cross_review.review(SHOTS, source_text="原文", provider="qwen", username="owner"))
    assert len(calls) == 1
    assert result["status"] == "uncertain" and result["verdict"] is None
    assert result["model"] == "qwen3.8-max" and result["issues"] == []

    async def rejected(task, inputs, *, provider, username):
        calls.append((task, provider, inputs))
        raise HTTPException(409, "今日额度不足")

    calls.clear()
    monkeypatch.setattr(cross_review, "run_brain", rejected)
    monkeypatch.setattr(brain, "provider_options",
                        lambda username: _options())
    result = run(cross_review.review(SHOTS, source_text="原文", provider="qwen", username="owner"))
    assert len(calls) == 1 and result["status"] == "rejected" and result["verdict"] is None


async def _options():
    return [{"id": "qwen", "label": "千问", "available": True, "model": "qwen3.8-max"}]


def test_off_review_never_calls(monkeypatch):
    async def fail(*args, **kwargs):
        raise AssertionError("off 不应发出审核")

    monkeypatch.setattr(cross_review, "run_brain", fail)
    assert run(cross_review.review(SHOTS, source_text="原文", provider="off",
                                   username="owner")) is None


@pytest.fixture
def dashscope_trial(client, monkeypatch):
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", "kb-review-owner")
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "1")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_MONTHLY_USD", "40")
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_DEFAULT", "deepseek")

    user = run(database.get_or_create_user("kb-review-owner"))
    headers = {"Authorization": f"Bearer {auth.create_token('kb-review-owner', user['session_version'])}"}

    state = {"requests": [], "director_calls": 0, "scheduled": []}

    async def available(username):
        return [{"id": "claude", "label": "Claude", "available": False,
                 "reason": "BYOK 未启用", "model": "claude-sonnet-5-5"},
                {"id": "qwen", "label": "千问", "available": True, "model": "qwen3.8-max"},
                {"id": "deepseek", "label": "DeepSeek", "available": True,
                 "model": "deepseek-v4-pro"}]

    class Director:
        model = "deepseek-v4-pro"

        async def call(self, task, inputs, images=None, repair=None):
            state["director_calls"] += 1
            assert task == "shot_plan"
            return reply(json.dumps(SHOT_OUTPUT, ensure_ascii=False), self.model)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        state["requests"].append({"url": str(request.url), "host": request.url.host,
                                  "path": request.url.path, "body": payload})
        return httpx.Response(200, json={
            "id": "chatcmpl-offline", "object": "chat.completion", "created": 0,
            "model": payload["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(REVIEW, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 600, "completion_tokens": 100,
                      "total_tokens": 700},
        })

    transport = httpx.MockTransport(handler)

    def qwen_client(**kwargs):
        kwargs["http_client"] = httpx.Client(transport=transport, trust_env=False)
        return openai.OpenAI(**kwargs)

    async def get_provider(provider, username, images=None):
        if provider == "deepseek":
            return Director()
        return brain.QwenProvider(api_key="offline-qwen-key", client_factory=qwen_client)

    def select_materials(tags, video_model, owner=None):
        text = "【scene-dialogue】对话模板：固定空间交换台词。"
        return {"template": {"id": "scene-dialogue"},
                "card_ids": ["scene-dialogue"], "text": text, "chars": len(text)}

    async def get_review_provider(pid, owner):
        return "qwen"

    monkeypatch.setattr(brain, "provider_options", available)
    monkeypatch.setattr(brain, "get_provider", get_provider)
    monkeypatch.setattr(kb_trial, "_select_materials", select_materials)
    monkeypatch.setattr(kb_trial, "_lint_shots", lambda shots, **kwargs: [])
    monkeypatch.setattr(kb_trial, "get_review_provider", get_review_provider)
    monkeypatch.setattr(kb_trial, "_schedule", lambda trial_id: state["scheduled"].append(trial_id))
    return {"client": client, "headers": headers, "state": state}


def test_deepseek_director_qwen_review_goes_to_dashscope(dashscope_trial):
    client, headers, state = (dashscope_trial["client"], dashscope_trial["headers"],
                              dashscope_trial["state"])
    created = client.post("/studio/projects", headers=headers,
                          json={"title": "deepseek 导演 qwen 审核"})
    assert created.status_code == 201, created.text
    p = created.json()
    assert p["brain_provider"] == "deepseek"
    body = {"scene_text": "面包房夜班。叶岚把钥匙放在操作台，周默说今晚他来收店。",
            "tags": {"scene_type": "dialogue", "pace": "mid", "emotion": "克制", "cast_count": 2,
                     "realism": "photoreal", "setting": "interior"},
            "target_seconds": 15, "video_model": "wan", "modes": ["with_kb", "without_kb"]}
    quote = client.post(f"/studio/projects/{p['id']}/kb/trial/quote", headers=headers, json=body)
    assert quote.status_code == 200, quote.text
    assert any("交叉审核" in line["name"] for line in quote.json()["items"])
    started = client.post(f"/studio/projects/{p['id']}/kb/trial/start", headers=headers,
                          json={"quote_id": quote.json()["id"]})
    assert started.status_code == 200, started.text
    run(kb_trial._run_trial(quote.json()["id"]))

    assert state["director_calls"] == 2
    assert len(state["requests"]) == 2
    for request in state["requests"]:
        assert request["host"] == "dashscope.aliyuncs.com"
        assert request["path"] == "/compatible-mode/v1/chat/completions"
        assert request["body"]["model"] == "qwen3.8-max"
        assert request["body"]["stream"] is False
        material = request["body"]["messages"][1]["content"]
        assert "source_text" in material and "shots" in material
    detail = client.get(f"/studio/projects/{p['id']}/kb/trials/{quote.json()['id']}",
                        headers=headers).json()
    assert detail["with_kb"]["status"] == "succeeded"
    assert detail["without_kb"]["status"] == "succeeded"
    assert detail["review"]["with_kb"]["status"] == "succeeded"
    assert detail["review"]["without_kb"]["status"] == "succeeded"
    assert detail["review"]["with_kb"]["model"] == "qwen3.8-max"


# ---------------------------------------------------------------------------
# G1 返修：M6（审核提供方被写死）与 M7（未分类异常被吞掉）的直接回归。
# 以下测试与夹具全部为新增，不改动上面的既有测试、输入与断言。
# ---------------------------------------------------------------------------

TRIAL_SCENE = "面包房夜班。叶岚把钥匙放在操作台，周默说今晚他来收店。"
TRIAL_TAGS = {"scene_type": "dialogue", "pace": "mid", "emotion": "克制", "cast_count": 2,
              "realism": "photoreal", "setting": "interior"}


def _start_review_trial(client, headers, title):
    """建项目、报价并确认一次双模式试拆；调度器在夹具里被暂停，由测试显式执行。"""
    created = client.post("/studio/projects", headers=headers, json={"title": title})
    assert created.status_code == 201, created.text
    project = created.json()
    body = {"scene_text": TRIAL_SCENE, "tags": TRIAL_TAGS, "target_seconds": 15,
            "video_model": "wan", "modes": ["with_kb", "without_kb"]}
    quote = client.post(f"/studio/projects/{project['id']}/kb/trial/quote", headers=headers, json=body)
    assert quote.status_code == 200, quote.text
    trial_id = quote.json()["id"]
    started = client.post(f"/studio/projects/{project['id']}/kb/trial/start", headers=headers,
                          json={"quote_id": trial_id})
    assert started.status_code == 200, started.text
    return project, trial_id


def _get_trial(client, headers, project, trial_id):
    response = client.get(f"/studio/projects/{project['id']}/kb/trials/{trial_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_review_qwen_uses_dashscope_with_real_run_brain(dashscope_trial):
    """M6：provider=qwen 必须落到 DashScope，不能因假 Director 存在而改道 deepseek。"""
    state = dashscope_trial["state"]
    result = run(cross_review.review(SHOTS, source_text=TRIAL_SCENE, provider="qwen",
                                     username="kb-review-owner"))
    assert result["status"] == "succeeded", result
    assert result["provider"] == "qwen"
    assert result["model"] == "qwen3.8-max"
    assert len(state["requests"]) == 1, state["requests"]
    request = state["requests"][0]
    assert request["host"] == "dashscope.aliyuncs.com"
    assert request["path"] == "/compatible-mode/v1/chat/completions"
    assert request["body"]["model"] == "qwen3.8-max"
    # 真实 run_brain 走的是 qwen 适配器；deepseek 的假 Director 一次也不该被调用。
    assert state["director_calls"] == 0


def test_trial_sends_two_shot_plans_to_director_and_two_reviews_to_qwen(
        dashscope_trial, monkeypatch):
    """完整试拆：deepseek 导演只收 shot_plan，qwen 审核两次都发 DashScope。"""
    client, headers, state = (dashscope_trial["client"], dashscope_trial["headers"],
                              dashscope_trial["state"])
    director_tasks = []
    fixture_get_provider = brain.get_provider

    async def tracking_get_provider(provider, username, images=None):
        adapter = await fixture_get_provider(provider, username, images=images)
        if provider == "deepseek":
            original_call = adapter.call

            async def call(task, inputs, images=None, repair=None):
                director_tasks.append(task)
                return await original_call(task, inputs, images=images, repair=repair)

            adapter.call = call
        return adapter

    monkeypatch.setattr(brain, "get_provider", tracking_get_provider)

    project, trial_id = _start_review_trial(client, headers, "审核路由完整试拆")
    run(kb_trial._run_trial(trial_id))

    assert state["director_calls"] == 2
    assert director_tasks == ["shot_plan", "shot_plan"]
    assert director_tasks.count("cross_review") == 0
    assert len(state["requests"]) == 2, state["requests"]
    for request in state["requests"]:
        assert request["host"] == "dashscope.aliyuncs.com"
        assert request["path"] == "/compatible-mode/v1/chat/completions"
        assert request["body"]["model"] == "qwen3.8-max"
        material = request["body"]["messages"][1]["content"]
        assert "source_text" in material and "shots" in material
    detail = _get_trial(client, headers, project, trial_id)
    for mode in ("with_kb", "without_kb"):
        assert detail[mode]["status"] == "succeeded"
        assert detail["review"][mode]["status"] == "succeeded"
        assert detail["review"][mode]["model"] == "qwen3.8-max"


def test_review_unclassified_exception_is_fixed_uncertain(monkeypatch):
    """M7：任何未分类异常都只能落成固定文案的 uncertain，异常正文不得外泄。"""
    leak = "含上游素材的正文"

    async def crash(task, inputs, *, provider, username):
        raise RuntimeError(leak)

    monkeypatch.setattr(cross_review, "run_brain", crash)
    result = run(cross_review.review(SHOTS, source_text=leak, provider="qwen", username="owner"))
    assert result["status"] == "uncertain"
    assert result["verdict"] is None
    assert result["issues"] == []
    assert result["model"] == "qwen3.8-max"
    assert leak not in result["summary"]


@pytest.fixture
def crashing_review_trial(dashscope_trial, monkeypatch):
    """qwen 审核适配器在真实 run_brain 里抛未分类异常；deepseek 仍走夹具 Director。"""
    fixture_get_provider = brain.get_provider

    class CrashingReviewer:
        model = "qwen3.8-max"

        async def call(self, task, inputs, images=None, repair=None):
            raise RuntimeError("含上游素材的正文")

    async def get_provider(provider, username, images=None):
        if provider == "qwen":
            return CrashingReviewer()
        return await fixture_get_provider(provider, username, images=images)

    monkeypatch.setattr(brain, "get_provider", get_provider)
    return dashscope_trial


def test_trial_keeps_shot_results_when_review_raises(crashing_review_trial):
    """完整试拆：审核抛未分类异常时两种模式的 shots 保留，审核固定为 uncertain。"""
    client, headers, state = (crashing_review_trial["client"], crashing_review_trial["headers"],
                              crashing_review_trial["state"])
    project, trial_id = _start_review_trial(client, headers, "审核异常完整试拆")
    run(kb_trial._run_trial(trial_id))

    assert state["director_calls"] == 2
    assert state["requests"] == []
    detail = _get_trial(client, headers, project, trial_id)
    for mode in ("with_kb", "without_kb"):
        entry = detail[mode]
        assert entry["status"] == "succeeded"
        assert len(entry["shots"]) == len(SHOTS)
        review = detail["review"][mode]
        assert review["status"] == "uncertain"
        assert review["verdict"] is None
        assert review["issues"] == []
        assert "含上游素材的正文" not in review["summary"]


@pytest.fixture(autouse=True)
def _strip_bracketed_no_proxy(monkeypatch):
    """本机 NO_PROXY 里的 [::1] 会让 httpx 0.28 在构造 OpenAI 客户端时抛 InvalidURL。

    本文件全部使用 MockTransport，这里只去掉方括号 IPv6 写法，不改代理地址，
    也不改任何既有测试的输入、断言或夹具。
    """
    import os
    for name in ("NO_PROXY", "no_proxy"):
        value = os.environ.get(name)
        if value and ("[" in value or "]" in value):
            kept = [part for part in value.split(",") if "[" not in part and "]" not in part]
            monkeypatch.setenv(name, ",".join(kept))
