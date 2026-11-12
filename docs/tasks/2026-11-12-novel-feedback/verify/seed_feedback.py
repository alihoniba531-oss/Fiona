"""修改意见卡走查造数：在隔离临时库里为 tester 造四本书、七张修改意见卡（六张挂在聊天消息上，一张留给流式注入）。

用法（先导出隔离环境变量，再在候选工作树的 backend/ 目录下运行）：
  .venv/bin/python <此文件>
输出 JSON：各本书与各张卡的 id。内容全部是虚构示例。
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.getcwd())

import database
from database import get_or_create_user, save_message
from agent_store import resolve_chat_conversation
from novel.store_db import get_db

U = "tester"
A = "11111111-1111-4111-8111-111111111111"  # 春山：等确认第 3 章细纲，逐章确认，主编自带模型
B = "22222222-2222-4222-8222-222222222222"  # 归舟：等确认第 5 章细纲，第 5 章被定为最后一章
C = "33333333-3333-4333-8333-333333333333"  # 旧梦：已完结
D = "44444444-4444-4444-8444-444444444444"  # 雾灯：重新定稿中途暂停


def config(editor="byok:self", automation="per_chapter", max_chapters=10):
    return {"seed_idea": "示例", "agents": {"editor": editor, "writer": "dashscope:qwen3.8-max", "archivist": "dashscope:qwen3.8-max"},
            "panel_mode": "critique", "automation": automation, "batch_size": 3,
            "target": {"min_chapters": 3, "max_chapters": max_chapters, "chapter_words": 2000},
            "adaptation": {"max_main_characters": 6, "max_scenes_per_chapter": 3},
            "drama_adaptation": False, "structure": "v1", "budget_strawberries": 5000}


BEAT = {"title": "船家的价", "chapter_goal": "阿岚第一次开口还价。", "advances_threads": [], "characters": [],
        "scenes": [{"location": "渡口栈桥", "summary": "船家把价翻了一倍。"}], "beats": ["船家加价", "阿岚还价不成"],
        "opening_hook": "雾里只剩最后一条船。", "ending_hook": "银子只够一个人。", "foreshadowing_plant": [], "foreshadowing_resolve": []}


def meeting(notes=(), responses=(), ending="continue", redo_note=None):
    data = {"mode": "critique", "brief": {"mode": "critique", "user_notes": list(notes)}, "proposals": [], "objections": [], "critiques": [],
            "decision": {"beat_sheet": BEAT, "rationale": "示例", "ending_status": ending, "objection_responses": [], "user_note_responses": list(responses)}}
    if redo_note is not None:
        data["_redo_note"] = redo_note
        data["_redo_count"] = 1
    return json.dumps(data, ensure_ascii=False)


BODY = "清晨，雾。\n\n阿岚站在栈桥尽头。" * 20


COMPASS = {"title": "示例", "logline": "少年在封渡前夜独自过江。", "theme": "离开与承担", "core_conflict": "要不要丢下等不到的人",
           "protagonist": {"name": "阿岚", "want": "过江", "need": "学会自己做决定"}, "candidate_endings": [{"summary": "信一直在他怀里"}],
           "main_threads": [{"id": "T1", "name": "过江", "description": "封渡之前找到一条船"}], "target": {"min_chapters": 3, "max_chapters": 10, "chapter_words": 2000}}
BIBLE = {"version": 1, "locked": {"characters": [{"id": "C1", "name": "阿岚", "role": "main", "age": "十六", "appearance": "瘦，背一个小包袱，常年赤脚走在渡口的石板上", "personality": "寡言", "motivation": "过江"}],
                                  "world_rules": ["封渡之后任何船不得离岸"], "style_guide": {"pov": "第三人称", "tense": "过去", "voice": "克制", "banned_phrases": []},
                                  "adaptation": {"max_main_characters": 6, "max_scenes_per_chapter": 3}},
         "dynamic": {"character_states": {}, "foreshadowing": [], "chapter_summaries": [], "timeline": [], "used_beats": []}}


async def add_book(db, novel_id, title, status, cfg, chapters, done, pause_reason=None):
    for table in ("novel_notes", "novel_chapters", "novel_bible_versions"):
        await db.execute(f"DELETE FROM {table} WHERE novel_id=?", (novel_id,))
    await db.execute("DELETE FROM novels WHERE id=?", (novel_id,))
    await db.execute("""INSERT INTO novels(id,username,title,seed_idea,status,pause_reason,config_json,bible_version,chapters_done,words_done,budget_strawberries,spent_strawberries)
                        VALUES(?,?,?,?,?,?,?,1,?,?,5000,0)""",
                     (novel_id, U, title, "示例", status, pause_reason, json.dumps(cfg, ensure_ascii=False), done, done * len(BODY)))
    await db.execute("UPDATE novels SET compass_json=? WHERE id=?", (json.dumps(COMPASS, ensure_ascii=False), novel_id))
    await db.execute("INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,1,?,'fb-seed')", (novel_id, U, json.dumps(BIBLE, ensure_ascii=False)))
    for number, chapter_status, chapter_title, meeting_json in chapters:
        body = BODY if chapter_status in ("done", "stale") else None
        await db.execute("INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,flags_json,meeting_json,review_json,archive_json) VALUES(?,?,?,?,?,?,'[]',?,'[]','{}')",
                         (novel_id, U, number, chapter_status, chapter_title, body, meeting_json or "{}"))


async def main():
    await database.init_db()
    for name in (U, "outsider"):
        await get_or_create_user(name)
    conversation = (await resolve_chat_conversation(U, None))["conversation"]["id"]
    out = {"conversation": conversation, "books": {"A": A, "B": B, "C": C, "D": D}}
    async with get_db() as db:
        await db.execute("DELETE FROM novel_feedback WHERE owner_username=?", (U,))
        await add_book(db, A, "春山", "awaiting_plan", config(), [(1, "done", "渡口", None), (2, "done", "北岸脚步", None), (3, "awaiting_plan_approval", None, None)], 2)
        cursor = await db.execute("INSERT INTO novel_notes(novel_id,username,text,status) VALUES(?,?,?,'pending')", (A, U, "以后要求乙：船家的口音别用汴京腔。"))
        n1 = cursor.lastrowid
        await db.execute("INSERT INTO novel_notes(novel_id,username,text,status) VALUES(?,?,?,'pending')", (A, U, "第三章结尾留一个钩子。"))
        await db.execute("UPDATE novel_chapters SET meeting_json=? WHERE novel_id=? AND chapter=3",
                         (meeting([{"id": f"N{n1}", "text": "以后要求乙：船家的口音别用汴京腔。"}], [{"note_id": f"N{n1}", "adopted": True, "response": "第三章里船家改说本地话。"}]), A))
        await add_book(db, B, "归舟", "awaiting_plan", config(editor="dashscope:qwen3.8-max"),
                       [(i, "done", f"第{i}回", None) for i in range(1, 5)] + [(5, "awaiting_plan_approval", None, meeting(ending="end"))], 4)
        await add_book(db, C, "旧梦", "completed", config(editor="dashscope:qwen3.8-max"), [(i, "done", f"旧梦{i}", None) for i in range(1, 4)], 3)
        await add_book(db, D, "雾灯", "paused", config(), [(1, "done", "灯下", None), (2, "planning", None, meeting(redo_note="细纲要求戊：让灯灭得更早。"))], 1, pause_reason="byok_unavailable")
        cards = {
            "FA": (A, "春山", "以后要求甲：后面每章少写天气，多写人。", "细纲要求甲：这一章要让阿岚先开口。", 3,
                   [{"chapter": 1, "title": "渡口", "issue": "问题甲一：时间线和第二章对不上。"}, {"chapter": 2, "title": "北岸脚步", "issue": "问题甲二：父亲提前露面了。"}], None, None),
            "FB": (A, "春山", "以后要求乙：船家的口音别用汴京腔。", "", None, [], n1, None),
            "FC": (B, "归舟", "以后要求丙：结局前把信的下落交代清楚。", "", None, [], None, None),
            "FD": (C, "旧梦", "", "", None, [{"chapter": 2, "title": "旧梦2", "issue": "问题丁：第二章人物动机不清楚。"}], None, None),
            "FE": (D, "雾灯", "", "细纲要求戊：让灯灭得更早。", 2, [], None, "2026-11-12 00:00:00"),
            "FF": (A, "春山", "以后要求己：流式注入的卡片。", "", None, [], None, None),
        }
        for key, (novel_id, title, next_text, plan_text, plan_chapter, written, note_id, redo_at) in cards.items():
            fid = f"fb-{key.lower()}-0000-4000-8000-000000000000"
            await db.execute("""INSERT INTO novel_feedback(id,owner_username,conversation_id,novel_id,book_title,next_chapters,current_plan,plan_chapter,written_json,note_id,note_sent_at,redo_started_at)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (fid, U, conversation, novel_id, title, next_text, plan_text, plan_chapter, json.dumps(written, ensure_ascii=False),
                              note_id, "2026-11-12 00:00:00" if note_id else None, redo_at))
            out[key] = fid
        await db.commit()
    for key in ("FA", "FB", "FC", "FD", "FE"):
        await save_message(U, "user", f"帮我把意见做成卡（{key}）", conversation_id=conversation)
        ok = await save_message(U, "assistant", f"修改意见卡已放进聊天（{key}）。", conversation_id=conversation, novel_feedback_id=out[key])
        assert ok
    print(json.dumps(out, ensure_ascii=False))


asyncio.run(main())
