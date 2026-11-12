"""案头三处小修：读正文去掉原始标题行、摘要只在未展开时截断、无项目提示补句号。

渲染用例复用 test_desk_views_frontend 的离线 SSR 加载器（真实 react 与
typescript），把它扩展成可指定命名导出、可把临时坏副本源码喂给同一个加载器。
缺 frontend 依赖或 node 时在启动 node 之前 skip；坏副本自检证明对应断言会变红。
"""
import json
import re
import subprocess

import pytest

import test_desk_views_frontend as desk_views
from test_desk_views_frontend import chapter, make_book


FRONTEND = desk_views.ROOT / "frontend"
READER_DIALOG = "components/desk/DeskDialogs.tsx"
CHAPTERS_VIEW = "components/desk/DeskChaptersView.tsx"
EPISODES_VIEW = "components/desk/DeskEpisodesView.tsx"
BODY_CLASSES = {"whitespace-pre-wrap", "break-words", "text-fs-16.5", "leading-[1.9]"}


def replace_once(source, marker, replacement):
    assert source.count(marker) == 1, f"渲染器标记不是唯一出现: {marker!r}"
    return source.replace(marker, replacement, 1)


def named_renderer():
    """在共享 SSR 加载器上支持命名导出与单个临时坏副本源码。"""
    renderer = replace_once(
        desk_views.NODE_RENDERER,
        "const component = loadModule(path.join(FRONTEND, process.argv[1]));",
        "const exported = loadModule(path.join(FRONTEND, process.argv[1]));\n"
        "  const component = exported[process.argv[3] || 'default'];",
    )
    renderer = replace_once(
        renderer,
        "if (typeof component.default !== 'function') {\n"
        "    throw new Error('component has no default export: ' + process.argv[1]);\n"
        "  }",
        "if (typeof component !== 'function') {\n"
        "    throw new Error('component has no export: ' + process.argv[1] + '#' + (process.argv[3] || 'default'));\n"
        "  }",
    )
    renderer = replace_once(
        renderer,
        "process.stdout.write(renderToStaticMarkup(React.createElement(component.default, props)));",
        "process.stdout.write(renderToStaticMarkup(React.createElement(component, props)));",
    )
    return replace_once(
        renderer,
        "const source = fs.readFileSync(full, 'utf8');",
        "const source = full === process.argv[4] ? fs.readFileSync(process.argv[5], 'utf8') : fs.readFileSync(full, 'utf8');",
    )


NAMED_RENDERER = named_renderer()


