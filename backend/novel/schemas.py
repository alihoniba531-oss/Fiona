"""Pure JSON parsing and field-by-field validation for the novel workshop.

No validator mutates its input.  Error messages name fields, never echo model
responses, so callers can safely feed the error list back for one correction.
"""

from __future__ import annotations

from copy import deepcopy
import json
import re
from typing import Any, Iterable


class ValidationError(ValueError):
    """A collection of Chinese, response-independent validation errors."""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("；".join(self.errors))


def compact(text: str) -> str:
    """Use the same whitespace, quotation and ellipsis rules on both texts."""
    text = re.sub(r'''[\s“”‘’「」『』"']+''', "", text)
    return re.sub(r"(?:…+|\.{3,})+", "…", text)


_OPTIONAL_TEXT_FIELDS = frozenset({
    "age", "appearance", "personality", "motivation", "location", "condition",
    "conflict", "ending_hook", "risks", "closing_reason", "comment",
    "merge_note", "fix", "note", "problem", "alternative",
})


def _normalized_copy(data: Any) -> Any:
    """Copy before accepting harmless model variations; keep typed checks below."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key == "age" and type(value) is int:
                result[key] = str(value)
            elif value is None and key in _OPTIONAL_TEXT_FIELDS:
                result[key] = ""
            else:
                result[key] = _normalized_copy(value)
        return result
    if isinstance(data, list):
        return [_normalized_copy(value) for value in data]
    return deepcopy(data)


def parse_json(text: str) -> dict:
    if not isinstance(text, str):
        raise ValidationError(["模型响应必须是文本"])

    def invalid_constant(_value):
        raise ValueError("非有限数字")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("重复字段")
            result[key] = value
        return result

    source = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", source, re.IGNORECASE)
    if fence:
        source = fence.group(1)
    options = {"parse_constant": invalid_constant, "object_pairs_hook": unique_object}
    # A complete JSON array/scalar is a schema error; do not accidentally
    # extract one object out of an otherwise valid array.
    try:
        value = json.loads(source, **options)
    except (ValueError, TypeError):
        pass
    else:
        if not isinstance(value, dict):
            raise ValidationError(["JSON 顶层必须是对象"])
        return value
    start, end = source.find("{"), source.rfind("}")
    if start < 0 or end < start:
        raise ValidationError(["响应中没有完整的 JSON 对象"])
    try:
        value = json.loads(source[start : end + 1], **options)
    except (ValueError, TypeError):
        raise ValidationError(["JSON 解析失败，请返回一个合法的 JSON 对象"]) from None
    if not isinstance(value, dict):
        raise ValidationError(["JSON 顶层必须是对象"])
    return value


class _Check:
    def __init__(self):
        self.errors: list[str] = []

    def fail(self, path: str, message: str):
        self.errors.append(f"{path}：{message}")

    def obj(self, value: Any, path: str, fields: Iterable[str] = ()) -> dict:
        if not isinstance(value, dict):
            self.fail(path, "必须是对象")
            return {}
        for field in fields:
            if field not in value:
                self.fail(f"{path}.{field}", "缺少字段")
        return value

    def array(self, value: Any, path: str, minimum=0, maximum=None) -> list:
        if not isinstance(value, list):
            self.fail(path, "必须是列表")
            return []
        if len(value) < minimum or (maximum is not None and len(value) > maximum):
            bound = f"{minimum}–{maximum}" if maximum is not None else f"至少 {minimum}"
            self.fail(path, f"条目数须为 {bound}")
        return value

    def text(self, value: Any, path: str, minimum=0, maximum=None) -> bool:
        if not isinstance(value, str):
            self.fail(path, "必须是字符串")
            return False
        size = len(compact(value))
        if size < minimum or (maximum is not None and size > maximum):
            self.fail(path, f"非空白字数须为 {minimum}–{maximum if maximum is not None else '不限'}")
            return False
        return True

    def boolean(self, value: Any, path: str) -> bool:
        if type(value) is not bool:
            self.fail(path, "必须是布尔值")
            return False
        return True

    def integer(self, value: Any, path: str, minimum=None, maximum=None) -> bool:
        if type(value) is not int:
            self.fail(path, "必须是整数（不能是布尔值）")
            return False
        if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
            self.fail(path, f"须在 {minimum if minimum is not None else '不限'}–{maximum if maximum is not None else '不限'} 之间")
            return False
        return True

    def enum(self, value: Any, path: str, choices: Iterable[str]):
        if not isinstance(value, str) or value not in choices:
            self.fail(path, "必须是允许的枚举值：" + "、".join(choices))

    def strings(self, value: Any, path: str, minimum=0, maximum=None, nonempty=False) -> list:
        items = self.array(value, path, minimum, maximum)
        for i, item in enumerate(items):
            self.text(item, f"{path}[{i}]", minimum=1 if nonempty else 0)
        return items

    def refs(self, value: Any, path: str, allowed: set[str], minimum=0) -> list:
        items = self.strings(value, path, minimum, nonempty=True)
        for i, item in enumerate(items):
            if isinstance(item, str) and item not in allowed:
                self.fail(f"{path}[{i}]", "引用的 ID 不存在或不在本次允许范围内")
        if len([x for x in items if isinstance(x, str)]) != len(set(x for x in items if isinstance(x, str))):
            self.fail(path, "ID 不得重复")
        return items

    def finish(self, data):
        if self.errors:
            raise ValidationError(self.errors)
        return deepcopy(data)


def _ids(items) -> set[str]:
    return {item["id"] for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)}


def _character(c: _Check, value: Any, path: str, *, initial=False, new=False,
               require_new_appearance=False):
    fields = ["name", "role", "age", "appearance", "personality", "motivation"]
    if initial:
        fields.append("initial_state")
    item = c.obj(value, path, fields)
    for field in ("name", "age", "personality", "motivation"):
        c.text(item.get(field), f"{path}.{field}", minimum=1 if field == "name" else 0)
    c.text(item.get("appearance"), f"{path}.appearance",
           minimum=20 if initial or (new and require_new_appearance) else 0)
    c.enum(item.get("role"), f"{path}.role", ("supporting",) if new else ("main", "supporting"))
    if initial:
        state = c.obj(item.get("initial_state"), f"{path}.initial_state", ("location", "condition", "knows"))
        for field in ("location", "condition"):
            c.text(state.get(field), f"{path}.initial_state.{field}")
        c.strings(state.get("knows"), f"{path}.initial_state.knows")


def _foreshadowing(c: _Check, value: Any, path: str):
    item = c.obj(value, path, ("description", "importance"))
    c.text(item.get("description"), f"{path}.description", minimum=1)
    c.enum(item.get("importance"), f"{path}.importance", ("major", "minor"))


def _genre_contract(c: _Check, data: Any, main_threads) -> dict:
    path = "genre_contract"
    root = c.obj(data, path, ("genre", "reader_promise", "core_thread", "core_payoffs",
                              "payoff_every_chapters", "progression_ladder", "drift_warnings"))
    for field in ("genre", "reader_promise"):
        c.text(root.get(field), f"{path}.{field}", minimum=1)
    allowed = {item.get("id", f"T{i}") for i, item in enumerate(main_threads, 1)
               if isinstance(item, dict) and isinstance(item.get("id", f"T{i}"), str)}
    c.text(root.get("core_thread"), f"{path}.core_thread", minimum=1)
    if not isinstance(root.get("core_thread"), str) or root["core_thread"] not in allowed:
        c.fail(f"{path}.core_thread", "必须引用 main_threads 中存在的主线 ID")
    c.strings(root.get("core_payoffs"), f"{path}.core_payoffs", 3, 8, nonempty=True)
    c.integer(root.get("payoff_every_chapters"), f"{path}.payoff_every_chapters", 1, 5)
    c.strings(root.get("progression_ladder"), f"{path}.progression_ladder", 3, 12, nonempty=True)
    c.strings(root.get("drift_warnings"), f"{path}.drift_warnings", 0, 5, nonempty=True)
    return root


def validate_genre_contract(data: Any, main_threads) -> dict:
    """Validate assigned compass IDs or setup's ordered, code-owned IDs."""
    data = _normalized_copy(data)
    c = _Check()
    _genre_contract(c, data, main_threads)
    return c.finish(data)


