"""讨论群的立项与轮次流程。

流程只从 ``plan_json`` 读取方案，不重放立项；每一步是一次 ``LLMRouter.call``，
已完成的步骤命中缓存，所以暂停、重启与追加轮数都靠「从第 1 轮顺序重放」恢复。
所有状态与消息的写入都经过 ``DiscussStepStore`` 的令牌守卫事务。
"""

from __future__ import annotations

import asyncio
import json

from novel.billing import InsufficientStrawberries, NovelBudgetExceeded, RunNoLongerActive

from . import avatar, research, roles, schemas
from . import config as discuss_config
from . import store as discuss_store
from .billing import DiscussBilling


WORKING: dict[str, set[str]] = {}
"""群 ID -> 正在发言的角色代号；runner 在任务结束时清空。"""


class SearchUnavailable(RuntimeError):
    """第 1 轮所有调研角色都没有拿到可用事实。"""


def _json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _member_pick(by_role: dict, role: str) -> dict:
    pick = by_role.get(role)
    if isinstance(pick, dict):
        return pick
    return {"role": role, "name": roles.role_name(role),
            "does": roles.role_does(role), "focus": ""}


def _merge_assignments(assignments) -> list[dict]:
    """Merge assignments by role, keeping first appearance order.

    A member may be given several tasks in one decision or rework plan.  Running
    one investigation per assignment would repeat the same step key and lose all
    but the first task, so join the non-empty tasks with a Chinese semicolon and
    investigate each member once.
    """
    merged: list[dict] = []
    positions: dict[str, int] = {}
    tasks: dict[str, list[str]] = {}
    for item in assignments or []:
        if not isinstance(item, dict) or not isinstance(item.get("role"), str):
            continue
        role = item["role"]
        if role not in positions:
            positions[role] = len(merged)
            merged.append({"role": role, "task": None})
            tasks[role] = []
        task = item.get("task")
        if isinstance(task, str) and task.strip():
            tasks[role].append(task)
    for role, role_tasks in tasks.items():
        if role_tasks:
            merged[positions[role]]["task"] = "；".join(role_tasks)
    return merged


def _seat_identity(config: dict, role: str) -> str:
    identities = config.get("identities")
    if isinstance(identities, dict):
        value = identities.get(role)
        if isinstance(value, dict) and isinstance(value.get("persona"), str):
            return value["persona"]
    return ""


