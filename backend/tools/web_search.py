# -*- coding: utf-8 -*-
"""
搜索关键词,返回卡片(3-5 条要点)。
v0.2: 用 Playwright 真浏览器 + 通义千问 VL 看搜索结果截图,完美绕过反爬。
不打开浏览器——信息向人来,人不离菲欧娜。
"""
from tools.visual_search import visual_search


def web_search(query: str) -> dict:
    """搜索关键词,返回卡片 dict"""
    return visual_search(query)