def validate_volume_plan(data: Any, *, compass: dict, bible: dict, volume: int,
                         start_chapter: int, end_chapter: int) -> dict:
    data = _normalized_copy(data)
    c = _Check()
    root = c.obj(data, "volume_plan", ("volume", "chapters", "goal", "milestones",
                                      "payoff_plan", "threads_focus", "foreshadowing_to_resolve",
                                      "new_mystery_budget"))
    if c.integer(root.get("volume"), "volume_plan.volume", 1) and root["volume"] != volume:
        c.fail("volume_plan.volume", f"必须为本次卷号 {volume}")
    bounds = c.array(root.get("chapters"), "volume_plan.chapters", 2, 2)
    for i, number in enumerate(bounds):
        c.integer(number, f"volume_plan.chapters[{i}]", 1)
    if bounds != [start_chapter, end_chapter]:
        c.fail("volume_plan.chapters", f"必须为本卷范围 [{start_chapter}, {end_chapter}]")
    c.text(root.get("goal"), "volume_plan.goal", minimum=1)
    thread_ids = _ids(compass["main_threads"])
    contract = compass["genre_contract"]
    milestones = c.array(root.get("milestones"), "volume_plan.milestones", 2, 5)
    identifiers = []
    has_core = False
    for i, milestone in enumerate(milestones):
        path = f"volume_plan.milestones[{i}]"
        item = c.obj(milestone, path, ("id", "thread", "description", "due_chapter"))
        c.text(item.get("id"), f"{path}.id", minimum=1)
        identifiers.append(item.get("id"))
        c.text(item.get("description"), f"{path}.description", minimum=1)
        c.text(item.get("thread"), f"{path}.thread", minimum=1)
        if not isinstance(item.get("thread"), str) or item["thread"] not in thread_ids:
            c.fail(f"{path}.thread", "必须引用存在的主线 ID")
        has_core |= item.get("thread") == contract["core_thread"]
        c.integer(item.get("due_chapter"), f"{path}.due_chapter", start_chapter, end_chapter)
        if "status" in item:
            c.enum(item["status"], f"{path}.status", ("open", "done", "missed"))
    if len(identifiers) != len(set(key for key in identifiers if isinstance(key, str))):
        c.fail("volume_plan.milestones", "里程碑 ID 不得重复")
    if not has_core:
        c.fail("volume_plan.milestones", "至少 1 条里程碑必须属于核心主线")
    period = contract["payoff_every_chapters"]
    minimum = (end_chapter - start_chapter + period) // period
    payoffs = c.array(root.get("payoff_plan"), "volume_plan.payoff_plan", minimum)
    if len(payoffs) < minimum:
        c.fail("volume_plan.payoff_plan", f"本卷 {end_chapter - start_chapter + 1} 章、爽点间隔 {period} 章，至少需要 {minimum} 条，实际 {len(payoffs)} 条")
    for i, payoff in enumerate(payoffs):
        path = f"volume_plan.payoff_plan[{i}]"
        item = c.obj(payoff, path, ("chapter_hint", "type"))
        c.integer(item.get("chapter_hint"), f"{path}.chapter_hint", start_chapter, end_chapter)
        c.enum(item.get("type"), f"{path}.type", contract["core_payoffs"])
    c.refs(root.get("threads_focus"), "volume_plan.threads_focus", thread_ids)
    open_ids = {item["id"] for item in bible["dynamic"]["foreshadowing"] if item["status"] == "open"}
    c.refs(root.get("foreshadowing_to_resolve"), "volume_plan.foreshadowing_to_resolve", open_ids)
    c.integer(root.get("new_mystery_budget"), "volume_plan.new_mystery_budget", 0, 6)
    return c.finish(data)


