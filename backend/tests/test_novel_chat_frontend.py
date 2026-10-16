"""Studio chat cards render with safe local links, entirely offline."""
from pathlib import Path
import shutil
import subprocess

import pytest

from test_claude_agent_frontend import render_card as render_shared_card

ROOT = Path(__file__).resolve().parents[2]
DEPENDENCIES = {"typescript": "typescript/lib/typescript.js", "react": "react/index.js", "react/jsx-runtime": "react/jsx-runtime.js", "react-dom/server": "react-dom/server.js"}


def render_card(card):
    missing = [name for name, entry in DEPENDENCIES.items() if not (ROOT / "frontend/node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")
    return render_shared_card(card)


@pytest.mark.parametrize("missing", DEPENDENCIES)
def test_render_skips_before_node_when_any_dependency_is_missing(monkeypatch, tmp_path, missing):
    for name, entry in DEPENDENCIES.items():
        path = tmp_path / "frontend/node_modules" / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        if name != missing:
            path.write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Node must not start without dependencies"))
    with pytest.raises(pytest.skip.Exception, match="frontend dependencies unavailable: " + missing):
        render_card({})


@pytest.mark.parametrize("url", ["/studio/project-1", "/studio/a_b/next-2", "/studio/ABC123"])
def test_studio_project_card_has_plain_internal_anchor(url):
    html = render_card({"subtype": "studio_project", "source": "短片工作室", "url": url, "points": ["《春山》", "6 章 · 1.5 万字 · 快照第 1 版", "已建项目，尚未花费"]})
    assert f'href="{url}"' in html
    assert "打开工作室" in html and "《春山》" in html and "已建项目，尚未花费" in html
    assert "target=" not in html and "onclick=" not in html


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://example.com/studio/p", "//example.com/studio/p", "/studio/../login", "/studio/a?embed=1", "/studio/a#x", "/studio/a%2fb", "/studio/中文", "/studio/", "/studios/a", "/studio/a\\b", "/studio/a\n", "/studio/a\r\n"])
def test_studio_project_card_rejects_unsafe_or_nonconforming_urls(url):
    html = render_card({"subtype": "studio_project", "source": "短片工作室", "url": url, "points": ["《春山》"]})
    assert "《春山》" in html
    assert "href=" not in html and "打开工作室" not in html


def test_studio_project_error_renders_only_error_text():
    html = render_card({"subtype": "studio_project", "source": "不应展示的来源", "url": "/studio/project", "points": ["不应展示的要点"], "error": "作品正在修改，请稍后再试"})
    assert "作品正在修改，请稍后再试" in html
    assert "不应展示" not in html and "href=" not in html and "打开工作室" not in html


def test_novel_read_privacy_is_an_independent_paragraph():
    source = (ROOT / "frontend/components/ChatModelSection.tsx").read_text()
    assert "<p>开启『聊天读小说』后，读到的章节原文会发送给当前聊天模型的厂商。</p>" in source
