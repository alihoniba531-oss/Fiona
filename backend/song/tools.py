# -*- coding: utf-8 -*-
"""Claude 写歌工具：只在本地 SQLite 读写简报与歌词。

四个工具都不扣草莓、不调用火山接口。项目必须属于当前用户且绑定本轮
会话；任何校验失败都不会创建项目或写入新稿。工具返回的是给模型看的
纯文本，不包含用户名、会话 id、内部路径或密钥。
"""
from __future__ import annotations

from typing import Any

from song import lyrics_check, store
from song.volc_options import (
    GENRE_VALUES,
    INSTRUMENT_VALUES,
    KEY_VALUES,
    KMODE_VALUES,
    LANG_VALUES,
    MOOD_VALUES,
    SCENE_VALUES,
    TEMPO_VALUES,
    TIMBRE_VALUES,
)


SONG_MODE_PROMPT = "\n".join(
    (
        "【写歌模式】主人明确想写歌、改歌时才进入，否则照常聊天。",
        "1. 先简短了解：写给谁、什么场合、想要的情绪和曲风、大约多长；"
        "一次最多问三个问题，主人说「你定」就由你决定。",
        "2. 想清楚后调用 song_save_brief 保存创作简报和结构蓝图"
        "（段落、每段行数、每行字数范围、押韵格式），再调用 song_save_lyrics "
        "提交整首歌词。歌词只通过工具提交，回复正文里不要重复贴整首歌词，"
        "用一两句话说明你的构思和需要主人确认的地方。",
        "3. 工具会返回字数和押韵的自检结果。有「问题」时先自己修改再提交一次；"
        "只有「提醒」时可以在回复里说明取舍。",
        "4. 主人要改某一段时，只用 song_revise_section 改那一段，"
        "其他段落一个字也不要动。",
        "5. 不模仿任何真实歌手的嗓音或唱腔；不照抄已有歌曲的歌词，"
        "连续 8 个字以上相同就算照抄。",
        "6. 生成试听由主人在卡片上点按钮确认，你不能替主人生成，"
        "也不要说「已经开始生成」。",
    )
)

GENDER_VALUES: tuple[str, ...] = ("Female", "Male")

_OPTIONAL_TEXT_LIMITS = {
    "occasion": (60, "场合 occasion"),
    "recipient": (60, "写给谁 recipient"),
    "style_notes": (200, "风格备注 style_notes"),
}

_ARRAY_FIELDS = (
    ("genre", GENRE_VALUES, 3, "曲风"),
    ("genre_extra", GENRE_VALUES, 2, "补充曲风"),
    ("mood", MOOD_VALUES, 2, "情绪"),
    ("timbre", TIMBRE_VALUES, 3, "音色"),
    ("instrument", INSTRUMENT_VALUES, 5, "乐器"),
    ("scene", SCENE_VALUES, 3, "场景"),
)

_SCALAR_FIELDS = (
    ("key", KEY_VALUES, "调性"),
    ("kmode", KMODE_VALUES, "调式"),
    ("tempo", TEMPO_VALUES, "速度"),
)

_LANGUAGE_LABELS = {"Chinese": "普通话", "English": "英文", "Cantonese": "粤语"}


def _tool(name: str, description: str, properties: dict, required: list) -> dict:
    """与 ``services.claude_agent._tool`` 相同的 schema 形状。"""
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def _enum(values) -> dict:
    return {"type": "string", "enum": list(values)}


def _enum_array(values, maximum: int) -> dict:
    return {
        "type": "array",
        "items": {"type": "string", "enum": list(values)},
        "maxItems": maximum,
    }


_BRIEF_PROPERTIES = {
    "theme": {"type": "string", "description": "歌曲主题，最多 200 字"},
    "occasion": {"type": "string", "description": "场合，最多 60 字"},
    "recipient": {"type": "string", "description": "写给谁，最多 60 字"},
    "language": _enum(LANG_VALUES),
    "duration_seconds": {"type": "integer", "minimum": 30, "maximum": 240},
    "gender": _enum(GENDER_VALUES),
    "genre": _enum_array(GENRE_VALUES, 3),
    "genre_extra": _enum_array(GENRE_VALUES, 2),
    "mood": _enum_array(MOOD_VALUES, 2),
    "timbre": _enum_array(TIMBRE_VALUES, 3),
    "key": _enum(KEY_VALUES),
    "kmode": _enum(KMODE_VALUES),
    "tempo": _enum(TEMPO_VALUES),
    "instrument": _enum_array(INSTRUMENT_VALUES, 5),
    "scene": _enum_array(SCENE_VALUES, 3),
    "style_notes": {"type": "string", "description": "风格备注，最多 200 字，不传给火山"},
}

