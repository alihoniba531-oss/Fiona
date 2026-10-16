"""Pure chapter mode/stage calculations and bounded context assembly."""

from __future__ import annotations

from copy import deepcopy


CLOSING_INSTRUCTION = "提案必须服务于回收主线与伏笔，不得开启新的主要支线"


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
                written_words=0, user_notes=()) -> dict:
    maximum = compass["target"]["max_chapters"]
    mode = chapter_mode(chapter, maximum, history)
    stage = chapter_stage(chapter, maximum, mode)
    dynamic = deepcopy(bible["dynamic"])
    dynamic["timeline"] = dynamic["timeline"][-5:]
    result = {
        "compass": deepcopy(compass),
        "locked": deepcopy(bible["locked"]),
        "dynamic": dynamic,
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
    return result


def build_writer_context(compass: dict, bible: dict, beat_sheet: dict,
                         chapter: int, previous_text="") -> dict:
    selected = set(beat_sheet["characters"])
    characters = []
    for source in bible["locked"]["characters"]:
        if source["id"] in selected:
            character = deepcopy(source)
            character["state"] = deepcopy(bible["dynamic"]["character_states"][source["id"]])
            characters.append(character)
    return {
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


def build_review_bible(compass: dict, bible: dict) -> dict:
    """Carry the original compass once, inside the review-only bible envelope.

    The persisted bible stays unchanged. Both chapter review and experiment C
    use this envelope so their input fields and access to the seed are equal.
    """
    result = deepcopy(bible)
    result["compass"] = deepcopy(compass)
    return result
