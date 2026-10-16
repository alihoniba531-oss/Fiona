"""F1: real offline character PATCH edits survive latest-chapter rebuilding."""

import asyncio
from copy import deepcopy
import json

import pytest

import database
from novel import runner, service
from novel.billing import NovelBilling
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.store_db import get_db
from rate_limit import limiter


USER = "p21-fix-author"
HEADERS = {"X-Dev-User": USER}
FIELDS = ("appearance", "personality", "motivation")
APPEARANCE = "齐肩黑发束在脑后，身形清瘦，穿洗旧的深蓝长外套，左眉有一道浅疤。"
LATER_APPEARANCE = "头发剪到耳边，肩背宽阔，身穿浅灰色亚麻长衫，右手食指戴旧银戒。"


class Workshop:
    def __init__(self, client):
        self.client = client
        self.baseline = FakeLLM()
        self.add_archive_character = False
        self.fake = FakeLLM(self.respond)

    def respond(self, request, _index):
        if request["task"] == "setup":
            answer = self.baseline.default_response(request)
            character = deepcopy(answer["characters"][0])
            character.update(name="周临", role="supporting", personality="沉默", motivation="保全证人")
            answer["characters"].append(character)
            return answer
        if request["task"] == "archive":
            answer = self.baseline.default_response(request)
            rearchive = request["step_key"].startswith("rearchive/")
            answer["character_state_changes"] = [{"id": "C2", "field": "location",
                "value": "新登记台" if rearchive else "旧档案室"}]
            if rearchive:
                answer["summary"] = "林澈重新核对改稿中的原始记录，保管人转移到新登记台。"
                answer["timeline_add"] = ["第1章：重新核对最新改稿。"]
            elif self.add_archive_character:
                answer["new_characters"] = [{"name": "临时证人", "role": "supporting", "age": "40",
                    "appearance": APPEARANCE, "personality": "慎言", "motivation": "交付原件"}]
            return answer

    def router(self, store, username, novel_id, token):
        router = LLMRouter(store, fake=self.fake, dry_run=True,
                           billing=NovelBilling(username, novel_id, token))
        router.retry_delay = 0
        return router

    async def drain(self, novel_id):
        task = runner.TASKS.get(novel_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), 10)

    async def create(self):
        await database.get_or_create_user(USER)
        data = service.CreateNovel(seed_idea="旧档案里的秘密", panel_mode="solo", automation="full_auto",
            agents={"editor": "dashscope:qwen3.8-max", "writer": "deepseek:deepseek-flash",
                    "archivist": "ark:doubao-seed-2-1-pro-260915", "reviewer": "dashscope:qwen3.8-max"},
            target={"min_chapters": 1, "max_chapters": 1, "chapter_words": 1000},
            budget_strawberries=100000)
        book = await service.create(USER, data)
        novel_id = book["id"]
        await self.drain(novel_id)
        await service.approve_setup(USER, novel_id, service.SetupApproval())
        await self.drain(novel_id)
        assert (await service.detail(USER, novel_id))["status"] == "awaiting_end"
        return novel_id

    def patch(self, novel_id, changes, character_id="C1"):
        response = self.client.patch(f"/novels/{novel_id}/characters/{character_id}",
                                     json=changes, headers=HEADERS)
        assert response.status_code == 200, response.text
        return response.json()

    async def rearchive(self, novel_id, body="# 第1章 改稿\n她重新保留了原始录像。"):
        before = await service.detail(USER, novel_id)
        response = await service.edit_chapter(USER, novel_id, 1, service.Manuscript(body=body))
        assert response["rearchiving"] is True
        await self.drain(novel_id)
        after = await service.detail(USER, novel_id)
        assert (after["status"], after["chapters_done"], after["pause_reason"]) == (
            before["status"], before["chapters_done"], before["pause_reason"])
        assert after["bible_version"] == before["bible_version"] + 1
        assert not runner.TASKS
        return await service.bible(USER, novel_id)

    async def versions(self, novel_id):
        async with get_db() as db:
            return await service.rows(db, "SELECT version,source,bible_json FROM novel_bible_versions "
                                      "WHERE novel_id=? ORDER BY version", (novel_id,))


