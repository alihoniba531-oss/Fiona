"""修改意见卡 · 变异测试（验收方脚本，不进产品代码）。

在工作树的若干写时复制克隆里，逐项把实现改坏一处，跑对应的新测试（排除坏副本自检用例），
必须变红；每项结束后按原字节还原。
用法：python3 -I mut_feedback.py <工作树> <克隆目录> <结果文件> [--workers N] [--only M1,M2]
"""
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import time

BACK = "tests/test_novel_chat_feedback.py"
FRONT = "tests/test_novel_chat_feedback_frontend.py"
DESK = "tests/test_desk_polish_frontend.py"
# 坏副本自检用例会读源码锚点；锚点被变异改掉时它们会因「找不到锚点」变红，不能算数。
DESELECT = "not test_bad_ and not self_check and not catch and not bad_copy"

S = "backend/novel/service.py"
FB = "backend/novel/feedback.py"
CA = "backend/services/claude_agent.py"
DB = "backend/database.py"
AS = "backend/agent_store.py"
CARD = "frontend/components/NovelFeedbackCard.tsx"

# (编号, 说明, 文件, [(旧, 新, 第几处出现或 None=恰一处)], 测试文件)
MUTS = [
    ("B1", "开关函数不看 FIONA_NOVEL_CHAT_FEEDBACK", "backend/studio/sources.py",
     [("return os.getenv('FIONA_NOVEL_CHAT_FEEDBACK', '0') == '1' and novel_chat_enabled(username)", "return novel_chat_enabled(username)", None)], [BACK]),
    ("B2", "追加工具时不看开关", CA,
     [("    if novel_feedback_enabled(ctx.user):\n        tools.append(NOVEL_FEEDBACK_TOOL)", "    tools.append(NOVEL_FEEDBACK_TOOL)", None)], [BACK]),
    ("B3", "每轮一张的限制失效", CA,
     [("                    if feedback_written:\n", "                    if False:\n", None)], [BACK]),
    ("B4", "卡片摘要换回会过时的说法", CA,
     [('"交给编辑部、重新定稿都要作者在卡片上点按钮"]', '"等作者在卡片上决定怎么用"]', None)], [BACK]),
    ("B5", "回灌文本章号 K+1 写成 K+2", CA,
     [("交出后要到第 {K + 1} 章规划细纲时编辑部才会看到。", "交出后要到第 {K + 2} 章规划细纲时编辑部才会看到。", None)], [BACK]),
    ("B6", "回灌文本不认 awaiting_is_final", CA,
     [("elif K is not None and (F or (M is not None and K >= M)):", "elif K is not None and (M is not None and K >= M):", None)], [BACK]),
    ("B7", "第 4 句不看是否逐章确认", CA,
     [('if K is not None and not clean["current_plan"] and A == "per_chapter":', 'if K is not None and not clean["current_plan"]:', None)], [BACK]),
    ("B8", "不把卡片 id 交给落库", CA,
     [('state.novel_feedback_id = created["id"]', "state.novel_feedback_id = None", None)], [BACK]),
    ("B36", "回灌文本不分等完结", CA,
     [('                                        if S == "awaiting_end":', "                                        if False:", None)], [BACK]),
    ("B9", "save_message 不核对卡片归属", DB,
     [("stored_novel_feedback_id = None\n        if novel_feedback_id is not None:", "stored_novel_feedback_id = novel_feedback_id\n        if False:", None)], [BACK]),
    ("B10", "清空历史不删卡", DB,
     [('        await db.execute("DELETE FROM novel_feedback WHERE owner_username = ?", (username,))\n        await db.commit()', "        await db.commit()", None)], [BACK]),
    ("B11", "删号不删卡", DB,
     [('        await db.execute("DELETE FROM novel_feedback WHERE owner_username = ?", (username,))\n        await db.execute("DELETE FROM users WHERE username = ?", (username,))',
       '        await db.execute("DELETE FROM users WHERE username = ?", (username,))', None)], [BACK]),
    ("B12", "删会话不删卡", AS,
     [('        await db.execute(\n            "DELETE FROM novel_feedback WHERE owner_username = ? AND conversation_id = ?",\n            (username, conversation_id),\n        )\n', "", None)], [BACK]),
    ("B13", "读消息不带卡片 id", AS,
     [("song_project_id, novel_draft_id, novel_feedback_id", "song_project_id, novel_draft_id, NULL AS novel_feedback_id", None)], [BACK]),
    ("B14", "INSERT 不写卡片 id", DB,
     [("stored_song_project_id, stored_novel_draft_id, stored_novel_feedback_id),", "stored_song_project_id, stored_novel_draft_id, None),", None)], [BACK]),
    ("B15", "删书不把卡片 novel_id 置 NULL", S,
     [("        await db.execute('UPDATE novel_feedback SET novel_id=NULL, updated_at=CURRENT_TIMESTAMP WHERE owner_username=? AND novel_id=?',(username,novel_id))\n", "", None)], [BACK]),
    ("B16", "已写章节不核对是否写好", FB,
     [("            if chapter not in done_titles:\n", "            if False:\n", None), ('"title": done_titles[chapter],', '"title": done_titles.get(chapter, ""),', None)], [BACK]),
    ("B17", "多条错误用逗号连接", FB,
     [('return None, "；".join(errors)', 'return None, "，".join(errors)', 1), ('return None, "；".join(errors)', 'return None, "，".join(errors)', 1)], [BACK]),
    ("B18", "非逐章确认也收 current_plan", FB,
     [('        elif automation != "per_chapter":\n', "        elif False:\n", None)], [BACK]),
    ("B19", "500 字上限差一（=500 也报错）", FB,
     [("if isinstance(next_raw, str) and len(next_text) > TEXT_MAX:", "if isinstance(next_raw, str) and len(next_text) >= TEXT_MAX:", None)], [BACK]),
    ("B20", "建卡时 awaiting_is_final 恒为 False", FB,
     [("                        awaiting_is_final = True", "                        awaiting_is_final = False", None)], [BACK]),
    ("B21", "视图不算 planned_chapter", S,
     [("                note['planned_chapter']=item['chapter']", "                note['planned_chapter']=None", None)], [BACK]),
    ("B22", "已写完（done）的章也算读到", S,
     [("status IN ('awaiting_plan_approval','planning','writing') ORDER BY chapter DESC", "status IN ('awaiting_plan_approval','planning','writing','done') ORDER BY chapter DESC", None)], [BACK]),
    ("B23", "主编自带模型不算 own_model", S,
     [("        if editor=='byok:self':\n", "        if False:\n", None)], [BACK]),
    ("B24", "redo_pending 不看 _redo_note", S,
     [("redo_pending=isinstance(plan_meeting,dict) and plan_meeting.get('_redo_note') is not None", "redo_pending=True", None)], [BACK]),
    ("B25", "视图 awaiting_is_final 恒为 False", S,
     [("awaiting_is_final=isinstance(pending_decision,dict) and pending_decision.get('ending_status')=='end'", "awaiting_is_final=False", None)], [BACK]),
    ("B26", "交留言不幂等", S,
     [("        if card['note_id'] is None:\n", "        if True:\n", None)], [BACK]),
    ("B27", "完结的书也能交留言", S,
     [("            if book['status']=='completed':\n                fail('这本书已经完结，编辑部不会再读留言')", "            if False:\n                fail('这本书已经完结，编辑部不会再读留言')", None)], [BACK]),
    ("B28", "重新定稿不核对章号", S,
     [("expected_chapter=card['plan_chapter'])", "expected_chapter=None)", None)], [BACK]),
    ("B29", "重新定稿不看逐章确认", S,
     [("            if automation!='per_chapter':\n", "            if False:\n", None)], [BACK]),
    ("B30", "重新定稿不幂等", S,
     [("        if card['redo_started_at'] is None:\n", "        if True:\n", None)], [BACK]),
    ("B31", "待下发上限 5 改 6", S,
     [("    if count['n']>=5:\n", "    if count['n']>=6:\n", None)], [BACK]),
    ("B32", "不在等确认时不报卡片自己的文案", S,
     [("            if book['status']!='awaiting_plan':\n                fail(f'第 {card[\"plan_chapter\"]} 章细纲已经不在等你确认了')", "            if False:\n                fail(f'第 {card[\"plan_chapter\"]} 章细纲已经不在等你确认了')", None)], [BACK]),
    ("B33", "视图待下发数恒为 0", S,
     [("            pending_notes=pending_count['n']", "            pending_notes=0", None)], [BACK]),
    ("B34", "交留言路由改成 GET", "backend/routers/novel.py",
     [("@router.post('/feedback/{feedback_id}/note')", "@router.get('/feedback/{feedback_id}/note')", None)], [BACK, FRONT]),
    ("B35", "提交后不启动后台", S,
     [("    if started:\n        from .runner import start_novel", "    if False:\n        from .runner import start_novel", None)], [BACK]),
    ("F1", "卡片不看逐章确认就给重新定稿按钮", CARD,
     [('    && book.automation === "per_chapter",\n', "", None)], [FRONT]),
    ("F2", "失败的书不先说不能再写（细纲一节）", CARD,
     [('    } else if (book.status === "failed") {\n      planDescription', "    } else if (false) {\n      planDescription", None)], [FRONT]),
    ("F3", "已被读到但书失败时仍说写完会下发", CARD,
     [('chaptersDescription = book.status === "failed"\n', "chaptersDescription = false\n", None)], [FRONT]),
    ("F4", "最后一章判断不认 awaiting_is_final", CARD,
     [("    Boolean(book?.awaiting_is_final)\n", "    false\n", None)], [FRONT]),
    ("F5", "已交待下发时章号写成 K", CARD,
     [("`第 ${awaitingChapter + 1} 章规划细纲时，编辑部会读到这条要求。`", "`第 ${awaitingChapter} 章规划细纲时，编辑部会读到这条要求。`", None)], [FRONT]),
    ("F6", "交留言成功后不复位 busyRef", CARD,
     [("      if (next.note !== null) setActionError(null);\n      busyRef.current = false;\n", "      if (next.note !== null) setActionError(null);\n", None)], [FRONT]),
    ("F7", "确认框费用句写死扣草莓", CARD,
     [("${redoCostSentence(refreshed.book?.redo_cost)}完成后新细纲仍会停下来等你确认。", "重新定稿会再调用一次编辑部，按实际用量扣草莓。完成后新细纲仍会停下来等你确认。", None)], [FRONT]),
    ("F8", "旧页面后半句不看是否已发起重新定稿", CARD,
     [('{view.redo_started_at ? "在旧页面上点', '{true ? "在旧页面上点', None)], [FRONT]),
    ("F9", "确认框询问期间按钮已显示正在发起", CARD,
     [('    setBusy("confirm");\n', '    setBusy("redo");\n', None)], [FRONT]),
    ("F10", "404 不区分修改意见不存在", CARD,
     [('error.message === "修改意见不存在"', 'error.message === "x-never"', None)], [FRONT]),
    ("F11", "卸载后交留言失败仍显示错误并重拉", CARD,
     [('    } catch (error) {\n      if (signal?.aborted) return;\n      setActionError({ section: "chapters"', '    } catch (error) {\n      setActionError({ section: "chapters"', None)], [FRONT]),
    ("F12", "满 5 条时按钮不关联原因（aria）", CARD,
     [('aria-describedby={chaptersButton === "full" ? chaptersDescriptionId : undefined}', "aria-describedby={undefined}", None)], [FRONT]),
    ("F13", "第一节可用时底部不提示回书架", CARD,
     [("const showBottomHint = note !== null || Boolean(view.redo_started_at) || planActionable;", "const showBottomHint = note !== null || Boolean(view.redo_started_at);", None)], [FRONT]),
    ("F14", "重新定稿请求路径错", "frontend/lib/novelFeedback.ts",
     [('feedbackPath(id) + "/redo"', 'feedbackPath(id) + "/plan/redo"', None)], [FRONT]),
    ("F15", "请求路径不编码 id", "frontend/lib/novelFeedback.ts",
     [("encodeURIComponent(id)", "id", None)], [FRONT]),
    ("F16", "刷新后不重建修改意见卡", "frontend/lib/useConversations.ts",
     [('    if (message.role === "assistant" && message.novel_feedback_id) {\n      cards.push({ source: "书斋", points: [], subtype: "novel_feedback", feedback_id: message.novel_feedback_id });\n    }\n', "", None)], [FRONT]),
    ("F17", "ChatCard 不认 novel_feedback", "frontend/components/ChatBubble.tsx",
     [('card.subtype === "novel_feedback"', 'card.subtype === "novel_feedback_x"', None)], [FRONT]),
    ("F18", "第一个流式卡片块漏 feedback_id", "frontend/app/page.tsx",
     [("              feedback_id: data.card.feedback_id,\n", "", 1)], [FRONT]),
    ("F19", "满 5 条时按钮仍可点", CARD,
     [('disabled={chaptersButton === "full" || busy !== null}', "disabled={busy !== null}", None)], [FRONT]),
    ("F20", "已下发标签用旧说法", CARD,
     [("`已下发到第 ${note.delivered_chapter} 章`", "`已用于第 ${note.delivered_chapter} 章`", None)], [FRONT]),
    ("F21", "自带模型费用句写成扣草莓", CARD,
     [('"这本书的主编用的是你自己的模型，重新定稿不扣草莓，但会用掉你自己的模型额度。"', '"重新定稿会再调用一次编辑部，按实际用量扣草莓。"', None)], [FRONT]),
    # ---- R1（规格 v1.4 §4.6）新增：复核方存活的变异 + 重读/章号核对 ----
    ("B37", "「已被读到」不查 writing 状态", S,
     [("status IN ('awaiting_plan_approval','planning','writing') ORDER BY chapter DESC", "status IN ('awaiting_plan_approval','planning') ORDER BY chapter DESC", None)], [BACK]),
    ("B38", "「已被读到」只查等确认", S,
     [("status IN ('awaiting_plan_approval','planning','writing') ORDER BY chapter DESC", "status IN ('awaiting_plan_approval') ORDER BY chapter DESC", None)], [BACK]),
    ("B19b", "current_plan 500 字上限差一", FB,
     [("if isinstance(current_raw, str) and len(current_text) > TEXT_MAX:", "if isinstance(current_raw, str) and len(current_text) >= TEXT_MAX:", None)], [BACK]),
    ("B19c", "已写章节 10 条上限差一", FB,
     [("if isinstance(written_raw, list) and len(written_raw) > WRITTEN_MAX:", "if isinstance(written_raw, list) and len(written_raw) >= WRITTEN_MAX:", None)], [BACK]),
    ("B19d", "issue 200 字上限差一", FB,
     [("if not issue_text or len(issue_text) > ISSUE_MAX:", "if not issue_text or len(issue_text) >= ISSUE_MAX:", None)], [BACK]),
    ("B33b", "待下发数不看 pending", S,
     [("\"SELECT COUNT(*) AS n FROM novel_notes WHERE novel_id=? AND status='pending'\",(card['novel_id'],)", "\"SELECT COUNT(*) AS n FROM novel_notes WHERE novel_id=?\",(card['novel_id'],)", None)], [BACK]),
    ("B33c", "待下发数不按书过滤", S,
     [("\"SELECT COUNT(*) AS n FROM novel_notes WHERE novel_id=? AND status='pending'\",(card['novel_id'],)", "\"SELECT COUNT(*) AS n FROM novel_notes WHERE username=? AND status='pending'\",(username,)", None)], [BACK]),
    ("B39", "已写章节不看 chapters_done", FB,
     [('if chapter.get("status") not in ("done", "stale") or number > chapters_done:', 'if chapter.get("status") not in ("done", "stale"):', None)], [BACK]),
    ("B40", "回灌最后一章不认 K >= max_chapters", CA,
     [("elif K is not None and (F or (M is not None and K >= M)):", "elif K is not None and F:", None)], [BACK]),
    ("B41", "P2 去掉：没记章号的卡也能重新定稿", S,
     [("if not (card['current_plan'] or '').strip() or card['plan_chapter'] is None:", "if not (card['current_plan'] or '').strip():", None)], [BACK]),
    ("F22", "最后一章不认 K >= max_chapters", CARD,
     [("    Boolean(book?.awaiting_is_final)\n    || (maxChapters !== null && awaitingChapter >= maxChapters)", "    Boolean(book?.awaiting_is_final)", None)], [FRONT]),
    ("F23", "交留言不防连点", CARD,
     [("  const sendNote = async () => {\n    if (busyRef.current) return;\n", "  const sendNote = async () => {\n", None)], [FRONT]),
    ("F24", "重新定稿不防连点", CARD,
     [("  const sendRedo = async () => {\n    if (busyRef.current) return;\n", "  const sendRedo = async () => {\n", None)], [FRONT]),
    ("F25", "确认框返回后不看是否已卸载", CARD,
     [("    if (signal?.aborted) return;\n    if (!confirmed) {", "    if (!confirmed) {", None)], [FRONT]),
    ("F26", "「新细纲在书斋里等你确认」不核对章号", CARD,
     [('if (book.status === "awaiting_plan" && book.awaiting_chapter === chapter) {\n          planDescription += "新细纲在书斋里等你确认。";',
       'if (book.status === "awaiting_plan") {\n          planDescription += "新细纲在书斋里等你确认。";', None)], [FRONT]),
    ("F27", "可重新定稿不核对章号", CARD,
     [("    && book.awaiting_chapter === view.plan_chapter\n", "", None)], [FRONT]),
    ("F28", "P1 点击时不重新读取（沿用旧视图）", CARD,
     [("      refreshed = await getNovelFeedback(feedbackId, signal);", "      refreshed = view;", None)], [FRONT]),
    ("F29", "P1 费用句仍取点击前的视图", CARD,
     [("${redoCostSentence(refreshed.book?.redo_cost)}完成后", "${redoCostSentence(view.book?.redo_cost)}完成后", None)], [FRONT]),
    ("F30", "P1 不对新视图判断能不能用", CARD,
     [("    if (!redoAvailable(refreshed) || chapter === null) {", "    if (chapter === null) {", None)], [FRONT]),
    ("F31", "P1 重新读取后不看是否已卸载", CARD,
     [('    if (signal?.aborted) return;\n    setResult({ kind: "ready", feedbackId, attempt, view: refreshed });', '    setResult({ kind: "ready", feedbackId, attempt, view: refreshed });', None)], [FRONT]),
    ("F32", "P1 重新读取失败后按钮不恢复", CARD,
     [('      setActionError({ section: "plan", message: novelErrorMessage(error) });\n      busyRef.current = false;\n      setBusy(null);\n      return;',
       '      setActionError({ section: "plan", message: novelErrorMessage(error) });\n      return;', None)], [FRONT]),
    ("F33", "P1 重新读取失败不提示", CARD,
     [('      setActionError({ section: "plan", message: novelErrorMessage(error) });\n      busyRef.current = false;\n      setBusy(null);\n      return;',
       '      busyRef.current = false;\n      setBusy(null);\n      return;', None)], [FRONT]),
    ("F34", "P1 重新读取后不替换视图", CARD,
     [('    if (signal?.aborted) return;\n    setResult({ kind: "ready", feedbackId, attempt, view: refreshed });\n    const chapter = refreshed.plan_chapter;',
       '    if (signal?.aborted) return;\n    const chapter = refreshed.plan_chapter;', None)], [FRONT]),
    # ---- R2（规格 v1.5 §4.7）新增：对抗式核查发现的测试缺口 ----
    ("F35", "P1 重读后不可用时不复位", CARD,
     [("    if (!redoAvailable(refreshed) || chapter === null) {\n      busyRef.current = false;\n      setBusy(null);\n      return;\n    }",
       "    if (!redoAvailable(refreshed) || chapter === null) {\n      return;\n    }", None)], [FRONT]),
    ("F36", "P1 重读后不可用时只漏复位 busyRef", CARD,
     [("    if (!redoAvailable(refreshed) || chapter === null) {\n      busyRef.current = false;\n      setBusy(null);\n      return;\n    }",
       "    if (!redoAvailable(refreshed) || chapter === null) {\n      setBusy(null);\n      return;\n    }", None)], [FRONT]),
    ("F37", "P1 重读失败时只漏复位 busyRef", CARD,
     [('      setActionError({ section: "plan", message: novelErrorMessage(error) });\n      busyRef.current = false;\n      setBusy(null);\n      return;',
       '      setActionError({ section: "plan", message: novelErrorMessage(error) });\n      setBusy(null);\n      return;', None)], [FRONT]),
    ("F38", "确认框取消时只漏复位 busyRef", CARD,
     [("    if (!confirmed) {\n      busyRef.current = false;\n      setBusy(null);\n      return;\n    }",
       "    if (!confirmed) {\n      setBusy(null);\n      return;\n    }", None)], [FRONT]),
    ("F39", "可重新定稿不看是否已发起", CARD,
     [("    && !view.redo_started_at\n", "", None)], [FRONT]),
    ("F40", "P1 重读被中止 reject 后不看是否已卸载", CARD,
     [("      refreshed = await getNovelFeedback(feedbackId, signal);\n    } catch (error) {\n      if (signal?.aborted) return;\n",
       "      refreshed = await getNovelFeedback(feedbackId, signal);\n    } catch (error) {\n", None)], [FRONT]),
    ("F41", "P1 重读失败直接显示原始报错", CARD,
     [('      setActionError({ section: "plan", message: novelErrorMessage(error) });\n      busyRef.current = false;',
       '      setActionError({ section: "plan", message: error instanceof Error ? error.message : "修改意见暂时读不到" });\n      busyRef.current = false;', None)], [FRONT]),
    ("B42", "「已被读到」放宽成除 done 以外都算", S,
     [("status IN ('awaiting_plan_approval','planning','writing') ORDER BY chapter DESC", "status<>'done' ORDER BY chapter DESC", None)], [BACK]),
    ("B43", "P2 章号判断挪到书态检查之后", S,
     [("if not (card['current_plan'] or '').strip() or card['plan_chapter'] is None:", "if not (card['current_plan'] or '').strip():", None),
      ("            await _begin_redo(db,username,novel_id,", "            if card['plan_chapter'] is None:\n                fail('这张卡没有重新定稿的要求')\n            await _begin_redo(db,username,novel_id,", None)], [BACK]),
    ("D1", "读正文不去掉原始标题行", "frontend/components/desk/DeskDialogs.tsx",
     [('const body = data?.body ? chapterReadingBody(data.body) : "";', 'const body = data?.body ?? "";', None)], [DESK]),
    ("D2", "展开后摘要仍截两行", "frontend/components/desk/DeskChaptersView.tsx",
     [('${isExpanded ? "" : "line-clamp-2"}', "line-clamp-2", None)], [DESK]),
    ("D3", "无项目原因不补句号", "frontend/components/desk/DeskEpisodesView.tsx",
     [('${reason}${missingEnd ? "。" : ""}', "${reason}", None)], [DESK]),
    ("D4", "已有句号也再补一个", "frontend/components/desk/DeskEpisodesView.tsx",
     [('const missingEnd = reason !== "" && !/[。！？.!?]$/.test(reason);', 'const missingEnd = reason !== "";', None)], [DESK]),
]


