"""讨论群文档检查：只读仓库里的文档，不访问网络、DNS 或 Git 历史。"""

import re
import socket
from pathlib import Path

import pytest

# 模块级导入讨论群代码，保证在基线提交（无 backend/discuss/）上收集阶段直接 ImportError。
from discuss import roles as discuss_roles


ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = (
    "README.md",
    "CLAUDE.md",
    "PLAN.md",
    "docs/ARCHITECTURE.md",
    "docs/DEPLOYMENT.md",
    "backend/.env.example",
)
FIXED_PHRASE = "讨论群（第一期，仅后端）"
LOCAL_PATH = re.compile(r"/Users/|/home/[^\s/]+|[A-Za-z]:[\\/](?![\\/])")
CJK = re.compile(r"[\u4e00-\u9fff]")


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("讨论群文档测试禁止网络与 DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


@pytest.mark.parametrize("path", DOCUMENTS)
def test_each_document_mentions_the_discussion_group(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert FIXED_PHRASE in text, f"{path} 缺少讨论群固定短语"


@pytest.mark.parametrize("path", DOCUMENTS)
def test_documents_contain_no_local_absolute_paths(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert not LOCAL_PATH.search(text), f"{path} 含本机绝对路径"


def test_env_template_declares_discuss_switches_and_defaults():
    text = (ROOT / "backend/.env.example").read_text(encoding="utf-8")
    for name, value in (
        ("FIONA_DISCUSS", "0"),
        ("FIONA_DISCUSS_USERS", ""),
        ("FIONA_DISCUSS_MAX_RUNNING", "2"),
        ("FIONA_DAILY_DISCUSS_GROUPS", "5"),
        ("FIONA_DISCUSS_SEARCH_STRAWBERRIES", "2"),
    ):
        assert re.search(rf"^{name}={re.escape(value)}$", text, re.M), name
    assert re.search(r"^# FIONA_DISCUSS_PRICE_JSON=", text, re.M)

    lines = text.splitlines()
    for name in (
        "FIONA_DISCUSS",
        "FIONA_DISCUSS_USERS",
        "FIONA_DISCUSS_MAX_RUNNING",
        "FIONA_DAILY_DISCUSS_GROUPS",
        "FIONA_DISCUSS_SEARCH_STRAWBERRIES",
        "FIONA_DISCUSS_PRICE_JSON",
    ):
        index = next(i for i, line in enumerate(lines) if name in line)
        comments = [line for line in lines[max(0, index - 2):index] if line.startswith("#")]
        assert any(CJK.search(line) for line in comments), f"{name} 缺少中文说明"


@pytest.mark.parametrize("path", ("README.md", "docs/ARCHITECTURE.md", "CLAUDE.md"))
def test_privacy_sections_cover_vendors_search_avatar_and_keys(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    for phrase in (
        "阿里云百炼",
        "DeepSeek",
        "火山方舟",
        "作者自带的厂商",
        "搜索问题与任务目标发给阿里云百炼",
        "私有长期记忆",
        "群聊上下文",
        "Key 只在调用时读取，不写库、日志或响应",
    ):
        assert phrase in text, f"{path} 隐私说明缺少：{phrase}"
    assert "阿里云百炼" in discuss_roles.PRIVACY_NOTICE


def test_deployment_lists_discuss_settings_and_vendor_alerts():
    text = (ROOT / "docs/DEPLOYMENT.md").read_text(encoding="utf-8")
    for name in (
        "FIONA_DISCUSS",
        "FIONA_DISCUSS_USERS",
        "FIONA_DISCUSS_MAX_RUNNING",
        "FIONA_DAILY_DISCUSS_GROUPS",
        "FIONA_DISCUSS_SEARCH_STRAWBERRIES",
        "FIONA_DISCUSS_PRICE_JSON",
    ):
        assert name in text, name
    assert "讨论群开启后会调用千问、DeepSeek、豆包和千问搜索" in text


def test_claude_md_stays_within_size_limit():
    raw = (ROOT / "CLAUDE.md").read_bytes()
    assert len(raw) <= 69_300, f"CLAUDE.md 为 {len(raw)} 字节"


def test_claude_md_discuss_section_stays_within_1800_bytes():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    marker = "## 讨论群（第一期）"
    start = text.index(marker)
    rest = text[start + len(marker):]
    following = re.search(r"\n## ", rest)
    end = len(text) if following is None else start + len(marker) + following.start() + 1
    assert len(text[start:end].encode("utf-8")) <= 1_800


def test_privacy_notice_and_docs_include_search_fee_sentence():
    """Y5：隐私说明末尾及三份文档都包含联网搜索另扣草莓。"""
    sentence = "联网搜索按次另扣草莓，与成员用哪个模型无关。"
    assert discuss_roles.PRIVACY_NOTICE.endswith(sentence)
    for path in ("README.md", "docs/ARCHITECTURE.md", "CLAUDE.md"):
        assert sentence in (ROOT / path).read_text(encoding="utf-8"), path
