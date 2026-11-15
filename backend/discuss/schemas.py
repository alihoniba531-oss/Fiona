"""讨论群各步骤的校验与截断。

校验器都是纯函数：不修改传入对象，失败时抛
`novel.schemas.ValidationError`，错误文字用中文、点名字段、列出合法取值，
不回显模型输出。校验只查结构与取值，不查字数；超长字符串在返回前截断。
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re
from typing import Iterable

from novel.schemas import ValidationError


_REFS = re.compile(r"S\d+")
_BRACKETS = re.compile(r"\[([^\[\]]{1,80})\]")


def refs_in(text: str) -> set[str]:
    """取文本里所有方括号内的 S 数字，写法与 pilot.py 一致。"""
    if not isinstance(text, str):
        return set()
    return set(_REFS.findall(" ".join(_BRACKETS.findall(text))))


def clip(text: str, limit: int) -> str:
    if not isinstance(text, str):
        return text
    return text[:limit]


def normalize_role(value, names: dict[str, str]) -> str:
    """把成员名字归一成代号；代号原样返回，「整体」「全体」归一成 overall。"""
    if not isinstance(value, str):
        return value
    value = value.strip()
    if value in ("整体", "全体"):
        return "overall"
    if value in names.values():
        return value
    return names.get(value, value)


def _nonempty(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _raise(errors: list[str]) -> None:
    if errors:
        raise ValidationError(errors)


def _role_map(items: Iterable) -> dict[str, str]:
    names: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        name, role = item.get("name"), item.get("role")
        if isinstance(name, str) and isinstance(role, str):
            names[name] = role
    return names


def _roles_text(roles: Iterable[str]) -> str:
    values = [role for role in roles if isinstance(role, str)]
    return "、".join(values) if values else "（无）"


def check_plan(data, *, role_pool, fixed_members=None) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(["plan：必须是对象"])

    pool = [item for item in (role_pool or []) if isinstance(item, dict)]
    fixed = None if fixed_members is None else [
        item for item in fixed_members if isinstance(item, dict)]
    pool_roles = [item["role"] for item in pool if isinstance(item.get("role"), str)]
    role_set = set(pool_roles)
    names = _role_map(pool)
    if fixed is not None:
        names.update(_role_map(fixed))
        for item in fixed:
            role = item.get("role")
            if isinstance(role, str) and role not in role_set:
                pool_roles.append(role)
                role_set.add(role)

    errors: list[str] = []

    title = data.get("title")
    if not _nonempty(title):
        errors.append("title：必须是非空字符串")
    goal = data.get("goal")
    if not _nonempty(goal):
        errors.append("goal：必须是非空字符串")

    deliverable = data.get("deliverable")
    if not isinstance(deliverable, dict):
        errors.append("deliverable：必须是对象")
        outline = None
    else:
        kind = deliverable.get("kind")
        if kind not in ("report", "plan", "comparison"):
            errors.append("deliverable.kind：必须是 report、plan 或 comparison 之一")
        outline = deliverable.get("outline")
        if not isinstance(outline, list) or not 3 <= len(outline) <= 8 or not all(
                _nonempty(item) for item in outline):
            errors.append("deliverable.outline：必须是 3–8 个非空字符串")

    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not 3 <= len(criteria) <= 6 or not all(
            _nonempty(item) for item in criteria):
        errors.append("criteria：必须是 3–6 个非空字符串")

    questions = data.get("questions")
    if not isinstance(questions, list) or len(questions) > 3 or not all(
            _nonempty(item) for item in questions):
        errors.append("questions：必须是 0–3 个非空字符串")

    picks = data.get("picks")
    parsed_picks: list[tuple[str, dict]] = []
    if not isinstance(picks, list):
        errors.append("picks：必须是调研成员数组")
    else:
        for index, item in enumerate(picks):
            if not isinstance(item, dict):
                errors.append(f"picks[{index}]：必须是对象")
                continue
            role = normalize_role(item.get("role"), names)
            focus = item.get("focus")
            if not isinstance(role, str) or role not in role_set:
                errors.append(
                    f"picks[{index}].role：必须是以下调研成员代号之一：{_roles_text(pool_roles)}")
            if not _nonempty(focus):
                errors.append(f"picks[{index}].focus：必须是非空字符串")
            parsed_picks.append((role, item))

        if fixed is None:
            picked_roles = [role for role, _item in parsed_picks]
            if not 2 <= len(parsed_picks) <= 4 or len(set(picked_roles)) != len(picked_roles) or not all(
                    isinstance(role, str) and role in role_set for role in picked_roles):
                errors.append(
                    "picks：主持人点将时必须挑 2–4 位互不重复的调研成员，"
                    f"role 只能是：{_roles_text(pool_roles)}")
            else:
                normalized_picks = []
                for role, item in parsed_picks:
                    copy = deepcopy(item)
                    copy["role"] = role
                    normalized_picks.append(copy)
                data = {**data, "picks": normalized_picks}
        else:
            expected = [item["role"] for item in fixed if isinstance(item.get("role"), str)]
            picked_roles = [role for role, _item in parsed_picks]
            if len(parsed_picks) != len(expected) or Counter(picked_roles) != Counter(expected) or not all(
                    isinstance(role, str) and role in role_set for role in picked_roles):
                errors.append(
                    "picks：作者组队时必须恰好等于主人定好的成员，不增不减，"
                    f"role 只能是：{_roles_text(expected or pool_roles)}")
            else:
                by_role = {role: item for role, item in parsed_picks}
                normalized_picks = []
                for role in expected:
                    copy = deepcopy(by_role[role])
                    copy["role"] = role
                    normalized_picks.append(copy)
                data = {**data, "picks": normalized_picks}

    _raise(errors)

    result = deepcopy(data)
    result["title"] = clip(title, 40)
    result["goal"] = clip(goal, 400)
    result["deliverable"]["outline"] = [clip(item, 300) for item in result["deliverable"]["outline"]]
    result["criteria"] = [clip(item, 120) for item in result["criteria"]]
    result["questions"] = [clip(item, 300) for item in result["questions"]]
    for item in result["picks"]:
        item["focus"] = clip(item["focus"], 300)
    return result


def check_queries(data) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(["queries：必须是对象"])
    queries = data.get("queries")
    if not isinstance(queries, list) or not 1 <= len(queries) <= 5 or not all(
            _nonempty(item) for item in queries):
        raise ValidationError(["queries：必须是 1–5 个非空字符串"])
    return data


def check_note(data, *, known) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(["note：必须是对象"])
    known_set = set(known)
    errors: list[str] = []

    note = data.get("note")
    if not _nonempty(note):
        errors.append("note：必须是非空字符串")
    elif not refs_in(note) <= known_set:
        errors.append("note：引用了来源登记表里没有的编号")

    points = data.get("key_points")
    if not isinstance(points, list) or not 2 <= len(points) <= 6:
        errors.append("key_points：必须有 2–6 条")
    else:
        for index, point in enumerate(points):
            if not isinstance(point, dict):
                errors.append(f"key_points[{index}]：必须是对象")
                continue
            if not _nonempty(point.get("text")):
                errors.append(f"key_points[{index}].text：必须是非空字符串")
            refs = point.get("refs")
            if not isinstance(refs, list) or not refs or not all(
                    isinstance(ref, str) and ref for ref in refs):
                errors.append(f"key_points[{index}].refs：必须是非空的来源编号数组")
            elif not set(refs) <= known_set:
                errors.append(f"key_points[{index}].refs：引用了来源登记表里没有的编号")

    gaps = data.get("gaps")
    if not isinstance(gaps, list) or len(gaps) > 3:
        errors.append("gaps：必须是 0–3 条非空字符串")
    else:
        for index, gap in enumerate(gaps):
            if not _nonempty(gap):
                errors.append(f"gaps[{index}]：必须是非空字符串")

    _raise(errors)

    result = deepcopy(data)
    result["note"] = clip(note, 2000)
    for point in result["key_points"]:
        point["text"] = clip(point["text"], 300)
    result["gaps"] = [clip(gap, 150) for gap in result["gaps"]]
    return result


def check_critique(data, *, roles, names) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(["critique：必须是对象"])
    role_list = list(roles)
    role_set = set(role_list)
    errors: list[str] = []
    normalized_targets: list[str] = []

    objections = data.get("objections")
    if not isinstance(objections, list) or not 1 <= len(objections) <= 5:
        errors.append("objections：必须是 1–5 条")
    else:
        for index, item in enumerate(objections):
            if not isinstance(item, dict):
                errors.append(f"objections[{index}]：必须是对象")
                normalized_targets.append(item)
                continue
            target = normalize_role(item.get("target"), names)
            normalized_targets.append(target)
            if target != "overall" and target not in role_set:
                errors.append(
                    f"objections[{index}].target：必须是以下成员代号之一：{_roles_text(role_list)}，或 overall")
            if item.get("type") not in (
                    "unsupported", "contradiction", "missing", "bias", "outdated"):
                errors.append(
                    f"objections[{index}].type：必须是 unsupported、contradiction、missing、bias、outdated 之一")
            if not _nonempty(item.get("problem")):
                errors.append(f"objections[{index}].problem：必须是非空字符串")
            if not _nonempty(item.get("suggestion")):
                errors.append(f"objections[{index}].suggestion：必须是非空字符串")

    if not _nonempty(data.get("counter_view")):
        errors.append("counter_view：必须是非空字符串")

    _raise(errors)

    result = deepcopy(data)
    for index, item in enumerate(result["objections"]):
        item["target"] = normalized_targets[index]
        item["problem"] = clip(item["problem"], 300)
        item["suggestion"] = clip(item["suggestion"], 300)
    result["counter_view"] = clip(result["counter_view"], 500)
    return result


def _validate_note_responses(value, note_ids, errors: list[str]) -> None:
    expected = list(note_ids)
    if not isinstance(value, list):
        errors.append("note_responses：必须是数组")
        return
    ids: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"note_responses[{index}]：必须是对象")
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"note_responses[{index}].id：必须是非空字符串")
        else:
            ids.append(identifier)
        if not _nonempty(item.get("reply")):
            errors.append(f"note_responses[{index}].reply：必须是非空字符串")
    if Counter(ids) != Counter(expected):
        errors.append("note_responses：必须对每条插话恰好回应一次")


def _validate_summary(data: dict, errors: list[str]) -> None:
    if "summary" in data and data["summary"] is not None and not isinstance(data["summary"], str):
        errors.append("summary：必须是字符串")


def _normalized_note_responses(items) -> list[dict]:
    result = []
    for item in items:
        copy = deepcopy(item)
        copy["reply"] = clip(copy["reply"], 300)
        result.append(copy)
    return result


def check_decide(data, *, roles, names, objection_ids, can_research_more, note_ids) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(["decide：必须是对象"])
    role_list = list(roles)
    role_set = set(role_list)
    errors: list[str] = []

    responses = data.get("responses")
    if not isinstance(responses, list):
        errors.append("responses：必须是数组")
    else:
        response_ids: list[str] = []
        for index, item in enumerate(responses):
            if not isinstance(item, dict):
                errors.append(f"responses[{index}]：必须是对象")
                continue
            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier:
                errors.append(f"responses[{index}].id：必须是非空字符串")
            else:
                response_ids.append(identifier)
            if item.get("action") not in ("accept", "partial", "reject"):
                errors.append(f"responses[{index}].action：必须是 accept、partial、reject 之一")
            if "reason" in item and item["reason"] is not None and not isinstance(item["reason"], str):
                errors.append(f"responses[{index}].reason：必须是字符串")
        if Counter(response_ids) != Counter(objection_ids):
            errors.append("responses：必须对每个意见编号恰好回应一次")

    decision = data.get("decision")
    if decision not in ("draft", "research"):
        errors.append("decision：必须是 draft 或 research 之一")
    elif decision == "research" and not can_research_more:
        errors.append("decision：can_research_more 为 false 时只能是 draft")

    if decision == "research":
        assignments = data.get("assignments")
        if not isinstance(assignments, list) or not 1 <= len(assignments) <= 3:
            errors.append(
                "assignments：decision 为 research 时必须是 1–3 条，"
                f"role 只能是：{_roles_text(role_list)}")
        else:
            for index, item in enumerate(assignments):
                if not isinstance(item, dict):
                    errors.append(f"assignments[{index}]：必须是对象")
                    continue
                role = normalize_role(item.get("role"), names)
                if not isinstance(role, str) or role not in role_set:
                    errors.append(
                        f"assignments[{index}].role：必须是以下调研成员代号之一：{_roles_text(role_list)}")
                if not _nonempty(item.get("task")):
                    errors.append(f"assignments[{index}].task：必须是非空字符串")
    elif decision == "draft":
        if not _nonempty(data.get("brief_for_writer")):
            errors.append("brief_for_writer：必须是非空字符串")

    _validate_note_responses(data.get("note_responses"), note_ids, errors)
    _validate_summary(data, errors)

    _raise(errors)

    result = deepcopy(data)
    for item in result["responses"]:
        if item.get("reason") is None:
            item["reason"] = ""
        else:
            item["reason"] = clip(item["reason"], 200)
    result["note_responses"] = _normalized_note_responses(result["note_responses"])
    if decision == "research":
        for item in result["assignments"]:
            item["role"] = normalize_role(item["role"], names)
            item["task"] = clip(item["task"], 300)
    if decision == "draft":
        result["brief_for_writer"] = clip(result["brief_for_writer"], 1200)
    if isinstance(result.get("summary"), str):
        result["summary"] = clip(result["summary"], 500)
    return result


def check_draft(text, *, known) -> str:
    if not isinstance(text, str):
        raise ValidationError(["draft：必须是文本"])
    errors: list[str] = []
    if len(text.strip()) < 400:
        errors.append("draft：去空白后不足 400 字")
    if not refs_in(text) <= set(known):
        errors.append("draft：引用了来源登记表里没有的编号")
    if "http://" in text or "https://" in text:
        errors.append("draft：不能包含网址")
    _raise(errors)
    return clip(text, 12000)


def check_accept(data, *, criteria, draft) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(["accept：必须是对象"])
    criteria_ids = [item.get("id") for item in criteria if isinstance(item, dict)]
    errors: list[str] = []

    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list):
        errors.append("verdicts：必须是数组")
    else:
        verdict_ids: list[str] = []
        for index, item in enumerate(verdicts):
            if not isinstance(item, dict):
                errors.append(f"verdicts[{index}]：必须是对象")
                continue
            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier:
                errors.append(f"verdicts[{index}].id：必须是非空字符串")
            else:
                verdict_ids.append(identifier)
            if type(item.get("pass")) is not bool:
                errors.append(f"verdicts[{index}].pass：必须是布尔值")
        if Counter(verdict_ids) != Counter(criteria_ids):
            errors.append("verdicts：必须对每条完成标准恰好给一个结论")

    if not isinstance(data.get("citation_issues"), list):
        errors.append("citation_issues：必须是数组")
    if not isinstance(data.get("rework"), list):
        errors.append("rework：必须是数组")

    _raise(errors)

    result = deepcopy(data)
    for item in result["verdicts"]:
        if isinstance(item.get("evidence"), str):
            item["evidence"] = clip(item["evidence"], 300)
    result["rework"] = [
        clip(item, 300) if isinstance(item, str) else item for item in result["rework"]]
    return result


def check_rework(data, *, roles, names, note_ids) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(["rework：必须是对象"])
    role_list = list(roles)
    role_set = set(role_list)
    errors: list[str] = []

    assignments = data.get("assignments")
    if not isinstance(assignments, list) or len(assignments) > 3:
        errors.append(
            "assignments：必须是 0–3 条，"
            f"role 只能是：{_roles_text(role_list)}")
    else:
        for index, item in enumerate(assignments):
            if not isinstance(item, dict):
                errors.append(f"assignments[{index}]：必须是对象")
                continue
            role = normalize_role(item.get("role"), names)
            if not isinstance(role, str) or role not in role_set:
                errors.append(
                    f"assignments[{index}].role：必须是以下调研成员代号之一：{_roles_text(role_list)}")
            if not _nonempty(item.get("task")):
                errors.append(f"assignments[{index}].task：必须是非空字符串")

    if not _nonempty(data.get("brief_for_writer")):
        errors.append("brief_for_writer：必须是非空字符串")

    _validate_note_responses(data.get("note_responses"), note_ids, errors)
    _validate_summary(data, errors)

    _raise(errors)

    result = deepcopy(data)
    for item in result["assignments"]:
        item["role"] = normalize_role(item["role"], names)
        item["task"] = clip(item["task"], 300)
    result["note_responses"] = _normalized_note_responses(result["note_responses"])
    result["brief_for_writer"] = clip(result["brief_for_writer"], 1200)
    if isinstance(result.get("summary"), str):
        result["summary"] = clip(result["summary"], 500)
    return result


def check_brief(data, *, question_count: int) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(["brief：必须是对象"])
    errors: list[str] = []

    context = data.get("context")
    if not _nonempty(context):
        errors.append("context：必须是非空字符串")

    answers = data.get("answers")
    if not isinstance(answers, list):
        errors.append("answers：必须是数组")
    else:
        for index, item in enumerate(answers):
            if not isinstance(item, dict):
                errors.append(f"answers[{index}]：必须是对象")
                continue
            question = item.get("q")
            if type(question) is not int:
                errors.append(f"answers[{index}].q：必须是整数")
            elif not 1 <= question <= question_count:
                errors.append(f"answers[{index}].q：必须在 1–{question_count} 之间")
            if not _nonempty(item.get("answer")):
                errors.append(f"answers[{index}].answer：必须是非空字符串")

    ask_owner = data.get("ask_owner")
    if not isinstance(ask_owner, list):
        errors.append("ask_owner：必须是整数数组")
    else:
        for index, item in enumerate(ask_owner):
            if type(item) is not int:
                errors.append(f"ask_owner[{index}]：必须是整数")

    _raise(errors)

    result = deepcopy(data)
    result["context"] = clip(result["context"], 600)
    for item in result["answers"]:
        item["answer"] = clip(item["answer"], 600)
    return result


def check_view(data) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(["view：必须是对象"])
    errors: list[str] = []

    comment = data.get("comment")
    if not _nonempty(comment):
        errors.append("comment：必须是非空字符串")

    must_fix = data.get("must_fix")
    if not isinstance(must_fix, list) or len(must_fix) > 3:
        errors.append("must_fix：必须是 0–3 条非空字符串")
    else:
        for index, item in enumerate(must_fix):
            if not _nonempty(item):
                errors.append(f"must_fix[{index}]：必须是非空字符串")

    _raise(errors)

    result = deepcopy(data)
    result["comment"] = clip(result["comment"], 600)
    result["must_fix"] = [clip(item, 600) for item in result["must_fix"]]
    return result