def validate_setup(data: Any, config: dict) -> dict:
    data = _normalized_copy(data)
    c = _Check()
    root = c.obj(data, "setup", ("title", "logline", "theme", "core_conflict", "protagonist",
                               "candidate_endings", "main_threads", "characters", "world_rules",
                               "style_guide", "initial_foreshadowing"))
    for field in ("title", "logline", "theme", "core_conflict"):
        c.text(root.get(field), f"setup.{field}", minimum=1)
    protagonist = c.obj(root.get("protagonist"), "setup.protagonist", ("name", "want", "need"))
    for field in ("name", "want", "need"):
        c.text(protagonist.get(field), f"setup.protagonist.{field}", minimum=1)
    for i, ending in enumerate(c.array(root.get("candidate_endings"), "setup.candidate_endings", 2, 3)):
        item = c.obj(ending, f"setup.candidate_endings[{i}]", ("summary",))
        c.text(item.get("summary"), f"setup.candidate_endings[{i}].summary", minimum=1)
    for i, thread in enumerate(c.array(root.get("main_threads"), "setup.main_threads", 1, 4)):
        item = c.obj(thread, f"setup.main_threads[{i}]", ("name", "description"))
        for field in ("name", "description"):
            c.text(item.get(field), f"setup.main_threads[{i}].{field}", minimum=1)
    characters = c.array(root.get("characters"), "setup.characters", 1, 12)
    for i, character in enumerate(characters):
        _character(c, character, f"setup.characters[{i}]", initial=True)
    maximum_main = config.get("adaptation", {}).get("max_main_characters", 6)
    if type(maximum_main) is not int or maximum_main < 1:
        c.fail("config.adaptation.max_main_characters", "必须是正整数")
    elif sum(isinstance(char, dict) and char.get("role") == "main" for char in characters) > maximum_main:
        c.fail("setup.characters", "主要人物数量超过配置上限")
    c.strings(root.get("world_rules"), "setup.world_rules", nonempty=True)
    style = c.obj(root.get("style_guide"), "setup.style_guide", ("pov", "tense", "voice", "banned_phrases"))
    for field in ("pov", "tense", "voice"):
        c.text(style.get(field), f"setup.style_guide.{field}", minimum=1)
    c.strings(style.get("banned_phrases"), "setup.style_guide.banned_phrases", minimum=5, nonempty=True)
    for i, foreshadow in enumerate(c.array(root.get("initial_foreshadowing"), "setup.initial_foreshadowing")):
        _foreshadowing(c, foreshadow, f"setup.initial_foreshadowing[{i}]")
    if config.get("structure") == "v2":
        threads = root.get("main_threads", [])
        _genre_contract(c, root.get("genre_contract"),
                        [{"id": f"T{i}"} for i, _ in enumerate(threads, 1)]
                        if isinstance(threads, list) else [])
    return c.finish(data)


