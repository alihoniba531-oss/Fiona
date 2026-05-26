# -*- coding: utf-8 -*-
"""
热点话题展开：传入热搜标题 → 千问 enable_search 联网搜索 → 返回结构化展开。

用于广场页"点开一个热点话题查看详情"——比单纯弹一个原链接信息密度高、
对用户更友好（很多热搜源页面是搜索页，没有内容）。
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
  "background": "如果有前因后果或上下文，1-2 句补充；没有就留空字符串",
  "sources": [{{"title": "来源标题", "url": "https://..."}}]
}}

【规则】
- whats_happening 必须含明确日期/时间（{now.year} 年内），不能含糊"近日"
- 全部用第三人称、中性陈述，不评价不站队
- key_facts 必须具体（带数字/时间/姓名），不要"广泛关注"这种空话
- 如果是娱乐/八卦类，也只陈述公开事实，不演绎不脑补
- sources 里 url 必须是搜索结果中出现的真实链接，记不准就删，宁可空也不假
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
        "sources": [{title, url}, ...],
        "error": "..."            # 仅失败时存在
      }
    """
    title = (title or "").strip()
    if not title:
        return {"title": "", "error": "标题为空"}

    client = _get_client()
    now = datetime.now()
    try:
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[
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
            ],
            extra_body={"enable_search": True},
            max_tokens=900,
            temperature=0.3,
        )
        content = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return {"title": title, "error": f"{type(e).__name__}:{str(e)[:120]}"}

    # 千问偶尔会在 JSON 外面包 ```json ... ```，剥一下
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    try:
        data = json.loads(content)
    except Exception:
        return {"title": title, "error": "模型返回不是合法 JSON", "raw": content[:300]}

    sources = data.get("sources", []) or []
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
    这里把死链的 url 清空（保留 title），前端就只显示标题不渲染点击。"""
    import requests
    from concurrent.futures import ThreadPoolExecutor

    def is_alive(url: str) -> bool:
        if not url or not url.startswith(("http://", "https://")):
            return False
        try:
            # 先 HEAD；某些站点 HEAD 405，退一步用 Range GET 拿头几字节
            for method in ("HEAD", "GET"):
                r = requests.request(
                    method,
                    url,
                    timeout=4,
                    allow_redirects=True,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Range": "bytes=0-0" if method == "GET" else "",
                    },
                    stream=(method == "GET"),
                )
                if r.status_code < 400:
                    return True
                if r.status_code != 405:  # 不是 method not allowed 就不重试
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
