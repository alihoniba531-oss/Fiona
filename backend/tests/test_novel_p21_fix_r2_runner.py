"""R2: a rebuilt character reusing an ID must not inherit another name's edits."""

import asyncio
from copy import deepcopy

from novel import service
from test_novel_p21_fix_r1_runner import (
    APPEARANCE, FIELDS, LATER_APPEARANCE, USER, characters, workshop,
)


def test_rearchive_skips_user_edits_when_new_character_reuses_id_with_another_name(workshop):
    async def scenario():
        workshop.add_archive_character = True
        respond = workshop.respond
        rebuilt_character = {
            "name": "老张", "role": "supporting", "age": "60",
            "appearance": "花白短发向后梳齐，肩背宽厚，穿着靛蓝色布褂，左腕戴一只旧铜表。",
            "personality": "急性子", "motivation": "守住铺子",
        }

        def reuse_id(request, index):
            answer = respond(request, index)
            if request["task"] == "archive" and request["step_key"].startswith("rearchive/"):
                answer["new_characters"] = [deepcopy(rebuilt_character)]
            return answer

        workshop.fake.script = reuse_id
        novel_id = await workshop.create()
        original = await service.bible(USER, novel_id)
        assert characters(original)["C3"]["name"] == "临时证人"

        witness_edits = {"appearance": LATER_APPEARANCE,
                         "personality": "心思缜密", "motivation": "逃离旧案"}
        patched = workshop.patch(novel_id, witness_edits, "C3")
        assert characters(patched)["C3"]["name"] == "临时证人"
        assert {field: characters(patched)["C3"][field] for field in FIELDS} == witness_edits

        same_name_edits = {"appearance": APPEARANCE,
                           "personality": "坚定且坦率", "motivation": "为证人保留原件"}
        workshop.patch(novel_id, same_name_edits, "C1")
        rebuilt = await workshop.rearchive(
            novel_id, body="# 第1章 重新登记\n临时证人已经离开，老张带着店铺账本出现。")

        # The name guard must preserve normal edits as well as reject reused IDs.
        assert characters(rebuilt)["C1"]["name"] == characters(original)["C1"]["name"]
        assert {field: characters(rebuilt)["C1"][field] for field in FIELDS} == same_name_edits
        assert characters(rebuilt)["C3"] == {**rebuilt_character, "id": "C3"}, (
            "GRAFTED ONTO UNRELATED CHARACTER: 临时证人的补改覆盖了老张的重建人物卡")

    asyncio.run(scenario())