def render(relative, props, *, export="default", bad_source=None, tmp_path=None):
    desk_views.require_node_dependencies()
    target = (FRONTEND / relative).resolve()
    assert target.is_file(), f"前端组件尚未实现: {target}"
    args = ["node", "-e", NAMED_RENDERER, relative, json.dumps(props, ensure_ascii=False), export]
    if bad_source is not None:
        assert tmp_path is not None
        bad = tmp_path / f"{target.stem}.bad-copy{target.suffix}"
        bad.write_text(bad_source, encoding="utf-8")
        args.extend([str(target), str(bad)])
    result = subprocess.run(args, cwd=FRONTEND, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(f"node SSR failed for {relative}#{export}:\n{result.stderr}")
    return result.stdout


def reader_props(body):
    data = None if body is None else {
        "chapter": 1,
        "title": "第 1 章 测试章名",
        "status": "done",
        "words": 100,
        "body": body,
        "flags": [],
        "edited_by_user": False,
    }
    return {
        "book": make_book(),
        "chapter": 1,
        "data": data,
        "loading": False,
        "error": None,
        "onClose": None,
        "onOpenNovel": None,
    }


def assert_reader_body(html):
    assert "# 第1章 标题" not in html
    assert "第一段正文" in html and "第二段正文" in html
    assert "这一章还没有正文。" not in html
    body_divs = [
        classes
        for classes in re.findall(r'<div class="([^"]*)"', html)
        if "text-fs-16.5" in classes.split()
    ]
    assert len(body_divs) == 1, html
    assert BODY_CLASSES <= set(body_divs[0].split()), body_divs[0]
    return body_divs[0]


def test_reader_dialog_strips_original_title_line_and_keeps_body(tmp_path):
    body = "# 第1章 标题\n\n第一段正文\n第二段正文"
    html = render(READER_DIALOG, reader_props(body), export="DeskReaderDialog")
    assert_reader_body(html)

    empty = render(READER_DIALOG, reader_props(""), export="DeskReaderDialog")
    assert "这一章还没有正文。" in empty
    assert "text-fs-16.5" not in empty
    title_only = render(
        READER_DIALOG, reader_props("# 第1章 标题\n"), export="DeskReaderDialog")
    assert "这一章还没有正文。" in title_only
    assert "text-fs-16.5" not in title_only

    source = (FRONTEND / READER_DIALOG).read_text(encoding="utf-8")
    marker = 'const body = data?.body ? chapterReadingBody(data.body) : "";'
    assert marker in source, "读正文的实现标记消失，无法做坏副本自检"
    bad_source = source.replace(marker, 'const body = data?.body ?? "";', 1)
    assert bad_source != source
    bad_html = render(
        READER_DIALOG, reader_props(body), export="DeskReaderDialog",
        bad_source=bad_source, tmp_path=tmp_path,
    )
    assert "# 第1章 标题" in bad_html
    with pytest.raises(AssertionError):
        assert_reader_body(bad_html)


SUMMARY_TAG = re.compile(r'<p class="([^"]*)">(第 1 章摘要)</p>')


def summary_classes(html):
    matches = SUMMARY_TAG.findall(html)
    assert len(matches) == 1, html
    return matches[0][0].split()


def assert_summary_clamp(html, *, clamped):
    classes = summary_classes(html)
    assert ("line-clamp-2" in classes) is clamped, classes
    assert "break-words" in classes, classes
    assert ("line-clamp-2" in html) is clamped, html


def test_chapter_summary_clamps_only_while_collapsed(tmp_path):
    book = make_book(chapters=[chapter(1, "done", words=3000)])
    collapsed = render(CHAPTERS_VIEW, desk_views.chapters_props(book))
    expanded = render(CHAPTERS_VIEW, desk_views.chapters_props(book, initial_expanded=1))
    assert_summary_clamp(collapsed, clamped=True)
    assert_summary_clamp(expanded, clamped=False)

    source = (FRONTEND / CHAPTERS_VIEW).read_text(encoding="utf-8")
    marker = 'className={`break-words text-fs-13 text-[color:var(--ink2)] ${isExpanded ? "" : "line-clamp-2"}`}'
    assert marker in source, "摘要截断的实现标记消失，无法做坏副本自检"
    bad_source = source.replace(
        marker,
        'className="break-words text-fs-13 text-[color:var(--ink2)] line-clamp-2"',
        1,
    )
    assert bad_source != source
    bad_expanded = render(
        CHAPTERS_VIEW, desk_views.chapters_props(book, initial_expanded=1),
        bad_source=bad_source, tmp_path=tmp_path,
    )
    assert "line-clamp-2" in summary_classes(bad_expanded)
    with pytest.raises(AssertionError):
        assert_summary_clamp(bad_expanded, clamped=False)


EMPTY_STATE = re.compile(r'<div class="py-6[^"]*">(.*?)</div>', re.S)


def no_project_props(reason):
    props = desk_views.episodes_props(desk_views.make_plan())
    props["candidate"] = {
        **desk_views.make_candidate(),
        "eligible": False,
        "reason": reason,
        "projects": [],
    }
    return props


def assert_no_project_message(reason, expected, *, bad_source=None, tmp_path=None):
    html = render(
        EPISODES_VIEW, no_project_props(reason),
        bad_source=bad_source, tmp_path=tmp_path,
    )
    matches = EMPTY_STATE.findall(html)
    assert len(matches) == 1, html
    assert matches[0] == expected, matches[0]


@pytest.mark.parametrize(("reason", "expected"), [
    ("短片项目还在准备中", "这本书还没有短片项目。短片项目还在准备中。"),
    ("短片项目还在准备中。", "这本书还没有短片项目。短片项目还在准备中。"),
    ("短片项目还在准备中！", "这本书还没有短片项目。短片项目还在准备中！"),
    ("短片项目还在准备中?", "这本书还没有短片项目。短片项目还在准备中?"),
    (None, "这本书还没有短片项目。"),
    ("   ", "这本书还没有短片项目。"),
])
def test_no_project_reason_gets_one_ending_period(reason, expected):
    assert_no_project_message(reason, expected)


def test_no_project_reason_bad_copy_without_period_fails(tmp_path):
    reason = "短片项目还在准备中"
    source = (FRONTEND / EPISODES_VIEW).read_text(encoding="utf-8")
    marker = 'const missingEnd = reason !== "" && !/[。！？.!?]$/.test(reason);'
    assert marker in source, "补句号的实现标记消失，无法做坏副本自检"
    bad_source = source.replace(marker, "const missingEnd = false;", 1)
    assert bad_source != source
    assert_no_project_message(
        None, "这本书还没有短片项目。", bad_source=bad_source, tmp_path=tmp_path)
    with pytest.raises(AssertionError):
        assert_no_project_message(
            reason, "这本书还没有短片项目。短片项目还在准备中。",
            bad_source=bad_source, tmp_path=tmp_path,
        )
