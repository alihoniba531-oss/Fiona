# -*- coding: utf-8 -*-
"""
底色探针（State Probe）。

在 detect_and_save 内部顺序运行，持久化「用户当前匹配底色」到 user_states 表：
  - connection_mode:      整体连接模式（seeking/processing/sharing/exploring）
  - emotional_intensity:  情绪激活程度 0-10
  - openness_level:       对连接的开放度（high/medium/low）
  - interest_anchor:      核心利益锚点（最稳定的匹配维度，永不暴露给用户）

interest_anchor 六种类型（内部信号，绝不出现在任何面向用户的字段里）：
  emotional_value   — 情绪价值：需要有人让自己感觉被理解、被激活、有共鸣、不孤独
  resource_exchange — 资源置换：需要经验、技能、人脉、机会
  safety            — 安全感：需要稳定、可靠、不会消失的人；怕被抛下
  recognition       — 认可：需要被看见、被选择、被重视；有价值感缺失感
  intimate          — 性/浪漫吸引：需要亲密连接、被渴望；渴望被"选中"
  light_connection  — 无明确锚点，随缘轻连接
"""
import json
from database import upsert_user_state

_VALID_MODES = {"seeking", "processing", "sharing", "exploring"}
_VALID_OPENNESS = {"high", "medium", "low"}
_VALID_ANCHORS = {
    "emotional_value", "resource_exchange", "safety",
    "recognition", "intimate", "light_connection",
}

_DEFAULT_STATE = {
    "connection_mode": "exploring",
    "emotional_intensity": 0,
    "openness_level": "medium",
    "interest_anchor": "light_connection",
}

STATE_PROBE_PROMPT = """你是底色探针，只输出 JSON，不解释。

根据用户最近几条消息，判断他/她此刻的整体状态。

输出：
{
  "connection_mode": 四选一：
    "seeking"    — 有困惑/需帮助/寻方向（问句、"怎么"、"不知道"为主）
    "processing" — 正在消化某件事，情绪翻腾（反复叙述、强情绪词）
    "sharing"    — 主动分享经验/观点（"我发现"、"我最近"、叙述式）
    "exploring"  — 轻松好奇，随聊，无深度投入,

  "emotional_intensity": 0-10 整数：
    0-3 平静/日常；4-6 有情绪但可控；7-10 激烈焦虑/愤怒/崩溃,

  "openness_level": 三选一：
    "high"   — 情绪平稳，话题开放，适合被推荐认识新人
    "medium" — 有情绪但可接受，话题半开放
    "low"    — 情绪激烈 / 发泄中 / 内容极私密，不适合被打扰,

  "interest_anchor": 六选一（最稳定的底层连接驱动力）：
    "emotional_value"   — 需要有人让自己感觉被理解、被激活、有共鸣、不孤独
    "resource_exchange" — 需要经验、技能、人脉、机会；有具体问题想解决
    "safety"            — 需要稳定、可靠、不会消失的人；怕被抛下、怕孤独
    "recognition"       — 需要被看见、被选择、被重视；有价值感缺失感
    "intimate"          — 需要亲密连接、被渴望；话题有情感张力、渴望被"选中"
    "light_connection"  — 随缘轻连接，无深层诉求
}

规则：
- 基于所有提供的用户消息整体走势，不只看最后一条
- 消息 < 2 条时，倾向 exploring + medium + light_connection
- emotional_intensity >= 7 时，openness_level 必须是 "low"
- 严格输出 JSON，不加任何解释文字
"""


async def run_state_probe(
    client,
    username: str,
    recent_msgs: list[dict],
) -> dict:
    """
    运行底色探针，将结果 upsert 到 user_states 表，同时返回结果供调用方直接使用。

    recent_msgs: 最近对话历史（含 role/content），内部只取 user 角色最近 5 条。
    """
    user_msgs = [
        m for m in recent_msgs
        if m.get("role") == "user"
        and (m.get("content") or "").strip()
        and not (m.get("content") or "").startswith("[")
    ][-5:]

    if len(user_msgs) < 1:
        await upsert_user_state(username, **_DEFAULT_STATE)
        return dict(_DEFAULT_STATE)

    ctx = "\n".join(
        f"user: {(m.get('content') or '')[:120]}"
        for m in user_msgs
    )

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": STATE_PROBE_PROMPT},
                {"role": "user", "content": f"最近消息：\n{ctx}"},
            ],
            response_format={"type": "json_object"},
            max_tokens=100,
            temperature=0.1,
        )
        raw = json.loads(resp.choices[0].message.content)

        connection_mode = raw.get("connection_mode", "exploring")
        if connection_mode not in _VALID_MODES:
            connection_mode = "exploring"

        try:
            emotional_intensity = max(0, min(10, int(raw.get("emotional_intensity", 0))))
        except (TypeError, ValueError):
            emotional_intensity = 0

        openness_level = raw.get("openness_level", "medium")
        if openness_level not in _VALID_OPENNESS:
            openness_level = "medium"
        if emotional_intensity >= 7:
            openness_level = "low"

        interest_anchor = raw.get("interest_anchor", "light_connection")
        if interest_anchor not in _VALID_ANCHORS:
            interest_anchor = "light_connection"

        state = {
            "connection_mode": connection_mode,
            "emotional_intensity": emotional_intensity,
            "openness_level": openness_level,
            "interest_anchor": interest_anchor,
        }
        await upsert_user_state(username, **state)
        return state

    except Exception:
        return dict(_DEFAULT_STATE)
