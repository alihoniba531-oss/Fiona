"""Pure chapter mode/stage calculations and bounded context assembly."""

from __future__ import annotations

from copy import deepcopy
import json


CLOSING_INSTRUCTION = "提案必须服务于回收主线与伏笔，不得开启新的主要支线"


def trim_bible(bible: dict, chapter: int | None = None, named_characters=(), *,
               timeline_limit=10) -> dict:
    """Return an isolated context view; never mutate or rewrite canonical history.

    Locked world facts are preserved, while character cards and states share the
    same appearance window. Knowledge is bounded only in this disposable view;
    validators and archive application continue to receive the complete bible.
    """
    result = deepcopy(bible)
    dynamic = result.get("dynamic")
    if not isinstance(dynamic, dict):
        return result
    summaries = dynamic.get("chapter_summaries", [])
    current = chapter if chapter is not None else max(
        (item.get("chapter", 0) for item in summaries), default=0) + 1
    recent = [item for item in summaries if item.get("chapter", 0) >= current - 10][-10:]
    dynamic["chapter_summaries"] = recent
    dynamic["timeline"] = dynamic.get("timeline", [])[-timeline_limit:]
    dynamic["used_beats"] = dynamic.get("used_beats", [])[-30:]
    if "structure_history" in dynamic:
        dynamic["structure_history"] = [item for item in dynamic["structure_history"]
                                          if item.get("chapter", 0) >= current - 10][-10:]
    foreshadowing = dynamic.get("foreshadowing", [])
    resolved = sorted((item for item in foreshadowing if item.get("status") != "open"),
                      key=lambda item: item.get("resolved_chapter", 0))[-5:]
    resolved_ids = {item.get("id") for item in resolved}
    dynamic["foreshadowing"] = [item for item in foreshadowing
                                 if item.get("status") == "open" or item.get("id") in resolved_ids]
    # Keep completed arcs only once their detailed summaries leave the window.
    if "arc_summaries" in dynamic:
        dynamic["arc_summaries"] = [item for item in dynamic["arc_summaries"]
                                    if item.get("start_chapter", 0) < current - 10]
    keep = set(named_characters)
    characters = result.get("locked", {}).get("characters", [])
    keep.update(item["id"] for item in characters if item.get("role") == "main")
    for item in summaries:
        if item.get("chapter", 0) >= current - 3:
            keep.update(item.get("characters", []))
    states = dynamic.get("character_states", {})
    for identifier, state in states.items():
        if isinstance(state, dict) and state.get("last_seen_chapter", -1) >= current - 3:
            keep.add(identifier)
    result["locked"]["characters"] = [item for item in characters if item["id"] in keep]
    dynamic["character_states"] = {key: value for key, value in states.items() if key in keep}
    for state in dynamic["character_states"].values():
        if isinstance(state, dict) and isinstance(state.get("knows"), list):
            state["knows"] = state["knows"][-30:]
    return result


def split_context_payload(payload: dict) -> tuple[dict, dict]:
    """Extract stable facts at their original paths for deterministic prefix caching."""
    stable_keys = ("locked", "compass", "creative_guidelines", "style_guide", "adaptation")

    def partition(value):
        stable, changing = {}, {}
        for key in sorted(value):
            item = value[key]
            if key in stable_keys:
                stable[key] = deepcopy(item)
            elif isinstance(item, dict):
                fixed, dynamic = partition(item)
                if fixed:
                    stable[key] = fixed
                changing[key] = dynamic
            else:
                changing[key] = deepcopy(item)
        return stable, changing

    return partition(payload)


def context_messages(payload: dict) -> list[dict]:
    stable, changing = split_context_payload(payload)
    return [{"role": "user", "content": json.dumps(part, ensure_ascii=False, sort_keys=True)}
            for part in (stable, changing)]


def _check_chapter(chapter: int, max_chapters: int):
    if type(chapter) is not int or type(max_chapters) is not int or not 1 <= chapter <= max_chapters:
        raise ValueError("章号与最多章数必须是正整数，且章号不得超过最多章数")


def chapter_mode(chapter: int, max_chapters: int, history=()) -> str:
    _check_chapter(chapter, max_chapters)
    if chapter == max_chapters:
        return "final"
    was_closing = any(isinstance(item, dict) and
                      (item.get("ending_status") == "closing" or
                       isinstance(item.get("decision"), dict) and item["decision"].get("ending_status") == "closing")
                      for item in history)
    # Integer arithmetic avoids floating-point threshold errors (e.g. M=100).
    if chapter >= (85 * max_chapters + 99) // 100 or was_closing:
        return "closing"
    return "normal"


