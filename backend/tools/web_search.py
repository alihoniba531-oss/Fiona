# -*- coding: utf-8 -*-
"""
搜索关键词，返回卡片(3-5 条要点)。

v0.3: 用通义千问 enable_search 替代 Playwright + VL 截图方案。
原因：云服务器 IP 直接出门访问百度/Bing/DDG 普遍被反爬拦截，截图截到的
都是验证码/挑战页，VL 看完只能说"没搜到"。千问 enable_search 走的是阿里云
内部的搜索通道，IP 干净、命中率高，还自带要点提炼。

天气走专门的 wttr.in 直通车（保留 visual_search 里的实现）。
"""
import json
import os
import re
from datetime import datetime
from openai import OpenAI


_search_client_cache = None
def _get_client():
    global _search_client_cache
    if _search_client_cache is None:
        _search_client_cache = OpenAI(
            api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _search_client_cache


_SEARCH_PROMPT = """你是一个搜索结果整理器。你需要联网搜索用户问题，并把答案整理成结构化要点。

【输出格式 - 严格 JSON，不加任何其他文字】
{
  "points": ["要点1", "要点2", "要点3"],
  "sources": [{"title": "来源标题", "url": "https://..."}]
}

【规则】
- points: 3-5 条，每条具体到事实/数字/时间/地点，不要笼统空话
- 如果是航班/票务/天气类，给出具体数字（价格、时间、温度等）
- 如果搜不到任何信息，points 写 ["没搜到相关信息"]，sources 留空数组
- 不要列出网站名，points 里直接给答案；sources 单独放原始链接
- sources 里的 url **必须是搜索结果里出现的真实 URL**，不要写 example.com 或者编造网址；
  如果记不准真实 URL，就把这一项删掉，宁可 sources 为空也别假
- 不输出 markdown、不加 ```json 围栏，直接 JSON 对象
"""


def _today_directive() -> str:
    """注入"今天日期 + 禁止过期措辞"指令 —— 防止模型按训练截止时段输出
    核酸/健康宝/绿码这种已废止的疫情措辞，或用陈年价格/政策回答。"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    weekday = "周" + "一二三四五六日"[now.weekday()]
    return (
        f"\n\n【时效性 — 必须遵守】\n"
        f"- 今天是 {today}（{weekday}），不是你训练数据里的某个过去时刻。\n"
        f"- 中国境内疫情管控自 2023 年初已全面取消，**禁止提及**核酸检测、健康宝、"
        f"绿码、行程卡、隔离观察、48 小时阴性证明等已废止措辞。\n"
        f"- 价格、政策、班次、官方流程必须用联网搜索的最新结果，不要照搬训练数据里的旧版本。"
    )


def web_search(query: str) -> dict:
    """走通义千问 enable_search 搜索，返回卡片 dict。

    出口卡片形状（前端契约）：
      { type: "card", source: "搜索:XX", url: "...", points: [...] }
    """
    if not query or not query.strip():
        return {"type": "card", "source": "搜索", "points": ["没说要搜啥"], "error": True}
    query = query.strip()

    # 天气仍走 wttr.in（更准、更快、有结构化字段供前端渲染天气卡）
    if "天气" in query:
        from tools.visual_search import _search_weather_direct
        card = _search_weather_direct(query)
        if card:
            return card

    client = _get_client()
    try:
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": _SEARCH_PROMPT + _today_directive()},
                {"role": "user", "content": f"搜索：{query}"},
            ],
            extra_body={"enable_search": True},
            max_tokens=700,
            temperature=0.2,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": [f"搜索失败:{type(e).__name__}", str(e)[:120]],
            "error": True,
        }

    # 容错：模型偶尔在 JSON 前后加 ``` 围栏或解释
    m = re.search(r"\{[\s\S]*\}", content)
    if m:
        content = m.group(0)
    try:
        data = json.loads(content)
    except Exception:
        # 不是 JSON 就按行切作 fallback
        lines = [l.strip("•- \t").strip() for l in content.split("\n") if l.strip()]
        lines = [l for l in lines if l and not l.startswith(("{", "}", '"'))]
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": lines[:5] or ["没搜到"],
        }

    points = [str(p).strip() for p in data.get("points", []) if p]
    # 千问偶尔会给 example.com 这种占位 URL，过滤掉假链接，避免误导用户点开
    raw_sources = data.get("sources") or []
    sources = []
    for s in raw_sources:
        u = (s or {}).get("url") or ""
        if not u.startswith(("http://", "https://")):
            continue
        if "example.com" in u or "example.org" in u:
            continue
        sources.append({"title": str((s or {}).get("title") or "")[:80], "url": u})
    first_url = sources[0]["url"] if sources else ""

    if not points:
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": ["没搜到"],
            "error": True,
        }

    return {
        "type": "card",
        "source": f"搜索:{query[:20]}",
        "url": first_url,
        "points": points[:5],
        "sources": sources[:5],  # 前端将来想展示来源列表也能用
    }
