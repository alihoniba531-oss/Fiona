"""走查用：在隔离临时库里，用后端自己的代码路径为 tester 造一份书斋草稿和一条带 novel_draft_id 的 assistant 消息。

用法（在候选 worktree 的 backend/ 目录下、与 backend.sh 相同的环境变量下运行）：
  .venv/bin/python <此文件> <标题> <思路>
输出 JSON：{conversation_id, draft_id, message_id}
"""
import asyncio
import json
import sys

import database
from agent_store import resolve_chat_conversation
from novel import drafts


async def main(title: str, seed: str) -> dict:
    await database.init_db()
    resolved = await resolve_chat_conversation("tester", None)
    conversation_id = resolved["conversation"]["id"]
    draft = await drafts.create_draft("tester", conversation_id, title, seed,
                                      {"min_chapters": 40, "max_chapters": 60, "chapter_words": 2500})
    card = {"type": "card", "subtype": "novel_draft", "source": "书斋",
            "points": [f"草稿《{title}》已送到书斋", "到书斋确认智能体与预算后开始写作"],
            "draft_id": draft["id"], "url": f"/novels/new?draft={draft['id']}", "error": False}
    from services import chat_service as chat
    content = "好，我把设定整理成草稿送到书斋了。［卡片：" + chat._summarize_card_for_history(card) + "］"
    saved = await database.save_message("tester", "assistant", content, conversation_id=conversation_id,
                                        novel_draft_id=draft["id"])
    import aiosqlite
    async with aiosqlite.connect(database.DB_PATH) as db:
        async with db.execute("SELECT id, novel_draft_id FROM messages WHERE username='tester' ORDER BY id DESC LIMIT 1") as cur:
            row = await cur.fetchone()
    return {"conversation_id": conversation_id, "draft_id": draft["id"], "message_id": row[0] if row else None,
            "stored_novel_draft_id": row[1] if row else None, "saved": bool(saved)}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(main(sys.argv[1], sys.argv[2])), ensure_ascii=False))
