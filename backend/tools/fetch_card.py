# -*- coding: utf-8 -*-
"""
读取网页主要内容,用 LLM 提炼成 3-5 条要点。返回卡片数据 dict。
不打开浏览器——信息向人来,人不离自己的道场。
"""
import json
import re
import os
import socket
import ipaddress
import requests
from urllib.parse import urlparse
from openai import OpenAI
from bs4 import BeautifulSoup


# 常见网站的友好名称
_SOURCE_MAP = {
    "weibo.com": "微博",
    "s.weibo.com": "微博",
    "zhihu.com": "知乎",
    "bilibili.com": "B站",
    "jd.com": "京东",
    "taobao.com": "淘宝",
    "tmall.com": "天猫",
    "sina.com.cn": "新浪",
    "news.sina.com.cn": "新浪新闻",
    "qq.com": "腾讯",
    "news.qq.com": "腾讯新闻",
    "36kr.com": "36氪",
    "ithome.com": "IT之家",
    "thepaper.cn": "澎湃新闻",
    "douban.com": "豆瓣",
    "xiaohongshu.com": "小红书",
    "163.com": "网易",
    "sohu.com": "搜狐",
}

_client_cache = None
def _get_client():
    global _client_cache
    if _client_cache is None:
        _client_cache = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url="https://api.deepseek.com",
        )
    return _client_cache


def _detect_source(url: str) -> str:
    """从 URL 提取友好的来源名"""
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        for domain, name in _SOURCE_MAP.items():
            if host == domain or host.endswith("." + domain):
                return name
        return host or "网页"
    except Exception:
        return "网页"


def _is_url(s: str) -> bool:
    """判断输入是 URL 还是搜索关键词"""
    s = s.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return True
    if re.match(r"^[\w-]+\.[a-z]{2,}", s, re.I):  # 像 baidu.com 这种
        return True
    return False


# 显式拉黑的元数据 IP:阿里云 100.100.100.200 在 100.64/10 运营商共享段,
# is_private 不一定覆盖,务必显式拦;169.254.169.254 是云厂商通用元数据地址。
_BLOCKED_IPS = {"100.100.100.200", "169.254.169.254"}


def _guard_url(url: str) -> None:
    """SSRF 防护:抓取用户给的任意 URL 前必须先过这关,否则攻击者能让服务器
    去访问云元数据(泄露 RAM 临时凭据)、本机/内网服务、做内网横向探测。
    校验对象是补全 scheme 之后、最终真正要请求的 URL。不合法直接抛 ValueError,
    由上层 fetch_card 的 try/except 接住转成『读不到这个网页』卡片。"""
    parsed = urlparse(url)
    # 1. 只允许 http / https
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不允许的 scheme: {parsed.scheme}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL 没有主机名")
    # 2. 把主机名解析成所有 IP,逐个判断;只要有一个落在危险范围就拒绝
    #    (防 DNS 多记录绕过:一条指白名单、另一条指内网)
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception as e:
        raise ValueError(f"DNS 解析失败: {e}")
    for info in infos:
        ip_str = info[4][0]
        # IPv4-mapped IPv6(如 ::ffff:127.0.0.1)还原成 IPv4 再判,避免绕过
        ip = ipaddress.ip_address(ip_str)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if str(ip) in _BLOCKED_IPS:
            raise ValueError(f"目标 IP 命中黑名单: {ip}")
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_unspecified or ip.is_multicast):
            raise ValueError(f"目标 IP 落在禁止范围: {ip}")


def _fetch_html(url: str, timeout: int = 8) -> str:
    """抓取网页 HTML"""
    if not url.startswith("http"):
        url = "https://" + url
    # SSRF 校验必须在补全 scheme 之后、真正发请求之前
    _guard_url(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    # 关闭重定向:卡片场景不需要跟随跳转,且能防『先给白名单 URL,再 302 跳内网』绕过
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=False)
    # 站点 301/302 时不跟随,直接当读不到(避免被跳板绕过 SSRF 校验)
    if resp.is_redirect or resp.is_permanent_redirect:
        raise ValueError(f"目标返回重定向({resp.status_code}),不跟随")
    resp.raise_for_status()
    if resp.encoding == "ISO-8859-1":  # requests 误判时用 chardet 猜
        resp.encoding = resp.apparent_encoding
    return resp.text


def _extract_main_text(html: str, max_chars: int = 5000) -> str:
    """从 HTML 提取主要文本——去掉脚本/样式/导航/页脚"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "iframe"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{2,}", "\n", text)
    return text[:max_chars]


def _summarize_points(text: str, source: str) -> list:
    """用 LLM 提炼成 3-5 条要点"""
    prompt = (
        f"下面是从网页抓到的文本(来源:{source})。\n"
        "请提炼成 **3-5 条要点**,每条 1-2 句,告诉用户这页的核心信息。\n"
        "要求:\n"
        "- 客观、具体、不评价\n"
        "- 不堆砌、不重复\n"
        "- 商品页:商品是什么、价格、卖点\n"
        "- 新闻页:事件、关键人物、影响\n"
        "- 社交内容:话题、主要观点、为什么火\n"
        "\n"
        "输出 JSON: {\"points\": [\"要点1\", \"要点2\", ...]}\n"
        "只输出 JSON,不要任何其他文字。\n"
        "\n"
        "网页文本:\n" + text
    )
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        points = data.get("points", [])
        cleaned = [str(p).strip() for p in points if p]
        return cleaned[:5] if cleaned else ["页面读到了,但没提炼出要点"]
    except Exception as e:
        return [f"提炼失败:{e}"]


def fetch_card(query: str) -> dict:
    """主入口:输入查询(URL 或关键词),返回卡片数据"""
    if not query:
        return {"type": "card", "source": "", "points": ["没指定要看哪个网页"], "error": True}
    query = query.strip()

    # v0.1: 只支持具体 URL,纯关键词暂时回退提示
    if not _is_url(query):
        return {
            "type": "card",
            "source": "提示",
            "points": [
                "v0.1 暂时只能读具体网址",
                f"你说的『{query}』,给我个 URL 我就能读(比如 https://...)",
            ],
            "error": True,
        }

    url = query if query.startswith("http") else "https://" + query
    source = _detect_source(url)
    try:
        html = _fetch_html(url)
    except Exception as e:
        return {
            "type": "card",
            "source": source,
            "points": [f"读不到这个网页:{type(e).__name__}", "可能是需要登录、被反爬、或网络问题"],
            "error": True,
        }

    text = _extract_main_text(html)
    if len(text) < 50:
        return {
            "type": "card",
            "source": source,
            "points": ["主内容抓不到(可能是 SPA / JS 动态加载)"],
            "error": True,
        }

    points = _summarize_points(text, source)
    return {
        "type": "card",
        "source": source,
        "url": url,
        "points": points,
    }
