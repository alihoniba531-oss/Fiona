"""案头视图组件服务端渲染：章回页、分集页与阶段标签。

离线运行：在 node 里用仓库内 typescript 的 transpileModule 把 TS/TSX 转成
CommonJS，再用只解析仓库内文件与少量桩模块的 require，交给真实的 react 与
react-dom/server 做服务端渲染。缺 frontend 依赖或 node 时整组 skip；参数化
自检证明缺任意依赖时在启动 node 之前就跳过。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DEPENDENCIES = {
    "typescript": "typescript/lib/typescript.js",
    "react": "react/index.js",
    "react-dom/server": "react-dom/server.js",
}
BOOK_ID = "12345678-1234-1234-1234-123456789abc"
SEAL_TEXT = "text-[color:var(--seal)]"
SEAL_BORDER = "border-[color:var(--seal)]"
SEAL_CLASSES = (SEAL_TEXT, SEAL_BORDER)
CHAPTER_TAGS = ("定稿", "待复核", "细纲等你确认")
INPUT_TAG = re.compile(r"<input\b[^>]*>")
TAG_SPAN = re.compile(r'<span class="([^"]*)"\s*>([^<]*)</span>')


def require_node_dependencies():
    missing = [name for name, entry in DEPENDENCIES.items()
               if not (ROOT / "frontend/node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")


@pytest.mark.parametrize("missing", [*DEPENDENCIES, "node"])
def test_renderer_skips_before_node_when_any_dependency_is_missing(monkeypatch, tmp_path, missing):
    for name, entry in DEPENDENCIES.items():
        path = tmp_path / "frontend/node_modules" / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        if name != missing:
            path.write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    if missing == "node":
        monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail(
        "Node must not start without dependencies"))
    expected = ("node is unavailable" if missing == "node"
                else "frontend dependencies unavailable: " + missing)
    with pytest.raises(pytest.skip.Exception, match=re.escape(expected)):
        require_node_dependencies()


# 只解析仓库内模块。react / react/jsx-runtime / react-dom/server 用真实包；
# lucide-react 的任意图标返回 null 组件；书斋与工作室的业务模块用最小桩，
# 其运行时 API 在 SSR 中不会被调用。
NODE_RENDERER = r"""
const fs = require('fs');
const path = require('path');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const FRONTEND = process.cwd();
const realRequire = require;

const Icon = () => null;
const iconModule = new Proxy({}, {
  get(_target, key) {
    if (typeof key !== 'string' || key === '__esModule') return key === '__esModule' ? false : undefined;
    return Icon;
  },
});

function GateBannerStub() { return null; }
function LinkStub({ href, children }) { return React.createElement('a', { href }, children); }
class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}
function apiJson() { throw new Error('network is disabled in desk view tests'); }
function apiFetch() { throw new Error('network is disabled in desk view tests'); }

const STUBS = {
  'lucide-react': iconModule,
  'next/link': LinkStub,
  '@/lib/agents': { ApiError, apiJson },
  '@/lib/auth': { apiFetch },
  '@/lib/config': { API_BASE: '/api' },
  '@/lib/studio': { studioErrorMessage: error => String((error && error.message) || error) },
  '@/components/novel/GateBanner': GateBannerStub,
  '@/components/studio/SourceChoices': { sourceDialogClass: '' },
};

const cache = new Map();

function insideFrontend(file) {
  const normalized = path.resolve(file);
  return normalized === FRONTEND || normalized.startsWith(FRONTEND + path.sep);
}

function resolveFile(spec, fromDir) {
  let base;
  if (spec.startsWith('@/')) base = path.join(FRONTEND, spec.slice(2));
  else if (spec.startsWith('./') || spec.startsWith('../')) base = path.resolve(fromDir, spec);
  else throw new Error('module is not allowed: ' + spec);
  const candidates = path.extname(base)
    ? [base]
    : [base + '.tsx', base + '.ts', base + '.js',
       path.join(base, 'index.tsx'), path.join(base, 'index.ts')];
  for (const candidate of candidates) {
    const full = path.resolve(candidate);
    if (!insideFrontend(full)) throw new Error('module escapes the repository: ' + spec);
    if (fs.existsSync(full) && fs.statSync(full).isFile()) return full;
  }
  throw new Error('module not found: ' + spec + ' from ' + fromDir);
}

