"""只规范化用户明确给出的城市文字，不猜测城市或访问城市库。"""
import re
import unicodedata


_CITY = re.compile(r"^[一-鿿]{2,10}$")
_PREFIXES = ("查一下", "换成", "改成", "在", "是", "查", "就", "那", "去")
_SUFFIXES = ("的天气", "天气", "吧", "呢", "啊", "呀", "的")
_SENTENCE_PREFIXES = (
    "帮我", "帮忙", "请", "给我", "我想", "我要", "我们", "我", "你",
    "能不能", "能否", "可以", "可不可以", "怎么", "为什么", "什么", "搜",
    "再", "顺便", "另外", "还有", "告诉我", "说说", "讲讲", "看看",
)
_SENTENCE_SUBSTRINGS = ("吗", "么", "一下", "新闻", "帮我", "搜索", "告诉", "推荐", "请问")


def _strip_edges(text: str) -> str:
    start, end = 0, len(text)
    while start < end and (text[start].isspace() or unicodedata.category(text[start]).startswith("P")):
        start += 1
    while end > start and (text[end - 1].isspace() or unicodedata.category(text[end - 1]).startswith("P")):
        end -= 1
    return text[start:end]


def normalize_city(text: str) -> str:
    """重复剥离口语前后缀，拒绝指定句式，只接受 2–10 个连续汉字。"""
    if not isinstance(text, str):
        return ""
    city = _strip_edges(text)
    while True:
        previous = city
        # 先剥完后缀，让「那曲啊的天气」的两字地名也受到长度护栏保护。
        while True:
            previous_suffix = city
            for suffix in _SUFFIXES:
                if city.endswith(suffix):
                    candidate = _strip_edges(city[:-len(suffix)])
                    if len(candidate) >= 2:
                        city = candidate
                    break
            if city == previous_suffix:
                break
        for prefix in _PREFIXES:
            if city.startswith(prefix):
                candidate = _strip_edges(city[len(prefix):])
                if len(candidate) >= 2:
                    city = candidate
                break
        if city == previous:
            if city.startswith(_SENTENCE_PREFIXES) or any(part in city for part in _SENTENCE_SUBSTRINGS):
                return ""
            return city if _CITY.fullmatch(city) else ""
