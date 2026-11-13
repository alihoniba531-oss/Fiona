"""续拆走查造数：在隔离临时库里为 tester 造一本连载中的书。内容全部是虚构示例。

用法（先导出隔离环境变量，再在候选副本的 backend/ 目录下运行）：
  .venv/bin/python <此文件>            # 写到第 5 章，第 6 章在规划中
  .venv/bin/python <此文件> --extend   # 「接着写」到第 12 章：改第 3 章正文、第 4 章标待复核、圣经新登记 C2 阿禾、第 13 章在规划中
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.getcwd())

import database
from database import get_or_create_user
from novel.store_db import get_db

U = "tester"
BOOK = "55555555-5555-4555-8555-555555555555"
COMPASS = {"title": "渡江", "logline": "少年在封渡前夜独自过江。", "theme": "离开与承担", "core_conflict": "要不要丢下等不到的人",
           "protagonist": {"name": "阿岚", "want": "过江", "need": "学会自己做决定"}, "candidate_endings": [{"summary": "信一直在他怀里"}],
           "main_threads": [{"id": "T1", "name": "过江", "description": "封渡之前找到一条船"}], "target": {"min_chapters": 10, "max_chapters": 30, "chapter_words": 2000}}
C1 = {"id": "C1", "name": "阿岚", "role": "main", "age": "十六", "appearance": "瘦，背一个小包袱，常年赤脚走在渡口的石板上", "personality": "寡言", "motivation": "过江"}
C2 = {"id": "C2", "name": "阿禾", "role": "support", "age": "十七", "appearance": "高个子，左手缠着旧布条，说话时总看向江面", "personality": "爽快", "motivation": "找哥哥"}


def bible(version, characters):
    return {"version": version, "locked": {"characters": characters, "world_rules": ["封渡之后任何船不得离岸"],
                                           "style_guide": {"pov": "第三人称", "tense": "过去", "voice": "克制", "banned_phrases": []},
                                           "adaptation": {"max_main_characters": 6, "max_scenes_per_chapter": 3}},
            "dynamic": {"character_states": {}, "foreshadowing": [], "chapter_summaries": [], "timeline": [], "used_beats": []}}


def body(number, edited=False):
    extra = "（改稿后）阿岚把船票塞回了怀里。" if edited else ""
    who = "阿禾" if number >= 2 else "船夫"
    return (f"第{number}章 正文开始。\n第{number}章第一场：阿岚在渡口第{number}次等船。{extra}\n"
            f"第{number}章第二场：{who}在雾里喊了一声。\n第{number}章第三场：江面上只剩一盏灯。\n")


def config():
    return {"seed_idea": "示例", "agents": {"editor": "dashscope:qwen3.8-max", "writer": "dashscope:qwen3.8-max", "archivist": "dashscope:qwen3.8-max"},
            "panel_mode": "critique", "automation": "per_chapter", "batch_size": 3,
            "target": {"min_chapters": 10, "max_chapters": 30, "chapter_words": 2000},
            "adaptation": {"max_main_characters": 6, "max_scenes_per_chapter": 3}, "drama_adaptation": False, "structure": "v1",
            "budget_strawberries": 5000}


async def main():
    extend = "--extend" in sys.argv
    await database.init_db()
    await get_or_create_user(U)
    async with get_db() as db:
        if not extend:
            for table in ("novel_notes", "novel_chapters", "novel_bible_versions"):
                await db.execute(f"DELETE FROM {table} WHERE novel_id=?", (BOOK,))
            await db.execute("DELETE FROM novels WHERE id=?", (BOOK,))
            await db.execute("""INSERT INTO novels(id,username,title,seed_idea,status,pause_reason,config_json,bible_version,chapters_done,words_done,budget_strawberries,spent_strawberries)
                                VALUES(?,?,?,?,'awaiting_plan',NULL,?,1,5,?,5000,0)""",
                             (BOOK, U, "渡江", "示例", json.dumps(config(), ensure_ascii=False), 5 * len(body(1))))
            await db.execute("UPDATE novels SET compass_json=? WHERE id=?", (json.dumps(COMPASS, ensure_ascii=False), BOOK))
            await db.execute("INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,1,?,'serial-seed')",
                             (BOOK, U, json.dumps(bible(1, [C1]), ensure_ascii=False)))
            for number in range(1, 6):
                await db.execute("INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,flags_json,meeting_json,review_json,archive_json) VALUES(?,?,?,?,?,?,'[]','{}','[]','{}')",
                                 (BOOK, U, number, "done", f"第{number}回", body(number)))
            await db.execute("INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,flags_json,meeting_json,review_json,archive_json) VALUES(?,?,6,'awaiting_plan_approval',NULL,NULL,'[]','{}','[]','{}')", (BOOK, U))
        else:
            await db.execute("DELETE FROM novel_chapters WHERE novel_id=? AND chapter=6", (BOOK,))
            for number in range(6, 13):
                await db.execute("INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,flags_json,meeting_json,review_json,archive_json) VALUES(?,?,?,?,?,?,'[]','{}','[]','{}')",
                                 (BOOK, U, number, "done", f"第{number}回", body(number)))
            await db.execute("INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,flags_json,meeting_json,review_json,archive_json) VALUES(?,?,13,'awaiting_plan_approval',NULL,NULL,'[]','{}','[]','{}')", (BOOK, U))
            await db.execute("UPDATE novel_chapters SET body=?,edited_by_user=1 WHERE novel_id=? AND chapter=3", (body(3, edited=True), BOOK))
            await db.execute("UPDATE novel_chapters SET status='stale' WHERE novel_id=? AND chapter=4", (BOOK,))
            await db.execute("INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,9,?,'serial-seed')",
                             (BOOK, U, json.dumps(bible(9, [C1, C2]), ensure_ascii=False)))
            await db.execute("UPDATE novels SET chapters_done=12,bible_version=9,words_done=? WHERE id=?", (12 * len(body(1)), BOOK))
        await db.commit()
    print(json.dumps({"book": BOOK, "extend": extend}))


asyncio.run(main())