_STRUCTURE_ITEMS = {
    "type": "object",
    "properties": {
        "id": {"type": "string", "description": "段落 id，形如 s1"},
        "type": {"type": "string", "enum": list(lyrics_check.SECTION_TYPES)},
        "lines": {"type": "integer", "minimum": 0, "maximum": 12},
        "chars": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1, "maximum": 30},
            "minItems": 2,
            "maxItems": 2,
        },
        "rhyme": {"type": "string", "enum": list(lyrics_check.RHYME_FORMATS)},
    },
    "required": ["id", "type"],
}

SONG_TOOLS = [
    _tool(
        "song_save_brief",
        "保存或更新写歌项目的创作简报和结构蓝图。没有 project_id 时新建项目。"
        "只写本地数据，不扣草莓、不生成音乐。",
        {
            "project_id": {"type": "string", "description": "已有项目 id；新建时省略"},
            "title": {"type": "string", "description": "歌名，1–20 字"},
            "brief": {
                "type": "object",
                "properties": _BRIEF_PROPERTIES,
                "required": ["theme", "language", "duration_seconds"],
            },
            "structure": {
                "type": "array",
                "items": _STRUCTURE_ITEMS,
                "minItems": 1,
                "maxItems": 16,
            },
        },
        ["title", "brief", "structure"],
    ),
    _tool(
        "song_save_lyrics",
        "提交整首歌词。base_revision 必须是项目当前最新稿号（新项目为 0），"
        "服务端会做字数和押韵自检。",
        {
            "project_id": {"type": "string"},
            "base_revision": {"type": "integer", "minimum": 0},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "lines": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 12,
                        },
                    },
                    "required": ["id", "lines"],
                },
            },
        },
        ["project_id", "base_revision", "sections"],
    ),
    _tool(
        "song_revise_section",
        "只改一段歌词，其余段落原样保留；服务端会做字数和押韵自检。",
        {
            "project_id": {"type": "string"},
            "base_revision": {"type": "integer", "minimum": 0},
            "section_id": {"type": "string"},
            "lines": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 12,
            },
            "reason": {"type": "string", "description": "修改原因，最多 60 字"},
        },
        ["project_id", "base_revision", "section_id", "lines"],
    ),
    _tool(
        "song_get_status",
        "只读查看写歌项目的简报、结构、最新歌词与自检、最近生成状态。",
        {"project_id": {"type": "string"}},
        ["project_id"],
    ),
]

SONG_TOOL_NAMES = frozenset(tool["name"] for tool in SONG_TOOLS)

_NOT_FOUND = "找不到这个写歌项目"
_CONFLICT = "歌词已被更新，请先调用 song_get_status"


def _text(value: Any, limit: int, label: str, errors: list[str], *, required: bool = False) -> str | None:
    if value is None:
        if required:
            errors.append(f"{label}必填")
        return None
    if not isinstance(value, str):
        errors.append(f"{label}必须是文字")
        return None
    text = value.strip()
    if required and not text:
        errors.append(f"{label}不能为空")
        return None
    if len(text) > limit:
        errors.append(f"{label}最多 {limit} 字，当前 {len(text)} 字")
        return None
    return text


