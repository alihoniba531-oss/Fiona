# -*- coding: utf-8 -*-
"""
搜索关键词，返回卡片(3-5 条要点)。

v0.3: 用通义千问 enable_search 替代 Playwright + VL 截图方案。
原因：云服务器 IP 直接出门访问百度/Bing/DDG 普遍被反爬拦截，截图截到的
都是验证码/挑战页，VL 看完只能说"没搜到"。千问 enable_search 走的是阿里云
内部的搜索通道，IP 干净、命中率高，还自带要点提炼。

"""
import re
from tools import native_search
from utils.beijing_time import beijing_now


_SEARCH_PROMPT = """你是一个搜索结果整理器。你需要联网搜索用户问题，并把答案整理成结构化要点。

【输出格式 - 严格 JSON，不加任何其他文字】
{
  "success": true,
  "points": ["要点1", "要点2", "要点3"]
}

【规则】
- success: 只有搜到可用的具体信息时才为 true；没有结果、搜索失败或无法核实内容时为 false
- points: 3-5 条，每条具体到事实/数字/时间/地点，不要笼统空话
- 如果是航班/票务/天气类，给出具体数字（价格、时间、温度等）
- 如果搜不到任何信息，points 写 ["没搜到相关信息"]
- 不要列出网站名，points 里直接给答案
- 不要输出任何 URL、链接或来源列表，来源由系统根据真实搜索结果附加
- 不输出 markdown、不加 ```json 围栏，直接 JSON 对象
"""


def _today_directive() -> str:
    """注入"今天日期 + 禁止过期措辞"指令 —— 防止模型按训练截止时段输出
    核酸/健康宝/绿码这种已废止的疫情措辞，或用陈年价格/政策回答。"""
    now = beijing_now()
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

    result = native_search.grounded_search([
        {"role": "system", "content": _SEARCH_PROMPT + _today_directive()},
        {"role": "user", "content": f"搜索：{query}"},
    ], max_tokens=700)
    if result["error"]:
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": [f"搜索失败:{result['error']}"],
            "error": True,
        }

    data = result["data"]
    if data is None:
        # 不是 JSON 就按行切作 fallback
        content = result["raw"]
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            content = match.group(0)
        lines = [native_search.strip_urls(native_search.strip_citations(line)).strip("•- \t").strip()
                 for line in content.split("\n")]
        lines = [l for l in lines if l and not l.startswith(("{", "}", '"'))]
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": lines[:5] or ["没搜到"],
            "error": True,
        }

    raw_points = data.get("points")
    raw_points = raw_points if isinstance(raw_points, list) else []
    points = [native_search.strip_urls(native_search.strip_citations(str(point)))
              for point in raw_points
              if isinstance(point, (str, int, float)) and not isinstance(point, bool)]
    points = [point for point in points if point][:5]
    sources = result["sources"]

    if not points:
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": ["没搜到"],
            "error": True,
        }

    if not sources:
        return {
            "type": "card",
            "source": f"搜索:{query[:20]}",
            "points": ["没搜到可核实的来源，换个说法再试试"],
            "error": True,
        }

    return {
        "type": "card",
        "source": f"搜索:{query[:20]}",
        "url": sources[0]["url"],
        "points": points,
        "sources": sources,
        "error": data.get("success") is not True,
    }
