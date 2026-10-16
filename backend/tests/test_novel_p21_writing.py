"""Offline P2.1 review rewrites and strict P1 archive entry points."""

import asyncio
from copy import deepcopy
import json

import pytest

from novel.bible import build_setup
from novel.context import build_review_bible, context_messages
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter, StepFailed
from novel.run_store import RunStore
from novel.writing import write_chapter


LONG_APPEARANCE = "身形清瘦，黑色齐耳短发，左眉有浅疤，常穿深灰工装外套。"


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("P2.1 writing tests must use the offline fake model")

    monkeypatch.setattr(LLMRouter, "_single_real_call", forbidden)


def workshop(*, experiment="P1", compressed=False):
    config = {"experiment": experiment, "seed_idea": "保全旧案原件",
              "target": {"min_chapters": 1, "max_chapters": 2, "chapter_words": 300},
              "adaptation": {"max_main_characters": 6, "max_scenes_per_chapter": 3},
              "agents": {role: f"fake:{role}"
                         for role in ("editor", "writer", "reviewer", "archivist")},
              "enable_context_compression": compressed}
    fake = FakeLLM()
    compass, bible = build_setup(fake.default_response({"task": "setup"}), config)
    meeting = {"decision": fake.default_response({"payload": {
        "task": "decision", "chapter": 1, "compass": compass, "bible": bible}})}
    return config, compass, bible, meeting


def run_chapter(tmp_path, values, script=None, *, arm="panel"):
    config, compass, bible, meeting = values
    fake = FakeLLM(script)
    store = RunStore(tmp_path, config)
    router = LLMRouter(store, fake=fake)
    router.retry_delay = 0
    result = asyncio.run(write_chapter(router, config, compass, bible, meeting,
                                     chapter=1, arm=arm))
    return result, fake, store


def issue(category="adaptation"):
    return {"category": category, "problem": "本章场景超过约定数量。",
            "evidence": "林澈立即拔掉了外接线", "fix": "合并重复场景。", "blocking": True}


@pytest.mark.parametrize("enabled", [False, True])
def test_adaptation_blocker_rewrites_once_only_when_enabled(tmp_path, enabled):
    values = workshop()
    config = values[0]
    config["drama_adaptation"] = enabled

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "review":
            return {"issues": [issue(), issue("style")] if payload["review_round"] == 0 else []}

    result, fake, _store = run_chapter(tmp_path, values, script)
    reviews = [FakeLLM.payload(call) for call in fake.calls if call["task"] == "review"]
    writes = [FakeLLM.payload(call) for call in fake.calls if call["task"] == "write"]
    assert result["revision_rounds"] == int(enabled)
    assert len(reviews) == len(writes) == 1 + int(enabled)
    assert result["flags"] == []
    assert result["reviews"][0]["issues"][1]["blocking"] is False
    for payload in reviews:
        if enabled:
            assert payload["adaptation_blocking"] is True
            assert payload["adaptation_limits"] == config["adaptation"]
        else:
            assert "adaptation_blocking" not in payload and "adaptation_limits" not in payload
    if enabled:
        assert reviews[1]["previous_blocking_issues"] == [result["reviews"][0]["issues"][0]]
        assert writes[1]["blocking_issues"] == reviews[1]["previous_blocking_issues"]


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("explicit_false", [False, True])
def test_disabled_review_user_payload_bytes_match_legacy_formula(
        tmp_path, compressed, explicit_false):
    values = workshop(compressed=compressed)
    config, compass, bible, meeting = values
    if explicit_false:
        config["drama_adaptation"] = False

    def script(request, _index):
        payload = FakeLLM.payload(request)
        if payload["task"] == "review":
            return {"issues": [issue("continuity")] if payload["review_round"] == 0 else []}

    result, fake, _store = run_chapter(tmp_path, values, script)
    review_calls = [call for call in fake.calls if call["task"] == "review"]
    assert len(review_calls) == 2
    for revision, call in enumerate(review_calls):
        legacy = {"task": "review", "chapter": 1, "body": result["body"],
                  "beat_sheet": meeting["decision"]["beat_sheet"],
                  "bible": build_review_bible(compass, bible, 1,
                                               meeting["decision"]["beat_sheet"]["characters"]),
                  "review_round": revision}
        if revision:
            legacy["previous_blocking_issues"] = result["reviews"][revision - 1]["issues"]
        expected = context_messages(legacy) if compressed else [{"role": "user", "content":
            json.dumps(legacy, ensure_ascii=False, sort_keys=True)}]
        actual = [message for message in call["messages"] if message["role"] == "user"]
        assert [message["content"].encode("utf-8") for message in actual] == [
            message["content"].encode("utf-8") for message in expected]
        assert "adaptation_blocking" not in FakeLLM.payload(call)
        assert "adaptation_limits" not in FakeLLM.payload(call)