function requireFrom(spec, fromDir) {
  if (spec === 'react') return React;
  if (spec === 'react/jsx-runtime') return realRequire('react/jsx-runtime');
  if (spec === 'react-dom/server') return realRequire('react-dom/server');
  if (Object.prototype.hasOwnProperty.call(STUBS, spec)) return STUBS[spec];
  return loadModule(resolveFile(spec, fromDir));
}

function loadModule(file) {
  const full = path.resolve(file);
  if (!insideFrontend(full)) throw new Error('module escapes the repository: ' + file);
  if (cache.has(full)) return cache.get(full).exports;
  const moduleObject = { exports: {} };
  cache.set(full, moduleObject);
  const source = fs.readFileSync(full, 'utf8');
  const compiled = ts.transpileModule(source, {
    fileName: full,
    compilerOptions: {
      target: ts.ScriptTarget.ES2020,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText;
  const fn = new Function('exports', 'require', 'module', '__filename', '__dirname', compiled);
  fn(moduleObject.exports, spec => requireFrom(spec, path.dirname(full)),
     moduleObject, full, path.dirname(full));
  return moduleObject.exports;
}

try {
  const component = loadModule(path.join(FRONTEND, process.argv[1]));
  if (typeof component.default !== 'function') {
    throw new Error('component has no default export: ' + process.argv[1]);
  }
  const props = JSON.parse(process.argv[2]);
  if (typeof props.__childrenText === 'string') {
    props.children = React.createElement('div', null, props.__childrenText);
    delete props.__childrenText;
  }
  process.stdout.write(renderToStaticMarkup(React.createElement(component.default, props)));
} catch (error) {
  process.stderr.write(String((error && error.stack) || error));
  process.exit(1);
}
"""


def render_view(component, props):
    """转译并 SSR 渲染一个案头视图，返回 HTML。"""
    require_node_dependencies()
    frontend = ROOT / "frontend"
    target = frontend / "components/desk" / component
    assert target.is_file(), f"前端视图组件尚未实现: {target}"
    result = subprocess.run(
        ["node", "-e", NODE_RENDERER, f"components/desk/{component}",
         json.dumps(props, ensure_ascii=False)],
        cwd=frontend, capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"node SSR failed for {component}:\n{result.stderr}")
    return result.stdout


def has_disabled(tag):
    """只匹配属性名 disabled，跳过 class 里的 disabled: 工具类。"""
    return re.search(r'\sdisabled(?:=""|(?=[\s/>]))', tag) is not None


def button_with_text(html, text):
    matches = re.findall(
        r"<button\b[^>]*>" + re.escape(text) + r"</button>", html)
    assert len(matches) == 1, f"期望恰好一个「{text}」按钮，实际 {matches}"
    return matches[0]


TABLIST_TAG = re.compile(r'<nav\b[^>]*role="tablist"[^>]*>')
EXPAND_BUTTON = re.compile(r'<button\b[^>]*aria-expanded="[^"]*"[^>]*>')
TAB_BUTTON = re.compile(r'<button\b[^>]*data-stage="[^"]+"[^>]*>')


def assert_tablist_orientation(html, *, vertical):
    tags = TABLIST_TAG.findall(html)
    assert len(tags) == 1, f"期望恰好一个 role=tablist，实际 {tags}"
    if vertical:
        assert 'aria-orientation="vertical"' in tags[0], tags[0]
        assert html.count('aria-orientation="vertical"') == 1, html
    else:
        assert 'aria-orientation="vertical"' not in tags[0], tags[0]
        assert html.count('aria-orientation="vertical"') == 0, html


def assert_expand_label(html, label):
    tags = EXPAND_BUTTON.findall(html)
    matching = [tag for tag in tags if f'aria-label="{label}"' in tag]
    assert len(matching) == 1, f"期望 aria-label 在唯一展开按钮上：{label}；实际 {tags}"
    return matching[0]


def assert_unique_tab_stop(html, stage):
    tabs = TAB_BUTTON.findall(html)
    assert len(tabs) == 5, tabs
    stops = [tab for tab in tabs if 'tabindex="0"' in tab]
    assert len(stops) == 1, stops
    assert f'data-stage="{stage}"' in stops[0], stops[0]
    assert 'aria-selected="true"' in stops[0], stops[0]
    assert sum('tabindex="-1"' in tab for tab in tabs) == 4, tabs


def tag_classes(html):
    found = {}
    for classes, text in TAG_SPAN.findall(html):
        if text in CHAPTER_TAGS and "tag" in classes.split():
            found[text] = classes
    return found


def assert_seal_only_on_settled_tag(html):
    tags = tag_classes(html)
    # 标签集合必须非空且恰好三种，避免负向断言在解析失败时空转。
    assert set(tags) == set(CHAPTER_TAGS), tags
    for text in SEAL_CLASSES:
        assert tags["定稿"].count(text) == 1, tags["定稿"]
    assert html.count(SEAL_TEXT) == 1
    assert html.count(SEAL_BORDER) == 1
    for label in ("细纲等你确认", "待复核"):
        for text in SEAL_CLASSES:
            assert text not in tags[label], f"{label} 不应带朱色类: {tags[label]}"


ASIDE_TAG = re.compile(r"<aside\b[^>]*>")
CLASS_ATTR = re.compile(r'\bclass="([^"]*)"')


def tag_span_classes(html, text):
    matches = [
        classes for classes, value in TAG_SPAN.findall(html)
        if value == text and "tag" in classes.split()
    ]
    assert len(matches) == 1, f"期望恰好一个 tag「{text}」标签，实际 {matches}"
    return matches[0]


def aside_classes(html):
    matches = ASIDE_TAG.findall(html)
    assert len(matches) == 1, f"期望恰好一个 <aside>，实际 {matches}"
    classes = CLASS_ATTR.search(matches[0])
    assert classes is not None, matches[0]
    return classes.group(1)


def assert_approved_tag_has_seal(html):
    classes = tag_span_classes(html, "已批准")
    assert SEAL_TEXT in classes.split(), classes
    assert SEAL_BORDER in classes.split(), classes
    assert html.count(SEAL_TEXT) == 1, html
    assert html.count(SEAL_BORDER) == 1, html


def assert_pending_tag_has_no_seal(html):
    classes = tag_span_classes(html, "待批准")
    for seal in SEAL_CLASSES:
        assert seal not in classes.split(), classes
    assert SEAL_TEXT not in html
    assert SEAL_BORDER not in html


def chapter(number, status, *, words=0):
    return {
        "chapter": number,
        "title": f"第 {number} 章 测试章名",
        "status": status,
        "words": words,
        "flags": [],
        "edited_by_user": False,
    }


def make_book(*, status="awaiting_plan", pending_notes=2, chapters=None, chapters_done=None):
    if chapters is None:
        chapters = [
            chapter(1, "done", words=3000),
            chapter(2, "awaiting_plan_approval"),
            chapter(3, "stale", words=2800),
        ]
    if chapters_done is None:
        chapters_done = max(
            (item["chapter"] for item in chapters if item["status"] == "done"),
            default=0,
        )
    target = {"min_chapters": 10, "max_chapters": 20, "chapter_words": 3000}
    adaptation = {"max_main_characters": 8, "max_scenes_per_chapter": 6}
    summaries = [
        {"chapter": item["chapter"], "title": item["title"],
         "summary": f"第 {item['chapter']} 章摘要"}
        for item in chapters
    ]
    return {
        "id": BOOK_ID,
        "title": "长夜",
        "status": status,
        "pause_reason": None,
        "bible_version": 2,
        "chapters_done": chapters_done,
        "max_chapters": 20,
        "words_done": 9000,
        "budget_strawberries": 100,
        "spent_strawberries": 20,
        "reserved_strawberries": 0,
        "created_at": "2026-11-01 10:00:00",
        "updated_at": "2026-11-10 10:00:00",
        "completed_at": "2026-11-10 09:00:00" if status == "completed" else None,
        "config": {
            "seed_idea": "一个关于夜的故事",
            "agents": {"planner": "dashscope:qwen3.8-max"},
            "panel_mode": "critique",
            "automation": "per_batch",
            "batch_size": 3,
            "target": target,
            "adaptation": adaptation,
            "drama_adaptation": False,
            "budget_strawberries": 100,
        },
        "compass": {
            "title": "长夜",
            "logline": "一句话故事",
            "theme": "主题",
            "core_conflict": "核心冲突",
            "protagonist": {"name": "主角", "want": "想要", "need": "需要"},
            "candidate_endings": [],
            "main_threads": [],
            "target": target,
            "seed_idea": "一个关于夜的故事",
        },
        "bible": {
            "version": 2,
            "locked": {
                "characters": [],
                "world_rules": [],
                "style_guide": {"pov": "third", "tense": "past",
                                "voice": "克制", "banned_phrases": []},
                "adaptation": adaptation,
            },
            "dynamic": {
                "character_states": {},
                "foreshadowing": [],
                "chapter_summaries": summaries,
                "timeline": [],
                "used_beats": [],
            },
        },
        "chapters": chapters,
        "pending_gate": "plan" if status == "awaiting_plan" else None,
        "pending_notes": pending_notes,
        "last_error": None,
    }


def book_summary(book):
    keys = (
        "id", "title", "status", "pause_reason", "bible_version", "chapters_done",
        "max_chapters", "words_done", "budget_strawberries", "spent_strawberries",
        "reserved_strawberries", "created_at", "updated_at", "completed_at",
    )
    return {key: book[key] for key in keys}


def chapters_props(book, *, initial_expanded=None):
    return {
        "book": book,
        "busy": False,
        "gateError": None,
        "onAction": None,
        "onAddNote": None,
        "onAsk": None,
        "onExport": None,
        "onOpenNovel": None,
        "onOpenPlan": None,
        "onOpenBody": None,
        "onOpenSettings": None,
        "initialExpanded": initial_expanded,
    }


def make_episode(no):
    return {
        "id": f"ep-{no}",
        "no": no,
        "title": f"第 {no} 集 测试标题",
        "unit_from": no * 2 - 1,
        "unit_to": no * 2,
        "change": f"第 {no} 集变化",
        "hook": f"第 {no} 集钩子",
        "notes": f"第 {no} 集备注",
        "target_min": 180,
        "target_max": 240,
        "effective_target_min": 180,
        "effective_target_max": 240,
        "est_seconds": 200,
        "est_shots": 57,
        "source_range": f"第 {no * 2 - 1}–{no * 2} 场",
        "characters": ["主角"],
        "warnings": [],
    }


def make_plan(**overrides):
    plan = {
        "episodes": [make_episode(1), make_episode(2)],
        "units": [{"seq": 1, "label": "场景 1"}, {"seq": 2, "label": "场景 2"}],
        "unassigned": [],
        "uncovered": [],
        "plan_revision": 3,
        "plan_approved_revision": None,
        "g0_approved": False,
        "total_seconds": 400,
        "status": "done",
        "breakdown_id": "breakdown-1",
        "active_breakdown_id": "breakdown-1",
        "active_breakdown_status": "done",
        "rebreakdown_pending": False,
        "settings": {"episode_seconds_min": 180, "episode_seconds_max": 240},
    }
    plan.update(overrides)
    return plan


def make_candidate():
    return {
        "id": BOOK_ID,
        "title": "长夜",
        "status": "completed",
        "chapters_done": 3,
        "words_done": 9000,
        "completed_at": "2026-11-10 09:00:00",
        "updated_at": "2026-11-10 10:00:00",
        "drama_adaptation": False,
        "eligible": True,
        "reason": None,
        "flagged": [],
        "projects": [{
            "id": "project-1",
            "title": "长夜 · 短片",
            "snapshot_no": 1,
            "created_at": "2026-11-10 09:30:00",
        }],
    }


def episodes_props(plan, *, notice=None, initial_expanded=None, initial_dialog=None,
                   on_dialog_open_change=None):
    return {
        "studioAllowed": True,
        "bookTitle": "长夜",
        "candidate": make_candidate(),
        "candidateError": None,
        "candidateLoading": False,
        "projectId": "project-1",
        "onSelectProject": None,
        "plan": plan,
        "planLoading": False,
        "planError": None,
        "busy": False,
        "onOperate": None,
        "onApprove": None,
        "onOpenStudio": None,
        "onAsk": None,
        "onRefresh": None,
        "notice": notice,
        "initialExpanded": initial_expanded,
        "initialDialog": initial_dialog,
        "onDialogOpenChange": on_dialog_open_change,
    }


def frame_props(book, *, mode="dock", composer_height=96, stage="chapters"):
    return {
        "mode": mode,
        "stage": stage,
        "onStageChange": None,
        "books": [book_summary(book)],
        "book": book,
        "loading": False,
        "error": None,
        "onRetry": None,
        "onSelectBook": None,
        "onRefresh": None,
        "onClose": None,
        "onOpenNovel": None,
        "onOpenStudio": None,
        "studioProjectId": None,
        "composerHeight": composer_height,
        "sheetExpanded": False,
        "onToggleSheet": None,
        "panelRef": None,
        "__childrenText": "阶段内容",
    }


# ────────────────────────── 章回页 ──────────────────────────


def test_chapter_tags_are_settled_only_for_done_chapter():
    html = render_view("DeskChaptersView.tsx", chapters_props(make_book()))
    assert_seal_only_on_settled_tag(html)


def test_chapter_tag_seal_checker_rejects_seal_on_unsettled_tag():
    """自检：给一段故意把朱色类加到其他标签的 HTML，检查器必须变红。"""
    html = render_view("DeskChaptersView.tsx", chapters_props(make_book()))
    assert_seal_only_on_settled_tag(html)
    bad, count = re.subn(
        r'(<span class=")([^"]*)(">细纲等你确认</span>)',
        lambda match: (f'{match.group(1)}{match.group(2)} '
                       f'{SEAL_TEXT} {SEAL_BORDER}{match.group(3)}'),
        html,
        count=1,
    )
    assert count == 1, "故意违规的标签没有替换成功"
    with pytest.raises(AssertionError):
        assert_seal_only_on_settled_tag(bad)


@pytest.mark.parametrize(
    "pending_notes,expect_disabled,expected_text",
    [
        (5, True, "待处理留言已满 5 条，等编辑部处理后再留。"),
        (2, False, "待处理留言 2 / 5"),
    ],
)
def test_chapter_notes_input_respects_pending_limit(pending_notes, expect_disabled, expected_text):
    html = render_view(
        "DeskChaptersView.tsx", chapters_props(make_book(pending_notes=pending_notes)))
    inputs = INPUT_TAG.findall(html)
    assert len(inputs) == 1, inputs
    assert has_disabled(inputs[0]) is expect_disabled, inputs[0]
    assert expected_text in html
    assert ("待处理留言已满" in html) is expect_disabled


def test_completed_book_has_no_note_composer():
    chapters = [chapter(1, "done", words=3000), chapter(2, "done", words=3200),
                chapter(3, "done", words=2800)]
    html = render_view(
        "DeskChaptersView.tsx",
        chapters_props(make_book(status="completed", pending_notes=0,
                                 chapters=chapters)),
    )
    # 先确认确实渲染了章回内容，再做“不出现”的断言。
    assert "定稿" in html
    assert "给编辑部留一句话" not in html
    assert "下一章定稿时会看到" not in html
    assert INPUT_TAG.search(html) is None
    assert "待处理留言" not in html


def test_chapter_expanded_written_chapter_has_read_body():
    html = render_view(
        "DeskChaptersView.tsx",
        chapters_props(make_book(), initial_expanded=1),
    )
    assert "读正文" in html
    assert "问分身" in html


def test_chapter_expanded_unwritten_chapter_hides_read_body():
    html = render_view(
        "DeskChaptersView.tsx",
        chapters_props(make_book(), initial_expanded=2),
    )
    assert "读正文" not in html
    assert "问分身" in html


# ────────────────────────── 分集页 ──────────────────────────


@pytest.mark.parametrize(
    "overrides",
    [
        {"active_breakdown_status": "running"},
        {"rebreakdown_pending": True},
    ],
)
def test_episodes_edits_blocked_disables_approval(overrides):
    html = render_view("DeskEpisodesView.tsx", episodes_props(make_plan(**overrides)))
    assert "拆解还没全部完成，暂时不能修改或批准，去工作室看进度。" in html
    assert has_disabled(button_with_text(html, "批准分集方案"))


def test_episodes_complete_plan_allows_approval():
    html = render_view("DeskEpisodesView.tsx", episodes_props(make_plan()))
    approval = button_with_text(html, "批准分集方案")
    assert not has_disabled(approval), approval
    assert "拆解还没全部完成" not in html
    assert "待批准" in html


def test_episodes_approved_plan_shows_tag_and_disables_approval():
    html = render_view(
        "DeskEpisodesView.tsx",
        episodes_props(make_plan(g0_approved=True, plan_approved_revision=3)),
    )
    assert "已批准" in html
    assert "待批准" not in html
    assert has_disabled(button_with_text(html, "批准分集方案"))


def test_episodes_approved_tag_has_seal_classes_and_pending_does_not():
    approved = render_view(
        "DeskEpisodesView.tsx",
        episodes_props(make_plan(g0_approved=True, plan_approved_revision=3)),
    )
    assert_approved_tag_has_seal(approved)

    pending = render_view("DeskEpisodesView.tsx", episodes_props(make_plan()))
    assert_pending_tag_has_no_seal(pending)

    # 自检：把朱色挪到汇总行而不是标签本身，检查器必须报错。
    bad = (
        f'<p class="{SEAL_TEXT} {SEAL_BORDER}">方案</p>'
        '<span class="tag">已批准</span>'
    )
    with pytest.raises(AssertionError):
        assert_approved_tag_has_seal(bad)


def test_episodes_edits_blocked_disables_modify_and_merge():
    html = render_view(
        "DeskEpisodesView.tsx",
        episodes_props(make_plan(active_breakdown_status="running"), initial_expanded=1),
    )
    assert "拆解还没全部完成，暂时不能修改或批准，去工作室看进度。" in html
    assert has_disabled(button_with_text(html, "修改"))
    assert has_disabled(button_with_text(html, "与下一集合并"))


def test_episodes_last_episode_merge_is_disabled_and_first_is_not():
    last = render_view(
        "DeskEpisodesView.tsx",
        episodes_props(make_plan(), initial_expanded=2),
    )
    assert has_disabled(button_with_text(last, "与下一集合并"))

    first = render_view(
        "DeskEpisodesView.tsx",
        episodes_props(make_plan(), initial_expanded=1),
    )
    assert not has_disabled(button_with_text(first, "与下一集合并"))


def test_episodes_notice_renders_alert_only_when_present():
    notice = "分集方案已在别处改动，已为你刷新，请再试一次。"
    with_notice = render_view(
        "DeskEpisodesView.tsx",
        episodes_props(make_plan(), notice=notice),
    )
    alert = re.search(r'<p role="alert"[^>]*>(.*?)</p>', with_notice)
    assert alert is not None, with_notice
    assert alert.group(1) == notice, alert.group(1)

    without_notice = render_view("DeskEpisodesView.tsx", episodes_props(make_plan()))
    assert 'role="alert"' not in without_notice


def test_episodes_empty_plan_only_shows_empty_state_and_studio_link():
    html = render_view(
        "DeskEpisodesView.tsx",
        episodes_props(make_plan(episodes=[])),
    )
    assert "还没有分集方案，拆解在工作室里做。" in html
    assert "在工作室打开" in html
    assert "方案第" not in html
    assert "批准分集方案" not in html


# ────────────────────────── 阶段标签 ──────────────────────────


def test_frame_renders_five_stage_tabs_and_only_one_selected():
    html = render_view("DeskFrame.tsx", frame_props(make_book()))
    assert "阶段内容" in html
    for label in ("立意", "章回", "分集", "分镜", "成片"):
        assert 'role="tab"' in button_with_text(html, label), label
    assert html.count('aria-selected="true"') == 1
    assert html.count('aria-selected="false"') == 4
    for label in ("分镜", "成片"):
        tab = button_with_text(html, label)
        assert has_disabled(tab), tab
        assert 'title="后续开放"' in tab, tab
    for label in ("立意", "章回", "分集"):
        tab = button_with_text(html, label)
        assert not has_disabled(tab), tab
        assert 'title="后续开放"' not in tab, tab


def test_frame_uses_opaque_drawer_and_sheet_and_correct_width_and_height():
    dock = render_view("DeskFrame.tsx", frame_props(make_book(), mode="dock"))
    dock_aside = aside_classes(dock)
    assert "bg-[color:var(--paper)]" not in dock_aside.split()
    assert_tablist_orientation(dock, vertical=True)

    drawer = render_view("DeskFrame.tsx", frame_props(make_book(), mode="drawer"))
    assert "bg-[color:var(--paper)]" in aside_classes(drawer).split()
    assert "w-[476px]" in drawer
    assert_tablist_orientation(drawer, vertical=True)

    sheet = render_view(
        "DeskFrame.tsx",
        frame_props(make_book(), mode="sheet", composer_height=88),
    )
    assert "bg-[color:var(--paper)]" in aside_classes(sheet).split()
    assert "45dvh" in sheet
    assert "56dvh" not in sheet
    assert (
        "min(45dvh, calc(100dvh - 94px - env(safe-area-inset-top) "
        "- var(--tabbar-h) - env(safe-area-inset-bottom) - 88px))"
    ) in sheet
    assert_tablist_orientation(sheet, vertical=False)
    bad_dock = dock.replace(' aria-orientation="vertical"', '', 1).replace(
        '<nav role="tablist"',
        '<div aria-orientation="vertical"></div><nav role="tablist"',
        1,
    )
    with pytest.raises(AssertionError):
        assert_tablist_orientation(bad_dock, vertical=True)
    bad_sheet = sheet.replace(
        '<nav role="tablist"',
        '<div aria-orientation="vertical"></div><nav role="tablist"',
        1,
    )
    with pytest.raises(AssertionError):
        assert_tablist_orientation(bad_sheet, vertical=False)
    for label in ("分镜", "成片"):
        tab = button_with_text(sheet, label)
        assert has_disabled(tab), tab
        assert 'title="后续开放"' in tab, tab


def test_chapter_expand_button_has_accessible_label():
    label = "第 1 章　测试章名"
    html = render_view("DeskChaptersView.tsx", chapters_props(make_book()))
    assert_expand_label(html, label)
    bad = (
        f'<div role="listitem" aria-label="{label}">'
        '<button type="button" aria-expanded="false">测试章名</button></div>'
    )
    with pytest.raises(AssertionError):
        assert_expand_label(bad, label)


def test_empty_chapters_are_not_inside_role_list():
    html = render_view(
        "DeskChaptersView.tsx",
        chapters_props(make_book(chapters=[], chapters_done=0)),
    )
    assert "第一章写好后会出现在这里。" in html
    assert 'role="list"' not in html


def test_episode_no_project_without_reason_has_no_invented_suffix():
    props = episodes_props(make_plan())
    props["candidate"] = {**make_candidate(), "eligible": False, "reason": None,
                          "projects": []}
    html = render_view("DeskEpisodesView.tsx", props)
    messages = re.findall(r'<div\b[^>]*>(这本书还没有短片项目。)</div>', html)
    assert messages == ["这本书还没有短片项目。"], html
    assert "暂时还不能建短片项目。" not in html


def test_episode_expand_button_has_accessible_label():
    label = "第 1 集　第 1 集 测试标题"
    html = render_view("DeskEpisodesView.tsx", episodes_props(make_plan()))
    assert_expand_label(html, label)
    bad = (
        f'<div role="listitem" aria-label="{label}">'
        '<button type="button" aria-expanded="false">标题</button></div>'
    )
    with pytest.raises(AssertionError):
        assert_expand_label(bad, label)


def test_frame_loading_title_is_blank_not_unnamed():
    props = frame_props(make_book())
    props["book"] = None
    props["loading"] = True
    html = render_view("DeskFrame.tsx", props)
    assert "正在取回作品…" in html
    assert "未命名" not in html


def test_stage_tabs_expose_exactly_one_tab_stop_in_both_orientations():
    dock = render_view(
        "DeskFrame.tsx", frame_props(make_book(), mode="dock", stage="episodes"))
    sheet = render_view(
        "DeskFrame.tsx", frame_props(make_book(), mode="sheet", stage="episodes"))
    assert_unique_tab_stop(dock, "episodes")
    assert_unique_tab_stop(sheet, "episodes")
    with pytest.raises(AssertionError):
        assert_unique_tab_stop(
            dock.replace('aria-selected="true"', 'aria-selected="false"', 1),
            "episodes",
        )


@pytest.mark.parametrize(("kind", "confirm"), [
    ("edit", None),
    ("merge", "确认合并"),
    ("approve", "确认批准"),
])
def test_locked_plan_dialogs_keep_cancel_enabled(kind, confirm):
    plan = make_plan(active_breakdown_status="running")
    initial = {"kind": "approve"} if kind == "approve" else {"kind": kind, "no": 1}
    html = render_view(
        "DeskEpisodesView.tsx",
        episodes_props(plan, initial_dialog=initial),
    )
    assert not has_disabled(button_with_text(html, "取消"))
    if confirm:
        assert has_disabled(button_with_text(html, confirm))
