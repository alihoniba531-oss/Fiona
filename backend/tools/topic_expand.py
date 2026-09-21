# -*- coding: utf-8 -*-
"""
热点话题展开：传入热搜标题 → 千问 enable_search 联网搜索 → 返回结构化展开。

用于广场页"点开一个热点话题查看详情"——比单纯弹一个原链接信息密度高、
对用户更友好（很多热搜源页面是搜索页，没有内容）。

sources 不让 LLM 自己输出 URL（之前千问会编 caixin.com/404/index.html 这种死链），
改用 dashscope 原生 HTTP 接口的 output.search_info.search_results —— 那是百度/必应
真实搜过的链接，URL 可靠。OpenAI 兼容模式不暴露 search_info，所以必须走原生接口。
"""
import json
import os
import re
import urllib.request
from datetime import datetime

from utils.safe_http import request_public_url

DASHSCOPE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"


def _request_search(messages: list[dict], api_key: str, *, max_tokens: int = 900) -> dict:
    """Use the native search response so sources come from search_info, not model URLs."""
    body = {
        "model": "qwen-plus",
        "input": {"messages": messages},
        "parameters": {
            "result_format": "message",
            "enable_search": True,
            "search_options": {
                "forced_search": True,
                "enable_source": True,
                "enable_citation": True,
            },
            "max_tokens": max_tokens,
            "temperature": 0.3,
        },
    }
    req = urllib.request.Request(
        DASHSCOPE_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Search response too large")
    return json.loads(raw)


def _build_expand_prompt() -> str:
    now = datetime.now()
    today_str = f"{now.year}年{now.month}月{now.day}日"
    return f"""你是热点话题解读者。用户给你一个**今天**上了微博/抖音/B站/头条热搜的话题标题，
你联网搜索后，把这件**正在发生**的事讲清楚。

【今日日期：{today_str}】

【核心原则——锁定时效】
- 这个话题**今天**在热搜上，所以一定有**最近 7 天内**的新闻报道在搜索结果里
- 你只挑选**{now.year} 年的新闻报道**作答；如果搜到的都是往年同名事件（比如往年的"浪姐淘汰"/"XX 道歉"/"XX 离婚"），
  **不要**用旧事件填充——往年的事情不可能今天才上热搜，肯定是新的一茬
- 真要碰到训练记忆与搜索结果矛盾，**信搜索结果，不要信训练记忆**
- 如果搜来搜去只有几年前的旧闻，就老实在 summary 写"未找到今年的新报道"，其余字段留空——
  **宁可空，不要拿旧事件糊弄**

【输出格式 - 严格 JSON，不加 markdown 围栏不加任何其他文字】
{{
  "summary": "一句话讲清楚发生了什么（30-60 字）",
  "whats_happening": "这件事是什么，2-4 句具体陈述事实，含人物/时间/地点/数字",
  "why_trending": "为什么上热搜，1-2 句指出引爆点（争议/反转/情感共鸣等）",
  "key_facts": ["关键事实1（具体到数字/时间）", "关键事实2", "关键事实3"],
  "background": "如果有前因后果或上下文，1-2 句补充；没有就留空字符串"
}}

【规则】
- whats_happening 必须含明确日期/时间（{now.year} 年内），不能含糊"近日"
- 全部用第三人称、中性陈述，不评价不站队
- key_facts 必须具体（带数字/时间/姓名），不要"广泛关注"这种空话
- 如果是娱乐/八卦类，也只陈述公开事实，不演绎不脑补
- **不要在输出里写来源链接** —— 来源由系统自动从真实搜索结果附加，你只管讲事实
- 不输出 markdown、不加 ```json 围栏
"""


def topic_expand(title: str) -> dict:
    """把一个热搜标题展开成结构化内容卡。

    返回:
      {
        "title": "...",           # 原标题
        "summary": "...",
        "whats_happening": "...",
        "why_trending": "...",
        "key_facts": [...],
        "background": "...",
        "sources": [{title, url, site_name}, ...],   # 真实搜索结果，非 LLM 编
        "error": "..."            # 仅失败时存在
      }
    """
    title = (title or "").strip()
    if not title:
        return {"title": "", "error": "标题为空"}

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return {"title": title, "error": "DASHSCOPE_API_KEY 未设置"}

    now = datetime.now()
    messages = [
        {"role": "system", "content": _build_expand_prompt()},
        {
            "role": "user",
            "content": (
                f"今天是 {now.year} 年 {now.month} 月 {now.day} 日。"
                f"刚刚上微博/抖音/B站/头条热搜的话题是：『{title}』。"
                f"用联网搜索查最近 7 天内关于这个话题的新闻，把这件事讲清楚。"
                f"如果搜到的全是往年同名事件，请忽略往年的、只保留今年的；"
                f"实在没今年的就告诉我没有，不要拿旧的糊弄。"
            ),
        },
    ]

    try:
        resp = _request_search(messages, api_key)
    except Exception as e:
        return {"title": title, "error": type(e).__name__}

    output = resp.get("output", {})
    choices = output.get("choices") or []
    if not choices:
        return {"title": title, "error": "模型无 choices 返回",
                "raw": json.dumps(resp, ensure_ascii=False)[:300]}
    content = ((choices[0].get("message") or {}).get("content") or "").strip()

    # 千问偶尔会在 JSON 外面包 ```json ... ```，剥一下
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    try:
        data = json.loads(content)
    except Exception:
        return {"title": title, "error": "模型返回不是合法 JSON", "raw": content[:300]}

    # 真实搜索结果（百度/必应等返回，非 LLM 编）
    search_results = (output.get("search_info") or {}).get("search_results") or []
    sources = [
        {
            "title": s.get("title", "") or "",
            "url": s.get("url", "") or "",
            "site_name": s.get("site_name", "") or "",
        }
        for s in search_results
        if s.get("url")
    ]
    # 兜底死链校验——绝大多数搜索结果应该是活的，但偶发文章删档/站点抽风也可能死
    sources = _verify_source_urls(sources)

    return {
        "title": title,
        "summary": data.get("summary", ""),
        "whats_happening": data.get("whats_happening", ""),
        "why_trending": data.get("why_trending", ""),
        "key_facts": data.get("key_facts", []) or [],
        "background": data.get("background", ""),
        "sources": sources,
    }


def _verify_source_urls(sources: list[dict]) -> list[dict]:
    """并发 HEAD 验证 source URL 是否真实可达。
    千问 enable_search 偶尔会编看似合理但不存在的链接（典型大模型幻觉），
    这里把死链的 url 清空（保留 title），前端就只显示标题不渲染点击。

    死链识别有两层：
      1. URL path 含 404/error/notfound 等关键词 → 直接判死（不发请求）
         例：https://other.caixin.com/404/index.html — LLM 把站点 404 落地页当文章链接
      2. HEAD/GET 跟随重定向，最终 status_code < 400 且最终 URL 不命中第 1 层
         （处理"302 跳到 /error" 这种软 404）
    """
    import re
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import urlparse

    # 命中即判死的路径关键词。要求关键词后跟分隔符或行尾，避免误伤 /articles/4042 这种
    _DEAD_RE = re.compile(r"/(?:404|error|notfound|not-found|page-not-found)(?:[/.?#]|$)")

    def looks_like_dead_landing(url: str) -> bool:
        try:
            path = (urlparse(url).path or "").lower()
            return bool(_DEAD_RE.search(path))
        except Exception:
            return False

    def is_alive(url: str) -> bool:
        if not url or not url.startswith(("http://", "https://")):
            return False
        if looks_like_dead_landing(url):
            return False
        try:
            # 先 HEAD；某些站点 HEAD 405，退一步用 Range GET 拿头几字节
            for method in ("HEAD", "GET"):
                response = request_public_url(
                    method,
                    url,
                    timeout=4,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Range": "bytes=0-0" if method == "GET" else "",
                    },
                    max_bytes=0,
                    follow_redirects=True,
                    max_redirects=3,
                )
                if response.status_code < 400:
                    # 软 404：服务端 302 跳到 /404 落地页但 HTTP 200 — 用最终 URL 再判一次
                    final_url = response.url or url
                    if looks_like_dead_landing(final_url):
                        return False
                    return True
                if response.status_code != 405:  # 不是 method not allowed 就不重试
                    return False
            return False
        except Exception:
            return False

    if not sources:
        return []
    urls = [s.get("url", "") for s in sources]
    with ThreadPoolExecutor(max_workers=6) as ex:
        alive = list(ex.map(is_alive, urls))
    return [
        {**s, "url": s.get("url", "") if ok else ""}
        for s, ok in zip(sources, alive)
    ]