def _validate_brief(brief: Any) -> tuple[dict | None, list[str]]:
    if not isinstance(brief, dict):
        return None, ["brief 必须是对象"]

    errors: list[str] = []
    normalized: dict[str, Any] = {}

    theme = _text(brief.get("theme"), 200, "主题 theme", errors, required=True)
    if theme is not None:
        normalized["theme"] = theme

    language = brief.get("language")
    if not isinstance(language, str) or language not in LANG_VALUES:
        errors.append("语言 language 必须是 " + " / ".join(LANG_VALUES) + " 之一")
    else:
        normalized["language"] = language

    duration = brief.get("duration_seconds")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 30 <= duration <= 240:
        errors.append("时长 duration_seconds 必须是 30–240 的整数")
    else:
        normalized["duration_seconds"] = duration

    for field, (limit, label) in _OPTIONAL_TEXT_LIMITS.items():
        value = _text(brief.get(field), limit, label, errors)
        if value:
            normalized[field] = value

    gender = brief.get("gender")
    if gender is not None:
        if not isinstance(gender, str) or gender not in GENDER_VALUES:
            errors.append("性别 gender 必须是 Female / Male 之一")
        else:
            normalized["gender"] = gender

    for field, allowed, maximum, label in _ARRAY_FIELDS:
        value = brief.get(field)
        if value is None:
            continue
        if not isinstance(value, list):
            errors.append(f"{label} {field} 必须是数组，最多 {maximum} 个")
            continue
        if len(value) > maximum:
            errors.append(f"{label} {field} 最多 {maximum} 个，当前 {len(value)} 个")
            continue
        items: list[str] = []
        for item in value:
            if not isinstance(item, str) or item not in allowed:
                errors.append(f"{label} {field} 包含不支持的值，请从工具给出的枚举中选择")
                break
            items.append(item)
        else:
            if items:
                normalized[field] = items

    for field, allowed, label in _SCALAR_FIELDS:
        value = brief.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or value not in allowed:
            errors.append(f"{label} {field} 不在允许的取值里")
        else:
            normalized[field] = value

    return normalized, errors


def _validate_structure(structure: Any) -> list[str]:
    issues = lyrics_check.structure_errors(structure)
    return [f"结构蓝图：{issue.get('message') or issue.get('code')}" for issue in issues]