def validate_proposals(data: Any, compass: dict, bible: dict) -> dict:
    data = _normalized_copy(data)
    c = _Check()
    root = c.obj(data, "proposals", ("proposals",))
    for i, proposal in enumerate(c.array(root.get("proposals"), "proposals.proposals", 1, 2)):
        path = f"proposals.proposals[{i}]"
        item = c.obj(proposal, path, ("direction", "advances_threads", "conflict", "ending_hook", "characters", "risks", "suggest_closing", "closing_reason"))
        for field in ("direction", "conflict", "ending_hook", "risks", "closing_reason"):
            c.text(item.get(field), f"{path}.{field}", minimum=1 if field == "direction" else 0)
        c.refs(item.get("advances_threads"), f"{path}.advances_threads", _ids(compass["main_threads"]), 1)
        c.refs(item.get("characters"), f"{path}.characters", _ids(bible["locked"]["characters"]))
        c.boolean(item.get("suggest_closing"), f"{path}.suggest_closing")
        if item.get("suggest_closing") is True:
            c.text(item.get("closing_reason"), f"{path}.closing_reason", minimum=1)
    return c.finish(data)


def validate_critique(data: Any, proposal_ids: Iterable[str]) -> dict:
    data = _normalized_copy(data)
    c = _Check()
    allowed = set(proposal_ids)
    root = c.obj(data, "critique", ("scores", "strongest_objection"))
    scored = []
    for i, score in enumerate(c.array(root.get("scores"), "critique.scores")):
        path = f"critique.scores[{i}]"
        item = c.obj(score, path, ("proposal_id", "logic", "character", "appeal", "compass_fit", "filmability", "comment"))
        c.text(item.get("proposal_id"), f"{path}.proposal_id", minimum=1)
        scored.append(item.get("proposal_id"))
        for field in ("logic", "character", "appeal", "compass_fit", "filmability"):
            c.integer(item.get(field), f"{path}.{field}", 1, 5)
        c.text(item.get("comment"), f"{path}.comment")
    if len(scored) != len(allowed) or any(scored.count(pid) != 1 for pid in allowed) or any(not isinstance(pid, str) or pid not in allowed for pid in scored):
        c.fail("critique.scores", "本次下发的每条提案必须恰好评分一次，且不得评分其他提案")
    objection = c.obj(root.get("strongest_objection"), "critique.strongest_objection", ("proposal_id", "objection"))
    c.text(objection.get("proposal_id"), "critique.strongest_objection.proposal_id", minimum=1)
    if not isinstance(objection.get("proposal_id"), str) or objection["proposal_id"] not in allowed:
        c.fail("critique.strongest_objection.proposal_id", "必须是本次下发的提案 ID")
    c.text(objection.get("objection"), "critique.strongest_objection.objection", minimum=1)
    return c.finish(data)


def validate_critique_plan(data: Any, role: str) -> dict:
    """Validate actionable comments on an editor's plan without voting."""
    data = _normalized_copy(data)
    c = _Check()
    root = c.obj(data, "critique_plan", ("objections", "keep"))
    for i, objection in enumerate(c.array(root.get("objections"),
                                         "critique_plan.objections", 1, 3)):
        path = f"critique_plan.objections[{i}]"
        item = c.obj(objection, path, ("severity", "target", "problem", "suggestion"))
        c.enum(item.get("severity"), f"{path}.severity", ("major", "minor"))
        for field in ("target", "problem", "suggestion"):
            c.text(item.get(field), f"{path}.{field}", minimum=1)
    c.text(root.get("keep"), "critique_plan.keep", minimum=1)
    if role == "twist_designer" or "alternative" in root:
        c.text(root.get("alternative"), "critique_plan.alternative",
               minimum=1 if role == "twist_designer" else 0)
    return c.finish(data)


def _response_id_errors(c: _Check, seen: list, allowed: set[str], path: str, error_start: int):
    if len(seen) != len(allowed) or any(seen.count(key) != 1 for key in allowed) or any(not isinstance(key, str) or key not in allowed for key in seen):
        c.errors.insert(error_start, f"{path}：本次下发的每条意见或留言必须恰好回应一次，不得出现其他 ID")
        seen_ids = {key for key in seen if isinstance(key, str)}
        categories = (("缺少", allowed - seen_ids), ("多出", seen_ids - allowed),
                      ("重复", {key for key in seen_ids if seen.count(key) > 1}))
        for label, identifiers in categories:
            # Display only generated ID shapes. Model-controlled ID fields may
            # otherwise contain prose or instructions; never echo that text.
            safe_ids = [key for key in identifiers if isinstance(key, str) and len(key) <= 32
                        and re.fullmatch(r"[OAN][0-9]+", key)]
            safe_ids.sort(key=lambda key: ("OAN".index(key[0]), int(key[1:]), key))
            if safe_ids:
                c.fail(path, label + "：" + "、".join(safe_ids))


def _responses(c: _Check, value: Any, path: str, allowed: set[str], id_field: str, *, notes=False,
               additional_ids=()):
    error_start = len(c.errors)
    seen = []
    for i, response in enumerate(c.array(value, path)):
        field_path = f"{path}[{i}]"
        item = c.obj(response, field_path, (id_field, "response", "adopted") if notes else (id_field, "response"))
        c.text(item.get(id_field), f"{field_path}.{id_field}", minimum=1)
        seen.append(item.get(id_field))
        c.text(item.get("response"), f"{field_path}.response", minimum=1)
        if notes:
            c.boolean(item.get("adopted"), f"{field_path}.adopted")
    _response_id_errors(c, [*seen, *additional_ids], allowed, path, error_start)


