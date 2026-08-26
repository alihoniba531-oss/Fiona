# -*- coding: utf-8 -*-
"""
对话画像提取器。
每 5 轮对话后，后台静默调用一次，更新用户画像。
用户完全感知不到这个过程。
"""
import asyncio
import json
from database import get_profile, update_profile, update_time_tag_prefs
from llm import MAIN_EXTRA_BODY, MAIN_MODEL
from utils.background_tasks import _background_tasks, create_background_task


def _track_background_task(coro) -> asyncio.Task:
    """兼容现有调用点，实际由应用级追踪器统一管理。"""
    return create_background_task(coro, label="profile-match")


# 对话兴趣词 → 广场标签映射
_INTEREST_TO_TAG: list[tuple[list[str], str]] = [
    (["美食", "吃", "餐", "菜", "料理", "食物", "烹饪"], "美食"),
    (["风景", "自然", "山", "海", "景色", "户外"], "风景"),
    (["旅行", "出行", "旅游", "出游", "出差", "游玩"], "旅行"),
    (["音乐", "歌", "乐器", "演唱", "歌曲", "听歌"], "音乐"),
    (["运动", "健身", "跑步", "骑行", "游泳", "锻炼", "球"], "运动"),
    (["宠物", "猫", "狗", "喵", "汪", "养了"], "宠物"),
    (["穿搭", "衣服", "时尚", "搭配", "衣橱"], "穿搭"),
    (["情感", "感情", "恋爱", "孤独", "失恋", "思念", "喜欢"], "情感"),
    (["创意", "设计", "艺术", "绘画", "摄影", "创作", "拍照"], "创意"),
    (["搞笑", "段子", "好笑", "哈哈", "喜剧"], "搞笑"),
    (["日常", "今天", "昨天", "生活", "日子"], "日常"),
    (["随拍", "随手", "拍了", "记录"], "随拍"),
]


def _interests_to_plaza_tags(interests: list) -> list:
    """把提取的兴趣词轻量映射到广场预设标签"""
    matched = set()
    text = " ".join(interests)
    for keywords, tag in _INTEREST_TO_TAG:
        if any(kw in text for kw in keywords):
            matched.add(tag)
    return list(matched)

EXTRACT_PROMPT = """你是一个信息提取器，只输出JSON，不说任何其他内容。

根据以下对话，提取用户的真实信息。规则：
- 只提取对话中自然流露的内容，不猜测、不推断
- 不确定的信息不填，宁可留空
- 用简洁词组，不用长句
- 旧画像已提供，只补充或更新有变化的字段，其他保持原样

输出格式（严格 JSON）：
{
  "interests": ["兴趣1", "兴趣2"],
  "values": ["重视的价值观1", "价值观2"],
  "needs": ["当前需求1", "想解决的问题2"],
  "skills": ["专业技能1", "可分享的经验2"],
  "struggles": ["当前困境1", "烦恼2"],
  "city": "城市（不确定留空字符串）",
  "occupation": "职业方向（不确定留空字符串）",
  "stage": "当前人生阶段关键词（如：职场转型期/初为父母/创业期）",
  "special_dates": ["MM-DD 描述"]
}

special_dates 规则：
- 只提取用户明确提到的、对他/她有情感意义的重复性日期
- 格式严格为 "MM-DD 简短描述"，如 "03-08 妈妈生日"、"06-14 分手纪念日"、"12-25 一个人过圣诞"
- 必须是用户亲口说到的，不猜测、不推断
- 旧的 special_dates 要保留，只追加新发现的
- 如果对话中没有提到任何特殊日期，返回空数组 []
"""


def _merge(old: dict, new: dict) -> dict:
    """合并画像：列表去重追加，字符串以非空新值覆盖"""
    result = dict(old)
    for k, v in new.items():
        if isinstance(v, list):
            existing = result.get(k, [])
            combined = list(dict.fromkeys(existing + [i for i in v if i]))
            result[k] = combined[:12]  # 最多保留 12 条
        elif isinstance(v, str):
            if v.strip():
                result[k] = v.strip()
    return result


async def extract_and_update(client, username: str, messages: list):
    """
    提取画像并更新数据库，完成后触发 Layer 2 画像级匹配。
    messages 是对话历史列表，每项 {role, content}。
    """
    if len(messages) < 4:
        return

    # 只用最近 40 条，避免 token 过多
    recent = messages[-40:]
    convo = "\n".join(
        f"{m['role']}: {m['content'][:200]}"  # 每条消息截断，避免超长
        for m in recent
        if m.get("content") and not m["content"].startswith("[")
    )
    if not convo.strip():
        return

    old_profile = await get_profile(username)

    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model=MAIN_MODEL,
            extra_body=MAIN_EXTRA_BODY,
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": f"旧画像：{json.dumps(old_profile, ensure_ascii=False)}\n\n对话：\n{convo}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=400,
            temperature=0.1,
        )
        new_data = json.loads(resp.choices[0].message.content)
        merged = _merge(old_profile, new_data)
        await update_profile(username, merged)

        # 把新提取的兴趣映射到广场标签，记入当前时段权重
        new_interests = new_data.get("interests", []) + new_data.get("needs", [])
        plaza_tags = _interests_to_plaza_tags(new_interests)
        if plaza_tags:
            await update_time_tag_prefs(username, plaza_tags, delta=0.5)  # 对话信号权重略低于点赞

        # Layer 2：画像更新后触发画像级跨用户匹配
        from conversation_matcher import detect_and_save_from_profile
        _track_background_task(detect_and_save_from_profile(client, username))
    except Exception as e:
        # 失败不影响主流程；不输出用户名或异常正文，避免日志携带用户内容。
        print(f"[extractor] extract_and_update failed type={type(e).__name__}", flush=True)
