"""T8.3 案头前端源码契约，全部为离线静态检查（不启动 node）。

只读仓库内的 ``frontend/app/page.tsx``、``frontend/lib/desk.ts`` 与
``frontend/components/desk/*.tsx``。每个“不得出现”的扫描都先证明扫描面
非空且包含预期文件，再用一段故意违规的文本和一段干净文本自检扫描器。
"""

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend/app/page.tsx"
DESK_LIB = ROOT / "frontend/lib/desk.ts"
DESK_DIR = ROOT / "frontend/components/desk"

BOM = b"\xef\xbb\xbf"

LOCKED_LITERALS = (
    "const openNovelAt = (path: string) => {",
    "onOpenNovel={openNovelAt}",
    'const [novelFrameSrc, setNovelFrameSrc] = useState("/novels?embed=1")',
    "src={novelFrameSrc}",
    "studioAllowed ? <iframe",
    "key={username}",
    'src="/studio?embed=1"',
)

DESK_FILES = (
    "DeskFrame.tsx",
    "DeskIdeaView.tsx",
    "DeskChaptersView.tsx",
    "DeskEpisodesView.tsx",
    "DeskDialogs.tsx",
    "DeskDock.tsx",
)

VIEW_FILES = (
    "DeskFrame.tsx",
    "DeskIdeaView.tsx",
    "DeskChaptersView.tsx",
    "DeskEpisodesView.tsx",
)

FORBIDDEN_CASES = (
    pytest.param(
        "font-weight-class",
        re.compile(r"font-medium|font-semibold|font-bold|font-extrabold|font-black"),
        '<div className="text-fs-13 font-bold" />',
        '<div className="text-fs-13 font-normal" />',
        id="font-weight-class",
    ),
    pytest.param(
        "fontWeight",
        re.compile(r"fontWeight"),
        "const style = { fontWeight: 600 };",
        'const style = { fontVariant: "normal" };',
        id="fontWeight",
    ),
    pytest.param(
        "font-weight",
        re.compile(r"font-weight"),
        '<div style="font-weight: 600" />',
        '<div style="font-size: 13px" />',
        id="font-weight-css",
    ),
    pytest.param(
        "hex-color",
        re.compile(r"#[0-9a-fA-F]{3,8}\b"),
        '<span style={{ color: "#1a2b3c" }} />',
        '<a href="https://example.com/docs#intro">文档</a>',
        id="hex-color",
    ),
    pytest.param(
        "rgb-color",
        re.compile(r"rgb\(|rgba\("),
        '<span style={{ color: "rgba(0, 0, 0, .5)" }} />',
        '<span className="text-[color:var(--ink2)]" />',
        id="rgb-color",
    ),
    pytest.param(
        "var(--stamp)",
        re.compile(r"var\(--stamp\)"),
        '<rect fill="var(--stamp)" />',
        '<rect fill="var(--seal)" />',
        id="var-stamp",
    ),
    pytest.param(
        "var(--ink3)",
        re.compile(r"var\(--ink3\)"),
        '<span className="text-[color:var(--ink3)]" />',
        '<span className="text-[color:var(--ink2)]" />',
        id="var-ink3",
    ),
    pytest.param(
        "var(--dim)",
        re.compile(r"var\(--dim\)"),
        '<span className="text-[color:var(--dim)]" />',
        '<span className="text-[color:var(--ink2)]" />',
        id="var-dim",
    ),
    pytest.param(
        "<iframe",
        re.compile(r"<iframe"),
        '<iframe src="/studio?embed=1" />',
        '<div className="min-h-0" />',
        id="iframe",
    ),
    pytest.param(
        "fetch(",
        re.compile(r"fetch\("),
        'await fetch("/api/desk");',
        "await beginRequest();",
        id="fetch",
    ),
    pytest.param(
        "ceramic-card",
        re.compile(r"ceramic-card"),
        '<div className="ceramic-card" />',
        '<div className="glaze-card" />',
        id="ceramic-card",
    ),
)

REACT_IMPORT = re.compile(
    r"""
    \bfrom\s*["']react(?:/jsx-runtime|/jsx-dev-runtime)?["']
    | \brequire\s*\(\s*["']react(?:/jsx-runtime|/jsx-dev-runtime)?["']\s*\)
    | \bimport\s*\(\s*["']react(?:/jsx-runtime|/jsx-dev-runtime)?["']\s*\)
    | ^\s*import\s*["']react(?:/jsx-runtime|/jsx-dev-runtime)?["']
    """,
    re.MULTILINE | re.VERBOSE,
)