def chapter_stage(chapter: int, max_chapters: int, mode: str) -> str:
    _check_chapter(chapter, max_chapters)
    if mode not in ("normal", "closing", "final"):
        raise ValueError("模式必须为 normal、closing 或 final")
    if mode in ("closing", "final"):
        return "收束"
    if chapter * 5 <= max_chapters:
        return "开端"
    if chapter * 5 <= max_chapters * 3:
        return "发展"
    return "高潮"


def build_brief(compass: dict, bible: dict, chapter: int, history=(),
                written_words=0, user_notes=(), *, timeline_limit=5,
                named_characters=(), config=None) -> dict:
    maximum = compass["target"]["max_chapters"]
    mode = chapter_mode(chapter, maximum, history)
    stage = chapter_stage(chapter, maximum, mode)
    view = trim_bible(bible, chapter, named_characters, timeline_limit=timeline_limit)
    result = {
        "compass": deepcopy(compass),
        "locked": view["locked"],
        "dynamic": view["dynamic"],
        "chapter": chapter,
        "mode": mode,
        "stage": stage,
        "progress": {"written_chapters": chapter - 1, "written_words": written_words,
                     "target": deepcopy(compass["target"]), "chapter": chapter,
                     "mode": mode, "stage": stage},
        "user_notes": deepcopy(list(user_notes)),
    }
    if mode in ("closing", "final"):
        result["closing_instruction"] = CLOSING_INSTRUCTION
    if (config or {}).get("structure") == "v2":
        result.update(v2_structure_context(compass, bible, chapter, history))
    return result


def v2_structure_context(compass: dict, bible: dict, chapter: int, history=()) -> dict:
    """Compute sliding windows from full history before any context trimming.

    Thread distance includes this chapter: three means two prior chapters were
    empty, so advancement now preserves the promised three-chapter window.
    """
    contract = compass["genre_contract"]
    dynamic = bible["dynamic"]
    records = {}
    for item in [*dynamic.get("structure_history", []), *history]:
        if not isinstance(item, dict):
            continue
        number = item.get("chapter")
        if type(number) is not int or not 0 < number < chapter:
            continue
        decision = item.get("decision", item)
        if not isinstance(decision, dict):
            continue
        beat = decision.get("beat_sheet", decision)
        if not isinstance(beat, dict):
            beat = {}
        old = records.get(number, {})
        records[number] = {
            "chapter": number,
            "genre_payoff": deepcopy(decision.get("genre_payoff", old.get("genre_payoff"))),
            "advances_threads": deepcopy(beat.get("advances_threads", old.get("advances_threads", []))),
        }
        archive = item.get("archive")
        confirmation = (archive if isinstance(archive, dict) and "payoff_delivered" in archive
                        else item if "payoff_delivered" in item else old)
        if "payoff_delivered" in confirmation:
            records[number]["payoff_delivered"] = confirmation["payoff_delivered"]
            if confirmation["payoff_delivered"] is False:
                records[number]["genre_payoff"] = None
    period = contract["payoff_every_chapters"]
    payoff_history = []
    for number in range(max(1, chapter - period * 2), chapter):
        record = records.get(number, {})
        payoff = {"chapter": number, "genre_payoff": deepcopy(record.get("genre_payoff"))}
        if "payoff_delivered" in record:
            payoff["payoff_delivered"] = record["payoff_delivered"]
        payoff_history.append(payoff)
    staleness = {}
    for thread in compass["main_threads"]:
        last = max((number for number, item in records.items()
                    if thread["id"] in item["advances_threads"]), default=0)
        staleness[thread["id"]] = chapter - last
    current = next((item for item in dynamic.get("volumes", [])
                    if item["chapters"][0] <= chapter <= item["chapters"][1]), None)
    open_count = sum(item.get("status") == "open" for item in dynamic["foreshadowing"])
    prior_payoff = any(records.get(number, {}).get("genre_payoff") is not None
                       for number in range(max(1, chapter - period + 1), chapter))
    payoff_required = chapter >= period and not prior_payoff
    flags = []
    core = contract["core_thread"]
    if staleness[core] >= 3:
        flags.append(f"核心主线 {core} 已 {staleness[core] - 1} 章未推进，本章必须推进（每 3 章至少 1 次）")
    for thread, distance in staleness.items():
        if thread != core and distance >= 6:
            flags.append(f"主线 {thread} 已连续 {distance - 1} 章未推进")
    if payoff_required:
        flags.append(f"本章必须安排类型爽点（每 {period} 章至少 1 个）")
    if current:
        for milestone in current["milestones"]:
            if milestone.get("status", "open") == "open" and milestone["due_chapter"] <= chapter:
                overdue = chapter - milestone["due_chapter"]
                timing = f"已逾期 {overdue} 章" if overdue else "到期"
                flags.append(f"里程碑 {milestone['id']} {timing}（第 {milestone['due_chapter']} 章），本章必须推进")
    for volume in dynamic.get("volumes", []):
        if volume["chapters"][1] < chapter:
            for milestone in volume["milestones"]:
                if milestone.get("status") == "missed":
                    flags.append(f"第 {volume['volume']} 卷里程碑 {milestone['id']} 未完成（到期第 {milestone['due_chapter']} 章）")
    if open_count > 20:
        flags.append(f"未回收伏笔 {open_count} 条，已超上限 20，新埋不得多于回收")
    planted = (sum(current["chapters"][0] <= item.get("planted_chapter", 0) < chapter
                   for item in dynamic["foreshadowing"]) if current else 0)
    if current and planted >= current["new_mystery_budget"]:
        flags.append(f"本卷已新埋伏笔 {planted} 条，卷预算 {current['new_mystery_budget']} 条，本章不得新埋")
    if open_count > 20 or current and planted >= current["new_mystery_budget"]:
        flags.append("本章章末钩子不得引入新的未解谜团，只能使用已有线索或正面冲突")
    return {
        "genre_contract": deepcopy(contract), "current_volume": deepcopy(current),
        "payoff_history": payoff_history, "thread_staleness": staleness,
        "open_foreshadowing_count": open_count, "foreshadowing_limit": 20,
        "volume_foreshadowing_planted": planted, "payoff_required": payoff_required,
        "red_flags": flags,
    }