@pytest.fixture
def workshop(client, monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("FIONA_NOVEL", "1")
    monkeypatch.setenv("FIONA_NOVEL_USERS", USER)
    monkeypatch.setattr(limiter, "enabled", False)

    async def forbidden(*args, **kwargs):
        raise AssertionError("F1 tests must never call a real model")

    monkeypatch.setattr(LLMRouter, "_single_real_call", forbidden)
    value = Workshop(client)
    monkeypatch.setattr(runner, "router_factory", value.router)
    return value


def characters(bible):
    return {character["id"]: character for character in bible["locked"]["characters"]}


@pytest.mark.parametrize("patches", [
    [{"appearance": APPEARANCE, "personality": "果断而细致", "motivation": "公开保护证人"}],
    [{"appearance": APPEARANCE}, {"motivation": "将原始记录交还证人"}],
], ids=["all-three-fields", "two-partial-patches"])
def test_rearchive_preserves_real_patches_and_matches_unpatched_rebuild(workshop, patches):
    async def scenario():
        novel_id = await workshop.create()
        original = await service.bible(USER, novel_id)
        expected_character = deepcopy(characters(original)["C1"])
        for changes in patches:
            patched = workshop.patch(novel_id, changes)
            expected_character.update(changes)
            assert characters(patched)["C1"] == expected_character
        history_before = await workshop.versions(novel_id)
        rebuilt = await workshop.rearchive(novel_id)
        for field in FIELDS:
            assert characters(rebuilt)["C1"][field] == expected_character[field], (
                f"user edit lost for C1.{field}")
        history_after = await workshop.versions(novel_id)
        assert history_after[:-1] == history_before
        assert [item["source"] for item in history_after[-len(patches)-1:]] == (
            ["user_edit"] * len(patches) + ["rearchive:1"])
        assert history_after[-1]["version"] == history_before[-1]["version"] + 1

        control_id = await workshop.create()
        control = await workshop.rearchive(control_id)
        assert characters(rebuilt)["C2"] == characters(control)["C2"]
        assert rebuilt["dynamic"] == control["dynamic"]
        assert rebuilt["dynamic"] != original["dynamic"]
        expected = deepcopy(control)
        expected["version"] = rebuilt["version"]
        characters(expected)["C1"].update(expected_character)
        assert rebuilt == expected

    asyncio.run(scenario())


def test_rearchive_replays_patches_in_version_order_across_multiple_rebuilds(workshop):
    async def scenario():
        novel_id = await workshop.create()
        workshop.patch(novel_id, {"appearance": APPEARANCE})
        first = await workshop.rearchive(novel_id)
        assert characters(first)["C1"]["appearance"] == APPEARANCE
        workshop.patch(novel_id, {"personality": "坚定且坦率"})
        workshop.patch(novel_id, {"appearance": LATER_APPEARANCE})
        latest = await workshop.rearchive(novel_id, body="# 第1章 二次改稿\n她把原件交还证人。")
        assert characters(latest)["C1"]["appearance"] == LATER_APPEARANCE
        assert characters(latest)["C1"]["personality"] == "坚定且坦率"
        assert latest["dynamic"] == first["dynamic"]
        versions = await workshop.versions(novel_id)
        assert [item["source"] for item in versions[-5:]] == [
            "user_edit", "rearchive:1", "user_edit", "user_edit", "rearchive:1"]

    asyncio.run(scenario())


def test_rearchive_skips_edited_characters_absent_from_the_rebuilt_chapter(workshop):
    async def scenario():
        workshop.add_archive_character = True
        novel_id = await workshop.create()
        assert "C3" in characters(await service.bible(USER, novel_id))
        workshop.patch(novel_id, {"appearance": LATER_APPEARANCE, "motivation": "远离旧案"}, "C3")
        workshop.patch(novel_id, {"personality": "先核对事实再下结论"})
        rebuilt = await workshop.rearchive(novel_id)
        assert set(characters(rebuilt)) == {"C1", "C2"}
        assert set(rebuilt["dynamic"]["character_states"]) == {"C1", "C2"}
        assert characters(rebuilt)["C1"]["personality"] == "先核对事实再下结论"

    asyncio.run(scenario())


def test_rearchive_diffs_each_user_edit_against_its_immediate_prior_version(workshop):
    async def scenario():
        novel_id = await workshop.create()
        original = await service.bible(USER, novel_id)
        workshop.patch(novel_id, {"personality": "只相信原始记录"})
        current = await service.bible(USER, novel_id)
        # Simulate a historical non-user version between PATCHes, with a gap.
        # These changes must not be mistaken for the next user's own edit.
        archived = {key: deepcopy(value) for key, value in current.items() if key != "compass"}
        archived["version"] += 2
        characters(archived)["C1"]["appearance"] = LATER_APPEARANCE
        characters(archived)["C2"]["motivation"] = "非用户归档差异"
        archived["locked"]["characters"].reverse()
        archived["locked"]["world_rules"].append("历史归档中的世界差异")
        archived["dynamic"]["timeline"].append("不应重放的历史归档事件")
        async with get_db() as db:
            await db.execute("INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) "
                             "VALUES(?,?,?,?,?)", (novel_id, USER, archived["version"],
                             service.encoded(archived), "rearchive:1"))
            await db.execute("UPDATE novels SET bible_version=? WHERE id=?", (archived["version"], novel_id))
            await db.commit()
        workshop.patch(novel_id, {"motivation": "带证人核对原件"})
        rebuilt = await workshop.rearchive(novel_id)
        assert characters(rebuilt)["C1"]["personality"] == "只相信原始记录"
        assert characters(rebuilt)["C1"]["motivation"] == "带证人核对原件"
        assert characters(rebuilt)["C1"]["appearance"] == characters(original)["C1"]["appearance"]
        assert characters(rebuilt)["C2"] == characters(original)["C2"]
        assert rebuilt["locked"]["world_rules"] == original["locked"]["world_rules"]
        assert "不应重放的历史归档事件" not in rebuilt["dynamic"]["timeline"]

    asyncio.run(scenario())