VIEW_FORBIDDEN = (
    pytest.param(
        "useAccountRequest",
        "const { beginRequest } = useAccountRequest(owner);",
        "const { beginRequest } = useOwnerRequest(owner);",
        id="useAccountRequest",
    ),
    pytest.param(
        "localStorage",
        'window.localStorage.getItem("fiona.desk.v1:me");',
        'window.sessionStorage.getItem("fiona.desk.v1:me");',
        id="localStorage",
    ),
    pytest.param(
        "listNovels(",
        "const books = await listNovels();",
        "const books = await loadNovels();",
        id="listNovels",
    ),
    pytest.param(
        "getNovel(",
        "const book = await getNovel(id);",
        "const book = await getNovelDetail(id);",
        id="getNovel",
    ),
    pytest.param(
        "getStudioEpisodes(",
        "const plan = await getStudioEpisodes(id);",
        "const plan = await loadStudioEpisodes(id);",
        id="getStudioEpisodes",
    ),
)


def read_source(path):
    assert path.is_file(), f"缺少源码文件：{path}"
    return path.read_text(encoding="utf-8")


def strip_js_comments(text):
    """去掉 // 与 /* */ 注释，但保留字符串和换行，避免注释误伤导入扫描。"""
    result = []
    index = 0
    quote = ""
    while index < len(text):
        char = text[index]
        if quote:
            result.append(char)
            if char == "\\" and index + 1 < len(text):
                result.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                quote = ""
            index += 1
            continue
        if char in ("'", '"', "`"):
            quote = char
            result.append(char)
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index)
            if newline == -1:
                break
            result.append("\n")
            index = newline + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                break
            comment = text[index:end + 2]
            result.append("".join("\n" if item == "\n" else " " for item in comment))
            index = end + 2
            continue
        result.append(char)
        index += 1
    return "".join(result)


def scan_forbidden(sources, pattern, *, strip_comments=False):
    """扫描源码中的禁止写法，返回 {相对路径: [(行号, 命中文本), ...]}。

    ``sources`` 中的 Path 读取仓库内文件；``(label, text)`` 元组用于自检，
    不会读取任何文件。
    """
    sources = list(sources)
    assert sources, "扫描面不能为空"
    hits = {}
    for source in sources:
        if isinstance(source, Path):
            assert source.is_file(), f"缺少扫描文件：{source}"
            label = source.relative_to(ROOT).as_posix()
            text = source.read_text(encoding="utf-8")
        else:
            label, text = source
        if strip_comments:
            text = strip_js_comments(text)
        matches = [
            (text.count("\n", 0, match.start()) + 1, match.group(0))
            for match in pattern.finditer(text)
        ]
        if matches:
            hits[label] = matches
    return hits


def desk_components():
    """返回案头目录里实际存在的组件，并先校验扫描面包含六个预期文件。"""
    assert DESK_DIR.is_dir(), f"缺少案头组件目录：{DESK_DIR}"
    found = {
        path.name: path
        for path in DESK_DIR.glob("*.tsx")
        if path.is_file()
    }
    assert found, "案头组件扫描面不能为空"
    missing = [name for name in DESK_FILES if name not in found]
    assert not missing, "缺少案头组件：" + ", ".join(missing)
    return found


def desk_scan_paths():
    """六个组件文件 + lib/desk.ts；目录里若还有别的组件也一并纳入扫描。"""
    components = desk_components()
    paths = [DESK_LIB] + [components[name] for name in sorted(components)]
    assert DESK_LIB.is_file(), f"缺少源码文件：{DESK_LIB}"
    names = {path.name for path in paths}
    assert len(paths) >= 7, f"案头源码扫描面不足：{len(paths)} 个文件"
    assert DESK_LIB.name in names
    assert set(DESK_FILES) <= names
    return paths


def view_paths():
    components = desk_components()
    assert set(VIEW_FILES) <= set(components), "视图文件扫描面缺少预期文件"
    return [components[name] for name in VIEW_FILES]


def check_page_bom(raw):
    assert raw.startswith(BOM), "page.tsx 必须以 UTF-8 BOM（EF BB BF）开头"


# ---- 1. page.tsx BOM ----


def test_page_starts_with_utf8_bom_bytes():
    assert PAGE.is_file(), f"缺少源码文件：{PAGE}"
    raw = PAGE.read_bytes()
    assert raw[:3] == BOM
    check_page_bom(raw)


def test_bom_check_rejects_source_without_bom():
    with pytest.raises(AssertionError):
        check_page_bom(b'"use client";\n')


# ---- 2. 规格 2.2 的七条字面量 ----


@pytest.mark.parametrize(
    "literal",
    LOCKED_LITERALS,
    ids=[f"locked-literal-{index}" for index in range(1, len(LOCKED_LITERALS) + 1)],
)
def test_page_keeps_locked_literal(literal):
    source = read_source(PAGE)
    assert source.count(literal) >= 1, f"page.tsx 丢失了锁定字面量：{literal!r}"


