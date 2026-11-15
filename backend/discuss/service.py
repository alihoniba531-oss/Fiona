"""讨论群的请求模型与作者侧业务操作。

作者侧的每一次写操作都通过 ``discuss_store.run_write`` 在受保护的
``BEGIN IMMEDIATE`` 事务里执行，并在事务里核对归属、状态与修订号，避免
嵌套事务和先查后写之间的竞态。后台流程只通过 ``discuss.runner`` 启动或
取消，这里不直接创建任务。
"""

from __future__ import annotations

import copy
import json
import re

from fastapi import HTTPException
from pydantic import BaseModel

from novel.byok_bridge import ByokBridge
from safety import CRISIS_RESOURCE_NOTE, assess_crisis

from . import avatar, billing, config, roles, runner, schemas
from . import store as discuss_store


class CreateGroup(BaseModel):
    request: str
    materials: str = ""
    budget_strawberries: int = 500
    max_rounds: int = 3
    avatar: bool = True
    models: dict[str, str] | None = None
    members: list[dict] | None = None
    identities: dict[str, dict] | None = None


class UpdatePlan(BaseModel):
    expected_revision: int
    title: str | None = None
    criteria: list[str] | None = None
    picks: list[dict] | None = None
    identities: dict[str, dict] | None = None
    budget_strawberries: int | None = None
    max_rounds: int | None = None
    avatar: bool | None = None
    models: dict[str, str] | None = None
    answers: str | None = None


class StartGroup(BaseModel):
    expected_revision: int


class NoteIn(BaseModel):
    text: str


class ResumeGroup(BaseModel):
    add_budget: int = 0


class ContinueGroup(BaseModel):
    add_rounds: int = 1
    add_budget: int = 0


NOT_FOUND = "讨论群不存在"
REVISION_CONFLICT = "方案已被修改，请刷新后再改"
ACTIVE_GROUP = "你有一个讨论群正在进行，等它停下来再建新的"
DAILY_LIMIT = "今天新建的讨论群已到上限，明天再来"
BYOK_UNAVAILABLE = "自带模型当前不可用，请到设置里检查"
BUDGET_EXHAUSTED = "预算已经用完，请先调高预算"
TOO_MANY_NOTES = "还有 5 条插话没被读到，等主持人回应后再说"
REWORK_NEEDS_NOTE = "先在群里写下你的意见，再点按意见返工"
CLOSE_RUNNING = "先暂停再结束"

_CUSTOM_ROLE = re.compile(r"custom([1-9][0-9]*)\Z")
_AVATAR_DOES = "代表主人的偏好和背景发言，从主人角度看成果合不合意。"


def _fail(message: str, status: int = 409):
    raise HTTPException(status, message)


def _invalid(message: str = "请求内容不合法"):
    raise HTTPException(422, message)


async def _rollback_fail(db, message: str, status: int = 409):
    """Abort the guarded transaction with an HTTP error.

    ``discuss_store.run_write`` rolls back the caller-owned transaction when the
    operation raises; this helper now only raises.  The async signature and
    ``db`` argument are kept so every existing call site stays unchanged.
    """
    raise HTTPException(status, message)


