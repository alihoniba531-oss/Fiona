# -*- coding: utf-8 -*-
"""
匹配引擎。
把当前用户画像 + 其他所有用户画像一起给 DeepSeek，让模型判断最佳匹配。
小规模用户量下无需向量数据库，直接 LLM 评估。
"""
import json
from database import get_profile, get_all_profiles, was_recently_matched, save_match

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
    for p in all_profiles:
        if p["username"] == username:
            continue
        if await was_recently_matched(username, p["username"]):
            continue
        others.append(p)

    if not others:
        return []

    others_text = "\n\n".join(
        f"用户「{p['username']}」：{json.dumps(p['profile'], ensure_ascii=False)}"
        for p in others
    )

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": MATCH_PROMPT},
                {"role": "user", "content": (
                    f"目标用户「{username}」的画像：\n"
                    f"{json.dumps(my_profile, ensure_ascii=False)}\n\n"
                    f"其他用户：\n{others_text}"
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
            temperature=0.3,
        )
        raw = resp.choices[0].message.content
        # DeepSeek JSON mode 有时会把数组包在对象里
        data = json.loads(raw)
        if isinstance(data, list):
            results = data
        else:
            # 找到第一个 list 值
            results = next((v for v in data.values() if isinstance(v, list)), [])
    except Exception:
        return []

    # 保存到 matches 表（避免 30 天内重复推荐）
    for r in results:
        matched_user = r.get("username", "")
        if matched_user:
            await save_match(username, matched_user)

    return results