def _alternative_responses(c: _Check, value: Any, allowed: set[str]) -> list[str]:
    """Validate the new field while allowing each A response in either field."""
    path = "decision.alternative_responses"
    error_start = len(c.errors)
    seen = []
    for i, response in enumerate(c.array(value, path)):
        field_path = f"{path}[{i}]"
        item = c.obj(response, field_path, ("alternative_id", "decision", "response"))
        c.text(item.get("alternative_id"), f"{field_path}.alternative_id", minimum=1)
        seen.append(item.get("alternative_id"))
        c.enum(item.get("decision"), f"{field_path}.decision", ("adopt", "partial", "reject"))
        c.text(item.get("response"), f"{field_path}.response", minimum=1)
    present = {key for key in seen if isinstance(key, str) and key in allowed}
    # Missing alternatives may be answered in the old field. Unknown IDs and
    # duplicates in this field still receive its own concrete diagnostics.
    _response_id_errors(c, seen, present, path, error_start)
    # Count unknown A IDs across both fields too, so an unrequested A cannot
    # evade duplicate diagnostics. O/N in this field never satisfy old replies.
    return [key for key in seen if isinstance(key, str) and re.fullmatch(r"A[0-9]+", key)]


def validate_decision(data: Any, *, compass: dict, bible: dict, chapter: int,
                      mode: str, proposal_ids: Iterable[str], objection_ids: Iterable[str],
                      note_ids: Iterable[str], solo=False, alternative_ids: Iterable[str] = (),
                      config=None, history=()) -> dict:
    data = _normalized_copy(data)
    if (isinstance(data, dict) and data.get("ending_status") != "closing"
            and data.get("closing_chapters_left") is None):
        data["closing_chapters_left"] = 0
    c = _Check()
    root = c.obj(data, "decision", ("chosen_proposal_ids", "merge_note", "objection_responses", "user_note_responses", "rationale", "beat_sheet", "ending_status", "closing_chapters_left", "unresolved_major_handling"))
    chosen = c.refs(root.get("chosen_proposal_ids"), "decision.chosen_proposal_ids", set(proposal_ids), 0 if solo else 1)
    if solo and chosen:
        c.fail("decision.chosen_proposal_ids", "独自构思模式必须为空列表")
    c.text(root.get("merge_note"), "decision.merge_note")
    c.text(root.get("rationale"), "decision.rationale", minimum=1)
    response_ids = set(objection_ids) | set(alternative_ids)
    alternative_ids = {key for key in response_ids if isinstance(key, str) and re.fullmatch(r"A[0-9]+", key)}
    alternative_check = _Check()
    answered_alternatives = (_alternative_responses(alternative_check, root["alternative_responses"], alternative_ids)
                             if "alternative_responses" in root else [])
    _responses(c, root.get("objection_responses"), "decision.objection_responses", response_ids, "objection_id",
               additional_ids=answered_alternatives)
    c.errors.extend(alternative_check.errors)
    _responses(c, root.get("user_note_responses"), "decision.user_note_responses", set(note_ids), "note_id", notes=True)
    beat = c.obj(root.get("beat_sheet"), "decision.beat_sheet", ("title", "chapter_goal", "advances_threads", "characters", "scenes", "beats", "opening_hook", "ending_hook", "foreshadowing_plant", "foreshadowing_resolve"))
    for field in ("title", "chapter_goal", "opening_hook", "ending_hook"):
        c.text(beat.get(field), f"decision.beat_sheet.{field}", minimum=1)
    c.refs(beat.get("advances_threads"), "decision.beat_sheet.advances_threads", _ids(compass["main_threads"]), 1)
    c.refs(beat.get("characters"), "decision.beat_sheet.characters", _ids(bible["locked"]["characters"]))
    for i, scene in enumerate(c.array(beat.get("scenes"), "decision.beat_sheet.scenes", 1, bible["locked"]["adaptation"]["max_scenes_per_chapter"])):
        item = c.obj(scene, f"decision.beat_sheet.scenes[{i}]", ("location", "summary"))
        for field in ("location", "summary"):
            c.text(item.get(field), f"decision.beat_sheet.scenes[{i}].{field}", minimum=1)
    c.strings(beat.get("beats"), "decision.beat_sheet.beats", 3, 8, nonempty=True)
    for i, plant in enumerate(c.array(beat.get("foreshadowing_plant"), "decision.beat_sheet.foreshadowing_plant")):
        _foreshadowing(c, plant, f"decision.beat_sheet.foreshadowing_plant[{i}]")
    foreshadow_statuses = {item["id"]: item["status"] for item in bible["dynamic"]["foreshadowing"]}
    open_foreshadows = {key for key, status in foreshadow_statuses.items() if status == "open"}
    resolve_path = "decision.beat_sheet.foreshadowing_resolve"
    requested = c.strings(beat.get("foreshadowing_resolve"), resolve_path, nonempty=True)
    requested_ids = [item for item in requested if isinstance(item, str)]
    if len(requested_ids) != len(set(requested_ids)):
        c.fail(resolve_path, "ID 不得重复")
    resolved, warnings = [], []
    for key in requested_ids:
        if key in open_foreshadows:
            resolved.append(key)
        else:
            warnings.append({"field": "beat_sheet.foreshadowing_resolve", "id": key,
                             "reason": "已回收" if foreshadow_statuses.get(key) == "resolved" else "不存在"})
    # These warnings describe code-side normalization, never model assertions.
    beat["foreshadowing_resolve"] = resolved
    root["warnings"] = warnings
    status = root.get("ending_status")
    c.enum(status, "decision.ending_status", ("continue", "closing", "end"))
    left = root.get("closing_chapters_left")
    left_ok = c.integer(left, "decision.closing_chapters_left", 0)
    target = compass["target"]
    if status == "closing" and left_ok:
        if left < 1 or chapter + left > target["max_chapters"]:
            c.fail("decision.closing_chapters_left", "收束剩余章数至少为 1，且当前章加剩余章数不得超过最多章数")
    if status == "end" and chapter < target["min_chapters"]:
        c.fail("decision.ending_status", "未达到目标最少章数，不得完结")
    if mode == "final" and status != "end":
        c.fail("decision.ending_status", "final 模式必须完结（end）")
    handling_ids = []
    for i, handling in enumerate(c.array(root.get("unresolved_major_handling"), "decision.unresolved_major_handling")):
        path = f"decision.unresolved_major_handling[{i}]"
        item = c.obj(handling, path, ("id", "decision", "reason"))
        c.text(item.get("id"), f"{path}.id", minimum=1)
        if not isinstance(item.get("id"), str) or item["id"] not in open_foreshadows:
            c.fail(f"{path}.id", "必须引用尚未回收的伏笔 ID")
        handling_ids.append(item.get("id"))
        c.enum(item.get("decision"), f"{path}.decision", ("leave_open",))
        c.text(item.get("reason"), f"{path}.reason", minimum=1)
    if len(handling_ids) != len(set(key for key in handling_ids if isinstance(key, str))):
        c.fail("decision.unresolved_major_handling", "伏笔 ID 不得重复")
    if status == "end":
        unresolved_major = {item["id"] for item in bible["dynamic"]["foreshadowing"] if item["status"] == "open" and item["importance"] == "major" and item["id"] not in resolved}
        if any(key not in handling_ids for key in unresolved_major):
            c.fail("decision.unresolved_major_handling", "完结时每条未回收的主要伏笔都必须给出 leave_open 和非空理由")
    if (config or {}).get("structure") == "v2":
        _decision_v2(c, root, beat, compass, bible, chapter, history)
    return c.finish(data)


