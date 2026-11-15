#!/usr/bin/env python3
"""讨论群第一期的变异测试：把实现的关键处逐一改坏，新测试必须变红。

用法（从仓库根运行）：
    python docs/tasks/2026-11-14-agent-group/verify/mut_discuss.py <克隆目录> <结果文件.json> [变异编号 …]

脚本先把仓库整个克隆到 <克隆目录>（APFS 克隆），所有改动都发生在克隆里，不碰真实工作区。
每条变异改一处（个别是成对的两处），跑 tests/test_discuss_*.py，失败即「杀死」，之后还原。
开头先在未改动的克隆上跑一遍作为正控：必须全过，否则整个结果无效。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ENGINE, BILLING, RUNNER = "backend/discuss/engine.py", "backend/discuss/billing.py", "backend/discuss/runner.py"
RESEARCH, SERVICE, SCHEMAS, STORE = ("backend/discuss/research.py", "backend/discuss/service.py",
                                     "backend/discuss/schemas.py", "backend/discuss/store.py")
ROUTER = "backend/routers/discuss.py"
AVATAR = "backend/discuss/avatar.py"
ROLES = "backend/discuss/roles.py"

# (编号, 说明, [(文件, 原文, 改成, 第几处)])
MUTATIONS = [
    ("E1", "末两轮也允许再查一轮", [(ENGINE, "can_research_more = r <= max_rounds - 2", "can_research_more = r <= max_rounds - 1", 1)]),
    ("E2", "有引用问题也算通过", [(ENGINE, 'passed = all(item["pass"] for item in verdict["verdicts"]) and not issues', 'passed = all(item["pass"] for item in verdict["verdicts"])', 1)]),
    ("E3", "作者要求返工被忽略", [(ENGINE, "if passed and r not in revisions:", "if passed:", 1)]),
    ("E4", "轮数用尽且未通过却记为完成", [(ENGINE, 'status="awaiting_user", stop_reason="rounds_exhausted", run_token=None)', 'status="done", stop_reason="accepted", run_token=None)', 1)]),
    ("E5", "首轮全部检索失败不暂停", [(ENGINE, "if r == 1 and not any(facts_by_role.get(role) for role in assigned_roles):", "if False and not any(facts_by_role.get(role) for role in assigned_roles):", 1)]),
    ("E6", "不是逐字片段的引用问题也保留", [(ENGINE, 'and item["quote"] in draft', "and True", 1)]),
    ("E7", "被驳回的质疑仍留给调研成员", [(ENGINE, 'for item in objections if actions[item["id"]] != "reject"', "for item in objections if True", 1)]),
    ("E8", "开工前的插话不进调研载荷", [(ENGINE, '"owner_notes": owner_notes,', '"owner_notes": "",', 1), (ENGINE, '"owner_notes": owner_notes,', '"owner_notes": "",', 1)]),
    ("E9", "分身出错时不再吞掉", [(ENGINE, '            raise asyncio.CancelledError() from error\n        await store.post_message(\n            round=chapter, sender="avatar"', '            raise asyncio.CancelledError() from error\n        raise\n        await store.post_message(\n            round=chapter, sender="avatar"', 1)]),
    ("E10", "分身步骤吞掉余额与预算异常", [(ENGINE, "_AVATAR_RAISE = (asyncio.CancelledError, RunNoLongerActive,\n                 InsufficientStrawberries, NovelBudgetExceeded)", "_AVATAR_RAISE = (asyncio.CancelledError, RunNoLongerActive)", 1)]),
    ("E11", "撰稿人拿不到上一版", [(ENGINE, '"previous_draft": draft or None,', '"previous_draft": None,', 1)]),
    ("E12", "返工安排的补查任务被丢弃", [(ENGINE, 'assignments = planned["assignments"]', "assignments = []", 1)]),
    ("E13", "裁决为再查一轮时仍然撰稿", [(ENGINE, 'if decision["decision"] == "research":', "if False:", 1)]),
    ("E14", "调研成员看不到自己之前的要点", [(ENGINE, "for point in previous],", "for point in []],", 1)]),
    ("E15", "裁决载荷里没有插话", [(ENGINE, '"user_notes": user_notes,', '"user_notes": [],', 1)]),
    ("E16", "读取点不认领插话", [(ENGINE, "await discuss_store.claim_notes(store, step_key)", "pass", 1)]),
    ("E17", "针对本人的质疑不下发", [(ENGINE, '"objections_to_address": objections,', '"objections_to_address": [],', 1)]),
    ("E18", "撰稿人拿到全量来源", [(ENGINE, 'for row in source_rows if row["id"] in used_refs', "for row in source_rows if True", 1)]),
    ("E19", "分身不看稿", [(ENGINE, "if _is_avatar_required(config):", "if False:", 2)]),
    ("E20", "成果不校验", [(ENGINE, "validator=lambda value: schemas.check_draft(value, known=known),", "validator=None,", 1)]),
    ("E21", "作者组队没有传给主持人", [(ENGINE, '"fixed_members": fixed_members,', '"fixed_members": [],', 1)]),
    ("E22", "作者组队不校验", [(ENGINE, "value, role_pool=role_pool, fixed_members=fixed_members or None),", "value, role_pool=role_pool, fixed_members=None),", 1)]),
    ("E23", "固定席位的身份设定不进提示词", [(ENGINE, "line = roles.identity_line(_seat_identity(config, role))", 'line = ""', 1)]),
    ("E24", "验收人拿不到分身的意见", [(ENGINE, '"owner_view": owner_view,', '"owner_view": None,', 1)]),
    ("E25", "立项时分身不发言", [(ENGINE, "if _is_avatar_required(config):", "if False:", 1)]),
    ("E26", "调研并发处的名字与职责不取方案", [(ENGINE, 'system=_system(config, "queries", role=role,\n                                       name=pick.get("name"), does=pick.get("does")),', 'system=_system(config, "queries", role=role,\n                                       name=roles.role_name(role), does=roles.role_does(role)),', 1)]),
    ("B1", "模型调用不查预算", [(BILLING, "raise DiscussBudgetExceeded()", "pass", 1)]),
    ("B2", "模型调用不查余额", [(BILLING, "raise InsufficientStrawberries()", "pass", 1)]),
    ("B3", "结算时总按预扣全额收", [(BILLING, "charged = 0 if charge is None else min(reserved, charge)", "charged = 0 if charge is None else reserved", 1)]),
    ("B4", "搜索永远免费", [(BILLING, 'if self.is_free({"model": "search"}) or amount == 0:', "if True:", 1)]),
    ("B5", "搜索不查预算", [(BILLING, "raise DiscussBudgetExceeded()", "pass", 2)]),
    ("B6", "自带模型也扣草莓", [(BILLING, 'call["model"] == "byok:self" or call["model"].startswith("fake:"))', 'call["model"].startswith("fake:"))', 1)]),
    ("B7", "开发模式也扣草莓", [(BILLING, 'return (os.getenv("DEV_MODE", "0") == "1" or call.get("dry_run", False) or', 'return (call.get("dry_run", False) or', 1)]),
    ("R1", "搜索不用缓存", [(RESEARCH, 'if record is not None and record.get("status") == "ok":', "if False:", 1)]),
    ("R2", "搜索失败不退还", [(RESEARCH, "await billing.refund_fixed(step_key)", "pass", 1)]),
    ("R3", "失败的搜索记成成功", [(RESEARCH, '"status": "failed",', '"status": "ok",', 1)]),
    ("N1", "已有令牌仍然再起一个任务", [(RUNNER, 'if group is None or group["status"] not in ("planning", "running") or group["run_token"]:', 'if group is None or group["status"] not in ("planning", "running"):', 1)]),
    ("N2", "恢复时不先查表是否存在", [(RUNNER, "name='discuss_groups'\")", "name='users'\")", 1)]),
    ("N3", "余额不足没有暂停原因", [(RUNNER, 'await _pause(store, "insufficient_strawberries")', 'await _pause(store, "step_failed")', 1)]),
    ("N4", "预算用完没有暂停原因", [(RUNNER, 'await _pause(store, "budget")', 'await _pause(store, "step_failed")', 1)]),
    ("N5", "搜索不可用没有暂停原因", [(RUNNER, 'await _pause(store, "search_unavailable")', 'await _pause(store, "step_failed")', 1)]),
    ("N6", "取消任务时不退还预扣", [(RUNNER, "await DiscussBilling(username, group_id).refund_reserved()", "pass", 1), (RUNNER, "await DiscussBilling(username, group_id).refund_reserved()", "pass", 1)]),
    ("N7", "自带模型不可用没有暂停原因", [(RUNNER, 'await _pause(store, "byok_unavailable",', 'await _pause(store, "step_failed",', 1)]),
    ("S1", "危机文本不拦", [(SERVICE, 'assess_crisis(value) == "high"', 'assess_crisis(value) == "never"', 1)]),
    ("S2", "每日上限不生效", [(SERVICE, "if created_today >= config.daily_groups():", "if False:", 1)]),
    ("S3", "建群不查是否已有在跑的群", [(SERVICE, "await _rollback_fail(db, ACTIVE_GROUP)", "pass", 1)]),
    ("S4", "改方案不查版本", [(SERVICE, "if revision != body.expected_revision:", "if False:", 1), (SERVICE, "if int(current.get(\"plan_revision\") or 0) != body.expected_revision:", "if False:", 1)]),
    ("S5", "未读插话不设上限", [(SERVICE, "_fail(TOO_MANY_NOTES)", "pass", 1)]),
    ("S6", "完成后没有插话也能返工", [(SERVICE, "await _rollback_fail(db, REWORK_NEEDS_NOTE)", "pass", 1)]),
    ("S7", "总轮数不设上限", [(SERVICE, 'await _rollback_fail(db, "总轮数最多 10 轮", 422)', "pass", 1)]),
    ("S8", "预算用完也能继续", [(SERVICE, "await _rollback_fail(db, BUDGET_EXHAUSTED)", "pass", 1)]),
    ("S9", "在跑时也能结束", [(SERVICE, "_fail(CLOSE_RUNNING)", "pass", 1), (SERVICE, "await _rollback_fail(db, CLOSE_RUNNING)", "pass", 1)]),
    ("S10", "没有成果也能接受", [(SERVICE, '_fail("还没有成果可以接受")', "pass", 1), (SERVICE, 'await _rollback_fail(db, "还没有成果可以接受")', "pass", 1)]),
    ("S11", "开工不查版本", [(SERVICE, "if int(group.get(\"plan_revision\") or 0) != body.expected_revision:", "if False:", 1), (SERVICE, "if int(current.get(\"plan_revision\") or 0) != body.expected_revision:", "if False:", 2)]),
    ("C1", "成果里允许写网址", [(SCHEMAS, 'if "http://" in text or "https://" in text:', "if False:", 1)]),
    ("C2", "成果不限最短字数", [(SCHEMAS, "if len(text.strip()) < 400:", "if False:", 1)]),
    ("C3", "笔记可以引用不存在的来源", [(SCHEMAS, "elif not refs_in(note) <= known_set:", "elif False:", 1), (SCHEMAS, "elif not set(refs) <= known_set:", "elif False:", 1)]),
    ("C4", "不允许再查时裁决为再查也放行", [(SCHEMAS, 'elif decision == "research" and not can_research_more:', "elif False:", 1)]),
    ("C5", "插话可以不回应", [(SCHEMAS, 'errors.append("note_responses：必须对每条插话恰好回应一次")', "pass", 1)]),
    ("T1", "后台写库不核对令牌", [(STORE, "WHERE g.id=? AND g.username=? AND g.run_token=?\"\"\",", "WHERE g.id=? AND g.username=? AND (g.run_token=? OR 1=1)\"\"\",", 1)]),
    ("T2", "来源不按网址去重", [(STORE, '"SELECT sid FROM discuss_sources WHERE group_id=? AND username=? AND url_key=?",', '"SELECT sid FROM discuss_sources WHERE group_id=? AND username=? AND url_key=? AND 1=0",', 1)]),
    ("T3", "开工时不认领插话", [(STORE, "UPDATE discuss_messages SET consumed_by='start'", "UPDATE discuss_messages SET consumed_by=NULL", 1)]),
    ("A1", "开关关闭时不返回 404", [(ROUTER, "raise HTTPException(404", "pass  # HTTPException(404", 1)]),
    ("P1a", "裁决派的任务不按成员合并", [(ENGINE, 'assignments = _merge_assignments(decision["assignments"])', 'assignments = decision["assignments"]', 1)]),
    ("P1b", "返工派的任务不按成员合并", [(ENGINE, "        assignments = _merge_assignments(assignments)", "        assignments = list(assignments)", 1)]),
    ("P1c", "同一成员的多条任务只留第一条", [(ENGINE, '"；".join(role_tasks)', "role_tasks[0]", 1)]),
    ("P2", "重放时轮次号倒退", [(ENGINE, "if r > current_round:", "if True:", 1)]),
    ("P3", "返工要求截到 160 字", [(ENGINE, 'str(item)[:300] for item in verdict["rework"]', 'str(item)[:160] for item in verdict["rework"]', 1)]),
    ("N8", "任务所属事件循环已关闭时仍去调度", [(RUNNER, "if loop.is_closed() or not loop.is_running():", "if False:", 1)]),
    ("N9", "处理过的任务不从登记表移除", [(RUNNER, "                TASKS.pop(group_id, None)\n                _owners.pop(group_id, None)", "                pass", 1)]),
    ("W1", "写事务不再受取消保护", [(STORE, "    return await NovelBilling._drain(transaction())", "    return await transaction()", 1)]),
    ("W2", "过期任务的写入不再被拒绝", [(STORE, "            if not await self.is_current(db):\n                raise RunNoLongerActive()", "            if False:\n                raise RunNoLongerActive()", 1)]),
    ("W3", "过期任务写终态时不再安静退出", [(RUNNER, "    except RunNoLongerActive:\n        # A stale worker must finish quietly", "    except ZeroDivisionError:\n        # A stale worker must finish quietly", 1)]),
    ("W4", "认领令牌的条件不成立时仍然起任务", [(RUNNER, "    if claimed is None:\n        return None", "    if False:\n        return None", 1)]),
    ("W5", "写事务既不受取消保护、出错也不回滚", [(STORE, "    return await NovelBilling._drain(transaction())", "    return await transaction()", 1), (STORE, "            except BaseException:\n                await db.rollback()\n                raise\n", "            except BaseException:\n                raise\n", 1)]),
    # ── 复核返修第 1 轮之后加的（V = 本轮改动；X = 复核做过、当时存活的变异，编号沿用复核）──
    ("V1", "分身取资料不受取消保护（系统提示）", [(AVATAR, "    agent = await NovelBilling._drain(agent_store.get_my_agent(username))\n    snapshot", "    agent = await agent_store.get_my_agent(username)\n    snapshot", 1)]),
    ("V2", "分身取名字不受取消保护", [(AVATAR, "    agent = await NovelBilling._drain(agent_store.get_my_agent(username))\n    name", "    agent = await agent_store.get_my_agent(username)\n    name", 1)]),
    ("V3", "分身取记忆不受取消保护", [(AVATAR, "    snapshot = await NovelBilling._drain(agent_store.get_memory_snapshot(username))", "    snapshot = await agent_store.get_memory_snapshot(username)", 1)]),
    ("V4", "继续按方案版本而不是按是否开工过判断", [(SERVICE, 'status = "planning" if int(current.get("round") or 0) == 0 else "running"', 'status = "planning" if int(current.get("plan_revision") or 0) == 0 else "running"', 1)]),
    ("V5", "身份设定不独占一行", [(ENGINE, '            text += "\\n" + line', '            text += line + "\\n"', 1)]),
    ("V6", "认领令牌后被取消不清令牌", [(RUNNER, "        await release_claim()\n        raise", "        raise", 1)]),
    ("V7a", "开工前不退残留预扣", [(SERVICE, "    await billing.DiscussBilling(username, group_id).refund_reserved()\n    await runner.start_group(group_id, username)", "    await runner.start_group(group_id, username)", 1)]),
    ("V7b", "继续前不退残留预扣", [(SERVICE, "    await billing.DiscussBilling(username, group_id).refund_reserved()\n    await runner.start_group(group_id, username)", "    await runner.start_group(group_id, username)", 2)]),
    ("V7c", "追加轮数前不退残留预扣", [(SERVICE, "    await billing.DiscussBilling(username, group_id).refund_reserved()\n    await runner.start_group(group_id, username)", "    await runner.start_group(group_id, username)", 3)]),
    ("V8", "删群时不退仍在预扣的草莓", [(STORE, "        if reserved > 0:", "        if False:", 1)]),
    ("V9", "固定席位名字传空字符串仍被拒", [(SERVICE, "            if len(name) > 12:", "            if not 1 <= len(name) <= 12:", 1)]),
    ("V10", "建群时成员重名不拒", [(SERVICE, '        if member["name"] in names:', "        if False:", 1)]),
    ("X1", "付费结算不写步骤缓存", [(BILLING, "                if step_record is not None:\n                    # A validated paid result", "                if False:\n                    # A validated paid result", 1)]),
    ("X4", "计费不核对令牌", [(BILLING, 'if row is None or (self.run_token is not None and row["run_token"] != self.run_token):', "if row is None:", 1)]),
    ("X25", "暂停不取消后台任务", [(SERVICE, "    await runner.cancel_group(group_id, username)\n", "    pass\n", 1)]),
    ("X26", "删群不取消后台任务", [(SERVICE, "    await runner.cancel_group(group_id, username)\n", "    pass\n", 2)]),
    ("X12", "返工载荷不带引用问题", [(ENGINE, "][:5] + [\n            f\"引用问题：「{item['quote']}」{item.get('problem', '')}\" for item in issues\n        ]", "][:5] + []", 1)]),
    ("X14", "并行步骤一个失败就立刻抛出", [(ENGINE, "outcomes = await asyncio.gather(*aws, return_exceptions=True)", "outcomes = await asyncio.gather(*aws)", 1)]),
    ("X15", "撰稿载荷不带分身提供的背景", [(ENGINE, '"owner_context": owner_context,', '"owner_context": None,', 3)]),
    ("X17", "恢复时步骤失败不记重启失败", [(RUNNER, 'await _pause(store, "server_restart_failed" if recovering else "step_failed")', 'await _pause(store, "step_failed")', 1)]),
    ("X18", "恢复时意外异常记成失败", [(RUNNER, 'await _pause(store, "server_restart_failed" if recovering else "error")', 'await _pause(store, "error")', 1)]),
    ("X19", "平时步骤失败记成失败状态", [(RUNNER, '"server_restart_failed" if recovering else "step_failed")', '"server_restart_failed" if recovering else "error")', 1)]),
    ("X20", "全站并发上限不生效", [(RUNNER, "asyncio.Semaphore(config.max_running())", "asyncio.Semaphore(10**6)", 1)]),
    ("X22", "补充材料不做危机检查", [(SERVICE, "    _check_crisis(request, materials)", "    _check_crisis(request)", 1)]),
    ("X27", "群列表不设上限", [(STORE, "async def list_groups(username, limit=50):", "async def list_groups(username, limit=10**6):", 1)]),
    ("X28", "删成员时不清它的模型设置", [(SERVICE, "        models.pop(role, None)", "        pass", 1)]),
    ("X30", "详情忽略 after", [(SERVICE, "list_messages(username, group_id, after=after, limit=200)", "list_messages(username, group_id, after=0, limit=200)", 1)]),
    ("X31", "开工不查是否有别的群在跑", [(SERVICE, "await _rollback_fail(db, ACTIVE_GROUP)", "pass", 2)]),
    ("X32", "继续不查是否有别的群在跑", [(SERVICE, "await _rollback_fail(db, ACTIVE_GROUP)", "pass", 3)]),
    ("X33", "追加轮数不查是否有别的群在跑", [(SERVICE, "await _rollback_fail(db, ACTIVE_GROUP)", "pass", 4)]),
    ("X34", "事实不截到 160 字", [(RESEARCH, 'item["fact"][:160]', 'item["fact"]', 1)]),
    ("X35", "笔记载荷带全部来源", [(ENGINE, "                    for row in source_rows if row[\"id\"] in cited\n", "                    for row in source_rows if True\n", 1)]),
    ("X37", "分身默认模型不看自带模型", [(AVATAR, '    return "byok:self"', "    return roles.DEFAULT_AVATAR_MODEL", 1)]),
    ("X39", "新增自定义成员不跳过已用代号", [(SERVICE, "            while number in used_numbers:", "            while False:", 1)]),
    ("X44", "身份设定可以超过 300 字", [(SERVICE, "if not isinstance(persona, str) or len(persona) > 300:", "if not isinstance(persona, str):", 1)]),
    # ── 复核返修第 2 轮之后加的（Y = 第 2 轮复核做过、当时存活的变异，编号沿用复核）──
    ("V11", "分身步骤把「已被取消时的普通异常」当成可跳过的失败", [(ENGINE, "        if current is not None and current.cancelling():", "        if False:", 1)]),
    ("V12", "接受成果后不退残留预扣", [(SERVICE, 'status="done", stop_reason="accepted_by_user")\n    await discuss_store.run_write(operation)\n    await billing.DiscussBilling(username, group_id).refund_reserved()\n', 'status="done", stop_reason="accepted_by_user")\n    await discuss_store.run_write(operation)\n', 1)]),
    ("V13", "结束后不退残留预扣", [(SERVICE, 'status="closed", stop_reason="user")\n    await discuss_store.run_write(operation)\n    await billing.DiscussBilling(username, group_id).refund_reserved()\n', 'status="closed", stop_reason="user")\n    await discuss_store.run_write(operation)\n', 1)]),
    ("Y1", "认领补偿清令牌时不限定是自己认领的那个", [(RUNNER, '                "WHERE id=? AND username=? AND run_token=?",\n                (group_id, username, token))', '                "WHERE id=? AND username=?",\n                (group_id, username))', 1)]),
    ("Y3", "详情里分身名字取两次", [(SERVICE, "username, config_data, working, name=avatar_name))", "username, config_data, working))", 1)]),
    ("Y5", "隐私说明没有搜索另扣那句", [(ROLES, '    "联网搜索按次另扣草莓，与成员用哪个模型无关。")', '    "")', 1)]),
    ("Y6", "建群重名检查只对自定义成员生效", [(SERVICE, '        if member["name"] in names:', '        if member["role"].startswith("custom") and member["name"] in names:', 1)]),
]


def replace_nth(text, old, new, nth):
    position = -1
    for _ in range(nth):
        position = text.find(old, position + 1)
        if position < 0:
            raise LookupError(f"找不到第 {nth} 处：{old[:60]!r}")
    return text[:position] + new + text[position + len(old):]


def run_tests(clone):
    env = dict(os.environ, NO_PROXY="localhost,127.0.0.1,::1,.local", no_proxy="localhost,127.0.0.1,::1,.local")
    env.pop("ANTHROPIC_BASE_URL", None)
    command = [".venv/bin/python", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
               *sorted(str(path.relative_to(clone / "backend")) for path in (clone / "backend/tests").glob("test_discuss_*.py"))]
    try:
        done = subprocess.run(command, cwd=clone / "backend", env=env, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    lines = [line for line in done.stdout.splitlines() if line.strip()]
    return done.returncode, lines[-1] if lines else ""


def main():
    clone, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    wanted = set(sys.argv[3:])
    if clone.exists():
        raise SystemExit("克隆目录已存在，请换一个")
    subprocess.run(["cp", "-cR", str(ROOT), str(clone)], check=True)
    code, summary = run_tests(clone)
    print(f"正控（未改动）：exit={code} {summary}", flush=True)
    if code != 0:
        raise SystemExit("正控没有全过，结果无效")
    results = []
    for mutation_id, title, edits in MUTATIONS:
        if wanted and mutation_id not in wanted:
            continue
        originals = {}
        try:
            for path, old, new, nth in edits:
                target = clone / path
                originals.setdefault(path, target.read_text(encoding="utf-8"))
                target.write_text(replace_nth(target.read_text(encoding="utf-8"), old, new, nth), encoding="utf-8")
        except LookupError as error:
            for path, text in originals.items():
                (clone / path).write_text(text, encoding="utf-8")
            results.append({"id": mutation_id, "title": title, "killed": None, "exit": None, "summary": str(error)})
            print(f"{mutation_id:4} 锚点缺失  {title}  [{error}]", flush=True)
            continue
        code, summary = run_tests(clone)
        for path, text in originals.items():
            (clone / path).write_text(text, encoding="utf-8")
        killed = code != 0
        # 只有断言失败才算数；夹具报错或超时可能是偶发问题，单独标出来人工复核。
        by_error = killed and " failed" not in f" {summary}"
        results.append({"id": mutation_id, "title": title, "killed": killed, "by_error": by_error,
                        "exit": code, "summary": summary})
        label = "存活" if not killed else "杀死（非断言失败，需复核）" if by_error else "杀死"
        print(f"{mutation_id:4} {label}  {title}  [{summary}]", flush=True)
    code, summary = run_tests(clone)
    print(f"收尾正控（全部还原后）：exit={code} {summary}", flush=True)
    survived = [item["id"] for item in results if item["killed"] is False]
    missing = [item["id"] for item in results if item["killed"] is None]
    killed_count = sum(1 for item in results if item["killed"] is True)
    suspicious = [item["id"] for item in results if item.get("by_error")]
    print(f"非断言失败的「杀死」：{suspicious}")
    out.write_text(json.dumps({"total": len(results), "killed": killed_count, "survived": survived,
                               "killed_without_failed_assertion": suspicious,
                               "anchor_missing": missing, "restored_ok": code == 0, "results": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"合计 {len(results)}，杀死 {killed_count}，存活 {survived}，锚点缺失 {missing}")


if __name__ == "__main__":
    main()
