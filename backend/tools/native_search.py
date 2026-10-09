"""Shared native search parsing; links come only from provider search results."""
import json
import os
import re

from tools.card_detail import _search_sources
from tools.topic_expand import _request_search


_CITATION_PATTERN = r"\[(\d+(?:\s*[,，、]\s*\d+)*)\]"


def grounded_search(messages: list[dict], *, max_tokens: int, max_sources: int = 5) -> dict:
    """Return parsed model data alongside separately grounded native sources."""
    result = {"data": None, "raw": "", "sources": [], "error": None}
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        result["error"] = "missing_key"
        return result

    try:
        response = _request_search(messages, api_key, max_tokens=max_tokens)
        output = response.get("output") if isinstance(response, dict) else None
        choices = output.get("choices") if isinstance(output, dict) else None
        choice = choices[0] if isinstance(choices, list) and choices else None
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            result["error"] = "bad_response"
            return result
        result["raw"] = content
        if choice.get("finish_reason") == "length":
            result["error"] = "truncated"
            return result

        # Keep the existing tolerance for JSON surrounded by prose or fences.
        match = re.search(r"\{[\s\S]*\}", content)
        try:
            data = json.loads(match.group(0) if match else content)
        except Exception:
            data = None
        result["data"] = data if isinstance(data, dict) else None

        groups = re.findall(_CITATION_PATTERN, content)
        cited = {int(index) for group in groups for index in re.findall(r"\d+", group)}
        info = output.get("search_info")
        search_results = info.get("search_results") if isinstance(info, dict) else None
        normalized = []
        for source in search_results if isinstance(search_results, list) else []:
            if not isinstance(source, dict):
                continue
            source = source.copy()
            index = source.get("index")
            if type(index) is int:
                pass
            elif isinstance(index, str) and re.fullmatch(r"\d+", index):
                source["index"] = int(index)
            else:
                source.pop("index", None)
            normalized.append(source)

        sources = _search_sources({"search_info": {"search_results": normalized}}, cited)
        result["sources"] = [
            {"title": source["title"][:80], "url": source["url"],
             "site_name": source["site_name"],
             **({"index": source["index"]} if "index" in source else {})}
            for source in sources[:max_sources]
        ]
        return result
    except Exception as error:
        # Provider bodies can contain credentials or untrusted URLs.
        return {"data": None, "raw": "", "sources": [], "error": type(error).__name__}


def strip_citations(text: str) -> str:
    """Remove numeric/reference footnotes while keeping descriptive brackets."""
    text = re.sub(r"\[(?:\d+(?:\s*[,，、]\s*\d+)*|ref_\d+)\]", "", text)
    text = re.sub(r"[ \t]+([，。！？；：、）】》」』…])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def strip_urls(text: str) -> str:
    """Keep Markdown link labels and remove model-written bare web URLs."""
    parts = []
    cursor = 0
    for link in re.finditer(r"\[([^\]\n]*)\]\(", text):
        if link.start() < cursor:
            continue
        end = link.end()
        depth = 1
        # URL destinations can contain parentheses, e.g. javascript:alert(1).
        while end < len(text) and depth and text[end] != "\n":
            if text[end] == "(":
                depth += 1
            elif text[end] == ")":
                depth -= 1
            end += 1
        if depth == 0:
            parts.extend((text[cursor:link.start()], link.group(1)))
            cursor = end
    text = "".join(parts) + text[cursor:]
    text = re.sub(r"(?:https?://|www\.)[^\s，。！？；：、）】》」』]*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+([，。！？；：、）】》」』…])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
