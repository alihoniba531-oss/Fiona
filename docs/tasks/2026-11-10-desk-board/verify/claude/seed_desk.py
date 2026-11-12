"""案头第一期走查造数：在隔离临时库里为 tester 造两本书和一个带分集方案的短片项目。

用法（先 source env.sh，再在候选 worktree 的 backend/ 目录下运行）：
  .venv/bin/python <此文件>
输出 JSON：{book_plan, book_done, project, project_empty}
  book_plan  《春山》：等你确认细纲；第 1 章待复核、第 2 章定稿、第 3 章细纲待批；2 条待处理留言
  book_done  《归舟》：已完结 3 章；有两个短片项目，新的那个拆解完成并有 3 集，旧的没有分集方案
  empty_user 没有任何书（空态）；其它账号不在书斋白名单（无权限态）
内容全部是虚构示例。
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.getcwd())  # 脚本放在仓库外，后端模块从当前目录（backend/）导入

import database
from database import get_or_create_user
from novel.store_db import get_db

A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
P_NEW, P_OLD, BID = "desk-proj-new", "desk-proj-old", "desk-bid-1"
U = "tester"

CONFIG = {"seed_idea": "示例", "agents": {"editor": "dashscope:qwen3.8-max", "writer": "dashscope:qwen3.8-max", "archivist": "dashscope:qwen3.8-max"},
          "panel_mode": "critique", "automation": "per_chapter", "batch_size": 3,
          "target": {"min_chapters": 8, "max_chapters": 10, "chapter_words": 2000},
          "adaptation": {"max_main_characters": 6, "max_scenes_per_chapter": 3},
          "drama_adaptation": True, "structure": "v1", "budget_strawberries": 5000}


def compass(title):
    return {"title": title, "logline": "少年在封渡前夜独自过江，去找一封没寄出的信。", "theme": "离开与承担",
            "core_conflict": "要不要丢下等不到的人", "protagonist": {"name": "阿岚", "want": "过江", "need": "学会自己做决定"},
            "candidate_endings": [{"summary": "信一直在他怀里"}],
            "main_threads": [{"id": "T1", "name": "过江", "description": "封渡之前找到一条船"}, {"id": "T2", "name": "那封信", "description": "信到底留在了哪一岸"}],
            "target": CONFIG["target"]}


def bible(summaries):
    return {"version": 1,
            "locked": {"characters": [{"id": "C1", "name": "阿岚", "role": "main", "age": "十六", "appearance": "瘦，背一个小包袱", "personality": "寡言", "motivation": "过江"}],
                       "world_rules": ["封渡之后任何船不得离岸"],
                       "style_guide": {"pov": "第三人称", "tense": "过去", "voice": "克制", "banned_phrases": []},
                       "adaptation": CONFIG["adaptation"]},
            "dynamic": {"character_states": {}, "foreshadowing": [], "chapter_summaries": summaries, "timeline": [], "used_beats": []}}


BEAT = {"title": "船家的价", "chapter_goal": "让阿岚第一次开口还价，并发现银子只够一个人过江。", "advances_threads": ["T1"], "characters": ["C1"],
        "scenes": [{"location": "渡口栈桥", "summary": "船家把价翻了一倍，阿岚数银子。"}, {"location": "岸边草棚", "summary": "阿岚听见北岸有人喊他的名字。"}],
        "beats": ["船家加价", "阿岚还价不成", "数银子", "北岸的喊声"], "opening_hook": "雾里只剩最后一条船。", "ending_hook": "银子只够一个人。",
        "foreshadowing_plant": [], "foreshadowing_resolve": []}
MEETING = {"mode": "critique", "brief": {"mode": "critique", "user_notes": []}, "proposals": [], "objections": [], "critiques": [],
           "decision": {"beat_sheet": BEAT, "rationale": "承接上一章的封渡消息。", "ending_status": "continue", "objection_responses": [], "user_note_responses": []}}
BODY = "清晨，雾。\n\n阿岚站在栈桥尽头，听见身后有人说，北岸今夜封渡。\n\n他没有回头。" * 40


async def main():
    await database.init_db()
    for name in (U, "empty_user", "outsider"):
        await get_or_create_user(name)
    async with get_db() as db:
        for novel in (A, B):
            for table in ("novel_notes", "novel_chapters", "novel_bible_versions"):
                await db.execute(f"DELETE FROM {table} WHERE novel_id=?", (novel,))
            await db.execute("DELETE FROM novels WHERE id=?", (novel,))
        sums_a = [{"chapter": 1, "title": "渡口", "summary": "清晨，雾。阿岚在渡口等船，听见北岸今夜封渡的消息。"},
                  {"chapter": 2, "title": "北岸脚步", "summary": "父亲没有露面，只有脚步声。阿岚决定不再等。"}]
        await db.execute("""INSERT INTO novels(id,username,title,seed_idea,status,config_json,compass_json,bible_version,chapters_done,words_done,budget_strawberries,spent_strawberries)
                            VALUES(?,?,?,?,?,?,?,1,2,?,5000,600)""",
                         (A, U, "春山", "示例", "awaiting_plan", json.dumps(CONFIG, ensure_ascii=False), json.dumps(compass("春山"), ensure_ascii=False), 2 * len(BODY)))
        await db.execute("INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,1,?,'desk-seed')", (A, U, json.dumps(bible(sums_a), ensure_ascii=False)))
        rows = [(1, "stale", "渡口", BODY, None), (2, "done", "北岸脚步", BODY, None), (3, "awaiting_plan_approval", None, None, json.dumps(MEETING, ensure_ascii=False))]
        for chapter, status, title, body, meeting in rows:
            await db.execute("INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,flags_json,meeting_json,review_json,archive_json) VALUES(?,?,?,?,?,?,'[]',?,'[]','{}')",
                             (A, U, chapter, status, title, body, meeting or "{}"))
        for text in ("船家的口音别用汴京腔。", "第三章结尾留一个钩子。"):
            await db.execute("INSERT INTO novel_notes(novel_id,username,text,status) VALUES(?,?,?,'pending')", (A, U, text))
        cfg_b = {**CONFIG, "target": {"min_chapters": 3, "max_chapters": 3, "chapter_words": 2000}}
        sums_b = [{"chapter": n, "title": t, "summary": s} for n, t, s in ((1, "归舟", "船回到南岸。"), (2, "当铺", "阿岚典当了包袱里唯一值钱的东西。"), (3, "信", "信其实一直在他怀里。"))]
        await db.execute("""INSERT INTO novels(id,username,title,seed_idea,status,config_json,compass_json,bible_version,chapters_done,words_done,budget_strawberries,spent_strawberries,completed_at)
                            VALUES(?,?,?,?,?,?,?,1,3,?,5000,900,CURRENT_TIMESTAMP)""",
                         (B, U, "归舟", "示例", "completed", json.dumps(cfg_b, ensure_ascii=False), json.dumps(compass("归舟"), ensure_ascii=False), 3 * len(BODY)))
        await db.execute("INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,1,?,'desk-seed')", (B, U, json.dumps(bible(sums_b), ensure_ascii=False)))
        for item in sums_b:
            await db.execute("INSERT INTO novel_chapters(novel_id,username,chapter,status,title,body,flags_json,meeting_json,review_json,archive_json) VALUES(?,?,?,'done',?,?,'[]','{}','[]','{}')",
                             (B, U, item["chapter"], item["title"], BODY))
        await db.commit()

    from studio import store, breakdown_plan as plan
    async with store.connection(transaction=True) as db:
        for pid in (P_NEW, P_OLD):
            for table in ("studio_plan_revisions", "studio_episodes"):
                await db.execute(f"DELETE FROM {table} WHERE project_id=?", (pid,))
        await db.execute("DELETE FROM studio_chunks WHERE breakdown_id=?", (BID,))
        await db.execute("DELETE FROM studio_units WHERE breakdown_id=?", (BID,))
        await db.execute("DELETE FROM studio_breakdowns WHERE id=?", (BID,))
        await db.execute("DELETE FROM studio_projects WHERE id IN (?,?)", (P_NEW, P_OLD))
        for pid, title, created in ((P_OLD, "归舟 · 旧项目", "2026-11-01T00:00:00+00:00"), (P_NEW, "归舟 · 短剧", "2026-11-09T00:00:00+00:00")):
            await db.execute("INSERT INTO studio_projects(id,owner,title,aspect,created_at,updated_at,brain_provider,source_kind,source_ref,snapshot_no) VALUES(?,?,?,'9:16',?,?,'qwen','novel',?,1)",
                             (pid, U, title, created, created, B))
        now = store.utcnow()
        await db.execute("""INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,status,settings_json,import_json,synopsis_json,created_at,updated_at)
                            VALUES(?,?,?,1,'qwen','done','{}','{}',?,?,?)""",
                         (BID, P_NEW, U, store._json({"logline": "少年独自过江。", "synopsis": "封渡前夜的一趟船。", "genre": "剧情", "tone": "克制", "themes": ["离开"]}), now, now))
        await db.execute("UPDATE studio_projects SET breakdown_id=? WHERE id=?", (BID, P_NEW))
        # 没有任何批次时，工作室刷新状态会把这次拆解判成 running；放一条已成功的梗概批次，状态才稳定在 done。
        await db.execute("INSERT INTO studio_chunks(id,breakdown_id,project_id,owner,no,task,provider,status) VALUES(?,?,?,?,1,'synopsis','qwen','succeeded')",
                         ("desk-chunk-1", BID, P_NEW, U))
        for seq in range(1, 9):
            await db.execute("""INSERT INTO studio_units(breakdown_id,seq,label,chapter,scene_index,location,summary,characters_json,est_seconds,change,start,end)
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (BID, seq, f"第 {(seq + 2) // 3} 章 第 {(seq - 1) % 3 + 1} 场", (seq + 2) // 3, (seq - 1) % 3 + 1, "渡口", "阿岚数银子。", '["阿岚"]', 30 + seq * 5, "得知封渡", (seq - 1) * 100, seq * 100))
        await plan.publish_plan(db, BID, [
            {"unit_from": 1, "unit_to": 2, "title": "雾里渡口", "change": "少年得知北岸今夜封渡。", "hook": "船家只肯再走一趟。"},
            {"unit_from": 3, "unit_to": 5, "title": "船家的价", "change": "少年第一次开口还价。", "hook": "船家在岸边把价翻倍，银子只够一个人过江。"},
            {"unit_from": 6, "unit_to": 7, "title": "一个人过江", "change": "少年把母亲的信留在了北岸。", "hook": "江心回头，北岸起了火光。"}])
    print(json.dumps({"book_plan": A, "book_done": B, "project": P_NEW, "project_empty": P_OLD}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
