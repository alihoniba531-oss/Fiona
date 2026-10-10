"""Public configuration and privacy contract for chat image tools."""

from pathlib import Path
import socket
import subprocess

import pytest

from persona import AGENT_IDENTITY_RULES


ROOT = Path(__file__).resolve().parents[2]


def git_baseline(path, **kwargs):
    """Read a file at the task baseline; CI's shallow checkout lacks that commit."""
    try:
        return subprocess.check_output(
            ["git", "show", f"7ac7b57:{path}"], text=True, stderr=subprocess.DEVNULL, **kwargs,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("基线提交 7ac7b57 不在本地 git 历史中（如 CI 浅克隆），跳过基线比对")


@pytest.fixture(autouse=True)
def offline_network_guard(monkeypatch):
    def guarded(original):
        def connect(sock, *args, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                raise AssertionError("R2 documentation tests prohibit real connections")
            return original(sock, *args, **kwargs)
        return connect

    def no_dns(*args, **kwargs):
        raise AssertionError("R2 documentation tests prohibit real DNS")

    monkeypatch.setattr(socket.socket, "connect", guarded(socket.socket.connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(socket.socket.connect_ex))
    monkeypatch.setattr(socket, "getaddrinfo", no_dns)


def test_persona_names_both_image_models_without_claiming_completion(monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    assert "当前聊天可以按文字描述生成图片（可选 Seedream 5.0 Flash 或 Qwen Image 3.0）" in AGENT_IDENTITY_RULES
    assert "只有实际收到生成结果时才说图片已生成" in AGENT_IDENTITY_RULES


@pytest.mark.parametrize("filename", [
    "README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md", "docs/DEPLOYMENT.md",
])
def test_docs_explain_tool_routing_billing_privacy_and_limits(monkeypatch, filename):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    document = (ROOT / filename).read_text()
    for required in (
        "FIONA_CHAT_IMAGE_TOOL", "deepseek-flash", "qwen3.8-flash", "每轮最多一张图",
        "使用的描述", "成功扣 10", "失败退款", "BYOK 文字仍免费", "字节跳动火山引擎",
        "描述可能包含对话里出现过的内容", "prompt_extend", "两次读之间的间隔",
        "加生图 150 秒",
    ):
        assert required in document, (filename, required)
    if filename == "docs/ARCHITECTURE.md":
        assert "工具路径 trace 的 model 保持回复模型" in document


def test_env_template_documents_runtime_switch_and_image_credentials(monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    document = (ROOT / "backend/.env.example").read_text()
    assert "FIONA_CHAT_IMAGE_TOOL=1" in document
    assert "ARK_API_KEY=\n" in document
    assert "SEEDREAM_IMAGE_MODEL=doubao-seedream-5-0-flash-260915" in document
    assert "两次读之间的间隔" in document
    assert "qwen3.8-flash" in document
    assert "deepseek-v4-pro / deepseek-flash" in document


@pytest.mark.parametrize("filename", [
    "README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md", "docs/DEPLOYMENT.md",
])
def test_docs_distinguish_crisis_tool_guard_from_legacy_pending(monkeypatch, filename):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    document = (ROOT / filename).read_text()
    assert "possible 信息/求助语境的生图 pending 沿用旧路由" in document
    assert "非 high/possible 危机、已预扣且" not in document


def test_existing_tests_default_to_legacy_route(monkeypatch):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    document = (ROOT / "backend/tests/conftest.py").read_text()
    assert 'os.environ.setdefault("FIONA_CHAT_IMAGE_TOOL", "0")' in document


@pytest.mark.parametrize("filename", [
    "README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md", "docs/DEPLOYMENT.md",
    "backend/.env.example",
])
def test_r1_docs_explain_native_and_planner_data_flow(monkeypatch, filename):
    monkeypatch.setenv("FIONA_CHAT_IMAGE_TOOL", "1")
    document = (ROOT / filename).read_text()
    for required in (
        "原生工具模式", "判断器模式", "qwen3.8-flash", "最近 6 条对话",
        "历史每条最多 600 字，本轮原话最多 1500 字（超长时保留首尾）", "阿里云 DashScope", "约 1–5 秒",
        "判断器不可用时退回旧路由", "判断器模式下镜子模式也能生图",
        "Kimi、智谱、自定义地址改走判断器模式",
    ):
        assert required in document, (filename, required)
    assert "Kimi、智谱、自定义地址及其他型号暂不支持，仍走旧路由" not in document
    assert "Kimi、智谱、自定义地址暂不支持工具化生图" not in document
    if filename == "docs/ARCHITECTURE.md":
        assert "原生工具路径 trace 的 model 保持回复模型" in document


@pytest.mark.parametrize("filename", [
    "README.md", "CLAUDE.md", "PLAN.md", "docs/ARCHITECTURE.md", "docs/DEPLOYMENT.md",
    "backend/.env.example",
])
def test_r2_docs_describe_planner_followup_triggers(filename):
    document = (ROOT / filename).read_text()
    assert "上一条回复与生图相关" in document
    assert "存在待补充的生图请求" in document
    assert "取消短语不调用判断器" in document


def test_r2_architecture_restores_complete_legacy_image_route():
    baseline = git_baseline("docs/ARCHITECTURE.md", cwd=ROOT)
    paragraph = next(p for p in baseline.split("\n\n") if p.startswith("图片生成通过同一个 `POST /chat` 接入："))
    document = (ROOT / "docs/ARCHITECTURE.md").read_text()
    assert "适用于开关关闭、判断器不可用、possible 轮与面板路径。" + paragraph in document
    assert "原生模式下，候选经确认后走带工具的 friend 回复；判断器模式下，先由判断器裁决，判为不画时跳过候选块，意图识别返回的 generate_image 视为无意图。" in document


def test_r2_deployment_explains_sse_no_transform_for_next_proxy():
    document = (ROOT / "docs/DEPLOYMENT.md").read_text()
    paragraph = next(p for p in document.split("\n\n") if "FIONA_BACKEND_ORIGIN=http://127.0.0.1:8001" in p)
    assert "Cache-Control: no-transform" in paragraph
    assert "Next 代理压缩缓冲导致流式事件延迟到达" in paragraph
