"""Check the six agent-mode documents without reading Git history or the network."""

import re
import socket
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = (
    "README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md",
    "docs/DEPLOYMENT.md", "backend/.env.example",
)


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Claude agent documentation tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


@pytest.mark.parametrize("path", DOCUMENTS)
def test_all_documents_explain_agent_conditions_data_billing_limits_and_caveats(path):
    text = (ROOT / path).read_text()
    for phrase in (
        "Claude 智能体模式", "FIONA_CLAUDE_AGENT", "FIONA_CLAUDE_AGENT_TOTAL_SECONDS",
        "chat", "anthropic", "high", "possible", "零余额",
        "图片和工具结果", "Anthropic", "联网搜索", "用户额度",
        "10 颗", "退款", "stale", "本轮用户原文", "最近 3 条 user",
        "4 次", "240 秒", "8000 字", "每轮一张图", "历史图片",
        "镜子模式不带工具", "危机轮不进入智能体模式", "卡片不落库",
    ):
        assert phrase in text, f"{path} is missing {phrase}"
    assert not re.search(r"/Users/|/home/[^\s]+|[A-Z]:\\(?:Users|Documents)\\", text)


def test_env_template_declares_switch_and_agent_budget_defaults():
    text = (ROOT / "backend/.env.example").read_text()
    assert re.search(r"^FIONA_CLAUDE_AGENT=1$", text, re.M)
    assert re.search(r"^FIONA_CLAUDE_AGENT_TOTAL_SECONDS=240$", text, re.M)
    assert "60–290" in text


@pytest.mark.parametrize("path", DOCUMENTS)
def test_r1_documents_explain_persistence_city_variants_image_copy_and_errors(path):
    text = (ROOT / path).read_text()
    for phrase in (
        "落库成功后才结算", "未落库的计费项退款", "行政后缀", "匹配到的主人原文",
        "长边不超过 2000 像素", "3.5MB", "质量 85", "上传落盘文件不变",
        "agent_tool_errors", "两段文字之间", "首个全局槽", "来源卡",
    ):
        assert phrase in text, f"{path} is missing R1 detail: {phrase}"
    assert "eager_input_streaming" not in text