def _decision_v2(c, root, beat, compass, bible, chapter, history):
    from .context import v2_structure_context

    structure = v2_structure_context(compass, bible, chapter, history)
    contract = compass["genre_contract"]
    if "genre_payoff" not in root:
        c.fail("decision.genre_payoff", "缺少字段")
    payoff = root.get("genre_payoff")
    if payoff is not None:
        item = c.obj(payoff, "decision.genre_payoff", ("type", "beat_index"))
        c.enum(item.get("type"), "decision.genre_payoff.type", contract["core_payoffs"])
        beats = beat.get("beats", [])
        c.integer(item.get("beat_index"), "decision.genre_payoff.beat_index", 1,
                  len(beats) if isinstance(beats, list) else 0)
    if structure["payoff_required"] and payoff is None:
        period = contract["payoff_every_chapters"]
        c.fail("decision.genre_payoff", f"最近 {period - 1} 章爽点数为 0，本章必须安排爽点；每 {period} 章至少 1 个")
    core = contract["core_thread"]
    advances = beat.get("advances_threads", [])
    if structure["thread_staleness"][core] >= 3 and (not isinstance(advances, list) or core not in advances):
        c.fail("decision.beat_sheet.advances_threads", f"核心主线已连续 {structure['thread_staleness'][core] - 1} 章未推进，本章必须推进；每 3 章至少 1 次")
    volume = structure["current_volume"]
    milestones = volume["milestones"] if volume else []
    advanced = c.refs(root.get("milestones_advanced"), "decision.milestones_advanced", _ids(milestones))
    for item in milestones:
        if item.get("status", "open") == "open" and item["due_chapter"] <= chapter and item["id"] not in advanced:
            overdue = chapter - item["due_chapter"]
            timing = f"已逾期 {overdue} 章，" if overdue else ""
            c.fail("decision.milestones_advanced", f"里程碑 {item['id']} 在第 {item['due_chapter']} 章到期，{timing}仍为 open，本章必须推进")
    plants = beat.get("foreshadowing_plant", [])
    resolves = beat.get("foreshadowing_resolve", [])
    if isinstance(plants, list) and isinstance(resolves, list):
        _foreshadowing_budget(c, "decision.beat_sheet.foreshadowing_plant", len(plants), len(resolves),
                              structure["open_foreshadowing_count"], volume,
                              structure["volume_foreshadowing_planted"])


