# -*- coding: utf-8 -*-
"""构造跨用户匹配可用的最小画像，不包含原始对话或高敏画像字段。"""

_LIST_FIELDS = ("interests", "values", "skills")
_TEXT_FIELDS = ("stage", "city")
_MAX_ITEMS_PER_FIELD = 8
_MAX_VALUE_CHARS = 60


def minimized_match_profile(profile: dict) -> dict:
    if not isinstance(profile, dict):
        return {}
    result: dict[str, list[str] | str] = {}
    for field in _LIST_FIELDS:
        value = profile.get(field)
        if not isinstance(value, list):
            continue
        cleaned = []
        for item in value:
            if not isinstance(item, str):
                continue
            text = " ".join(item.split())[:_MAX_VALUE_CHARS]
            if text and text not in cleaned:
                cleaned.append(text)
            if len(cleaned) == _MAX_ITEMS_PER_FIELD:
                break
        if cleaned:
            result[field] = cleaned
    for field in _TEXT_FIELDS:
        value = profile.get(field)
        if isinstance(value, str):
            text = " ".join(value.split())[:_MAX_VALUE_CHARS]
            if text:
                result[field] = text
    return result