def build_writer_context(compass: dict, bible: dict, beat_sheet: dict,
                         chapter: int, previous_text="", *, compressed=False) -> dict:
    bible = trim_bible(bible, chapter, beat_sheet["characters"])
    selected = set(beat_sheet["characters"])
    if compressed:
        selected.update(bible["dynamic"]["character_states"])
    characters = []
    for source in bible["locked"]["characters"]:
        if source["id"] in selected:
            character = deepcopy(source)
            character["state"] = deepcopy(bible["dynamic"]["character_states"][source["id"]])
            characters.append(character)
    result = {
        "compass": deepcopy(compass),
        "style_guide": deepcopy(bible["locked"]["style_guide"]),
        "adaptation": deepcopy(bible["locked"]["adaptation"]),
        "characters": characters,
        "chapter_summaries": deepcopy(bible["dynamic"]["chapter_summaries"]),
        "previous_tail": previous_text[-1500:] if chapter > 1 else "",
        "beat_sheet": deepcopy(beat_sheet),
        "open_major_foreshadowing": [deepcopy(item) for item in bible["dynamic"]["foreshadowing"]
                                      if item["status"] == "open" and item["importance"] == "major"],
        "chapter": chapter,
    }
    if compressed:
        # Cards, style and adaptation already occur in the stable locked block.
        # The variable writer block carries only each selected character's state.
        result["characters"] = [{"id": item["id"], "state": item["state"]}
                                for item in characters]
        result.pop("style_guide")
        result.pop("adaptation")
        dynamic = deepcopy(bible["dynamic"])
        dynamic.pop("character_states", None)
        dynamic.pop("chapter_summaries", None)
        result.update(locked=deepcopy(bible["locked"]), dynamic=dynamic)
    return result


def build_review_bible(compass: dict, bible: dict, chapter=None, named_characters=()) -> dict:
    """Carry the original compass once, inside the review-only bible envelope.

    The persisted bible stays unchanged. Both chapter review and experiment C
    use this envelope so their input fields and access to the seed are equal.
    """
    result = trim_bible(bible, chapter, named_characters)
    result["compass"] = deepcopy(compass)
    return result
