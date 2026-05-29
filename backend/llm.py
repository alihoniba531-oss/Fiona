# -*- coding: utf-8 -*-
import os

from dotenv import load_dotenv
from openai import OpenAI

from model_router import choose_model, token_budget

# ─── 括号旁白过滤器 ───
# DeepSeek 角色扮演时本能加 "（动作描述）"，prompt 禁令屡禁不止——只能在流式输出里硬过滤。
# 流式状态机：遇到 ( 或 （ 进入吞字状态，遇到 ) 或 ） 退出。同时丢弃过滤后开头的孤立空白。
class BracketFilter:
    def __init__(self):
        self.in_bracket = False
        self.has_emitted_non_whitespace = False

    def filter_chunk(self, text: str) -> str:
        result = []
        for ch in text:
            if self.in_bracket:
                if ch in '）)':
                    self.in_bracket = False
                continue
            if ch in '（(':
                self.in_bracket = True
                continue
            # 第一个非空白之前的空白(过滤后的空头)都丢弃
            if not self.has_emitted_non_whitespace and ch.isspace():
                continue
            if not ch.isspace():
                self.has_emitted_non_whitespace = True
            result.append(ch)
        return "".join(result)


_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=_env_path, override=True)

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# ── 模型路由槽配置 ──────────────────────────────────────────
DEEPSEEK_MODEL = "deepseek-chat"
QWEN_CLIENT    = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
QWEN_MODEL     = "qwen-plus"



def _create_stream_with_fallback(use_qwen: bool, messages: list, **kwargs):
    """
    轻量槽走通义 qwen-plus，失败自动回退 DeepSeek。
    返回 (stream, actually_used_qwen)
    """
    if use_qwen:
        try:
            stream = QWEN_CLIENT.chat.completions.create(
                model=QWEN_MODEL,
                messages=messages,
                stream=True,
                **kwargs,
            )
            return stream, True
        except Exception:
            pass
    stream = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        stream=True,
        **kwargs,
    )
    return stream, False
