"""DeskDock 容器竞态回归：真实组件 + 迷你 hooks 运行时 + 延迟桩。

离线运行，只读仓库内源码。覆盖规格 11.1 的两个加载卡死场景和 11.4 的
“关闭后不再发 GET”场景。node 或 typescript 缺失时在启动 node 之前 skip。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
DEPENDENCIES = {"typescript": "typescript/lib/typescript.js"}


def require_node_dependencies():
    missing = [name for name, entry in DEPENDENCIES.items()
               if not (FRONTEND / "node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")


@pytest.mark.parametrize("missing", [*DEPENDENCIES, "node"])
def test_race_tests_skip_before_node_when_dependency_is_missing(monkeypatch, tmp_path, missing):
    for name, entry in DEPENDENCIES.items():
        path = tmp_path / "frontend/node_modules" / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        if name != missing:
            path.write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "FRONTEND", tmp_path / "frontend")
    if missing == "node":
        monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail(
        "Node must not start without dependencies"))
    expected = ("node is unavailable" if missing == "node"
                else "frontend dependencies unavailable: " + missing)
    with pytest.raises(pytest.skip.Exception, match=re.escape(expected)):
        require_node_dependencies()


# 迷你 hooks 运行时来自复核报告附录 desk-race.js；只读仓库内源码，桩后端
# 用延迟 Promise 模拟。每个场景输出一行 JSON，Python 侧绑定断言。
NODE_DRIVER = r"""
const fs = require('fs');
const path = require('path');
const ts = require(path.join(process.cwd(), 'node_modules/typescript'));
const FRONTEND = process.cwd();