def _foreshadowing_budget(c, path, planted, resolved, open_count, volume, volume_planted):
    if planted > 2:
        c.fail(path, f"本章新埋 {planted} 条，超过每章上限 2 条")
    if open_count > 20 and planted > resolved:
        c.fail(path, f"未回收伏笔 {open_count} 条，超过上限 20；本章新埋 {planted} 条不得多于回收 {resolved} 条")
    if volume and volume_planted + planted > volume["new_mystery_budget"]:
        c.fail(path, f"本卷此前新埋 {volume_planted} 条，本章 {planted} 条，合计 {volume_planted + planted} 条，超过卷预算 {volume['new_mystery_budget']} 条")


def validate_review(data: Any, body: str, *, adaptation_blocking=False) -> dict:
    original = data
    data = _normalized_copy(data)
    c = _Check()
    root = c.obj(data, "review", ("issues",))
    issues = c.array(root.get("issues"), "review.issues")
    # The review envelope is required, but an unverifiable individual report
    # must not fail the whole chapter or become a blocking issue.
    c.finish(data)
    kept, dropped = [], []
    body_compact = compact(body)
    for i, issue in enumerate(issues):
        path = f"review.issues[{i}]"
        issue_check = _Check()
        if isinstance(issue, dict):
            issue.pop("blocking_defaulted", None)
            if issue.get("blocking") is None:
                issue["blocking"] = False
                issue["blocking_defaulted"] = True
        item = issue_check.obj(issue, path, ("category", "problem", "evidence", "fix", "blocking"))
        issue_check.enum(item.get("category"), f"{path}.category", ("continuity", "character", "beat_sheet", "foreshadowing", "style", "adaptation"))
        for field in ("problem", "evidence", "fix"):
            issue_check.text(item.get(field), f"{path}.{field}")
        issue_check.boolean(item.get("blocking"), f"{path}.blocking")
        if issue_check.errors:
            raw_issue = deepcopy(original["issues"][i])
            discarded = raw_issue if isinstance(raw_issue, dict) else {"issue": raw_issue}
            discarded["drop_reason"] = "字段不完整或类型错误"
            dropped.append(discarded)
            continue
        evidence = compact(item["evidence"])
        normalized = deepcopy(item)
        if len(evidence) < 6 or evidence not in body_compact:
            normalized["drop_reason"] = "证据少于 6 字或不是正文的逐字摘录"
            dropped.append(normalized)
            continue
        if (item.get("category") == "style"
                or (item.get("category") == "adaptation" and not adaptation_blocking)):
            normalized["blocking"] = False
        kept.append(normalized)
    return {"issues": kept, "dropped_issues": dropped,
            "passed": not any(item["blocking"] for item in kept)}


def validate_archive(data: Any, bible: dict, *, require_new_appearance=False,
                     config=None, decision=None) -> dict:
    data = _normalized_copy(data)
    c = _Check()
    root = c.obj(data, "archive", ("summary", "character_state_changes", "timeline_add", "foreshadowing_planted", "foreshadowing_resolved", "used_beats_add", "new_characters", "deviation_from_beat_sheet", "locked_conflicts"))
    c.text(root.get("summary"), "archive.summary", 1, 400)
    character_ids = _ids(bible["locked"]["characters"])
    for i, change in enumerate(c.array(root.get("character_state_changes"), "archive.character_state_changes")):
        path = f"archive.character_state_changes[{i}]"
        item = c.obj(change, path, ("id", "field", "value"))
        c.text(item.get("id"), f"{path}.id", minimum=1)
        if not isinstance(item.get("id"), str) or item["id"] not in character_ids:
            c.fail(f"{path}.id", "人物 ID 不存在")
        c.enum(item.get("field"), f"{path}.field", ("location", "condition", "knows", "relationships"))
        if item.get("field") == "relationships":
            relations = c.obj(item.get("value"), f"{path}.value")
            for key, value in relations.items():
                if key not in character_ids:
                    c.fail(f"{path}.value", "关系对象的人物 ID 不存在")
                c.text(value, f"{path}.value.关系", minimum=1)
        elif item.get("field") == "knows" and isinstance(item.get("value"), list):
            c.strings(item["value"], f"{path}.value")
        else:
            c.text(item.get("value"), f"{path}.value")
    c.strings(root.get("timeline_add"), "archive.timeline_add", nonempty=True)
    c.strings(root.get("used_beats_add"), "archive.used_beats_add", nonempty=True)
    c.strings(root.get("locked_conflicts"), "archive.locked_conflicts", nonempty=True)
    for i, planted in enumerate(c.array(root.get("foreshadowing_planted"), "archive.foreshadowing_planted")):
        _foreshadowing(c, planted, f"archive.foreshadowing_planted[{i}]")
    open_ids = {item["id"] for item in bible["dynamic"]["foreshadowing"] if item["status"] == "open"}
    resolved_ids = []
    for i, resolved in enumerate(c.array(root.get("foreshadowing_resolved"), "archive.foreshadowing_resolved")):
        path = f"archive.foreshadowing_resolved[{i}]"
        item = c.obj(resolved, path, ("id", "note"))
        c.text(item.get("id"), f"{path}.id", minimum=1)
        if not isinstance(item.get("id"), str) or item["id"] not in open_ids:
            c.fail(f"{path}.id", "伏笔 ID 不存在或已经回收")
        resolved_ids.append(item.get("id"))
        c.text(item.get("note"), f"{path}.note")
    if len(resolved_ids) != len(set(key for key in resolved_ids if isinstance(key, str))):
        c.fail("archive.foreshadowing_resolved", "同一伏笔不得重复回收")
    for i, character in enumerate(c.array(root.get("new_characters"), "archive.new_characters", 0, 2)):
        _character(c, character, f"archive.new_characters[{i}]", new=True,
                   require_new_appearance=require_new_appearance)
    deviation = c.obj(root.get("deviation_from_beat_sheet"), "archive.deviation_from_beat_sheet", ("deviated", "note"))
    c.boolean(deviation.get("deviated"), "archive.deviation_from_beat_sheet.deviated")
    c.text(deviation.get("note"), "archive.deviation_from_beat_sheet.note")
    if (config or {}).get("structure") == "v2":
        _archive_v2(c, root, bible, decision)
    return c.finish(data)