def test_page_uses_desk_auto_opens_guard():
    source = read_source(PAGE)
    assert source.count("deskAutoOpens(window.innerWidth)") == 1
    assert 'deskMode(window.innerWidth) !== "sheet"' not in source


# ---- 3. 案头开关在朗读开关之前 ----


def test_desk_toggle_is_unique_and_precedes_voice_toggle():
    source = read_source(PAGE)
    trigger = 'aria-controls="desk-panel"'
    voice = 'aria-label="朗读"'
    assert trigger in source, "page.tsx 缺少 aria-controls=\"desk-panel\""
    assert voice in source, "page.tsx 缺少 aria-label=\"朗读\""
    assert source.count(trigger) == 1, "aria-controls=\"desk-panel\" 必须恰好出现一次"

    trigger_index = source.index(trigger)
    voice_index = source.index(voice)
    assert trigger_index < voice_index, "案头按钮必须出现在朗读按钮之前"

    button_start = source.rfind("<button", 0, trigger_index)
    button_end = source.find("</button>", trigger_index)
    assert button_start != -1, "找不到 aria-controls=\"desk-panel\" 所在的按钮"
    assert button_end != -1, "找不到案头按钮的闭合标签"
    assert button_end > trigger_index
    button = source[button_start:button_end]
    assert 'aria-label="案头"' in button, "aria-controls=\"desk-panel\" 必须属于案头按钮"
    assert button_start < voice_index, "案头按钮的开始位置必须在朗读按钮之前"


# ---- 4. DeskDock 在对话面板之后、分身抽屉之前 ----


def test_desk_dock_is_mounted_once_between_chat_panel_and_agent_drawer():
    source = read_source(PAGE)
    chat_anchor = "data-chat-panel"
    dock_anchor = "<DeskDock"
    agent_anchor = 'id="agent-drawer"'
    assert chat_anchor in source, "page.tsx 缺少 data-chat-panel 锚点"
    assert agent_anchor in source, "page.tsx 缺少 id=\"agent-drawer\" 锚点"
    assert source.count(dock_anchor) == 1, "<DeskDock 必须恰好挂载一次"

    chat_index = source.index(chat_anchor)
    dock_index = source.index(dock_anchor)
    agent_index = source.index(agent_anchor)
    assert chat_index < dock_index, "<DeskDock 必须在 data-chat-panel 之后"
    assert dock_index < agent_index, "<DeskDock 必须在 id=\"agent-drawer\" 之前"


# ---- 5. 案头组件文件 ----


def test_desk_component_directory_has_required_six_files():
    assert DESK_DIR.is_dir(), f"缺少案头组件目录：{DESK_DIR}"
    found = {
        path.name
        for path in DESK_DIR.glob("*.tsx")
        if path.is_file()
    }
    assert found, "案头组件扫描面不能为空"
    missing = set(DESK_FILES) - found
    assert not missing, "缺少案头组件：" + ", ".join(sorted(missing))
    assert len(found) >= 6, f"案头组件文件不足六个：{sorted(found)}"


# ---- 6. 六个组件文件 + lib/desk.ts 的禁止写法 ----


@pytest.mark.parametrize("label, pattern, violating, clean", FORBIDDEN_CASES)
def test_forbidden_patterns_absent_from_desk_sources(label, pattern, violating, clean):
    files = desk_scan_paths()
    assert files, "案头源码扫描面不能为空"
    names = {path.name for path in files}
    assert DESK_LIB.name in names
    assert set(DESK_FILES) <= names

    hits = scan_forbidden(files, pattern)
    assert not hits, f"案头源码出现禁止写法 {label}：{hits}"

    bad_hits = scan_forbidden([("selfcheck.tsx", violating)], pattern)
    assert bad_hits, f"自检失败：{label} 的违规样本没有被抓到：{violating!r}"
    good_hits = scan_forbidden([("selfcheck.tsx", clean)], pattern)
    assert not good_hits, f"自检失败：{label} 的干净样本被误伤：{good_hits}"


# ---- 7. lib/desk.ts 不 import react ----


def test_desk_lib_does_not_import_react():
    assert DESK_LIB.is_file(), f"缺少源码文件：{DESK_LIB}"
    files = [DESK_LIB]
    assert files, "扫描面不能为空"
    assert DESK_LIB.name in {path.name for path in files}
    hits = scan_forbidden(files, REACT_IMPORT, strip_comments=True)
    assert not hits, f"frontend/lib/desk.ts 不得 import react：{hits}"