let slots = [], cursor = 0, pendingEffects = [], scheduled = false, Component = null, props = null, lastTree = null;
function schedule() { if (!scheduled) { scheduled = true; setTimeout(flush, 0); } }
function flush() {
  scheduled = false; cursor = 0; pendingEffects = [];
  lastTree = Component(props);
  for (const run of pendingEffects) run();
}
const React = {
  useState(init) {
    const i = cursor++;
    if (!(i in slots)) slots[i] = { v: typeof init === 'function' ? init() : init };
    const slot = slots[i];
    return [slot.v, next => { const v = typeof next === 'function' ? next(slot.v) : next; if (!Object.is(v, slot.v)) { slot.v = v; schedule(); } }];
  },
  useRef(init) { const i = cursor++; if (!(i in slots)) slots[i] = { current: init }; return slots[i]; },
  useCallback(fn, deps) { const i = cursor++; const prev = slots[i]; if (prev && deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return prev.fn; slots[i] = { fn, deps }; return fn; },
  useMemo(fn, deps) { const i = cursor++; const prev = slots[i]; if (prev && deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return prev.v; const v = fn(); slots[i] = { v, deps }; return v; },
  useEffect(fn, deps) {
    const i = cursor++; const prev = slots[i];
    if (prev && deps && prev.deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return;
    if (!prev) slots[i] = { deps: null, cleanup: null };
    pendingEffects.push(() => { const p = slots[i]; if (p.cleanup) p.cleanup(); const c = fn(); slots[i] = { deps, cleanup: typeof c === 'function' ? c : null }; });
  },
  useId() { cursor++; return 'id'; },
  useSyncExternalStore(_s, get) { cursor++; return get(); },
};
const jsx = (type, p, key) => ({ type, props: p || {}, key });

const t0 = Date.now();
const getCalls = [];
const log = [];
const stamp = () => ((Date.now() - t0) / 1000).toFixed(2) + 's';
const delay = (ms, value, signal, label) => new Promise((resolve, reject) => {
  let settled = false;
  const t = setTimeout(() => { settled = true; log.push(`${stamp()} ${label} 完成`); resolve(typeof value === 'function' ? value() : value); }, ms);
  if (signal) signal.addEventListener('abort', () => { if (settled) return; settled = true; clearTimeout(t); log.push(`${stamp()} ${label} 被取消`); reject(Object.assign(new Error('aborted'), { name: 'AbortError' })); });
});
const get = (ms, value, signal, label) => { getCalls.push(label); return delay(ms, value, signal, label); };

const SCENARIO = process.argv[1] || 'episodes';
const CHAPTER_SCENARIO = SCENARIO === 'write' || SCENARIO === 'close';
const CHAPTER_STAGE = CHAPTER_SCENARIO || SCENARIO === 'locate';
const MULTI_BOOK = SCENARIO === 'write' || SCENARIO === 'locate';
const A = '11111111-1111-1111-1111-111111111111', B = '22222222-2222-2222-2222-222222222222';
const book = { id: A, title: '甲', status: CHAPTER_SCENARIO ? 'awaiting_review' : 'completed', chapters_done: 3, words_done: 9000, updated_at: '2026-11-10', chapters: [], config: { batch_size: 3, adaptation: { max_scenes_per_chapter: 6 } }, pending_notes: 0, bible: null, compass: null };
const plan = { episodes: [{ id: 'e1', no: 1, title: '一', warnings: [] }], units: [], unassigned: [], plan_revision: 2, plan_approved_revision: null, g0_approved: false, total_seconds: 200, status: 'done', active_breakdown_status: 'running', rebreakdown_pending: true };
class ApiError extends Error { constructor(m, s) { super(m); this.status = s; } }
const STUBS = {
  react: React,
  'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
  '@/lib/auth': { getUsername: () => 'fixture-user', ensureAccountIdentity: async () => {} },
  '@/lib/agents': { ApiError },
  '@/lib/novels': {
    listNovels: signal => get(30, MULTI_BOOK ? [book, { ...book, id: B, title: '乙' }] : [book], signal, 'GET 书目'),
    getNovel: (id, signal) => get(id === B ? 300 : 30, id === B ? { ...book, id: B, title: '乙' } : book, signal, `GET 详情 ${id === B ? '乙' : '甲'}`),
    novelApi: { action: (id, action, body, opts) => delay(120, {}, opts && opts.signal, `POST ${action}`) },
    getNovelChapter: async () => ({}), getNovelDraft: async () => ({}),
    addNovelNote: async () => ({}), exportNovel: async () => null, novelErrorMessage: e => String(e && e.message),
  },
  '@/lib/studio': {
    listStudioNovelSources: signal => get(800, { enabled: true, books: [{ id: A, eligible: true, projects: [{ id: 'p1', title: '甲短片', snapshot_no: 1, created_at: '2026-11-10' }] }] }, signal, 'GET 工作室来源(候选)'),
    studioErrorMessage: String,
  },
  '@/lib/studio-breakdown': {
    getStudioEpisodes: (id, signal) => get(100, plan, signal, 'GET 分集方案'),
    operateStudioEpisodes: async () => plan,
    approveStudioEpisodes: async () => plan,
  },
  '@/components/novel/NovelShell': { canCloseNovelDrawer: () => false },
  './DeskChaptersView': { __esModule: true, default: function DeskChaptersView() {} },
  './DeskDialogs': { DeskPlanDialog() {}, DeskReaderDialog() {} },
  './DeskEpisodesView': { __esModule: true, default: function DeskEpisodesView() {} },
  './DeskFrame': { __esModule: true, default: function DeskFrame() {} },
  './DeskIdeaView': { __esModule: true, default: function DeskIdeaView() {} },
};
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const mod = { exports: {} }; cache.set(file, mod);
  const out = ts.transpileModule(fs.readFileSync(file, 'utf8'), { fileName: file, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function('exports', 'require', 'module', out)(mod.exports, spec => {
    if (spec in STUBS) return STUBS[spec];
    if (spec.startsWith('@/')) { const base = path.join(FRONTEND, spec.slice(2)); return load(fs.existsSync(base + '.ts') ? base + '.ts' : base + '.tsx'); }
    throw new Error('unexpected import ' + spec);
  }, mod);
  return mod.exports;
}
const store = new Map([['fiona.desk.v1:fixture-user', JSON.stringify({ open: true, novelId: A, stage: CHAPTER_STAGE ? 'chapters' : 'episodes' })]]);
global.window = { localStorage: { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) }, requestAnimationFrame: cb => setTimeout(cb, 0), cancelAnimationFrame: t => clearTimeout(t), addEventListener() {}, removeEventListener() {}, innerWidth: 1440, setTimeout, clearTimeout };
global.HTMLElement = class HTMLElement {};
global.document = { activeElement: null, hidden: false, addEventListener() {}, removeEventListener() {}, querySelector: () => null, querySelectorAll: () => [] };

function find(tree, name) {
  if (!tree || typeof tree !== 'object') return null;
  if (Array.isArray(tree)) { for (const t of tree) { const f = find(t, name); if (f) return f; } return null; }
  if (tree.type && tree.type.name === name) return tree;
  return find(tree.props && tree.props.children, name);
}
const { default: DeskDock } = load(path.join(FRONTEND, 'components/desk/DeskDock.tsx'));
props = { owner: 'fixture-user', open: true, onOpenChange() {}, studioAllowed: true, composerHeight: 96, focus: SCENARIO === 'locate' ? { subject: { kind: 'project', projectId: 'p1' }, nonce: 1 } : null, onAsk() {}, onOpenNovel() {}, onOpenNovelShelf() {}, onOpenStudio() {}, onOpenSettings() {} };
Component = DeskDock(props).type;
flush();
const sleep = ms => new Promise(r => setTimeout(r, ms));
const view = () => { const v = find(lastTree, 'DeskEpisodesView'); return v ? { candidateLoading: v.props.candidateLoading, hasPlan: !!v.props.plan } : null; };
async function writeScenario() {
  await sleep(300);
  log.push(`${stamp()} 点 GateBanner「继续写下 3 章」，POST 进行中立即在「作品」下拉切到乙`);
  const action = find(lastTree, 'DeskChaptersView').props.onAction('continue').catch(() => {});
  await sleep(10);
  find(lastTree, 'DeskFrame').props.onSelectBook(B);
  await action; await sleep(1500);
  const frame = find(lastTree, 'DeskFrame').props;
  console.log(JSON.stringify({ scenario: 'write', loading: frame.loading, book: frame.book && frame.book.title, error: frame.error, log }));
  process.exit(0);
}
async function locateScenario() {
  await sleep(1800);
  log.push(`${stamp()} 卡片定位后：${JSON.stringify({ book: find(lastTree, 'DeskFrame').props.book?.title, stage: find(lastTree, 'DeskFrame').props.stage })}`);
  const frame = find(lastTree, 'DeskFrame').props;
  frame.onSelectBook(B);
  await sleep(700);
  frame.onStageChange('chapters');
  await sleep(150);
  props = { ...props, open: false };
  flush();
  await sleep(100);
  const before = getCalls.filter(label => label.includes('工作室来源')).length;
  props = { ...props, open: true };
  flush();
  await sleep(1800);
  const afterFrame = find(lastTree, 'DeskFrame').props;
  const reopened = getCalls.filter(label => label.includes('工作室来源')).length - before;
  console.log(JSON.stringify({ scenario: 'locate', book: afterFrame.book && afterFrame.book.title, stage: afterFrame.stage, sourcesAfterReopen: reopened, log }));
  process.exit(0);
}
async function closeScenario() {
  await sleep(300);
  log.push(`${stamp()} 开始写操作后立即关闭案头`);
  const action = find(lastTree, 'DeskChaptersView').props.onAction('continue').catch(() => {});
  props = { ...props, open: false };
  flush();
  const before = getCalls.length;
  await action; await sleep(1500);
  console.log(JSON.stringify({ scenario: 'close', getCallsAfterClose: getCalls.length - before, log }));
  process.exit(0);
}
(async () => {
  if (SCENARIO === 'write') return writeScenario();
  if (SCENARIO === 'close') return closeScenario();
  if (SCENARIO === 'locate') return locateScenario();
  await sleep(1500);
  log.push(`${stamp()} 首次载入后：${JSON.stringify(view())}（此后每 5 秒轮询一次分集方案）`);
  await sleep(4400);
  log.push(`${stamp()} 点「刷新」`);
  find(lastTree, 'DeskFrame').props.onRefresh();
  await sleep(12000);
  log.push(`${stamp()} 等待 12 秒后：${JSON.stringify(view())}`);
  console.log(JSON.stringify({ scenario: 'episodes', ...view(), log }));
  process.exit(0);
})();
"""


def run_scenario(scenario):
    require_node_dependencies()
    result = subprocess.run(
        ["node", "-e", NODE_DRIVER, scenario],
        cwd=FRONTEND, capture_output=True, text=True, timeout=40,
    )
    if result.returncode != 0:
        pytest.fail(f"node race scenario {scenario} failed:\n{result.stderr}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, result.stdout
    return json.loads(lines[-1])


def test_write_then_switch_book_clears_loading_and_selects_new_book():
    result = run_scenario("write")
    assert result["loading"] is False, result
    assert result["book"] == "乙", result
    assert result["error"] is None, result


def test_refresh_during_plan_poll_clears_candidate_loading():
    result = run_scenario("episodes")
    assert result["candidateLoading"] is False, result
    assert result["hasPlan"] is True, result


def test_close_stops_new_get_requests():
    result = run_scenario("close")
    assert result["getCallsAfterClose"] == 0, result


def test_locate_happens_only_once_per_card_nonce():
    result = run_scenario("locate")
    assert result["book"] == "乙", result
    assert result["stage"] == "chapters", result
    assert result["sourcesAfterReopen"] == 0, result


# 复核报告附录 A 的焦点/409 探针，改成可断言的独立场景驱动器。
NODE_FOCUS_DRIVER = r"""
const fs = require('fs');
const path = require('path');
const ts = require(path.join(process.cwd(), 'node_modules/typescript'));
const FRONTEND = process.cwd();
const SCENARIO = process.argv[1] || 'lockedit';
const LOCK = SCENARIO === 'lockedit' || SCENARIO === 'lockapprove';
const CONFLICT = SCENARIO === 'conflict';
const LOCATE_CANCEL = SCENARIO === 'locatecancel';
let slots = [], cursor = 0, pendingEffects = [], scheduled = false, Component = null, props = null, lastTree = null;
let afterRender = () => {};
function schedule() { if (!scheduled) { scheduled = true; setTimeout(flush, 0); } }
function flush() {
  scheduled = false; cursor = 0; pendingEffects = [];
  lastTree = Component(props);
  afterRender(lastTree);
  for (const run of pendingEffects) run();
}
const React = {
  useState(init) {
    const i = cursor++;
    if (!(i in slots)) slots[i] = { v: typeof init === 'function' ? init() : init };
    const slot = slots[i];
    return [slot.v, next => { const v = typeof next === 'function' ? next(slot.v) : next; if (!Object.is(v, slot.v)) { slot.v = v; schedule(); } }];
  },
  useRef(init) { const i = cursor++; if (!(i in slots)) slots[i] = { current: init }; return slots[i]; },
  useCallback(fn, deps) { const i = cursor++; const prev = slots[i]; if (prev && deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return prev.fn; slots[i] = { fn, deps }; return fn; },
  useMemo(fn, deps) { const i = cursor++; const prev = slots[i]; if (prev && deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return prev.v; const v = fn(); slots[i] = { v, deps }; return v; },
  useEffect(fn, deps) {
    const i = cursor++; const prev = slots[i];
    if (prev && deps && prev.deps && deps.every((d, k) => Object.is(d, prev.deps[k]))) return;
    if (!prev) slots[i] = { deps: null, cleanup: null };
    pendingEffects.push(() => { const p = slots[i]; if (p.cleanup) p.cleanup(); const c = fn(); slots[i] = { deps, cleanup: typeof c === 'function' ? c : null }; });
  },
  useId() { cursor++; return 'id'; },
  useSyncExternalStore(_s, get) { cursor++; return get(); },
};
const jsx = (type, p, key) => ({ type, props: p || {}, key });
const log = [];
const t0 = Date.now();
const stamp = () => ((Date.now() - t0) / 1000).toFixed(2) + 's';
const delay = (ms, value, signal, label) => new Promise((resolve, reject) => {
  let settled = false;
  const t = setTimeout(() => { settled = true; log.push(`${stamp()} ${label} 完成`); resolve(typeof value === 'function' ? value() : value); }, ms);
  if (signal) signal.addEventListener('abort', () => { if (settled) return; settled = true; clearTimeout(t); log.push(`${stamp()} ${label} 被取消`); reject(Object.assign(new Error('aborted'), { name: 'AbortError' })); });
});

class HTMLElement {
  constructor(name, parent) { this.name = name; this.parent = parent || null; this.isConnected = true; }
  focus() { if (this.isConnected) { document.activeElement = this; log.push(`${stamp()} 焦点 → ${this.name}`); } }
  matches(selector) { return selector === 'button[aria-controls="desk-panel"]' && this.name === '头部「案头」开关'; }
  getClientRects() { return this.isConnected ? [{}] : []; }
  contains(other) { for (let node = other; node; node = node.parent) if (node === this) return true; return false; }
}
global.HTMLElement = HTMLElement;
const body = new HTMLElement('body');
const toggle = new HTMLElement('头部「案头」开关');
const textarea = new HTMLElement('输入框');
const panel = new HTMLElement('案头面板 #desk-panel');
const closeButton = new HTMLElement('面板里的「收起案头」X', panel);
global.document = {
  activeElement: body, hidden: false, body,
  addEventListener() {}, removeEventListener() {},
  querySelector: () => null,
  querySelectorAll: selector => selector === 'button[aria-controls="desk-panel"]' ? [toggle] : [],
};

const A = '11111111-1111-1111-1111-111111111111';
class ApiError extends Error { constructor(m, s) { super(m); this.status = s; } }
const book = { id: A, title: '甲', status: 'completed', chapters_done: 3, words_done: 9000, updated_at: '2026-11-10', chapters: [], config: { batch_size: 3, adaptation: { max_scenes_per_chapter: 6 } }, pending_notes: 0, bible: null, compass: null };
let locked = false;
let operationConflict = LOCK || CONFLICT;
let versionBump = false;
const planNow = () => ({
  episodes: [{ id: 'e1', no: 1, title: '一', warnings: [] }, { id: 'e2', no: 2, title: '二', warnings: [] }],
  units: [], unassigned: [],
  plan_revision: (LOCK || CONFLICT ? 5 : 2) + (versionBump ? 1 : 0),
  plan_approved_revision: null, g0_approved: false, total_seconds: 400, status: 'done',
  active_breakdown_status: locked ? 'running' : 'done',
  rebreakdown_pending: locked,
});
const lockMessage = SCENARIO === 'lockapprove'
  ? '拆解尚未全部完成，不能批准分集方案'
  : '拆解尚未完成，完成后才能修改分集方案';
const STUBS = {
  react: React, 'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'Fragment' },
  '@/lib/auth': { getUsername: () => 'fixture-user', ensureAccountIdentity: async () => {} },
  '@/lib/agents': { ApiError },
  '@/lib/novels': {
    listNovels: signal => delay(30, [book], signal, 'GET 书目'),
    getNovel: (id, signal) => delay(30, book, signal, 'GET 详情'),
    novelApi: { action: async () => ({}) }, getNovelChapter: async () => ({}), getNovelDraft: async () => ({}),
    addNovelNote: async () => ({}), exportNovel: async () => null, novelErrorMessage: e => String(e && e.message),
  },
  '@/lib/studio': {
    listStudioNovelSources: signal => delay(LOCATE_CANCEL ? 800 : 60, { enabled: true, books: [{ id: A, eligible: true, projects: [{ id: 'p1', title: '甲短片', snapshot_no: 1, created_at: '2026-11-10' }] }] }, signal, 'GET 工作室来源'),
    studioErrorMessage: e => String(e && e.message),
  },
  '@/lib/studio-breakdown': {
    getStudioEpisodes: (id, signal) => delay(60, planNow, signal, 'GET 分集方案'),
    operateStudioEpisodes: async () => { if (operationConflict) throw new ApiError(lockMessage, 409); return planNow(); },
    approveStudioEpisodes: async () => { if (operationConflict) throw new ApiError(lockMessage, 409); return planNow(); },
  },
  '@/components/novel/NovelShell': { canCloseNovelDrawer: () => false },
  './DeskChaptersView': { __esModule: true, default: function DeskChaptersView() {} },
  './DeskDialogs': { DeskPlanDialog() {}, DeskReaderDialog() {} },
  './DeskEpisodesView': { __esModule: true, default: function DeskEpisodesView() {} },
  './DeskFrame': { __esModule: true, default: function DeskFrame() {} },
  './DeskIdeaView': { __esModule: true, default: function DeskIdeaView() {} },
};
const cache = new Map();
function load(file) {
  if (cache.has(file)) return cache.get(file).exports;
  const mod = { exports: {} }; cache.set(file, mod);
  const out = ts.transpileModule(fs.readFileSync(file, 'utf8'), { fileName: file, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function('exports', 'require', 'module', out)(mod.exports, spec => {
    if (spec in STUBS) return STUBS[spec];
    if (spec.startsWith('@/')) { const base = path.join(FRONTEND, spec.slice(2)); return load(fs.existsSync(base + '.ts') ? base + '.ts' : base + '.tsx'); }
    throw new Error('unexpected import ' + spec);
  }, mod);
  return mod.exports;
}
function find(tree, name) {
  if (!tree || typeof tree !== 'object') return null;
  if (Array.isArray(tree)) { for (const t of tree) { const f = find(t, name); if (f) return f; } return null; }
  if (tree.type && tree.type.name === name) return tree;
  return find(tree.props && tree.props.children, name);
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const stage = LOCK || CONFLICT ? 'episodes' : 'chapters';
const store = new Map([['fiona.desk.v1:fixture-user', JSON.stringify({ open: true, novelId: A, stage })]]);
global.window = { localStorage: { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) }, requestAnimationFrame: cb => setTimeout(cb, 0), cancelAnimationFrame: t => clearTimeout(t), addEventListener() {}, removeEventListener() {}, innerWidth: 1280, setTimeout, clearTimeout };
afterRender = tree => {
  const frame = find(tree, 'DeskFrame');
  if (frame) { frame.props.panelRef.current = panel; panel.isConnected = true; closeButton.isConnected = true; }
  else if (panel.isConnected) {
    panel.isConnected = false; closeButton.isConnected = false;
    if (panel.contains(document.activeElement)) { document.activeElement = body; log.push(`${stamp()} 面板卸载，焦点掉到 body`); }
  }
};
const { default: DeskDock } = load(path.join(FRONTEND, 'components/desk/DeskDock.tsx'));
const baseProps = {
  owner: 'fixture-user', open: false, studioAllowed: true, composerHeight: 96, focus: null,
  onAsk() {}, onOpenNovel() {}, onOpenNovelShelf() {}, onOpenStudio() {}, onOpenSettings() {},
  onOpenChange(next) { props = { ...props, open: next }; schedule(); },
};
const initialOpen = LOCK || CONFLICT || LOCATE_CANCEL;
props = { ...baseProps, open: initialOpen, focus: LOCATE_CANCEL ? { subject: { kind: 'project', projectId: 'p1' }, nonce: 7 } : null };
Component = DeskDock(props).type;
flush();

async function lockScenario(kind) {
  await sleep(500);
  let view = find(lastTree, 'DeskEpisodesView').props;
  const beforeActive = view.plan.active_breakdown_status;
  locked = true; operationConflict = true;
  log.push(`${stamp()} 载入未阻塞方案后，在工作室发起重新拆解；回到案头执行 ${kind}`);
  let outcome;
  try {
    if (kind === 'edit') await view.onOperate({ op: 'edit', no: 1, fields: { title: '作者刚改的标题', change: '', hook: '', notes: '', target_min: null, target_max: null } });
    else await view.onApprove();
    outcome = { rejected: false };
  } catch (error) {
    outcome = { rejected: true, status: error.status, message: error.message };
  }
  await sleep(300);
  view = find(lastTree, 'DeskEpisodesView').props;
  console.log(JSON.stringify({
    scenario: SCENARIO, onConfirm: outcome, notice: view.notice, busy: view.busy,
    planRevision: view.plan.plan_revision, activeStatus: view.plan.active_breakdown_status,
    beforeActive,
  }));
  process.exit(0);
}

async function conflictScenario() {
  await sleep(500);
  let view = find(lastTree, 'DeskEpisodesView').props;
  operationConflict = true; versionBump = true;
  log.push(`${stamp()} 载入第 5 版后，别处发布第 6 版；回到案头保存修改`);
  let outcome;
  try {
    await view.onOperate({ op: 'edit', no: 1, fields: { title: '作者刚改的标题', change: '', hook: '', notes: '', target_min: null, target_max: null } });
    outcome = { rejected: false };
  } catch (error) {
    outcome = { rejected: true, status: error.status, message: error.message };
  }
  await sleep(300);
  view = find(lastTree, 'DeskEpisodesView').props;
  console.log(JSON.stringify({
    scenario: SCENARIO, onConfirm: outcome, notice: view.notice,
    planRevision: view.plan.plan_revision, activeStatus: view.plan.active_breakdown_status,
  }));
  process.exit(0);
}

async function xcloseScenario(how) {
  if (how === 'restore') {
    document.activeElement = body;
    props = { ...baseProps, open: true };
    flush();
  } else {
    props = { ...baseProps, open: false };
    flush();
    await sleep(50);
    document.activeElement = how === 'auto' ? textarea : toggle;
    if (how === 'auto') log.push(`${stamp()} 流式卡片到达，自动打开（焦点在输入框）`);
    else log.push(`${stamp()} 作者点头部开关打开（焦点在开关上）`);
    props = { ...props, open: true };
    flush();
  }
  await sleep(300);
  const afterOpen = document.activeElement.name;
  log.push(`${stamp()} 打开后焦点在：${afterOpen}`);
  closeButton.focus();
  find(lastTree, 'DeskFrame').props.onClose();
  await sleep(300);
  console.log(JSON.stringify({ scenario: SCENARIO, focusAfterOpen: afterOpen, focusAfterClose: document.activeElement.name }));
  process.exit(0);
}

async function locateCancelScenario() {
  await sleep(150);
  log.push(`${stamp()} 定位请求在途时收起案头`);
  props = { ...props, open: false }; flush();
  await sleep(300);
  log.push(`${stamp()} 再打开`);
  props = { ...props, open: true }; flush();
  await sleep(1600);
  const frame = find(lastTree, 'DeskFrame').props;
  console.log(JSON.stringify({ scenario: SCENARIO, stage: frame.stage, book: frame.book && frame.book.title }));
  process.exit(0);
}

(async () => {
  if (SCENARIO === 'lockedit') return lockScenario('edit');
  if (SCENARIO === 'lockapprove') return lockScenario('approve');
  if (SCENARIO === 'conflict') return conflictScenario();
  if (SCENARIO === 'xclose-restore' || SCENARIO === 'xclose-auto' || SCENARIO === 'xclose-hand') return xcloseScenario(SCENARIO.slice(7));
  if (SCENARIO === 'locatecancel') return locateCancelScenario();
  throw new Error('unknown scenario ' + SCENARIO);
})();
"""


def run_focus_scenario(scenario):
    require_node_dependencies()
    result = subprocess.run(
        ["node", "-e", NODE_FOCUS_DRIVER, scenario],
        cwd=FRONTEND, capture_output=True, text=True, timeout=40,
    )
    if result.returncode != 0:
        pytest.fail(f"node focus scenario {scenario} failed:\n{result.stderr}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert lines, result.stdout
    return json.loads(lines[-1])


def test_non_conflict_409_keeps_reason_and_refreshes_locked_plan():
    edit = run_focus_scenario("lockedit")
    assert edit["onConfirm"] == {
        "rejected": True,
        "status": 409,
        "message": "拆解尚未完成，完成后才能修改分集方案",
    }, edit
    assert edit["notice"] is None
    assert edit["planRevision"] == 5
    assert edit["beforeActive"] == "done"
    assert edit["activeStatus"] == "running"

    approve = run_focus_scenario("lockapprove")
    assert approve["onConfirm"] == {
        "rejected": True,
        "status": 409,
        "message": "拆解尚未全部完成，不能批准分集方案",
    }, approve
    assert approve["notice"] is None
    assert approve["beforeActive"] == "done"
    assert approve["activeStatus"] == "running"


def test_real_version_conflict_sets_notice_and_resolves():
    result = run_focus_scenario("conflict")
    assert result["onConfirm"] == {"rejected": False}, result
    assert result["notice"] == "分集方案已在别处改动，已为你刷新，请再试一次。", result
    assert result["planRevision"] == 6
    assert result["activeStatus"] == "done"


def test_close_from_panel_restores_focus_after_restore_open():
    result = run_focus_scenario("xclose-restore")
    assert result["focusAfterOpen"] == "body", result
    assert result["focusAfterClose"] == "头部「案头」开关", result


def test_close_from_panel_restores_focus_after_auto_open():
    result = run_focus_scenario("xclose-auto")
    assert result["focusAfterOpen"] == "输入框", result
    assert result["focusAfterClose"] == "头部「案头」开关", result


def test_close_from_panel_restores_focus_after_hand_open():
    result = run_focus_scenario("xclose-hand")
    assert result["focusAfterOpen"] == "案头面板 #desk-panel", result
    assert result["focusAfterClose"] == "头部「案头」开关", result


def test_locate_request_cancelled_by_close_retries_on_reopen():
    result = run_focus_scenario("locatecancel")
    assert result["stage"] == "episodes", result
    assert result["book"] == "甲", result