def _model_for(config: dict, role: str) -> str:
    models = config.get("models")
    value = models.get(role) if isinstance(models, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return roles.DEFAULT_MODELS.get(role) or roles.DEEPSEEK


def _system(config: dict, task: str, *, role: str | None = None, name: str | None = None,
            does: str | None = None, output: str = "json") -> str:
    text = roles.prompt(task, name=name, does=does)
    if role is not None:
        line = roles.identity_line(_seat_identity(config, role))
        if line:
            text += "\n" + line
    text += roles.RULES
    if output == "json":
        text += roles.JSON_RULE
    return text


async def _call(router, store, *, step_key: str, role: str, model: str, system: str, task: str,
                payload: dict, max_tokens: int, validator=None, output: str = "json",
                chapter: int = 0):
    """One model step with the shared message shape and the WORKING marker."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({"task": task, **payload}, ensure_ascii=False)},
    ]
    WORKING.setdefault(store.group_id, set()).add(role)
    try:
        return await router.call(
            step_key=step_key, role=role, model=model, messages=messages,
            max_tokens=max_tokens, validator=validator, output=output,
            experiment="discuss", arm="", chapter=chapter,
        )
    finally:
        WORKING.setdefault(store.group_id, set()).discard(role)


async def _gather_all(aws):
    """Wait for every parallel step, then re-raise the first failure.

    A failing research step must not leave its siblings writing steps after the
    runner has already refunded and invalidated this token.
    """
    outcomes = await asyncio.gather(*aws, return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
    return outcomes


async def _read_group(store):
    group = await discuss_store.get_group(store.username, store.group_id)
    if group is None:
        raise RunNoLongerActive()
    return group


def _complete_plan(result: dict, *, role_pool) -> dict:
    """Fill names/does and C ids into the validated plan result."""
    pool: dict[str, dict] = {}
    for item in role_pool or []:
        if isinstance(item, dict) and isinstance(item.get("role"), str):
            pool[item["role"]] = item
    picks = []
    for item in result["picks"]:
        role = item["role"]
        base = pool.get(role, {})
        name = base.get("name") or item.get("name") or roles.role_name(role)
        does = base.get("does") or item.get("does") or roles.role_does(role)
        picks.append({"role": role, "name": name, "does": does, "focus": item["focus"]})
    deliverable = result["deliverable"]
    return {
        "title": result["title"],
        "goal": result["goal"],
        "deliverable": {"kind": deliverable["kind"], "outline": list(deliverable["outline"])},
        "criteria": [{"id": f"C{index}", "text": text}
                     for index, text in enumerate(result["criteria"], 1)],
        "picks": picks,
        "questions": list(result["questions"]),
    }


def _plan_content(plan: dict) -> str:
    parts = [
        f"任务：{plan['title']}",
        f"目标：{plan['goal']}",
        "成果：" + plan["deliverable"]["kind"] + "，提纲：" + "、".join(plan["deliverable"]["outline"]),
        "完成标准：\n" + "\n".join(f"- {item['id']} {item['text']}" for item in plan["criteria"]),
        "点将：\n" + "\n".join(f"- {pick['name']}：{pick['focus']}" for pick in plan["picks"]),
    ]
    if plan.get("questions"):
        parts.append("想问主人：\n" + "\n".join(f"- {question}" for question in plan["questions"]))
    return "\n\n".join(parts)


def _brief_content(result: dict, questions: list[str]) -> str:
    lines = [f"背景：{result['context']}"]
    if result["answers"]:
        lines.extend(["", "回答："])
        for item in result["answers"]:
            index = item["q"] - 1
            question = questions[index] if 0 <= index < len(questions) else f"问题 {item['q']}"
            lines.append(f"- {question}：{item['answer']}")
    if result["ask_owner"]:
        lines.extend(["", "需要主人回答："])
        seen: set[int] = set()
        for question_id in result["ask_owner"]:
            if question_id in seen:
                continue
            seen.add(question_id)
            if 1 <= question_id <= len(questions):
                lines.append(f"- {questions[question_id - 1]}")
            else:
                lines.append(f"- 问题 {question_id}")
    return "\n".join(lines)


def _view_content(result: dict) -> str:
    lines = [f"意见：{result['comment']}"]
    if result["must_fix"]:
        lines.extend(["", "必须修改："])
        lines.extend(f"- {item}" for item in result["must_fix"])
    return "\n".join(lines)


def _critique_content(objections: list[dict], counter_view: str, by_role: dict) -> str:
    lines = []
    for item in objections:
        target = by_role.get(item["target"], {}).get("name") or "整体"
        lines.append(
            f"- {item['id']}（{target}，{item['type']}）{item['problem']} 建议：{item['suggestion']}")
    lines.extend(["", f"反方观点：{counter_view}"])
    return "\n".join(lines)


def _note_content(note: dict) -> str:
    text = note["note"]
    if note["gaps"]:
        text += "\n\n还没查清：" + "；".join(note["gaps"])
    return text


def _decision_content(result: dict) -> str:
    lines = [f"- {item['id']} {item['action']}：{item.get('reason', '')}"
             for item in result["responses"]]
    decision = "开始撰稿" if result["decision"] == "draft" else "再查一轮"
    lines.extend(["", f"决定：{decision}。{result.get('summary') or ''}"])
    if result["note_responses"]:
        lines.extend(["", "对主人插话："])
        lines.extend(f"- {item['id']}：{item['reply']}" for item in result["note_responses"])
    return "\n".join(lines)


def _verdict_content(verdicts: list[dict], issues: list[dict], passed: bool) -> str:
    lines = [
        f"- {item['id']} {'通过' if item['pass'] else '未通过'}：{item.get('evidence', '')}"
        for item in verdicts
    ]
    if issues:
        lines.extend(["", "引用问题："])
        lines.extend(f"- 「{item['quote']}」{item.get('problem', '')}" for item in issues)
    lines.extend(["", f"结论：{'通过' if passed else '未通过'}"])
    return "\n".join(lines)


def _rework_content(result: dict, by_role: dict) -> str:
    if result["assignments"]:
        tasks = "；".join(
            f"{by_role.get(item['role'], {}).get('name') or roles.role_name(item['role'])}"
            f"——{item['task']}"
            for item in result["assignments"])
    else:
        tasks = "不补查，只改写"
    lines = [f"返工安排：{tasks}", "", f"给撰稿人：{result['brief_for_writer']}"]
    if result["note_responses"]:
        lines.extend(["", "对主人插话："])
        lines.extend(f"- {item['id']}：{item['reply']}" for item in result["note_responses"])
    return "\n".join(lines)


def _note_payload_user_notes(rows: list[dict]) -> list[dict]:
    return [{"id": f"N{index}", "text": row["content"]} for index, row in enumerate(rows, 1)]


async def _claimed_notes(store, step_key: str) -> tuple[list[dict], list[str]]:
    """Claim unread author notes for a reading point, then number them N1…."""
    record = await store.read_step(step_key)
    if record is None or record.get("status") != "ok":
        await discuss_store.claim_notes(store, step_key)
    rows = await discuss_store.notes_for(store.username, store.group_id, step_key)
    user_notes = _note_payload_user_notes(rows)
    return user_notes, [item["id"] for item in user_notes]


async def _cached_brief_context(store) -> str:
    record = await store.read_step("r00/02-brief-avatar")
    if record is None or record.get("status") != "ok":
        return ""
    result = record.get("result")
    if isinstance(result, dict) and isinstance(result.get("context"), str):
        return result["context"]
    return ""


async def _start_notes(store, config: dict) -> str:
    rows = await discuss_store.notes_for(store.username, store.group_id, "start")
    parts = [row["content"] for row in rows if isinstance(row.get("content"), str)]
    answers = config.get("answers")
    if isinstance(answers, str) and answers.strip():
        parts.append(answers)
    return "\n".join(parts)


def _is_avatar_required(config: dict) -> bool:
    return bool(config.get("avatar"))


_AVATAR_RAISE = (asyncio.CancelledError, RunNoLongerActive,
                 InsufficientStrawberries, NovelBudgetExceeded)


async def _avatar_try(store, router, config: dict, *, step_key: str, task: str, payload: dict,
                      max_tokens: int, validator, chapter: int) -> tuple[bool, dict | None]:
    """Best-effort avatar step: four fatal classes propagate, the rest becomes a notice."""
    try:
        models = config.get("models")
        configured = models.get("avatar") if isinstance(models, dict) else None
        model = await avatar.effective_model(store.username, configured)
        system = await avatar.system_for(store.username, task)
        result = await _call(
            router, store, step_key=step_key, role="avatar", model=model, system=system,
            task=task, payload=payload, max_tokens=max_tokens, validator=validator,
            output="json", chapter=chapter,
        )
        return True, result
    except _AVATAR_RAISE:
        raise
    except Exception as error:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            # A protected read may finish with a normal exception after the
            # caller was cancelled (_drain re-raises the inner exception and
            # cancelling() stays > 0).  Do not turn that into a skippable
            # avatar notice; hand the cancellation back instead.
            raise asyncio.CancelledError() from error
        await store.post_message(
            round=chapter, sender="avatar", kind="notice", content="分身这次没能发言",
            payload={}, step_key=f"{step_key}-skip",
        )
        return False, None


async def run_planning(store, router) -> None:
    """r00: host plans, avatar gives context, then the group waits for the author."""
    group = await _read_group(store)
    if group.get("status") != "planning":
        return
    config = group.get("config") or {}
    fixed = config.get("fixed_members")
    fixed_members = [item for item in fixed if isinstance(item, dict)] if isinstance(fixed, list) else []
    if fixed_members:
        role_pool = fixed_members
    else:
        role_pool = [
            {"role": role, "name": name, "does": does}
            for role, (name, does) in roles.LENSES.items()
        ]
    today = discuss_config.today_beijing()
    result = await _call(
        router, store,
        step_key="r00/01-plan-host",
        role="host",
        model=_model_for(config, "host"),
        system=_system(config, "plan", role="host"),
        task="plan",
        payload={
            "request": group.get("request") or "",
            "materials": group.get("materials") or "",
            "today": today,
            "role_pool": role_pool,
            "fixed_members": fixed_members,
        },
        max_tokens=1500,
        validator=lambda value: schemas.check_plan(
            value, role_pool=role_pool, fixed_members=fixed_members or None),
        chapter=0,
    )
    completed = _complete_plan(result, role_pool=role_pool)
    if int(group.get("plan_revision") or 0) == 0:
        async def operation(db):
            await discuss_store.update_group_on_connection(
                db, store.username, store.group_id,
                plan_json=_json_text(completed), plan_revision=1, title=completed["title"],
            )
        await store.transaction(operation)
        plan = completed
    else:
        stored = group.get("plan")
        plan = stored if isinstance(stored, dict) and stored else completed
    await store.post_message(
        round=0, sender="host", kind="plan", content=_plan_content(plan),
        payload=plan, step_key="r00/01-plan-host",
    )
    if _is_avatar_required(config):
        questions = plan.get("questions") or []
        ok, brief = await _avatar_try(
            store, router, config,
            step_key="r00/02-brief-avatar",
            task="brief",
            payload={
                "request": group.get("request") or "",
                "goal": plan.get("goal") or "",
                "questions": [{"q": index, "text": text}
                              for index, text in enumerate(questions, 1)],
            },
            max_tokens=800,
            validator=lambda value: schemas.check_brief(
                value, question_count=len(questions)),
            chapter=0,
        )
        if ok and isinstance(brief, dict):
            await store.post_message(
                round=0, sender="avatar", kind="brief",
                content=_brief_content(brief, questions),
                payload=brief, step_key="r00/02-brief-avatar",
            )
    await store.update_group(
        status="awaiting_start", stop_reason=None, run_token=None, last_error=None)


async def run_rounds(store, router) -> None:
    """Replay every round from 1, rebuilding state until the first uncached step."""
    group = await _read_group(store)
    if group.get("status") != "running":
        return
    config = group.get("config") or {}
    plan = group.get("plan")
    if not isinstance(plan, dict) or not plan:
        raise RuntimeError("讨论群缺少方案")
    picks = []
    for item in plan.get("picks") or []:
        if not isinstance(item, dict) or not isinstance(item.get("role"), str):
            continue
        role = item["role"]
        name = item.get("name")
        does = item.get("does")
        picks.append({
            "role": role,
            "name": name if isinstance(name, str) and name.strip() else roles.role_name(role),
            "does": does if isinstance(does, str) and does.strip() else roles.role_does(role),
            "focus": item["focus"] if isinstance(item.get("focus"), str) else "",
        })
    lens_roles = [item["role"] for item in picks]
    by_role = {item["role"]: item for item in picks}
    names = {item["name"]: item["role"] for item in picks if item["name"]}
    max_rounds = int(group.get("max_rounds") or 0)
    current_round = int(group.get("round") or 0)
    revisions = config.get("revisions")
    revisions = [item for item in revisions if isinstance(item, int)] if isinstance(revisions, list) else []

    owner_context = await _cached_brief_context(store)
    owner_notes = await _start_notes(store, config)
    billing = DiscussBilling(store.username, store.group_id, store.run_token)
    draft = ""

    points: dict[str, list[dict]] = {}
    gaps: dict[str, list[str]] = {}
    assignments = _merge_assignments([{"role": role, "task": None} for role in lens_roles])
    open_objections: list[dict] = []
    brief = ""
    counter_view = ""
    rework: list[str] = []
    owner_view: dict | None = None
    slots = asyncio.Semaphore(3)

    for r in range(1, max_rounds + 1):
        if r > current_round:
            await store.update_group(round=r)
            current_round = r
        prefix = f"r{r:02d}"
        had_research = bool(assignments)

        if had_research:
            async def investigate(assignment):
                async with slots:
                    role = assignment["role"]
                    pick = _member_pick(by_role, role)
                    result = await _call(
                        router, store,
                        step_key=f"{prefix}/10-queries-{role}",
                        role=role,
                        model=_model_for(config, role),
                        system=_system(config, "queries", role=role,
                                       name=pick.get("name"), does=pick.get("does")),
                        task="queries",
                        payload={
                            "goal": plan["goal"],
                            "focus": pick.get("focus") or "",
                            "assignment": assignment.get("task"),
                            "today": discuss_config.today_beijing(),
                            "known_points": [point["text"] for point in points.get(role, [])],
                            "owner_context": owner_context,
                            "owner_notes": owner_notes,
                        },
                        max_tokens=400,
                        validator=schemas.check_queries,
                        chapter=r,
                    )
                    queries = result["queries"]
                    results = await _gather_all([
                        research.run_search(
                            store, billing, f"{prefix}/11-search-{role}-{index}",
                            role, query, plan["goal"])
                        for index, query in enumerate(queries, 1)
                    ])
                    return role, assignment.get("task"), queries, list(results)

            gathered = await _gather_all([investigate(item) for item in assignments])
            tasks_by_role: dict[str, str | None] = {}
            queries_by_role: dict[str, list[str]] = {}
            results_by_role: dict[str, list[dict]] = {}
            for role, task, queries, results in gathered:
                tasks_by_role[role] = task
                queries_by_role[role] = queries
                results_by_role[role] = results

            facts_by_role: dict[str, list[dict]] = {}
            for role in lens_roles:
                if role not in results_by_role:
                    continue
                facts = await research.register_findings(store, results_by_role[role])
                facts_by_role[role] = facts if isinstance(facts, list) else []

            assigned_roles = [item["role"] for item in assignments]
            for role in assigned_roles:
                if facts_by_role.get(role):
                    continue
                await store.post_message(
                    round=r, sender=role, kind="notice",
                    content="（本轮检索没有拿到可用事实，未产出笔记。检索的问题："
                            + "；".join(queries_by_role.get(role, [])) + "）",
                    payload={}, step_key=f"{prefix}/14-empty-{role}",
                )
            if r == 1 and not any(facts_by_role.get(role) for role in assigned_roles):
                raise SearchUnavailable()

            source_rows = await discuss_store.list_sources(store.username, store.group_id)
            known = {row["id"] for row in source_rows}
            active = [role for role in lens_roles if facts_by_role.get(role)]

            async def write_note(role):
                pick = _member_pick(by_role, role)
                facts = facts_by_role[role]
                previous = points.get(role, [])
                cited = {ref for fact in facts for ref in fact.get("refs", [])}
                cited.update(ref for point in previous for ref in point.get("refs", []))
                sources = [
                    {"id": row["id"], "title": row.get("title") or "",
                     "site": row.get("site_name") or ""}
                    for row in source_rows if row["id"] in cited
                ]
                objections = [item for item in open_objections
                              if item.get("target") in (role, "overall")]
                return role, await _call(
                    router, store,
                    step_key=f"{prefix}/13-note-{role}",
                    role=role,
                    model=_model_for(config, role),
                    system=_system(config, "note", role=role,
                                   name=pick.get("name"), does=pick.get("does")),
                    task="note",
                    payload={
                        "goal": plan["goal"],
                        "focus": pick.get("focus") or "",
                        "assignment": tasks_by_role.get(role),
                        "findings": facts,
                        "your_previous_points": [{"text": point["text"], "refs": point["refs"]}
                                                 for point in previous],
                        "objections_to_address": objections,
                        "sources": sources,
                        "owner_context": owner_context,
                        "owner_notes": owner_notes,
                    },
                    max_tokens=1500,
                    validator=lambda value: schemas.check_note(value, known=known),
                    chapter=r,
                )

            notes = await _gather_all([write_note(role) for role in active])
            for role, note in notes:
                await store.post_message(
                    round=r, sender=role, kind="note", content=_note_content(note),
                    payload=note, step_key=f"{prefix}/13-note-{role}",
                )
                points.setdefault(role, []).extend(
                    {**point, "round": r} for point in note["key_points"])
                gaps[role] = note["gaps"]

        if had_research:
            digest = [
                {"role": role,
                 "name": _member_pick(by_role, role).get("name") or roles.role_name(role),
                 "key_points": points.get(role, []),
                 "gaps": gaps.get(role, [])}
                for role in lens_roles
            ]
            critique = await _call(
                router, store,
                step_key=f"{prefix}/20-critique-critic",
                role="critic",
                model=_model_for(config, "critic"),
                system=_system(config, "critique", role="critic"),
                task="critique",
                payload={
                    "goal": plan["goal"],
                    "criteria": plan["criteria"],
                    "notes": digest,
                    "previous_draft": draft[:3000] if draft else None,
                },
                max_tokens=1500,
                validator=lambda value: schemas.check_critique(
                    value, roles=lens_roles, names=names),
                chapter=r,
            )
            objections = [{"id": f"O{index}", **item}
                          for index, item in enumerate(critique["objections"], 1)]
            await store.post_message(
                round=r, sender="critic", kind="critique",
                content=_critique_content(objections, critique["counter_view"], by_role),
                payload={"objections": objections, "counter_view": critique["counter_view"]},
                step_key=f"{prefix}/20-critique-critic",
            )

            user_notes, note_ids = await _claimed_notes(store, f"{prefix}/30-decide-host")
            can_research_more = r <= max_rounds - 2
            decision = await _call(
                router, store,
                step_key=f"{prefix}/30-decide-host",
                role="host",
                model=_model_for(config, "host"),
                system=_system(config, "decide", role="host"),
                task="decide",
                payload={
                    "round": r,
                    "max_rounds": max_rounds,
                    "can_research_more": can_research_more,
                    "goal": plan["goal"],
                    "criteria": plan["criteria"],
                    "outline": plan["deliverable"]["outline"],
                    "notes": digest,
                    "objections": objections,
                    "user_notes": user_notes,
                    "members": [{"role": item["role"], "name": item["name"]} for item in picks],
                },
                max_tokens=1800,
                validator=lambda value: schemas.check_decide(
                    value, roles=lens_roles, names=names,
                    objection_ids=[item["id"] for item in objections],
                    can_research_more=can_research_more, note_ids=note_ids),
                chapter=r,
            )
            await store.post_message(
                round=r, sender="host", kind="decision",
                content=_decision_content(decision), payload=decision,
                step_key=f"{prefix}/30-decide-host",
            )
            actions = {item["id"]: item["action"] for item in decision["responses"]}
            open_objections = [
                {"target": item["target"], "problem": item["problem"],
                 "suggestion": item["suggestion"], "host": actions[item["id"]]}
                for item in objections if actions[item["id"]] != "reject"
            ]
            if decision["decision"] == "research":
                assignments = _merge_assignments(decision["assignments"])
                continue
            brief = decision["brief_for_writer"]
            counter_view = critique["counter_view"]

        source_rows = await discuss_store.list_sources(store.username, store.group_id)
        known = {row["id"] for row in source_rows}
        used_refs = {ref for rows in points.values() for point in rows
                     for ref in point.get("refs", [])}
        cited_sources = [
            {"id": row["id"], "title": row.get("title") or "",
             "site": row.get("site_name") or ""}
            for row in source_rows if row["id"] in used_refs
        ]

        draft_key = f"{prefix}/40-draft-writer"
        text = await _call(
            router, store,
            step_key=draft_key,
            role="writer",
            model=_model_for(config, "writer"),
            system=_system(config, "draft", role="writer", output="text"),
            task="draft",
            payload={
                "goal": plan["goal"],
                "deliverable": plan["deliverable"],
                "criteria": plan["criteria"],
                "brief": brief,
                "counter_view": counter_view,
                "points": points,
                "gaps": gaps,
                "sources": cited_sources,
                "previous_draft": draft or None,
                "rework": rework,
                "owner_context": owner_context,
            },
            max_tokens=6000,
            validator=lambda value: schemas.check_draft(value, known=known),
            output="text",
            chapter=r,
        )
        version = await store.save_output(r, draft_key, text)
        await store.post_message(
            round=r, sender="writer", kind="draft",
            content=f"（提交了第 {version} 版成果，{len(text)} 字，引用来源 {len(schemas.refs_in(text))} 条）",
            payload={"version": version}, step_key=draft_key,
        )
        draft = text

        if _is_avatar_required(config):
            ok, view = await _avatar_try(
                store, router, config,
                step_key=f"{prefix}/41-view-avatar",
                task="view",
                payload={"goal": plan["goal"], "criteria": plan["criteria"], "draft": draft},
                max_tokens=800,
                validator=schemas.check_view,
                chapter=r,
            )
            if ok and isinstance(view, dict):
                await store.post_message(
                    round=r, sender="avatar", kind="view", content=_view_content(view),
                    payload=view, step_key=f"{prefix}/41-view-avatar",
                )
                owner_view = view
            else:
                owner_view = None
        else:
            owner_view = None

        accept_key = f"{prefix}/50-accept-acceptor"
        verdict = await _call(
            router, store,
            step_key=accept_key,
            role="acceptor",
            model=_model_for(config, "acceptor"),
            system=_system(config, "accept", role="acceptor"),
            task="accept",
            payload={
                "criteria": plan["criteria"],
                "draft": draft,
                "sources": cited_sources,
                "points": points,
                "owner_view": owner_view,
            },
            max_tokens=1800,
            validator=lambda value: schemas.check_accept(
                value, criteria=plan["criteria"], draft=draft),
            chapter=r,
        )
        issues = [
            item for item in verdict["citation_issues"]
            if isinstance(item, dict) and isinstance(item.get("quote"), str)
            and item["quote"] in draft
        ]
        passed = all(item["pass"] for item in verdict["verdicts"]) and not issues
        await store.save_verdict(
            version,
            {"verdicts": verdict["verdicts"], "citation_issues": issues,
             "rework": verdict["rework"]},
            passed,
        )
        await store.post_message(
            round=r, sender="acceptor", kind="verdict",
            content=_verdict_content(verdict["verdicts"], issues, passed),
            payload={"verdicts": verdict["verdicts"], "citation_issues": issues,
                     "rework": verdict["rework"], "passed": passed},
            step_key=accept_key,
        )

        if passed and r not in revisions:
            await store.update_group(status="done", stop_reason="accepted", run_token=None)
            return
        if r == max_rounds:
            if passed:
                await store.update_group(status="done", stop_reason="accepted", run_token=None)
            else:
                await store.update_group(
                    status="awaiting_user", stop_reason="rounds_exhausted", run_token=None)
            return

        rework = [str(item)[:300] for item in verdict["rework"]][:5] + [
            f"引用问题：「{item['quote']}」{item.get('problem', '')}" for item in issues
        ]
        user_notes, note_ids = await _claimed_notes(store, f"{prefix}/60-rework-host")
        planned = await _call(
            router, store,
            step_key=f"{prefix}/60-rework-host",
            role="host",
            model=_model_for(config, "host"),
            system=_system(config, "rework", role="host"),
            task="rework",
            payload={
                "round": r,
                "criteria": plan["criteria"],
                "verdicts": verdict["verdicts"],
                "rework": rework,
                "owner_view": owner_view,
                "user_notes": user_notes,
                "members": [{"role": item["role"], "name": item["name"]} for item in picks],
            },
            max_tokens=1200,
            validator=lambda value: schemas.check_rework(
                value, roles=lens_roles, names=names, note_ids=note_ids),
            chapter=r,
        )
        await store.post_message(
            round=r, sender="host", kind="rework", content=_rework_content(planned, by_role),
            payload=planned, step_key=f"{prefix}/60-rework-host",
        )
        assignments = planned["assignments"]
        assignments = _merge_assignments(assignments)
        brief = planned["brief_for_writer"]
