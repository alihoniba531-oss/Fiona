"""Offline source contracts for the P2 UI; all inputs are in this checkout."""
import ast
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
COMPONENTS = FRONTEND / "components/novel"


def read(relative):
    path = ROOT / relative
    assert path.resolve().is_relative_to(ROOT.resolve())
    return path.read_text(encoding="utf-8")


def novel_source():
    files = [FRONTEND / "lib/novels.ts", *COMPONENTS.glob("*.tsx"), *(FRONTEND / "app/novels").rglob("*.tsx")]
    return "\n".join(file.read_text(encoding="utf-8") for file in files)


def test_sidebar_has_six_bookmarks_and_novel_drawer_mapping():
    source = read("frontend/components/Sidebar.tsx")
    nav = source.split("const navItems = [", 1)[1].split("];", 1)[0]
    assert re.findall(r'label: "([^"]+)"', nav) == ["对话", "分身", "广场", "世界", "设置", "书斋"]
    for contract in ("onNovelClick", "novelActive", '"novel-drawer"', 'pathname.startsWith("/novels/")'):
        assert contract in source
    # Preserve existing six equal slots and two-character labels at 360 px.
    assert "min-w-0 flex-1" in source
    assert "whitespace-nowrap text-sm tracking-[.2em]" in source


def test_home_keeps_novel_iframe_mounted_when_drawer_closes():
    source = read("frontend/app/page.tsx")
    assert '"novel" | null' in source
    drawer = source.split('id="novel-drawer"', 1)[1].split("</Glaze>", 1)[0]
    assert "...drawerStyle(novelOpen)" in drawer
    assert 'src="/novels?embed=1"' in drawer
    assert "aria-hidden={!novelOpen}" in drawer and "inert={!novelOpen}" in drawer
    assert not re.search(r"novelOpen\s*&&\s*<iframe", drawer)
    assert 'event.origin !== window.location.origin' in source
    assert "event.source !== novelFrameRef.current?.contentWindow" in source


@pytest.mark.parametrize("route", ["page.tsx", "new/page.tsx", "[id]/page.tsx"])
def test_three_client_pages_exist_and_search_params_are_suspended(route):
    page = read(f"frontend/app/novels/{route}")
    assert '"use client"' in page
    assert "Suspense" in page


@pytest.mark.parametrize("label", [
    "立项中", "等你确认立项", "写作中", "等你审阅", "等你确认细纲", "等你确认完结", "已完结", "已暂停",
    "预算快用完", "草莓不足", "自带模型不可用", "推演卡住了", "与设定冲突", "今日额度已用完", "恢复失败", "出错了",
])
def test_every_state_label_is_present(label):
    assert label in novel_source()


@pytest.mark.parametrize("copy", [
    "主编正在生成罗盘和设定…", "设定已生成，看看合不合意。", "立项修改不符合设定格式", "已写完第", "章，看完再继续。",
    "章细纲已定稿。", "智能体判断故事可以收尾了。", "确认完结", "还没完，再写", "全书完结，共", "已暂停。",
    "本书已花掉预算的 80%。", "调高预算并继续", "草莓余额不足，充值后继续。", "去设置启用", "改用平台模型",
    "主编这一章没能给出合格的定稿", "某一步失败", "重试会再次计费。", "档案员发现正文与锁定设定冲突，请先查看再继续。",
    "今天的章节额度已用完，北京时间零点后可继续。", "服务重启后没能自动恢复。",
])
def test_every_gate_copy_is_present(copy):
    assert copy in novel_source()


def backend_paths(relative, prefix=""):
    tree = ast.parse(read(relative))
    paths = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"get", "post", "put", "patch", "delete"}:
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "router" and node.args and isinstance(node.args[0], ast.Constant):
                paths.add(re.sub(r"\{[^}]+\}", "{}", prefix + node.args[0].value))
    return paths


