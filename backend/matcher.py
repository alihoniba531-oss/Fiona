# -*- coding: utf-8 -*-
"""
匹配引擎。
把当前用户画像 + 其他所有用户画像一起给主力大脑（qwen3.8-max），让模型判断最佳匹配。
小规模用户量下无需向量数据库，直接 LLM 评估。
"""
import asyncio
import json
from database import (
    get_all_profiles,
    get_profile,
    get_user_settings,
    save_match,
    was_recently_matched,
)
from llm import MAIN_EXTRA_BODY, MAIN_MODEL
from utils.match_privacy import minimized_match_profile

_VALID_MATCH_TYPES = {"精准对接", "互助伙伴", "话题连接"}


def _preference_allows(match_pref: str, other_gender: str | None) -> bool:
    return match_pref == "both" or other_gender == match_pref

MATCH_PROMPT = """你是Chloe的后台匹配系统，只输出JSON，不输出任何其他内容。

目标用户的画像已提供，其他用户的画像也已提供。
找出最适合和目标用户连接的 1-3 个人。

匹配优先级（按顺序）：
1. 互补：目标用户的需求/困境，对方恰好有对应经验/技能/资源
2. 共鸣：双方处境相似，可以互相支持
3. 话题：共同兴趣，能自然展开对话

输出规则：
- reason 说具体连接点，一两句，不要废话，不透露对方隐私细节
- type 只能是："精准对接" / "互助伙伴" / "话题连接"
- tags 最多 3 个简短标签，概括这次连接的主题
- 如果没有合适的匹配，返回空数组 []
- 只返回 JSON 数组，不加任何解释

输出格式：
[
  {"username": "xxx", "reason": "...", "type": "精准对接", "tags": ["标签1", "标签2", "标签3"]},
  ...
]
"""


async def find_matches(client, username: str) -> list[dict]:
    """
    为 username 找匹配，返回结果列表。
    每项包含 {username, reason, type, tags}。
    """
    my_profile = await get_profile(username)
    if not my_profile:
        return []

    all_profiles = await get_all_profiles()
    # 过滤自己 + 近期已推荐的
    others = []
    my_settings = await get_user_settings(username)
    for p in all_profiles:
        if p["username"] == username:
            continue
        if await was_recently_matched(username, p["username"]):
            continue
        peer_settings = await get_user_settings(p["username"])
        if not _preference_allows(my_settings.get("match_pref", "both"), p.get("gender")):
            continue
        if not _preference_allows(
            peer_settings.get("match_pref", "both"),
            my_settings.get("gender"),
        ):
            continue
        others.append({**p, "profile": minimized_match_profile(p["profile"])})

    if not others:
        return []

    others_text = "\n\n".join(
        f"用户「{p['username']}」：{json.dumps(p['profile'], ensure_ascii=False)}"
        for p in others
    )

    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=MAIN_MODEL,
            extra_body=MAIN_EXTRA_BODY,
            messages=[
                {"role": "system", "content": MATCH_PROMPT},
                {"role": "user", "content": (
                    f"目标用户「{username}」的画像：\n"
                    f"{json.dumps(minimized_match_profile(my_profile), ensure_ascii=False)}\n\n"
                    f"其他用户：\n{others_text}"
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content
        # LLM JSON mode 有时会把数组包在对象里
        data = json.loads(raw)
        if isinstance(data, list):
            results = data
        else:
            # 找到第一个 list 值
            results = next((v for v in data.values() if isinstance(v, list)), [])
    except Exception:
        return []

    # 模型输出是不可信数据：只能返回本次候选集合中的用户，并规范化字段。
    allowed_usernames = {p["username"] for p in others}
    sanitized = []
    seen = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        matched_user = item.get("username")
        if matched_user not in allowed_usernames or matched_user in seen:
            continue
        match_type = item.get("type")
        reason = item.get("reason")
        if match_type not in _VALID_MATCH_TYPES or not isinstance(reason, str):
            continue
        reason = reason.strip()[:100]
        if not reason:
            continue
        raw_tags = item.get("tags")
        tags = []
        if isinstance(raw_tags, list):
            for tag in raw_tags:
                if not isinstance(tag, str):
                    continue
                clean = tag.strip()[:30]
                if clean and clean not in tags:
                    tags.append(clean)
                if len(tags) == 3:
                    break
        sanitized.append({
            "username": matched_user,
            "reason": reason,
            "type": match_type,
            "tags": tags,
        })
        seen.add(matched_user)
        if len(sanitized) == 3:
            break

    # 保存到 matches 表（避免 30 天内重复推荐）
    for result in sanitized:
        await save_match(username, result["username"])

    return sanitized
