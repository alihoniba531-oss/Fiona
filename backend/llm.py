# -*- coding: utf-8 -*-
import os

from dotenv import load_dotenv
from openai import OpenAI

from model_router import choose_model, token_budget

# ─── 括号旁白过滤器 ───
# 历史上 DeepSeek 角色扮演本能加 "（动作描述）"、prompt 禁不住，只能在流式输出里硬过滤；
# 主力大脑换掉后这层兜底保留（任何模型触发都无害）。
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

# 主脑与轻量槽现都在百炼 DashScope；保留两个 client 按路由槽命名，
# 将来某个槽换供应商只改这里。
client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# ── 模型路由槽配置 ──────────────────────────────────────────
MAIN_MODEL      = "qwen3.8-max"   # 主力大脑（原 DeepSeek deepseek-chat）
# qwen3.8-max 默认开思考模式：JSON 小槽位的思考会吃光小额 max_tokens
# 预算并弄脏 JSON 输出；聊天槽位则徒增首字延迟。统一关掉。
MAIN_EXTRA_BODY = {"enable_thinking": False}
QWEN_CLIENT    = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
QWEN_MODEL     = "qwen-plus"



def _create_stream_with_fallback(use_qwen: bool, messages: list, **kwargs):
    """
    轻量槽走通义 qwen-plus，失败自动回退主力大脑 qwen3.8-max。
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
        model=MAIN_MODEL,
        messages=messages,
        stream=True,
        extra_body=MAIN_EXTRA_BODY,
        **kwargs,
    )
    return stream, False