@pytest.mark.parametrize(
    "bad",
    [
        'import { useState } from "react";',
        "import { useState } from 'react';",
        'import React from "react";',
        'import * as React from "react";',
        'const React = require("react");',
        "const React = require('react');",
        'import "react";',
        'const React = import("react");',
        'export { useState } from "react";',
    ],
    ids=[
        "from-double-quote",
        "from-single-quote",
        "default-import",
        "namespace-import",
        "require-double-quote",
        "require-single-quote",
        "side-effect-import",
        "dynamic-import",
        "re-export",
    ],
)
def test_react_import_scanner_detects_common_forms(bad):
    hits = scan_forbidden([("selfcheck.ts", bad)], REACT_IMPORT, strip_comments=True)
    assert hits, f"自检失败：react import 违规样本没有被抓到：{bad!r}"


def test_react_import_scanner_ignores_comments_and_other_modules():
    clean = (
        '// import { useState } from "react"\n'
        '/* import React from "react"; */\n'
        'import type { NovelChapterSummary } from "@/lib/novels";\n'
        'const label = "from react";\n'
    )
    hits = scan_forbidden([("selfcheck.ts", clean)], REACT_IMPORT, strip_comments=True)
    assert not hits, f"自检失败：注释或其他模块被误伤：{hits}"


# ---- 8. 视图文件不自己取数、不读 localStorage ----


@pytest.mark.parametrize("literal, violating, clean", VIEW_FORBIDDEN)
def test_view_components_do_not_own_data_access(literal, violating, clean):
    files = view_paths()
    assert files, "视图文件扫描面不能为空"
    assert {path.name for path in files} == set(VIEW_FILES)

    pattern = re.compile(re.escape(literal))
    hits = scan_forbidden(files, pattern)
    assert not hits, f"视图文件出现禁止写法 {literal!r}：{hits}"

    bad_hits = scan_forbidden([("selfcheck.tsx", violating)], pattern)
    assert bad_hits, f"自检失败：{literal!r} 的违规样本没有被抓到：{violating!r}"
    good_hits = scan_forbidden([("selfcheck.tsx", clean)], pattern)
    assert not good_hits, f"自检失败：{literal!r} 的干净样本被误伤：{good_hits}"


# ---- 9. 案头对话框必须写成 JSX，不能躲开 dialog 门禁 ----


def test_desk_dialogs_use_one_jsx_dialog_and_no_create_element_dialog():
    components = desk_components()
    assert "DeskDialogs.tsx" in components
    dialogs = read_source(components["DeskDialogs.tsx"])
    assert dialogs.count("<dialog") == 1, "DeskDialogs.tsx 必须恰好写一个 JSX <dialog>"

    files = list(components.values())
    assert files, "案头组件扫描面不能为空"
    assert "DeskDialogs.tsx" in {path.name for path in files}

    pattern = re.compile(r"createElement\(\s*['\"]dialog['\"]")
    hits = scan_forbidden(files, pattern)
    assert not hits, f"案头组件不得用 createElement 生成 dialog：{hits}"

    for violating in (
        'return React.createElement("dialog", { className: sourceDialogClass });',
        "return React.createElement('dialog', { className: sourceDialogClass });",
    ):
        bad_hits = scan_forbidden([("selfcheck.tsx", violating)], pattern)
        assert bad_hits, f"自检失败：违规 dialog 写法没有被抓到：{violating!r}"

    clean = '<dialog className={sourceDialogClass} />'
    good_hits = scan_forbidden([("selfcheck.tsx", clean)], pattern)
    assert not good_hits, f"自检失败：JSX dialog 被误伤：{good_hits}"


# ---- 10. 阶段标签使用 deskStageByKey，不再用 useRovingTabs ----


def test_desk_frame_stage_tabs_use_stage_key_helper_and_data_stage():
    source = read_source(DESK_DIR / "DeskFrame.tsx")
    assert "deskStageByKey(" in source
    assert "useRovingTabs" not in source
    assert source.count("data-stage={item.id}") == 2
    assert source.count("tabIndex={item.enabled && selected ? 0 : -1}") == 2


# ---- 11. 分集对话框通知定位、细纲关闭按钮与呈现方式清空 ----


def test_desk_episode_dialogs_join_focus_guard_and_plan_close_is_busy_disabled():
    episodes = read_source(DESK_DIR / "DeskEpisodesView.tsx")
    dock = read_source(DESK_DIR / "DeskDock.tsx")
    dialogs = read_source(DESK_DIR / "DeskDialogs.tsx")
    assert "onDialogOpenChange?.(dialogOpen)" in episodes
    assert "onDialogOpenChange={handleEpisodeDialogOpenChange}" in dock
    assert dialogs.count("disabled={busy} onClick={onClose}>关闭</button>") == 1
    assert "setMode(null)" in dock