def new_character_archive(fake, request, appearance):
    archive = fake.default_response(request)
    archive["new_characters"] = [{"name": "记录保管人", "role": "supporting", "age": "40",
        "appearance": appearance, "personality": "谨慎", "motivation": "保全原件"}]
    return archive


@pytest.mark.parametrize("experiment,arm", [("P1", "solo"), ("P1", "panel"),
    ("A", "solo"), ("A", "panel"), ("A2", "panel"), ("B", "panel"), ("C", "panel")])
@pytest.mark.parametrize("short_appearance", [None, "短发"])
def test_only_p1_writing_repairs_short_new_character_appearance(
        tmp_path, experiment, arm, short_appearance):
    values = workshop(experiment=experiment)
    baseline = FakeLLM()
    attempts = []

    def script(request, _index):
        if request["task"] == "archive":
            attempts.append(deepcopy(request))
            return new_character_archive(baseline, request,
                short_appearance if len(attempts) == 1 else LONG_APPEARANCE)

    result, _fake, store = run_chapter(tmp_path, values, script, arm=arm)
    strict = experiment == "P1"
    assert len(attempts) == (2 if strict else 1)
    assert result["bible"]["locked"]["characters"][-1]["appearance"] == (
        LONG_APPEARANCE if strict else (short_appearance or ""))
    step = store.read_step(f"arm-{arm}/ch001/06-archive-archivist.json")
    assert step["status"] == "ok" and step["attempts"] == len(attempts)
    if strict:
        assert "new_characters[0].appearance" in attempts[1]["messages"][-1]["content"]


def test_p1_writing_rejects_repeated_short_appearance(tmp_path):
    values = workshop()
    baseline = FakeLLM()
    fake = FakeLLM(lambda request, _index: new_character_archive(baseline, request, "短发")
                   if request["task"] == "archive" else None)
    store = RunStore(tmp_path, values[0])
    router = LLMRouter(store, fake=fake)
    with pytest.raises(StepFailed):
        asyncio.run(write_chapter(router, *values, chapter=1, arm="panel"))
    assert sum(call["task"] == "archive" for call in fake.calls) == 2
    assert values[2]["version"] == 1
    assert store.read_step("arm-panel/ch001/06-archive-archivist.json")["status"] == "step_failed"


def test_rearchive_repairs_short_new_appearance_before_persisting(monkeypatch, tmp_path):
    import database
    from novel import runner, service
    from novel.billing import NovelBilling
    from novel.store_db import get_db

    async def scenario():
        monkeypatch.setenv("DEV_MODE", "1")
        monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "rearchive.db"))
        await database.init_db()
        await database.get_or_create_user("author")
        baseline = FakeLLM()
        rearchives = []

        def script(request, _index):
            if request["step_key"].startswith("rearchive/") and request["task"] == "archive":
                rearchives.append(deepcopy(request))
                return new_character_archive(baseline, request,
                    "短发" if len(rearchives) == 1 else LONG_APPEARANCE)

        fake = FakeLLM(script)

        def factory(store, username, novel_id, token):
            router = LLMRouter(store, fake=fake, dry_run=True,
                               billing=NovelBilling(username, novel_id, token))
            router.retry_delay = 0
            return router

        async def drain(novel_id):
            task = runner.TASKS.get(novel_id)
            if task is not None:
                await asyncio.wait_for(asyncio.shield(task), 10)

        monkeypatch.setattr(runner, "router_factory", factory)
        data = service.CreateNovel(seed_idea="保全旧案原件", panel_mode="solo", automation="full_auto",
            agents={"editor": "dashscope:qwen3.8-max", "writer": "deepseek:deepseek-flash",
                    "archivist": "ark:doubao-seed-2-1-pro-260915", "reviewer": "dashscope:qwen3.8-max"},
            target={"min_chapters": 1, "max_chapters": 1, "chapter_words": 1000},
            budget_strawberries=100000)
        book = await service.create("author", data)
        novel_id = book["id"]
        await drain(novel_id)
        await service.approve_setup("author", novel_id, service.SetupApproval())
        await drain(novel_id)
        before = await service.detail("author", novel_id)
        assert before["status"] == "awaiting_end"
        await service.edit_chapter("author", novel_id, 1,
                                   service.Manuscript(body="# 第1章 改稿\n她保留了原始录像。"))
        await drain(novel_id)
        after = await service.detail("author", novel_id)
        assert after["status"] == "awaiting_end"
        assert after["bible_version"] == before["bible_version"] + 1
        assert len(rearchives) == 2
        assert "new_characters[0].appearance" in rearchives[1]["messages"][-1]["content"]
        bible = await service.bible("author", novel_id)
        assert bible["locked"]["characters"][-1]["appearance"] == LONG_APPEARANCE
        async with get_db() as db:
            async with db.execute("SELECT source FROM novel_bible_versions WHERE novel_id=? "
                                  "ORDER BY version DESC LIMIT 1", (novel_id,)) as cursor:
                assert (await cursor.fetchone())["source"] == "rearchive:1"
        assert not runner.TASKS

    asyncio.run(scenario())