def _join(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return "、".join(str(item) for item in value if item)
    return str(value) if value else ""


def _brief_summary(brief: dict) -> str:
    parts: list[str] = []
    if brief.get("theme"):
        parts.append(f"主题：{brief['theme']}")
    if brief.get("occasion"):
        parts.append(f"场合：{brief['occasion']}")
    if brief.get("recipient"):
        parts.append(f"写给：{brief['recipient']}")
    if brief.get("language"):
        parts.append(f"语言：{_LANGUAGE_LABELS.get(brief['language'], brief['language'])}")
    if brief.get("duration_seconds") is not None:
        parts.append(f"时长：{brief['duration_seconds']} 秒")
    for field, label in (
        ("genre", "曲风"),
        ("genre_extra", "补充曲风"),
        ("mood", "情绪"),
        ("timbre", "音色"),
        ("key", "调性"),
        ("kmode", "调式"),
        ("tempo", "速度"),
        ("instrument", "乐器"),
        ("scene", "场景"),
        ("gender", "人声"),
        ("style_notes", "风格备注"),
    ):
        value = _join(brief.get(field))
        if value:
            parts.append(f"{label}：{value}")
    return "；".join(parts) if parts else "（还没有简报）"


def _check_summary(check: Any) -> str:
    if not isinstance(check, dict):
        return "自检：还没有自检结果。"
    errors = check.get("errors") if isinstance(check.get("errors"), list) else []
    warnings = check.get("warnings") if isinstance(check.get("warnings"), list) else []
    if not errors and not warnings:
        return "自检：通过，没有问题和提醒。"
    lines = [f"自检：{len(errors)} 个问题、{len(warnings)} 条提醒。"]
    lines.extend(f"- 问题：{item.get('message', '')}" for item in errors if isinstance(item, dict))
    lines.extend(f"- 提醒：{item.get('message', '')}" for item in warnings if isinstance(item, dict))
    return "\n".join(lines)


def _section_label(section_type: Any) -> str:
    if isinstance(section_type, str):
        return lyrics_check.SECTION_TYPE_LABELS.get(section_type, section_type)
    return "段落"


def _format_lyrics(structure: Any, sections: Any) -> str:
    blueprints = structure if isinstance(structure, list) else []
    by_id = {
        section.get("id"): section
        for section in sections
        if isinstance(section, dict) and isinstance(section.get("id"), str)
    }
    lines: list[str] = []
    if blueprints:
        for blueprint in blueprints:
            if not isinstance(blueprint, dict):
                continue
            section_id = blueprint.get("id")
            section_type = blueprint.get("type")
            lines.append(f"[{_section_label(section_type)} {section_id}]")
            if section_type in lyrics_check.INSTRUMENTAL_TYPES:
                lines.append("（器乐）")
                continue
            section = by_id.get(section_id, {})
            for line in section.get("lines") or []:
                if isinstance(line, str):
                    lines.append(line)
        return "\n".join(lines)
    for section in sections:
        if not isinstance(section, dict):
            continue
        lines.append(f"[{_section_label(section.get('type'))} {section.get('id')}]")
        for line in section.get("lines") or []:
            if isinstance(line, str):
                lines.append(line)
    return "\n".join(lines)


def _versions_summary(versions: list[dict]) -> str:
    if not versions:
        return "最近版本：还没有生成。"
    lines = ["最近版本："]
    for version in versions[:3]:
        parts = [
            f"第 {version.get('lyrics_revision')} 稿",
            str(version.get("status") or "unknown"),
        ]
        if version.get("progress") is not None and version.get("status") in {
            "queued", "submitting", "submitted", "running", "downloading",
        }:
            parts.append(f"进度 {version.get('progress')}%")
        if version.get("duration_s") is not None:
            parts.append(f"{version.get('duration_s')} 秒")
        if version.get("failure_message"):
            parts.append(str(version.get("failure_message")))
        lines.append("- " + " · ".join(parts))
    return "\n".join(lines)


def _normalize_sections(sections: Any, structure: Any) -> list[dict]:
    type_by_id = {
        section.get("id"): section.get("type")
        for section in (structure if isinstance(structure, list) else [])
        if isinstance(section, dict)
    }
    normalized: list[dict] = []
    for section in sections if isinstance(sections, list) else []:
        if not isinstance(section, dict):
            normalized.append({"id": None, "type": None, "lines": []})
            continue
        section_id = section.get("id")
        raw_lines = section.get("lines")
        lines = (
            [line if isinstance(line, str) else "" for line in raw_lines]
            if isinstance(raw_lines, list)
            else []
        )
        normalized.append({
            "id": section_id,
            "type": type_by_id.get(section_id),
            "lines": lines,
        })
    return normalized


def _language(project: dict) -> str:
    brief = project.get("brief") if isinstance(project.get("brief"), dict) else {}
    language = brief.get("language")
    return language if language in LANG_VALUES else "Chinese"


async def _owned_project(ctx, conversation_id: Any, project_id: Any) -> dict | None:
    if not isinstance(project_id, str) or not project_id:
        return None
    return await store.get_project(
        project_id,
        owner_username=ctx.user,
        conversation_id=conversation_id,
    )


def _valid_conversation(conversation_id: Any) -> bool:
    return isinstance(conversation_id, str) and bool(conversation_id)


async def _save_brief(args: dict, ctx, conversation_id: str, context: dict) -> str:
    errors: list[str] = []
    title = _text(args.get("title"), 20, "标题 title", errors, required=True)
    brief, brief_errors = _validate_brief(args.get("brief"))
    errors.extend(brief_errors)
    errors.extend(_validate_structure(args.get("structure")))
    if errors:
        return "创作简报没有保存：\n" + "\n".join(f"- {message}" for message in errors)

    structure = args.get("structure")
    project_id = args.get("project_id")
    if project_id is None or project_id == "":
        project = await store.create_project(
            owner_username=ctx.user,
            conversation_id=conversation_id,
            title=title,
            brief=brief,
            structure=structure,
        )
        if project is None:
            return _NOT_FOUND
        action = "已创建写歌项目"
    else:
        project = await store.update_project(
            project_id,
            owner_username=ctx.user,
            conversation_id=conversation_id,
            title=title,
            brief=brief,
            structure=structure,
        )
        if project is None:
            return _NOT_FOUND
        action = "已更新写歌项目"

    context["project_id"] = project["id"]
    summary = lyrics_check.summarize_structure(project.get("structure"))
    lines = [
        f"{action}（id={project['id']}）。",
        f"标题：《{project.get('title') or title}》",
        f"结构：{summary}",
    ]
    if project.get("lyrics_revision"):
        lines.extend(await _recheck_lyrics_after_brief(project, ctx, conversation_id))
    lines.append("下一步：按这个结构写歌词并调用 song_save_lyrics 提交。")
    return "\n".join(lines)


async def _recheck_lyrics_after_brief(project: dict, ctx, conversation_id: str) -> list[str]:
    """结构或语言更新后，用最新一稿的旧段落重跑自检并另存一稿。

    旧段落按原列表保留（不按新结构裁剪），结构 id 对不上时由
    ``check_lyrics`` 给出 ``structure_mismatch``，新稿因此不可生成。
    保存失败只追加提示，不回滚已经成功的简报更新。
    """
    failure = "简报已更新，但歌词重检没有保存，请调用 song_get_status 查看。"
    try:
        latest = await store.get_lyrics(project["id"])
        if latest is None:
            return [failure]
        sections = latest.get("sections") or []
        check = lyrics_check.check_lyrics(
            project.get("structure"),
            sections,
            _language(project),
        )
        saved = await store.save_lyrics(
            project["id"],
            owner_username=ctx.user,
            conversation_id=conversation_id,
            base_revision=latest["revision"],
            sections=sections,
            check=check,
            changed_section_ids=[],
        )
    except Exception:
        return [failure]

    if saved.get("status") == "conflict":
        return ["简报已更新，但歌词重检没有保存：歌词已被更新，请先调用 song_get_status。"]
    if saved.get("status") != "ok":
        return [failure]
    revision = saved["project"]["lyrics_revision"]
    return [f"已按新结构重检第 {revision} 稿。", _check_summary(check)]


async def _save_lyrics(args: dict, ctx, conversation_id: str, context: dict) -> str:
    project = await _owned_project(ctx, conversation_id, args.get("project_id"))
    if project is None:
        return _NOT_FOUND

    base_revision = args.get("base_revision")
    if isinstance(base_revision, bool) or not isinstance(base_revision, int) or base_revision < 0:
        return "base_revision 必须是项目当前最新稿号（新项目为 0）。"
    if base_revision != project["lyrics_revision"]:
        return _CONFLICT

    sections = args.get("sections")
    if not isinstance(sections, list):
        return "歌词没有保存：sections 必须是数组。"

    normalized = _normalize_sections(sections, project.get("structure"))
    check = lyrics_check.check_lyrics(project.get("structure"), normalized, _language(project))
    saved = await store.save_lyrics(
        project["id"],
        owner_username=ctx.user,
        conversation_id=conversation_id,
        base_revision=base_revision,
        sections=normalized,
        check=check,
        changed_section_ids=[],
    )
    if saved.get("status") == "not_found":
        return _NOT_FOUND
    if saved.get("status") == "conflict":
        return _CONFLICT

    revision = saved["project"]["lyrics_revision"]
    context["project_id"] = project["id"]
    return f"已保存第 {revision} 稿。\n" + _check_summary(check)


async def _revise_section(args: dict, ctx, conversation_id: str, context: dict) -> str:
    project = await _owned_project(ctx, conversation_id, args.get("project_id"))
    if project is None:
        return _NOT_FOUND

    base_revision = args.get("base_revision")
    if isinstance(base_revision, bool) or not isinstance(base_revision, int) or base_revision < 0:
        return "base_revision 必须是这一稿的稿号。"
    if base_revision != project["lyrics_revision"]:
        return _CONFLICT

    section_id = args.get("section_id")
    if not isinstance(section_id, str) or not section_id:
        return "section_id 必须是结构蓝图里的段落 id。"

    reason = args.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason.strip()) > 60):
        return "修改原因 reason 最多 60 字。"

    lines = args.get("lines")
    if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
        return "lines 必须是字符串数组。"

    structure_ids = {
        section.get("id")
        for section in (project.get("structure") if isinstance(project.get("structure"), list) else [])
        if isinstance(section, dict)
    }
    if section_id not in structure_ids:
        return f"结构蓝图里没有段落「{section_id}」，请先调用 song_get_status。"

    base_lyrics = await store.get_lyrics(project["id"], base_revision)
    if base_lyrics is None:
        return f"找不到第 {base_revision} 稿歌词，请先调用 song_get_status。"

    sections = [
        dict(section) if isinstance(section, dict) else {"id": None, "type": None, "lines": []}
        for section in (base_lyrics.get("sections") or [])
    ]
    target = next(
        (section for section in sections if section.get("id") == section_id),
        None,
    )
    if target is None:
        return f"第 {base_revision} 稿里没有段落「{section_id}」，请先调用 song_get_status。"

    old_lines = list(target.get("lines") or [])
    target["lines"] = list(lines)
    check = lyrics_check.check_lyrics(project.get("structure"), sections, _language(project))
    saved = await store.save_lyrics(
        project["id"],
        owner_username=ctx.user,
        conversation_id=conversation_id,
        base_revision=base_revision,
        sections=sections,
        check=check,
        changed_section_ids=[section_id],
    )
    if saved.get("status") == "not_found":
        return _NOT_FOUND
    if saved.get("status") == "conflict":
        return _CONFLICT

    revision = saved["project"]["lyrics_revision"]
    context["project_id"] = project["id"]
    old_text = "\n".join(old_lines) if old_lines else "（空）"
    new_text = "\n".join(lines) if lines else "（空）"
    return "\n".join(
        (
            f"已保存第 {revision} 稿（只修改了 {_section_label(target.get('type'))} {section_id}）。",
            "【修改前】",
            old_text,
            "【修改后】",
            new_text,
            _check_summary(check),
        )
    )