def _encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _trim(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_optional_text(item: dict, key: str, limit: int) -> str | None:
    """Optional override: null/absent means inherit, otherwise 1–limit chars."""
    if item.get(key) is None:
        return None
    value = item.get(key)
    if not isinstance(value, str):
        _invalid("成员内容不合法")
    value = value.strip()
    if not 1 <= len(value) <= limit:
        _invalid("成员内容不合法")
    return value


def _parse_required_text(item: dict, key: str, limit: int) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        _invalid("成员内容不合法")
    value = value.strip()
    if not 1 <= len(value) <= limit:
        _invalid("成员内容不合法")
    return value


def _parse_members(raw) -> list[dict] | None:
    """Validate the author's roster and assign custom1, custom2… in order."""
    if raw is None:
        return None
    if not isinstance(raw, list) or not 1 <= len(raw) <= 5:
        _invalid("调研成员需要 1–5 位")
    members: list[dict] = []
    seen: set[str] = set()
    names: set[str] = set()
    custom = 0
    for item in raw:
        if not isinstance(item, dict):
            _invalid("调研成员不合法")
        role = item.get("role")
        if role is not None:
            if not isinstance(role, str) or role not in roles.LENSES:
                _invalid("调研成员代号不合法")
            if role in seen:
                _invalid("调研成员不能重复")
            seen.add(role)
            default_name, default_does = roles.LENSES[role]
            name = _parse_optional_text(item, "name", 12) or default_name
            does = _parse_optional_text(item, "does", 200) or default_does
            member = {"role": role, "name": name, "does": does}
        else:
            custom += 1
            member = {
                "role": f"custom{custom}",
                "name": _parse_required_text(item, "name", 12),
                "does": _parse_required_text(item, "does", 200),
            }
        if member["name"] in names:
            _invalid("调研成员的名字不能重复")
        names.add(member["name"])
        members.append(member)
    return members


def _parse_identities(raw) -> dict[str, dict]:
    if not isinstance(raw, dict):
        _invalid("身份设定不合法")
    result: dict[str, dict] = {}
    for seat, item in raw.items():
        if seat not in roles.CORE_ROLES or not isinstance(item, dict):
            _invalid("身份设定不合法")
        entry: dict[str, str] = {}
        if item.get("name") is not None:
            name = item.get("name")
            if not isinstance(name, str):
                _invalid("身份设定不合法")
            name = name.strip()
            if len(name) > 12:
                _invalid("固定席位的名字最多 12 字")
            entry["name"] = name
        if item.get("persona") is not None:
            persona = item.get("persona")
            if not isinstance(persona, str) or len(persona) > 300:
                _invalid("身份设定最多 300 字")
            entry["persona"] = persona
        result[seat] = entry
    return result


async def _validate_models(username: str, raw, allowed: set[str]) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        _invalid("模型选择不合法")
    values: dict[str, str] = {}
    for role, model in raw.items():
        if role not in allowed:
            _invalid("模型选择不合法")
        if not isinstance(model, str) or model not in (*roles.PLATFORM_MODELS, "byok:self"):
            _invalid("模型选择不合法")
        values[role] = model
    if "byok:self" in values.values():
        try:
            await ByokBridge(username).describe()
        except Exception:
            _invalid(BYOK_UNAVAILABLE)
    return values


def _check_crisis(*values: str) -> None:
    for value in values:
        if isinstance(value, str) and value and assess_crisis(value) == "high":
            raise HTTPException(400, CRISIS_RESOURCE_NOTE)


def _seat_entry(config_data: dict, role: str) -> dict:
    identities = config_data.get("identities")
    if isinstance(identities, dict):
        entry = identities.get(role)
        if isinstance(entry, dict):
            return entry
    return {}


def _seat_name(config_data: dict, role: str) -> str:
    name = _seat_entry(config_data, role).get("name")
    return name.strip() if isinstance(name, str) and name.strip() else roles.role_name(role)


def _seat_persona(config_data: dict, role: str) -> str:
    persona = _seat_entry(config_data, role).get("persona")
    return persona if isinstance(persona, str) else ""


def _model_for(config_data: dict, role: str) -> str:
    models = config_data.get("models")
    value = models.get(role) if isinstance(models, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return roles.DEFAULT_MODELS.get(role) or roles.DEEPSEEK


def _member_kind(role: str) -> str:
    return "lens" if role in roles.LENSES else "custom"


def _current_picks(plan: dict) -> list[dict]:
    picks = plan.get("picks") if isinstance(plan, dict) else None
    return [item for item in picks if isinstance(item, dict)] if isinstance(picks, list) else []


def _pick_base(role: str, current: dict[str, dict]) -> tuple[str, str]:
    existing = current.get(role) or {}
    if role in roles.LENSES:
        default_name, default_does = roles.LENSES[role]
    else:
        default_name, default_does = roles.role_name(role), roles.role_does(role)
        if not default_does:
            default_does = "负责调研"
    name = existing.get("name")
    does = existing.get("does")
    return (
        name.strip() if isinstance(name, str) and name.strip() else default_name,
        does.strip() if isinstance(does, str) and does.strip() else default_does,
    )


def _parse_picks(raw, current_picks: list[dict]) -> list[dict]:
    """Replace the research roster, keeping existing codes and assigning new ones."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= 5:
        _invalid("调研成员需要 1–5 位")
    current = {
        item["role"]: item for item in current_picks
        if isinstance(item.get("role"), str)
    }
    used_numbers = {
        int(match.group(1)) for role in current if (match := _CUSTOM_ROLE.match(role))
    }
    seen_roles: set[str] = set()
    seen_names: set[str] = set()
    result: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            _invalid("调研成员不合法")
        focus = item.get("focus")
        if not isinstance(focus, str) or not focus.strip() or len(focus.strip()) > 300:
            _invalid("调研成员的分工需要 1–300 字")
        role = item.get("role")
        if role is not None:
            if not isinstance(role, str):
                _invalid("调研成员代号不合法")
            if role in roles.LENSES:
                default_name, default_does = _pick_base(role, current)
            elif _CUSTOM_ROLE.match(role) and role in current:
                default_name, default_does = _pick_base(role, current)
            else:
                _invalid("调研成员代号不合法")
            name = _parse_optional_text(item, "name", 12) or default_name
            does = _parse_optional_text(item, "does", 200) or default_does
        else:
            number = 1
            while number in used_numbers:
                number += 1
            used_numbers.add(number)
            role = f"custom{number}"
            name = _parse_required_text(item, "name", 12)
            does = _parse_required_text(item, "does", 200)
        if role in seen_roles:
            _invalid("调研成员不能重复")
        if name in seen_names:
            _invalid("调研成员的名字不能重复")
        seen_roles.add(role)
        seen_names.add(name)
        result.append({"role": role, "name": name, "does": does, "focus": focus.strip()})
    return result


def _title(group: dict) -> str:
    title = group.get("title")
    if isinstance(title, str) and title:
        return title
    request = group.get("request")
    return _text(request)[:20]


def _summary(group: dict) -> dict:
    return {
        "id": group["id"],
        "title": _title(group),
        "status": group["status"],
        "stop_reason": group.get("stop_reason"),
        "round": int(group.get("round") or 0),
        "max_rounds": int(group.get("max_rounds") or 0),
        "budget_strawberries": int(group.get("budget_strawberries") or 0),
        "spent_strawberries": int(group.get("spent_strawberries") or 0),
        "output_version": int(group.get("output_version") or 0),
        "created_at": group.get("created_at"),
        "updated_at": group.get("updated_at"),
    }


async def _core_member(config_data: dict, role: str, working: set[str]) -> dict:
    return {
        "role": role,
        "name": _seat_name(config_data, role),
        "kind": "core",
        "does": _seat_persona(config_data, role),
        "model": _model_for(config_data, role),
        "working": role in working,
    }


def _research_member(item: dict, config_data: dict, working: set[str]) -> dict:
    role = item["role"]
    return {
        "role": role,
        "name": _text(item.get("name")) or roles.role_name(role),
        "kind": _member_kind(role),
        "does": _text(item.get("does")) or roles.role_does(role),
        "focus": _text(item.get("focus")),
        "model": _model_for(config_data, role),
        "working": role in working,
    }


async def _avatar_member(
    username: str, config_data: dict, working: set[str],
    name: str | None = None,
) -> dict:
    models = config_data.get("models")
    configured = models.get("avatar") if isinstance(models, dict) else None
    return {
        "role": "avatar",
        "name": name if name is not None else await avatar.display_name(username),
        "kind": "avatar",
        "does": "",
        "model": await avatar.effective_model(username, configured),
        "working": "avatar" in working,
    }


async def access() -> dict:
    return {"allowed": True}


async def catalog(username: str) -> dict:
    role_list = [
        {"id": role, "name": roles.CORE_INFO[role]["name"],
         "does": roles.CORE_INFO[role]["does"], "kind": "core"}
        for role in roles.CORE_ROLES
    ]
    role_list.extend(
        {"id": role, "name": name, "does": does, "kind": "lens"}
        for role, (name, does) in roles.LENSES.items()
    )
    role_list.append(
        {"id": "avatar", "name": "分身", "does": _AVATAR_DOES, "kind": "avatar"})
    try:
        byok = await ByokBridge(username).describe()
    except Exception:
        byok = None
    prices = billing.get_prices()
    defaults = {role: roles.DEFAULT_MODELS[role]
                for role in (*roles.CORE_ROLES, *roles.LENSES)}
    defaults["avatar"] = await avatar.effective_model(username, None)
    return {
        "roles": role_list,
        "models": [{"id": model, "price": prices[model]} for model in roles.PLATFORM_MODELS],
        "byok": byok,
        "defaults": defaults,
        "limits": {
            "budget_min": 100,
            "budget_max": 20000,
            "budget_default": 500,
            "rounds_min": 1,
            "rounds_max": 6,
            "rounds_default": 3,
            "members_min": 1,
            "members_max": 5,
            "name_max": 12,
            "persona_max": 300,
            "custom_does_max": 200,
            "request_min": 10,
            "request_max": 2000,
            "materials_max": 20000,
            "unread_notes_max": 5,
        },
        "search_price": config.search_strawberries(),
        "notice": roles.PRIVACY_NOTICE,
    }


async def create_group(username: str, body: CreateGroup) -> dict:
    request = _trim(body.request)
    if not 10 <= len(request) <= 2000:
        _invalid("诉求需要 10–2000 字")
    materials = body.materials if isinstance(body.materials, str) else ""
    if len(materials) > 20000:
        _invalid("补充材料最多 20000 字")
    if not _is_int(body.budget_strawberries) or not 100 <= body.budget_strawberries <= 20000:
        _invalid("预算需要在 100–20000 颗之间")
    if not _is_int(body.max_rounds) or not 1 <= body.max_rounds <= 6:
        _invalid("轮数需要在 1–6 之间")

    _check_crisis(request, materials)
    fixed_members = _parse_members(body.members)
    identities = _parse_identities(body.identities) if body.identities is not None else None
    allowed = set(roles.CORE_ROLES) | {"avatar"} | set(roles.LENSES)
    if fixed_members:
        allowed |= {item["role"] for item in fixed_members}
    models = await _validate_models(username, body.models, allowed)

    config_data: dict = {
        "models": models,
        "avatar": bool(body.avatar),
        "revisions": [],
        "answers": "",
    }
    if identities is not None:
        config_data["identities"] = identities
    if fixed_members is not None:
        config_data["fixed_members"] = fixed_members

    group_id = discuss_store.new_group_id()
    day = config.today_beijing()
    async def operation(db):
        async with db.execute(
            "SELECT 1 FROM users WHERE username=?", (username,)
        ) as cursor:
            if await cursor.fetchone() is None:
                await _rollback_fail(db, "账号不存在", 404)
        async with db.execute(
            "SELECT 1 FROM discuss_groups WHERE username=? "
            "AND status IN ('planning','running') LIMIT 1",
            (username,),
        ) as cursor:
            if await cursor.fetchone() is not None:
                await _rollback_fail(db, ACTIVE_GROUP)
        async with db.execute(
            "SELECT COUNT(*) FROM discuss_groups WHERE username=? AND created_day=?",
            (username, day),
        ) as cursor:
            created_today = int((await cursor.fetchone())[0])
        if created_today >= config.daily_groups():
            await _rollback_fail(db, DAILY_LIMIT, 429)
        await discuss_store.create_group_on_connection(
            db, username,
            group_id=group_id,
            request=request,
            materials=materials,
            budget_strawberries=body.budget_strawberries,
            max_rounds=body.max_rounds,
            config=config_data,
            created_day=day,
        )
    await discuss_store.run_write(operation)
    await runner.start_group(group_id, username)
    group = await discuss_store.get_group(username, group_id)
    return _summary(group)


async def list_groups(username: str) -> list[dict]:
    return [_summary(group) for group in await discuss_store.list_groups(username)]


async def detail(username: str, group_id: str, after: int = 0) -> dict:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    config_data = group.get("config") if isinstance(group.get("config"), dict) else {}
    plan = group.get("plan") if isinstance(group.get("plan"), dict) else None
    working = runner.WORKING.get(group_id, set())
    messages = await discuss_store.list_messages(username, group_id, after=after, limit=200)
    output = await discuss_store.output_summary(username, group_id)
    unread = await discuss_store.unread_notes(username, group_id)

    avatar_name = None
    if (config_data.get("avatar")
            or any(message.get("sender") == "avatar" for message in messages)):
        avatar_name = await avatar.display_name(username)

    members: list[dict] = [await _core_member(config_data, "host", working)]
    if plan is not None:
        picks = _current_picks(plan)
        members.extend(_research_member(item, config_data, working) for item in picks)
    else:
        fixed = config_data.get("fixed_members")
        if isinstance(fixed, list):
            for item in fixed:
                if not isinstance(item, dict) or not isinstance(item.get("role"), str):
                    continue
                role = item["role"]
                members.append({
                    "role": role,
                    "name": _text(item.get("name")) or roles.role_name(role),
                    "kind": _member_kind(role),
                    "does": _text(item.get("does")),
                    "focus": "",
                    "model": _model_for(config_data, role),
                    "working": role in working,
                })
    for role in ("critic", "writer", "acceptor"):
        members.append(await _core_member(config_data, role, working))
    if config_data.get("avatar"):
        members.append(await _avatar_member(
            username, config_data, working, name=avatar_name))

    pick_names = {
        item["role"]: _text(item.get("name"))
        for item in _current_picks(plan or {})
        if isinstance(item.get("role"), str)
    }
    fixed_names = {
        item["role"]: _text(item.get("name"))
        for item in (config_data.get("fixed_members") or [])
        if isinstance(item, dict) and isinstance(item.get("role"), str)
    }

    rendered = []
    for message in messages:
        sender = message.get("sender") or ""
        if sender == "user":
            sender_name = "你"
        elif sender == "avatar":
            sender_name = avatar_name
        elif sender in roles.CORE_ROLES:
            sender_name = _seat_name(config_data, sender)
        else:
            sender_name = (pick_names.get(sender) or fixed_names.get(sender)
                           or roles.role_name(sender))
        rendered.append({
            "id": message["id"],
            "round": message["round"],
            "sender": sender,
            "sender_name": sender_name,
            "kind": message["kind"],
            "content": message["content"],
            "payload": message["payload"],
            "created_at": message["created_at"],
            "consumed": (bool(message.get("consumed_by")) if sender == "user" else None),
        })

    return {
        "id": group["id"],
        "title": _title(group),
        "request": group["request"],
        "status": group["status"],
        "stop_reason": group.get("stop_reason"),
        "last_error": group.get("last_error"),
        "round": int(group.get("round") or 0),
        "max_rounds": int(group.get("max_rounds") or 0),
        "budget_strawberries": int(group.get("budget_strawberries") or 0),
        "spent_strawberries": int(group.get("spent_strawberries") or 0),
        "reserved_strawberries": int(group.get("reserved_strawberries") or 0),
        "output_version": int(group.get("output_version") or 0),
        "plan_revision": int(group.get("plan_revision") or 0),
        "created_at": group.get("created_at"),
        "updated_at": group.get("updated_at"),
        "plan": plan,
        "members": members,
        "messages": rendered,
        "output": output,
        "pending_notes": len(unread),
    }


async def update_plan(username: str, group_id: str, body: UpdatePlan) -> dict:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    if group.get("status") != "awaiting_start":
        _fail("现在不能改方案")
    revision = int(group.get("plan_revision") or 0)
    if revision != body.expected_revision:
        _fail(REVISION_CONFLICT)

    plan = copy.deepcopy(group.get("plan") or {})
    config_data = copy.deepcopy(group.get("config") or {})
    if not isinstance(config_data, dict):
        config_data = {}
    title = group.get("title") or ""

    if body.title is not None:
        title = _trim(body.title)
        if not 1 <= len(title) <= 40:
            _invalid("标题需要 1–40 字")
        plan["title"] = title
    if body.criteria is not None:
        if not isinstance(body.criteria, list) or not 3 <= len(body.criteria) <= 6:
            _invalid("完成标准需要 3–6 条")
        texts = []
        for item in body.criteria:
            if not isinstance(item, str) or not item.strip() or len(item) > 120:
                _invalid("完成标准需要 3–6 条，每条最多 120 字")
            texts.append(item)
        plan["criteria"] = [
            {"id": f"C{index}", "text": text} for index, text in enumerate(texts, 1)]

    current_picks = _current_picks(plan)
    old_roles = {item["role"] for item in current_picks if isinstance(item.get("role"), str)}
    new_picks = None
    if body.picks is not None:
        new_picks = _parse_picks(body.picks, current_picks)
        plan["picks"] = new_picks
        current_roles = {item["role"] for item in new_picks}
    else:
        current_roles = old_roles
    removed_roles = old_roles - current_roles

    if body.identities is not None:
        incoming = _parse_identities(body.identities)
        identities = config_data.get("identities")
        identities = dict(identities) if isinstance(identities, dict) else {}
        for seat, entry in incoming.items():
            merged = identities.get(seat)
            merged = dict(merged) if isinstance(merged, dict) else {}
            merged.update(entry)
            identities[seat] = merged
        config_data["identities"] = identities
    if body.avatar is not None:
        config_data["avatar"] = bool(body.avatar)
    if body.answers is not None:
        if not isinstance(body.answers, str) or len(body.answers) > 1000:
            _invalid("补充回答最多 1000 字")
        config_data["answers"] = body.answers

    allowed = set(roles.CORE_ROLES) | {"avatar"} | current_roles
    models = config_data.get("models")
    models = dict(models) if isinstance(models, dict) else {}
    if body.models is not None:
        models.update(await _validate_models(username, body.models, allowed))
    for role in removed_roles:
        models.pop(role, None)
    config_data["models"] = models

    updates: dict = {
        "plan_json": _encoded(plan),
        "config_json": _encoded(config_data),
        "plan_revision": revision + 1,
    }
    if body.title is not None:
        updates["title"] = title
    if body.budget_strawberries is not None:
        if (not _is_int(body.budget_strawberries)
                or not 100 <= body.budget_strawberries <= 20000):
            _invalid("预算需要在 100–20000 颗之间")
        updates["budget_strawberries"] = body.budget_strawberries
    if body.max_rounds is not None:
        if not _is_int(body.max_rounds) or not 1 <= body.max_rounds <= 6:
            _invalid("轮数需要在 1–6 之间")
        updates["max_rounds"] = body.max_rounds

    async def operation(db):
        current = await discuss_store.get_group_on_connection(db, username, group_id)
        if current is None:
            await _rollback_fail(db, NOT_FOUND, 404)
        if current.get("status") != "awaiting_start":
            await _rollback_fail(db, "现在不能改方案")
        if int(current.get("plan_revision") or 0) != body.expected_revision:
            await _rollback_fail(db, REVISION_CONFLICT)
        await discuss_store.update_group_on_connection(
            db, username, group_id, **updates)
    await discuss_store.run_write(operation)
    return await detail(username, group_id)


async def start(username: str, group_id: str, body: StartGroup) -> dict:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    if group.get("status") != "awaiting_start":
        _fail("现在不能开工")
    if int(group.get("plan_revision") or 0) != body.expected_revision:
        _fail(REVISION_CONFLICT)

    async def operation(db):
        current = await discuss_store.get_group_on_connection(db, username, group_id)
        if current is None:
            await _rollback_fail(db, NOT_FOUND, 404)
        if current.get("status") != "awaiting_start":
            await _rollback_fail(db, "现在不能开工")
        if int(current.get("plan_revision") or 0) != body.expected_revision:
            await _rollback_fail(db, REVISION_CONFLICT)
        await discuss_store.update_group_on_connection(
            db, username, group_id, status="running", stop_reason=None, last_error=None)
        await discuss_store.consume_notes_start(db, username, group_id)
        async with db.execute(
            "SELECT 1 FROM discuss_groups WHERE username=? "
            "AND status IN ('planning','running') AND id<>? LIMIT 1",
            (username, group_id),
        ) as cursor:
            if await cursor.fetchone() is not None:
                await _rollback_fail(db, ACTIVE_GROUP)
    await discuss_store.run_write(operation)
    await billing.DiscussBilling(username, group_id).refund_reserved()
    await runner.start_group(group_id, username)
    return await detail(username, group_id)


async def add_note(username: str, group_id: str, body: NoteIn) -> dict:
    text = _trim(body.text)
    if not 1 <= len(text) <= 500:
        _invalid("插话需要 1–500 字")
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    if group.get("status") in ("closed", "failed"):
        _fail("讨论群已经结束")
    _check_crisis(text)
    try:
        message = await discuss_store.post_user_note(
            username, group_id, text, int(group.get("round") or 0))
    except ValueError as error:
        if str(error) == "too_many":
            _fail(TOO_MANY_NOTES)
        if str(error) == "closed":
            _fail("讨论群已经结束")
        raise
    if message is None:
        _fail(NOT_FOUND, 404)
    return {
        "id": message["id"],
        "round": message["round"],
        "sender": message["sender"],
        "sender_name": "你",
        "kind": message["kind"],
        "content": message["content"],
        "payload": message["payload"],
        "created_at": message["created_at"],
        "consumed": False,
    }


async def pause(username: str, group_id: str) -> dict:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    if group.get("status") not in ("planning", "running"):
        _fail("现在没有在跑，不用暂停")
    await runner.cancel_group(group_id, username)
    async def operation(db):
        current = await discuss_store.get_group_on_connection(db, username, group_id)
        if current is None:
            await _rollback_fail(db, NOT_FOUND, 404)
        if current.get("status") in ("planning", "running"):
            await discuss_store.update_group_on_connection(
                db, username, group_id, status="paused", stop_reason="user")
    await discuss_store.run_write(operation)
    return await detail(username, group_id)


async def resume(username: str, group_id: str, body: ResumeGroup) -> dict:
    if not _is_int(body.add_budget) or body.add_budget < 0:
        _invalid("追加预算不能是负数")
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    if group.get("status") not in ("paused", "failed"):
        _fail("现在不能继续")

    async def operation(db):
        current = await discuss_store.get_group_on_connection(db, username, group_id)
        if current is None:
            await _rollback_fail(db, NOT_FOUND, 404)
        if current.get("status") not in ("paused", "failed"):
            await _rollback_fail(db, "现在不能继续")
        budget = int(current.get("budget_strawberries") or 0) + body.add_budget
        if budget > 20000:
            await _rollback_fail(db, "预算最多 20000 颗", 422)
        if budget <= int(current.get("spent_strawberries") or 0):
            await _rollback_fail(db, BUDGET_EXHAUSTED)
        async with db.execute(
            "SELECT 1 FROM discuss_groups WHERE username=? "
            "AND status IN ('planning','running') AND id<>? LIMIT 1",
            (username, group_id),
        ) as cursor:
            if await cursor.fetchone() is not None:
                await _rollback_fail(db, ACTIVE_GROUP)
        status = "planning" if int(current.get("round") or 0) == 0 else "running"
        await discuss_store.update_group_on_connection(
            db, username, group_id,
            status=status, budget_strawberries=budget,
            stop_reason=None, last_error=None, run_token=None)
    await discuss_store.run_write(operation)
    await billing.DiscussBilling(username, group_id).refund_reserved()
    await runner.start_group(group_id, username)
    return await detail(username, group_id)


async def continue_group(username: str, group_id: str, body: ContinueGroup) -> dict:
    if not _is_int(body.add_rounds) or not 1 <= body.add_rounds <= 3:
        _invalid("追加轮数需要 1–3")
    if not _is_int(body.add_budget) or body.add_budget < 0:
        _invalid("追加预算不能是负数")
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    if group.get("status") not in ("awaiting_user", "done"):
        _fail("现在不能追加轮数")

    async def operation(db):
        current = await discuss_store.get_group_on_connection(db, username, group_id)
        if current is None:
            await _rollback_fail(db, NOT_FOUND, 404)
        if current.get("status") not in ("awaiting_user", "done"):
            await _rollback_fail(db, "现在不能追加轮数")
        config_data = copy.deepcopy(current.get("config") or {})
        if not isinstance(config_data, dict):
            config_data = {}
        if current.get("status") == "done":
            async with db.execute(
                "SELECT COUNT(*) FROM discuss_messages WHERE group_id=? AND username=? "
                "AND sender='user' AND kind='user' AND consumed_by IS NULL",
                (group_id, username),
            ) as cursor:
                unread = int((await cursor.fetchone())[0])
            if unread < 1:
                await _rollback_fail(db, REWORK_NEEDS_NOTE)
            revisions = config_data.get("revisions")
            revisions = [item for item in revisions if _is_int(item)] \
                if isinstance(revisions, list) else []
            if int(current.get("round") or 0) not in revisions:
                revisions.append(int(current.get("round") or 0))
            config_data["revisions"] = revisions
        max_rounds = int(current.get("max_rounds") or 0) + body.add_rounds
        if max_rounds > 10:
            await _rollback_fail(db, "总轮数最多 10 轮", 422)
        budget = int(current.get("budget_strawberries") or 0) + body.add_budget
        if budget > 20000:
            await _rollback_fail(db, "预算最多 20000 颗", 422)
        if budget <= int(current.get("spent_strawberries") or 0):
            await _rollback_fail(db, BUDGET_EXHAUSTED)
        async with db.execute(
            "SELECT 1 FROM discuss_groups WHERE username=? "
            "AND status IN ('planning','running') AND id<>? LIMIT 1",
            (username, group_id),
        ) as cursor:
            if await cursor.fetchone() is not None:
                await _rollback_fail(db, ACTIVE_GROUP)
        await discuss_store.update_group_on_connection(
            db, username, group_id,
            status="running", max_rounds=max_rounds, budget_strawberries=budget,
            config_json=_encoded(config_data),
            stop_reason=None, last_error=None, run_token=None)
    await discuss_store.run_write(operation)
    await billing.DiscussBilling(username, group_id).refund_reserved()
    await runner.start_group(group_id, username)
    return await detail(username, group_id)


async def accept(username: str, group_id: str) -> dict:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    if group.get("status") not in ("awaiting_user", "paused"):
        _fail("现在不能接受成果")
    if int(group.get("output_version") or 0) < 1:
        _fail("还没有成果可以接受")
    async def operation(db):
        current = await discuss_store.get_group_on_connection(db, username, group_id)
        if current is None:
            await _rollback_fail(db, NOT_FOUND, 404)
        if current.get("status") not in ("awaiting_user", "paused"):
            await _rollback_fail(db, "现在不能接受成果")
        if int(current.get("output_version") or 0) < 1:
            await _rollback_fail(db, "还没有成果可以接受")
        await discuss_store.update_group_on_connection(
            db, username, group_id, status="done", stop_reason="accepted_by_user")
    await discuss_store.run_write(operation)
    await billing.DiscussBilling(username, group_id).refund_reserved()
    return await detail(username, group_id)


async def close(username: str, group_id: str) -> dict:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    if group.get("status") in ("planning", "running"):
        _fail(CLOSE_RUNNING)
    if group.get("status") == "closed":
        await billing.DiscussBilling(username, group_id).refund_reserved()
        return await detail(username, group_id)
    async def operation(db):
        current = await discuss_store.get_group_on_connection(db, username, group_id)
        if current is None:
            await _rollback_fail(db, NOT_FOUND, 404)
        if current.get("status") in ("planning", "running"):
            await _rollback_fail(db, CLOSE_RUNNING)
        if current.get("status") != "closed":
            await discuss_store.update_group_on_connection(
                db, username, group_id, status="closed", stop_reason="user")
    await discuss_store.run_write(operation)
    await billing.DiscussBilling(username, group_id).refund_reserved()
    return await detail(username, group_id)


async def delete(username: str, group_id: str) -> dict:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    await runner.cancel_group(group_id, username)
    await discuss_store.delete_group(username, group_id)
    return {"deleted": True}


async def sources(username: str, group_id: str) -> list[dict]:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    rows = await discuss_store.list_sources(username, group_id)
    return [
        {"id": row["id"], "title": row["title"],
         "site_name": row["site_name"], "url": row["url"]}
        for row in rows
    ]


async def output(username: str, group_id: str, version=None) -> dict:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    result = await discuss_store.get_output(username, group_id, version)
    if result is None:
        _fail("成果不存在", 404)
    return {
        "version": int(result["version"]),
        "round": int(result["round"]),
        "content": result["content"],
        "passed": bool(result["passed"]),
        "verdict": result["verdict"],
        "created_at": result["created_at"],
    }


async def export(username: str, group_id: str) -> tuple[str, str]:
    group = await discuss_store.get_group(username, group_id)
    if group is None:
        _fail(NOT_FOUND, 404)
    result = await discuss_store.get_output(username, group_id)
    if result is None:
        _fail("成果不存在", 404)
    content = result["content"] if isinstance(result["content"], str) else ""
    referenced = schemas.refs_in(content)
    rows = await discuss_store.list_sources(username, group_id)
    rows = sorted(
        (row for row in rows if row["id"] in referenced),
        key=lambda row: int(row["sid"]),
    )
    lines = [
        f"- {row['id']} {row['title']}（{row['site_name']}）{row['url']}"
        for row in rows
    ]
    body = content + "\n\n## 来源\n\n" + "\n".join(lines)
    filename = _text(group.get("title")) or "讨论群成果"
    return body, filename + ".md"