def apply(data, pairs):
    for old, new, nth in pairs:
        o, n = old.encode(), new.encode()
        count = data.count(o)
        if nth is None:
            if count != 1:
                raise ValueError(f"锚点出现 {count} 次（应恰 1 次）：{old[:60]!r}")
            data = data.replace(o, n, 1)
        else:
            if count < nth:
                raise ValueError(f"锚点只出现 {count} 次（要第 {nth} 处）：{old[:60]!r}")
            idx = -1
            for _ in range(nth):
                idx = data.index(o, idx + 1)
            data = data[:idx] + n + data[idx + len(o):]
    return data


def run_tests(clone, tests):
    env = dict(os.environ, NO_PROXY="localhost,127.0.0.1,::1,.local", no_proxy="localhost,127.0.0.1,::1,.local")
    cmd = [os.path.join(clone, "backend/.venv/bin/python"), "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-k", DESELECT, *tests]
    started = time.time()
    proc = subprocess.run(cmd, cwd=os.path.join(clone, "backend"), env=env, capture_output=True, text=True, timeout=900)
    out = proc.stdout + proc.stderr
    summary = [line for line in out.splitlines() if re.search(r"\d+ (passed|failed|error)", line)]
    failed = re.findall(r"^FAILED (\S+)", out, re.M) + re.findall(r"^ERROR (\S+)", out, re.M)
    return proc.returncode, (summary[-1] if summary else out[-300:]), failed[:3], round(time.time() - started, 1)