async def _get_status(args: dict, ctx, conversation_id: str, context: dict) -> str:
    project = await _owned_project(ctx, conversation_id, args.get("project_id"))
    if project is None:
        return _NOT_FOUND

    lyrics = await store.get_lyrics(project["id"])
    versions = await store.list_versions(project["id"], limit=3)
    section_summary = lyrics_check.summarize_structure(project.get("structure"))
    lines = [
        f"写歌项目 id：{project['id']}",
        f"标题：《{project.get('title') or '未命名'}》",
        _brief_summary(project.get("brief") if isinstance(project.get("brief"), dict) else {}),
        f"结构：{section_summary}",
    ]
    if lyrics:
        lines.append(f"最新稿号：第 {lyrics.get('revision')} 稿")
        lines.append("歌词：")
        lines.append(_format_lyrics(project.get("structure"), lyrics.get("sections") or []))
        lines.append(_check_summary(lyrics.get("check")))
    else:
        lines.append("最新稿号：第 0 稿（还没有歌词）")
        lines.append("自检：还没有歌词。")
    lines.append(_versions_summary(versions))
    context["project_id"] = project["id"]
    return "\n".join(lines)


async def execute(
    name: str,
    args: dict,
    *,
    ctx,
    conversation_id: str,
    context: dict | None = None,
) -> str:
    """执行一个写歌工具；成功时把项目 id 写进 ``context``。"""
    if context is None:
        context = {}
    if not isinstance(args, dict):
        args = {}
    if not _valid_conversation(conversation_id):
        return _NOT_FOUND
    if name == "song_save_brief":
        return await _save_brief(args, ctx, conversation_id, context)
    if name == "song_save_lyrics":
        return await _save_lyrics(args, ctx, conversation_id, context)
    if name == "song_revise_section":
        return await _revise_section(args, ctx, conversation_id, context)
    if name == "song_get_status":
        return await _get_status(args, ctx, conversation_id, context)
    return "未知的写歌工具。"


async def card_for_project(project_id: str, *, ctx, conversation_id: str) -> dict | None:
    """写歌卡片；项目不存在、不属于当前用户或不属于本会话时返回 None。"""
    project = await _owned_project(ctx, conversation_id, project_id)
    if project is None:
        return None
    title = project.get("title") or "未命名"
    revision = project.get("lyrics_revision") or 0
    return {
        "type": "card",
        "subtype": "song_project",
        "source": "写歌",
        "points": [f"《{title}》第 {revision} 稿"],
        "project_id": project["id"],
        "error": False,
    }
