# -*- coding: utf-8 -*-
"""
旅行规划工具。

route.py 走 OSRM 算驾车导航，对"宁波 → 新德里"这种跨国旅行毫无意义
（会给你算出 5810 km 穿过 7 个国家的开车路线）。

此工具用千问 enable_search 联网搜索 + 整理：航班 / 高铁 / 签证 / 季节
提示 / 大致预算等多维度，给出可执行的旅行方案。
"""
import json
import os
import re
from datetime import datetime
from openai import OpenAI


_client_cache = None
def _get_client():
    global _client_cache
    if _client_cache is None:
        _client_cache = OpenAI(
            api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _client_cache


_PROMPT = """你是一个旅行规划助手。用户给出起点、终点、可选的出行时间/天数，你需要联网搜索并整理一个**可执行**的旅行方案。

【输出格式 - 严格 JSON】
{
  "headline": "一句话主线方案（如：宁波栎社→上海浦东→德里英迪拉，全程约18小时，含中转）",
  "points": [
    "交通推荐：建议方式 + 关键航班号/车次 + 大致时长 + 起飞/发车时段",
    "中转/换乘：在哪里中转、需要多久、是否需要签注",
    "签证/证件：是否需要签证、办理方式、所需时间（跨国时必填）",
    "费用范围：合理票价 + 旺/淡季差异",
    "时间建议：最佳出行月份、当地季节/气候提醒",
    "其他注意：行李/SIM卡/插座/支付方式 等实用提示"
  ],
  "sources": [{"title": "信息来源标题", "url": "https://..."}]
}

【规则】
- points: 3-6 条，每条必须有具体内容（航班号、时刻、价格、天数），不要笼统
- 跨国/跨大区时必含签证项；同城/同省驾车时直接给路线即可
- sources 给真实搜到的链接；编不出真实 URL 就留空数组
- 不输出 markdown、不加 ```json 围栏，直接 JSON 对象
"""


def _today_directive() -> str:
    """注入"今天日期 + 禁止过期措辞"指令 —— 防止模型按训练截止时段（约 2024）输出
    核酸/健康宝/绿码这种已废止的疫情措辞。"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    weekday = "周" + "一二三四五六日"[now.weekday()]
    return (
        f"\n\n【时效性 — 必须遵守】\n"
        f"- 今天是 {today}（{weekday}），不是你训练数据里的某个过去时刻。\n"
        f"- 中国境内疫情管控自 2023 年初已全面取消，**禁止提及**核酸检测、健康宝、"
        f"绿码、行程卡、隔离观察、48 小时阴性证明等已废止措辞。\n"
        f"- 票价、班次、签证流程必须用联网搜索的最新结果，不要照搬训练数据里的旧政策旧价格。\n"
        f"- 目的地国家若仍有入境要求（电子签、ETA、健康申报等），以搜到的当前官方口径为准。"
    )


def travel_plan(query: str) -> dict:
    """旅行规划。query 是用户的原话或 "起点 → 终点 + 时间/天数" 描述。"""
    q = (query or "").strip()
    if not q:
        return {"type": "card", "source": "旅行规划", "points": ["没说要去哪"], "error": True}

    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": _PROMPT + _today_directive()},
                {"role": "user", "content": q},
            ],
            extra_body={"enable_search": True},
            max_tokens=1200,
            temperature=0.3,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return {
            "type": "card",
            "source": f"旅行规划 · {q[:20]}",
            "points": [f"规划失败：{type(e).__name__}", str(e)[:120]],
            "error": True,
        }

    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        content = m.group(0)
    try:
        data = json.loads(content)
    except Exception:
        lines = [l.strip("•- \t").strip() for l in content.split("\n") if l.strip()]
        lines = [l for l in lines if l and not l.startswith(("{", "}", '"'))]
        return {
            "type": "card",
            "source": f"旅行规划 · {q[:20]}",
            "points": lines[:6] or ["没规划出方案"],
        }

    headline = (data.get("headline") or "").strip() if isinstance(data, dict) else ""
    raw_points = data.get("points") if isinstance(data, dict) else None
    raw_points = raw_points if isinstance(raw_points, list) else []
    points = [str(p).strip() for p in raw_points if p]
    # headline 放第一条，方便手机/卡片首屏看到主线
    if headline:
        points.insert(0, headline)

    raw_sources = (data.get("sources") or []) if isinstance(data, dict) else []
    raw_sources = raw_sources if isinstance(raw_sources, list) else [raw_sources]
    sources = []
    for s in raw_sources:
        if not isinstance(s, dict):
            continue
        u = s.get("url") or ""
        if not u.startswith(("http://", "https://")):
            continue
        if "example.com" in u or "example.org" in u:
            continue
        sources.append({"title": str(s.get("title") or "")[:80], "url": u})
    first_url = sources[0]["url"] if sources else ""

    if not points:
        return {
            "type": "card",
            "source": f"旅行规划 · {q[:20]}",
            "points": ["没规划出方案"],
            "error": True,
        }

    return {
        "type": "card",
        "subtype": "travel_plan",  # 前端/口播路径用 subtype 区分卡型
        "source": f"旅行规划 · {q[:20]}",
        "url": first_url,
        "points": points[:6],
        "sources": sources[:5],
    }


# ── 口播文本构建：把卡片要点串成自然中文，末尾追加优化方向反问 ─────────
_OPT_FOLLOWUP = (
    "如果想再细一点，可以告诉我是想省时间、省钱、还是舒适度优先，"
    "我再按那个方向帮你对比一版。"
)


def build_playback(card: dict) -> str:
    """travel_plan 卡片 → 完整口播文本（TTS 用）。
    第一条 points 是 headline，单独成句；其余每条单独一句；末尾追加反问。"""
    points = [str(p or "").strip() for p in (card.get("points") or []) if p]
    if not points:
        return "没规划出方案，要不你换个说法再问我一次？"
    parts: list[str] = []
    for i, p in enumerate(points):
        # 已有句号 / 问号的不再补；否则补句号让 TTS 切句更自然
        if p[-1] not in "。！？.!?；;":
            p = p + "。"
        # 首条前面加引导词，让口播听起来不像念清单
        if i == 0:
            parts.append(p)
        else:
            parts.append(p)
    parts.append(_OPT_FOLLOWUP)
    return " ".join(parts)
