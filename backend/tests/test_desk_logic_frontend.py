"""案头纯函数契约：在 node 里转译执行 frontend/lib/desk.ts。

离线运行。缺 frontend 依赖或 node 时整组 skip；缺依赖自检证明在起 node
之前就跳过。所有用例都直接调用真实导出，断言精确结果。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DESK = ROOT / "frontend/lib/desk.ts"
DEPENDENCIES = {
    "typescript": "typescript/lib/typescript.js",
}
DRAFT_ID = "12345678-1234-1234-1234-123456789abc"
DEFAULT_PREFS = {"open": False, "novelId": None, "stage": "chapters"}


def require_node_dependencies():
    missing = [name for name, entry in DEPENDENCIES.items()
               if not (ROOT / "frontend/node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")


@pytest.mark.parametrize("missing", [*DEPENDENCIES, "node"])
def test_node_tests_skip_before_node_when_any_dependency_is_missing(monkeypatch, tmp_path, missing):
    for name, entry in DEPENDENCIES.items():
        path = tmp_path / "frontend/node_modules" / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        if name != missing:
            path.write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    if missing == "node":
        monkeypatch.setattr(shutil, "which", lambda command: None)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail(
        "Node must not start without dependencies"))
    expected = ("node is unavailable" if missing == "node"
                else "frontend dependencies unavailable: " + missing)
    with pytest.raises(pytest.skip.Exception, match=re.escape(expected)):
        require_node_dependencies()


NODE_LOADER = """
const fs = require('fs');
const ts = require('typescript');
const source = fs.readFileSync(process.argv[1], 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const moduleObject = { exports: {} };
function localRequire(name) { throw new Error('unexpected runtime import: ' + name); }
new Function('exports', 'require', 'module', compiled)(moduleObject.exports, localRequire, moduleObject);
const desk = moduleObject.exports;
"""


def run_desk(script, payload):
    require_node_dependencies()
    assert DESK.is_file(), "frontend/lib/desk.ts 尚未实现"
    source = NODE_LOADER + "\nconst payload = " + json.dumps(
        payload, ensure_ascii=False) + ";\n" + script
    result = subprocess.run(
        ["node", "-e", source, str(DESK)],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail("node runner failed:\n" + result.stderr)
    return json.loads(result.stdout)


def test_desk_stages_default_prefs_and_mode():
    payload = {
        "stages": [
            {"id": "idea", "label": "立意", "enabled": True},
            {"id": "chapters", "label": "章回", "enabled": True},
            {"id": "episodes", "label": "分集", "enabled": True},
            {"id": "shots", "label": "分镜", "enabled": False},
            {"id": "film", "label": "成片", "enabled": False},
        ],
        "defaultPrefs": DEFAULT_PREFS,
    }
    result = run_desk("""
process.stdout.write(JSON.stringify({
  stages: desk.DESK_STAGES,
  defaultPrefs: desk.DESK_DEFAULT_PREFS,
  modes: [
    desk.deskMode(1440), desk.deskMode(1439), desk.deskMode(768),
    desk.deskMode(767), desk.deskMode(NaN),
  ],
}));
""", payload)
    # 顺序、文案、enabled 与默认偏好逐项精确比对。
    assert result["stages"] == payload["stages"]
    assert result["defaultPrefs"] == DEFAULT_PREFS
    assert result["modes"] == ["dock", "drawer", "drawer", "sheet", "sheet"]


def test_desk_auto_opens_only_for_desktop_and_tablet_modes():
    result = run_desk("""
process.stdout.write(JSON.stringify({
  widths: [767, 768, 1439, 1440].map(width => desk.deskAutoOpens(width)),
}));
""", {})
    assert result["widths"] == [False, True, True, True]


def test_is_revision_conflict_only_when_revision_really_changed():
    result = run_desk("""
process.stdout.write(JSON.stringify({
  changed: desk.isRevisionConflict(2, { plan_revision: 3 }),
  same: desk.isRevisionConflict(2, { plan_revision: 2 }),
  nullValue: desk.isRevisionConflict(2, null),
  undefinedValue: desk.isRevisionConflict(2, undefined),
}));
""", {})
    assert result == {
        "changed": True,
        "same": False,
        "nullValue": False,
        "undefinedValue": False,
    }


def test_desk_stage_by_key_moves_only_between_enabled_stages_and_wraps():
    result = run_desk("""
process.stdout.write(JSON.stringify({
  downFromEpisodes: desk.deskStageByKey("episodes", "ArrowDown", "vertical"),
  upFromIdea: desk.deskStageByKey("idea", "ArrowUp", "vertical"),
  downFromChapters: desk.deskStageByKey("chapters", "ArrowDown", "vertical"),
  rightInVertical: desk.deskStageByKey("chapters", "ArrowRight", "vertical"),
  rightFromEpisodesHorizontal: desk.deskStageByKey("episodes", "ArrowRight", "horizontal"),
  downInHorizontal: desk.deskStageByKey("chapters", "ArrowDown", "horizontal"),
  homeFromChapters: desk.deskStageByKey("chapters", "Home", "horizontal"),
  homeFromChaptersVertical: desk.deskStageByKey("chapters", "Home", "vertical"),
  endFromChapters: desk.deskStageByKey("chapters", "End", "vertical"),
  endFromChaptersHorizontal: desk.deskStageByKey("chapters", "End", "horizontal"),
  unrelated: desk.deskStageByKey("chapters", "Enter", "vertical"),
  disabledCurrent: desk.deskStageByKey("shots", "ArrowDown", "vertical"),
}));
""", {})
    assert result == {
        "downFromEpisodes": "idea",
        "upFromIdea": "episodes",
        "downFromChapters": "episodes",
        "rightInVertical": None,
        "rightFromEpisodesHorizontal": "idea",
        "downInHorizontal": None,
        "homeFromChapters": "idea",
        "homeFromChaptersVertical": "idea",
        "endFromChapters": "episodes",
        "endFromChaptersHorizontal": "episodes",
        "unrelated": None,
        "disabledCurrent": None,
    }


def test_desk_subject_from_card_accepts_only_two_card_shapes():
    cases = [
        {"subtype": "novel_draft", "draft_id": DRAFT_ID},
        {"subtype": "studio_project", "url": "/studio/proj_1-A", "error": False},
        {"subtype": "studio_project", "url": "/studio/ok", "error": None},
        {"subtype": "studio_project", "url": "/studio/a/b"},
        {"subtype": "studio_project", "url": "/studio/../x"},
        {"subtype": "studio_project", "url": "/studio/a?b=1"},
        {"subtype": "studio_project", "url": "https://x/studio/a"},
        {"subtype": "studio_project", "url": "/studio/blocked", "error": True},
        {"subtype": "novel_draft", "draft_id": "12345678-1234-1234-1234-123456789ab"},
        {"subtype": "novel_draft", "draft_id": "12345678-1234-1234-1234-123456789ABC"},
        {"subtype": "weather", "draft_id": DRAFT_ID},
        None,
        "novel_draft",
        7,
    ]
    result = run_desk("""
const seen = payload.cases.map(card => desk.deskSubjectFromCard(card));
process.stdout.write(JSON.stringify(seen));
""", {"cases": cases})
    assert result == [
        {"kind": "draft", "draftId": DRAFT_ID},
        {"kind": "project", "projectId": "proj_1-A"},
        {"kind": "project", "projectId": "ok"},
        None, None, None, None, None, None, None, None, None, None, None,
    ]


def test_desk_ask_prefix_is_complete_and_follows_chapter_priority():
    cases = [
        {"title": "  书 名  ", "chapter": 3},
        {"title": "书", "episode": 2},
        {"title": "书"},
        {"title": None, "chapter": 3},
        {"title": "   "},
        {"title": "书", "chapter": 3, "episode": 2},
    ]
    result = run_desk("""
process.stdout.write(JSON.stringify(payload.cases.map(target => desk.deskAskPrefix(target))));
""", {"cases": cases})
    assert result == [
        "关于《书 名》第 3 章：",
        "关于《书》第 2 集：",
        "关于《书》：",
        "关于这本书第 3 章：",
        "关于这本书：",
        "关于《书》第 3 章：",
    ]


def test_parse_desk_prefs_rejects_bad_values_and_returns_fresh_defaults():
    cases = [
        None,
        "{bad",
        "[]",
        "null",
        '"x"',
        "3",
        '{"open":"true"}',
        json.dumps({"open": True, "novelId": DRAFT_ID, "stage": "shots"}),
        json.dumps({"open": True, "novelId": "nope", "stage": "episodes"}),
        json.dumps({"open": True, "novelId": DRAFT_ID, "stage": "idea"}),
        json.dumps({"open": False, "novelId": DRAFT_ID, "stage": "film"}),
        '{"open":1}',
    ]
    result = run_desk("""
const first = desk.parseDeskPrefs(null);
const second = desk.parseDeskPrefs(null);
process.stdout.write(JSON.stringify({
  parsed: payload.cases.map(raw => desk.parseDeskPrefs(raw)),
  freshDefault: first !== desk.DESK_DEFAULT_PREFS,
  distinct: first !== second,
  key: desk.deskPrefsKey("alice"),
}));
""", {"cases": cases})
    assert result["parsed"] == [
        DEFAULT_PREFS,
        DEFAULT_PREFS,
        DEFAULT_PREFS,
        DEFAULT_PREFS,
        DEFAULT_PREFS,
        DEFAULT_PREFS,
        {"open": False, "novelId": None, "stage": "chapters"},
        {"open": True, "novelId": DRAFT_ID, "stage": "chapters"},
        {"open": True, "novelId": None, "stage": "episodes"},
        {"open": True, "novelId": DRAFT_ID, "stage": "idea"},
        {"open": False, "novelId": DRAFT_ID, "stage": "chapters"},
        {"open": False, "novelId": None, "stage": "chapters"},
    ]
    assert result["freshDefault"] is True
    assert result["distinct"] is True
    assert result["key"] == "fiona.desk.v1:alice"


def test_read_desk_prefs_swallows_errors_and_uses_account_key():
    result = run_desk("""
const valid = JSON.stringify({open: true, novelId: payload.validNovelId, stage: "episodes"});
const calls = [];
const storage = {getItem(key) { calls.push(key); return valid; }};
const validRead = desk.readDeskPrefs(storage, "alice");

const emptyCalls = [];
const emptyStorage = {getItem(key) { emptyCalls.push(key); return valid; }};
const emptyRead = desk.readDeskPrefs(emptyStorage, "");

const throwing = {getItem() { throw new Error("blocked"); }};
const throwingRead = desk.readDeskPrefs(throwing, "alice");

process.stdout.write(JSON.stringify({
  validRead,
  calls,
  emptyRead,
  emptyCalls,
  throwingRead,
  nullStorage: desk.readDeskPrefs(null, "alice"),
  undefinedStorage: desk.readDeskPrefs(undefined, "alice"),
  nullRaw: desk.readDeskPrefs({getItem() { return null; }}, "alice"),
}));
""", {"validNovelId": DRAFT_ID})
    assert result["validRead"] == {"open": True, "novelId": DRAFT_ID, "stage": "episodes"}
    assert result["calls"] == ["fiona.desk.v1:alice"]
    assert result["emptyRead"] == DEFAULT_PREFS
    assert result["emptyCalls"] == []
    assert result["throwingRead"] == DEFAULT_PREFS
    assert result["nullStorage"] == DEFAULT_PREFS
    assert result["undefinedStorage"] == DEFAULT_PREFS
    assert result["nullRaw"] == DEFAULT_PREFS


def test_update_desk_prefs_merges_revalidates_and_swallows_storage_errors():
    result = run_desk("""
function makeStorage(initial, throwOnGet, throwOnSet) {
  const calls = [];
  return {
    calls,
    value: {
      getItem(key) {
        calls.push(["get", key]);
        if (throwOnGet) throw new Error("blocked");
        return initial;
      },
      setItem(key, next) {
        calls.push(["set", key, next]);
        if (throwOnSet) throw new Error("quota");
      },
    },
  };
}

const normal = makeStorage(JSON.stringify({
  open: true, novelId: payload.validNovelId, stage: "chapters",
}), false, false);
const normalResult = desk.updateDeskPrefs(normal.value, "alice", {stage: "episodes"});

const invalid = makeStorage(JSON.stringify({
  open: true, novelId: payload.validNovelId, stage: "episodes",
}), false, false);
const invalidResult = desk.updateDeskPrefs(invalid.value, "alice", {
  open: "true", novelId: "bad", stage: "shots",
});

const preserve = makeStorage(JSON.stringify({
  open: false, novelId: payload.validNovelId, stage: "idea",
}), false, false);
const preserveResult = desk.updateDeskPrefs(preserve.value, "alice", {});

const quota = makeStorage(JSON.stringify({
  open: false, novelId: null, stage: "chapters",
}), false, true);
let quotaError = null;
let quotaResult = null;
try {
  quotaResult = desk.updateDeskPrefs(quota.value, "alice", {open: true});
} catch (error) {
  quotaError = String(error);
}

const empty = makeStorage(JSON.stringify({
  open: true, novelId: payload.validNovelId, stage: "episodes",
}), false, false);
const emptyResult = desk.updateDeskPrefs(empty.value, "", {open: true});

const getThrowCalls = [];
const getThrow = {
  getItem(key) {
    getThrowCalls.push(["get", key]);
    throw new Error("blocked");
  },
  setItem(key, next) {
    getThrowCalls.push(["set", key, next]);
  },
};
const getThrowResult = desk.updateDeskPrefs(getThrow, "alice", {open: true, stage: "idea"});

process.stdout.write(JSON.stringify({
  normalResult,
  normalCalls: normal.calls,
  invalidResult,
  invalidCalls: invalid.calls,
  preserveResult,
  preserveCalls: preserve.calls,
  quotaResult,
  quotaError,
  quotaCalls: quota.calls,
  emptyResult,
  emptyCalls: empty.calls,
  getThrowResult,
  getThrowCalls,
  nullStorageResult: desk.updateDeskPrefs(null, "alice", {stage: "episodes"}),
  undefinedStorageResult: desk.updateDeskPrefs(undefined, "alice", {open: true}),
}));
""", {"validNovelId": DRAFT_ID})

    assert result["normalResult"] == {"open": True, "novelId": DRAFT_ID, "stage": "episodes"}
    assert [call[0] for call in result["normalCalls"]] == ["get", "set"]
    assert result["normalCalls"][0][1] == "fiona.desk.v1:alice"
    assert result["normalCalls"][1][1] == "fiona.desk.v1:alice"
    assert json.loads(result["normalCalls"][1][2]) == result["normalResult"]

    assert result["invalidResult"] == {"open": False, "novelId": None, "stage": "chapters"}
    assert json.loads(result["invalidCalls"][1][2]) == result["invalidResult"]

    assert result["preserveResult"] == {"open": False, "novelId": DRAFT_ID, "stage": "idea"}
    assert json.loads(result["preserveCalls"][1][2]) == result["preserveResult"]

    assert result["quotaError"] is None
    assert result["quotaResult"] == {"open": True, "novelId": None, "stage": "chapters"}
    assert [call[0] for call in result["quotaCalls"]] == ["get", "set"]

    assert result["emptyResult"] == {"open": True, "novelId": None, "stage": "chapters"}
    assert result["emptyCalls"] == []

    assert result["getThrowResult"] == {"open": True, "novelId": None, "stage": "idea"}
    assert [call[0] for call in result["getThrowCalls"]] == ["get", "set"]
    assert json.loads(result["getThrowCalls"][1][2]) == result["getThrowResult"]

    assert result["nullStorageResult"] == {"open": False, "novelId": None, "stage": "episodes"}
    assert result["undefinedStorageResult"] == {"open": True, "novelId": None, "stage": "chapters"}


def test_chapter_tag_table_and_current_chapter_number():
    tags = [
        [5, "stale", 3],
        [4, "awaiting_plan_approval", 3],
        [4, "planning", 3],
        [4, "writing", 3],
        [4, "failed", 3],
        [2, "done", 2],
        [3, "unexpected", 2],
        [4, "done", 3],
    ]
    books = [
        {"chapters_done": 0, "chapters": []},
        {"chapters_done": 1, "chapters": [
            {"chapter": 1, "status": "done"},
            {"chapter": 2, "status": "stale"},
            {"chapter": 3, "status": "writing"},
            {"chapter": 4, "status": "planning"},
        ]},
        {"chapters_done": 3, "chapters": [
            {"chapter": 1, "status": "done"},
            {"chapter": 2, "status": "stale"},
            {"chapter": 3, "status": "done"},
        ]},
    ]
    result = run_desk("""
process.stdout.write(JSON.stringify({
  tags: payload.tags.map(([chapter, status, done]) => desk.chapterTag({chapter, status}, done)),
  currents: payload.books.map(book => desk.currentChapterNumber(book)),
}));
""", {"tags": tags, "books": books})
    assert result["tags"] == [
        {"label": "待复核", "settled": False},
        {"label": "细纲等你确认", "settled": False},
        {"label": "定细纲中", "settled": False},
        {"label": "写作中", "settled": False},
        {"label": "出错了", "settled": False},
        {"label": "定稿", "settled": True},
        {"label": "处理中", "settled": False},
        {"label": "处理中", "settled": False},
    ]
    assert result["currents"] == [None, 3, 3]


def test_episode_locks_matches_breakdown_rules():
    plans = [
        {"status": "running"},
        {"status": "partial"},
        {"status": "done", "rebreakdown_pending": True},
        {"status": "cancelled"},
        {},
        {"status": "done"},
        {"status": "done", "active_breakdown_status": "running"},
        {"status": "done", "active_breakdown_status": "partial"},
        {"status": "done", "active_breakdown_status": None},
    ]
    result = run_desk("""
process.stdout.write(JSON.stringify(payload.plans.map(plan => desk.episodeLocks(plan))));
""", {"plans": plans})
    assert result == [
        {"editsBlocked": True, "approvalBlocked": True},
        {"editsBlocked": True, "approvalBlocked": True},
        {"editsBlocked": True, "approvalBlocked": True},
        {"editsBlocked": False, "approvalBlocked": True},
        {"editsBlocked": False, "approvalBlocked": False},
        {"editsBlocked": False, "approvalBlocked": False},
        {"editsBlocked": True, "approvalBlocked": True},
        {"editsBlocked": True, "approvalBlocked": True},
        {"editsBlocked": False, "approvalBlocked": False},
    ]


def test_latest_project_uses_max_created_at_and_keeps_first_on_ties():
    groups = [
        [],
        [
            {"id": "later", "created_at": "2026-11-10T09:00:00"},
            {"id": "earlier", "created_at": "2026-11-09T09:00:00"},
        ],
        [
            {"id": "first", "created_at": "2026-11-10T09:00:00"},
            {"id": "second", "created_at": "2026-11-10T09:00:00"},
            {"id": "older", "created_at": "2026-11-08T09:00:00"},
        ],
        [
            {"id": "mid", "created_at": "2026-11-10T08:00:00"},
            {"id": "max", "created_at": "2026-11-10T12:00:00"},
            {"id": "min", "created_at": "2026-11-10T01:00:00"},
        ],
    ]
    result = run_desk("""
process.stdout.write(JSON.stringify(payload.groups.map(projects => desk.latestProject(projects))));
""", {"groups": groups})
    assert result[0] is None
    assert result[1]["id"] == "later"
    assert result[2]["id"] == "first"
    assert result[3]["id"] == "max"