def worker(clone, items):
    rows = []
    for mid, desc, rel, pairs, tests in items:
        path = os.path.join(clone, rel)
        original = open(path, "rb").read()
        try:
            mutated = apply(original, pairs)
        except ValueError as error:
            rows.append({"id": mid, "desc": desc, "status": "ANCHOR", "detail": str(error)})
            continue
        try:
            open(path, "wb").write(mutated)
            code, summary, failed, secs = run_tests(clone, tests)
        finally:
            open(path, "wb").write(original)
        status = "KILLED" if code == 1 and failed else ("SURVIVED" if code == 0 else f"EXIT{code}")
        rows.append({"id": mid, "desc": desc, "status": status, "summary": summary, "failed": failed, "secs": secs})
        print(f"{mid:4} {status:9} {secs:6}s {desc} | {summary} | {failed[:1]}", flush=True)
    return rows


def main():
    wt, clones, out = sys.argv[1], sys.argv[2], sys.argv[3]
    workers = 6
    only = None
    args = sys.argv[4:]
    if "--workers" in args:
        workers = int(args[args.index("--workers") + 1])
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))
    muts = [m for m in MUTS if only is None or m[0] in only]
    os.makedirs(clones, exist_ok=True)
    paths = []
    for i in range(workers):
        dest = os.path.join(clones, f"w{i}")
        if os.path.exists(dest):
            shutil.rmtree(dest)
        subprocess.run(["cp", "-cR", wt, dest], check=True)
        paths.append(dest)
    # 正控：未变异时，排除自检后的三个文件必须全绿
    code, summary, failed, secs = run_tests(paths[0], [BACK, FRONT, DESK])
    print(f"POSITIVE-CONTROL exit={code} {summary} {secs}s", flush=True)
    if code != 0:
        print("正控失败，停止", failed)
        sys.exit(3)
    buckets = [[] for _ in range(workers)]
    for i, m in enumerate(muts):
        buckets[i % workers].append(m)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(worker, paths, buckets):
            rows.extend(part)
    order = {m[0]: i for i, m in enumerate(MUTS)}
    rows.sort(key=lambda r: order[r["id"]])
    json.dump({"positive_control": summary, "rows": rows}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("TOTAL", len(rows), counts)
    for r in rows:
        if r["status"] != "KILLED":
            print("NOT-KILLED", r["id"], r["status"], r["desc"], r.get("summary") or r.get("detail"))


if __name__ == "__main__":
    main()