def _archive_v2(c, root, bible, decision):
    decision = decision or {}
    advanced = decision.get("milestones_advanced", [])
    if "milestones_done" in root:
        c.refs(root["milestones_done"], "archive.milestones_done", set(advanced))
    if decision.get("genre_payoff") is not None or "payoff_delivered" in root:
        c.boolean(root.get("payoff_delivered"), "archive.payoff_delivered")
    # Upgrading changes future planning rules, never the factual archive of a
    # chapter originally written under v1 (which had no genre_payoff key).
    if "genre_payoff" not in decision:
        return
    planted = root.get("foreshadowing_planted", [])
    resolved = root.get("foreshadowing_resolved", [])
    if not isinstance(planted, list) or not isinstance(resolved, list):
        return
    dynamic = bible["dynamic"]
    # The pending chapter immediately follows canonical summaries; an archive
    # may never add more mysteries than its already validated decision budget.
    chapter = max((item["chapter"] for item in dynamic["chapter_summaries"]), default=0) + 1
    volume = next((item for item in dynamic.get("volumes", [])
                   if item["chapters"][0] <= chapter <= item["chapters"][1]), None)
    prior = (sum(volume["chapters"][0] <= item.get("planted_chapter", 0) < chapter
                 for item in dynamic["foreshadowing"]) if volume else 0)
    open_count = sum(item.get("status") == "open" for item in dynamic["foreshadowing"])
    _foreshadowing_budget(c, "archive.foreshadowing_planted", len(planted), len(resolved),
                          open_count, volume, prior)
    if decision:
        planned = decision.get("beat_sheet", {}).get("foreshadowing_plant", [])
        if len(planted) > len(planned):
            c.fail("archive.foreshadowing_planted", f"实际新埋 {len(planted)} 条，不得超过细纲计划 {len(planned)} 条")


def validate_insertions(data: Any, body: str, bible: dict | None = None) -> dict:
    data = _normalized_copy(data)
    c = _Check()
    root = c.obj(data, "insertions", ("insertions",))
    insertions = c.array(root.get("insertions"), "insertions.insertions", 3, 3)
    fact_groups = (set(), set(), set())
    if bible is not None:
        locked, dynamic = bible["locked"], bible["dynamic"]
        locked_facts = list(locked["world_rules"])
        for character in locked["characters"]:
            locked_facts.extend(character.get(field) for field in ("appearance", "motivation"))
        state_facts = [state.get(field) for state in dynamic["character_states"].values()
                       for field in ("location", "condition")]
        history_facts = list(dynamic["timeline"]) + [item.get("description") for item in dynamic["foreshadowing"]]
        fact_groups = [{compact(fact) for fact in group if isinstance(fact, str) and compact(fact)}
                       for group in (locked_facts, state_facts, history_facts)]
    categories = ("锁定外形或设定", "当前位置或伤病", "时间线或伏笔")
    seen_anchors = set()
    for i, insertion in enumerate(insertions):
        path = f"insertions.insertions[{i}]"
        item = c.obj(insertion, path, ("after_anchor", "new_sentence", "contradicts"))
        for field in ("after_anchor", "new_sentence", "contradicts"):
            c.text(item.get(field), f"{path}.{field}", minimum=1 if field == "after_anchor" else 0)
        anchor = item.get("after_anchor")
        if isinstance(anchor, str) and (not anchor or
                sum(body.startswith(anchor, position) for position in range(len(body))) != 1):
            c.fail(f"{path}.after_anchor", "锚点必须在正文中恰好出现一次")
        if isinstance(anchor, str):
            if anchor in seen_anchors:
                c.fail(f"{path}.after_anchor", "三个锚点必须互不相同")
            seen_anchors.add(anchor)
        citation = item.get("contradicts")
        citation = compact(citation) if isinstance(citation, str) else ""
        windows = {citation[start:start + 8] for start in range(len(citation) - 7)}
        item["citation_check"] = {
            "matched_categories": [category for category, facts in zip(categories, fact_groups)
                                   if any(window in fact for window in windows for fact in facts)],
            "minimum_shared_length": 8,
        }
    return c.finish(data)