def test_every_frontend_api_path_exists_in_backend_routes():
    source = read("frontend/lib/novels.ts")
    routes = backend_paths("backend/routers/novel.py", "/novels") | backend_paths("backend/routers/me.py")
    paths = set()
    actions = re.findall(r'action\(id, "([^"]+)"', source)
    assert set(actions) == {"setup/approve", "plan/approve", "plan/redo", "continue", "pause", "resume", "end/confirm", "end/reject"}
    for template in re.findall(r"`([^`]+)`", source):
        if not template.startswith(("${API_BASE}/", "${bookPath(id)}")):
            continue
        path = template.replace("${API_BASE}", "").replace("${bookPath(id)}", "/novels/{}")
        path = path.replace("${encodeURIComponent(id)}", "{}").replace("${chapter}", "{}")
        if "${path}" in path:
            paths.update(path.replace("${path}", action) for action in actions)
        else:
            assert "${" not in path, f"Unrecognized API interpolation: {path}"
            paths.add(path)
    assert paths >= {"/novels", "/novels/{}/bible", "/novels/{}/notes", "/novels/{}/chapters/{}", "/strawberry"}
    assert paths <= routes, f"Frontend API without backend route: {paths - routes}"


def test_novel_ui_uses_existing_theme_and_plain_text_contracts():
    source = novel_source()
    assert "max-md:" not in source
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|font-family|<Seal\b|font-mono", source)
    for contract in ("mobile:", "whitespace-pre-wrap", "leading-[1.95]", "max-w-[38em]", "maxLength={30000}", "maxLength={500}"):
        assert contract in source
    for flag in ("review_unresolved", "length_out_of_range", "deviation", "locked_conflict", "edited_by_user", "stale"):
        assert flag in read("frontend/components/novel/ChapterList.tsx")
    api = read("frontend/lib/novels.ts")
    assert "apiFetch" in api and "apiJson" in api and "ApiError" in api
    assert "Content-Type" in api and "text/markdown" in api


def test_workbench_polls_only_running_books_and_pauses_on_visibility():
    source = read("frontend/components/novel/NovelWorkbench.tsx")
    assert "setTimeout" in source and "3000" in source
    assert "visibilitychange" in source and "document.hidden" in source
    assert '"setup_running"' in source and '"running"' in source
    assert "setInterval" not in source
    assert "useAccountRequest" in source and "isCurrent" in source
    assert "<dialog" in read("frontend/components/novel/NovelSettingsDialog.tsx")
    assert "confirm(" in source


def test_r1_container_query_and_scroll_skeleton_contracts():
    source = read("frontend/components/novel/NovelWorkbench.tsx")
    for contract in (
        "@container", "@[1040px]:hidden", "@[1040px]:grid", "hidden @[1040px]:block",
        "grid-cols-[minmax(180px,.65fr)_minmax(480px,2fr)_minmax(300px,1fr)]",
        "h-dvh overflow-hidden", "overflow-y-auto", "[overflow-wrap:anywhere]",
    ):
        assert contract in source
    assert "grid-cols-[minmax(150px" not in source
    assert "chapterCache" not in source and "setRevision" not in source
    assert 'mobile:pb-[calc(var(--tabbar-h)+env(safe-area-inset-bottom)+16px)]' not in source
    assert "getNovel(" not in read("frontend/components/novel/NovelShelf.tsx")


def test_r1_drawer_close_matches_settings_and_keeps_focus_outline_hidden():
    source = read("frontend/app/page.tsx")
    settings = source.split('id="settings-drawer"', 1)[1].split("</Glaze>", 1)[0]
    novel = source.split('id="novel-drawer"', 1)[1].split("</Glaze>", 1)[0]
    settings_close = re.search(r'className="([^"]+)"\s+title="收起"', settings)
    novel_close = re.search(r'className="([^"]+)"\s+title="收起书斋"', novel)
    assert settings_close and novel_close
    assert settings_close[1] == novel_close[1]
    assert "overflow-hidden outline-none" in novel
    directory = read("frontend/components/novel/ChapterList.tsx")
    assert 'from "lucide-react"' in directory
    assert 'selectedChapter === chapter.chapter ? "true"' in directory
    assert not any(icon in directory for icon in ("⚑", "◷", "↔", "↗", "✎"))
