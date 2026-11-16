"""讨论群纯函数契约：在 node 里转译执行 frontend/lib/discussLogic.ts。

离线运行。缺 frontend 依赖或 node 时整组 skip；缺依赖自检证明在起 node
之前就跳过。所有用例都直接调用真实导出，断言精确结果。
"""
import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LOGIC = ROOT / "frontend/lib/discussLogic.ts"
DEPENDENCIES = {
    "typescript": "typescript/lib/typescript.js",
}


def require_node_dependencies():
    missing = [name for name, entry in DEPENDENCIES.items()
               if not (ROOT / "frontend/node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")


@pytest.mark.parametrize("missing", [*DEPENDENCIES, "node"])
def test_node_tests_skip_before_node_when_any_dependency_is_missing(
        monkeypatch, tmp_path, missing):
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
const logic = moduleObject.exports;
"""


def run_logic(script, payload):
    require_node_dependencies()
    assert LOGIC.is_file(), "frontend/lib/discussLogic.ts 尚未实现"
    source = NODE_LOADER + "\nconst payload = " + json.dumps(
        payload, ensure_ascii=False) + ";\n" + script
    result = subprocess.run(
        ["node", "-e", source, str(LOGIC)],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail("node runner failed:\n" + result.stderr)
    return json.loads(result.stdout)


LIMITS = {
    "budget_min": 100,
    "budget_max": 20000,
    "budget_default": 500,
    "rounds_min": 1,
    "rounds_max": 6,
    "rounds_default": 3,
    "members_min": 1,
    "members_max": 5,
    "name_max": 12,
    "persona_max": 300,
    "custom_does_max": 200,
    "request_min": 10,
    "request_max": 2000,
    "materials_max": 20000,
    "unread_notes_max": 5,
}

SEATS = ("host", "critic", "writer", "acceptor")
SEAT_MODELS = {
    "host": "dashscope:qwen3.8-max",
    "critic": "ark:doubao-seed-2-1-pro-260915",
    "writer": "dashscope:qwen3.8-max",
    "acceptor": "ark:doubao-seed-2-1-pro-260915",
}


def identity(role, name="", persona="", model=None):
    model = model or SEAT_MODELS[role]
    return {
        "role": role,
        "name": name,
        "persona": persona,
        "model": model,
        "default_model": SEAT_MODELS[role],
    }


def lens(
    role="market", selected=True, name="市场与行业", does="查市场",
    default_name="市场与行业", default_does="查市场",
    model="deepseek:deepseek-flash", default_model="deepseek:deepseek-flash",
):
    return {
        "role": role,
        "selected": selected,
        "name": name,
        "does": does,
        "default_name": default_name,
        "default_does": default_does,
        "model": model,
        "default_model": default_model,
    }


def custom(
    name="成本顾问", does="查成本",
    model="deepseek:deepseek-flash", default_model="deepseek:deepseek-flash",
):
    return {
        "name": name,
        "does": does,
        "model": model,
        "default_model": default_model,
    }


def create_form(**overrides):
    value = {
        "request": "帮我查清楚这件事值不值得做",
        "materials": "",
        "team": "self",
        "lenses": [lens()],
        "custom_members": [],
        "avatar": True,
        "avatar_model": "dashscope:qwen3.8-max",
        "default_avatar_model": "dashscope:qwen3.8-max",
        "budget_strawberries": 500,
        "max_rounds": 3,
        "identities": [identity(role) for role in SEATS],
    }
    value.update(overrides)
    return value


DETAIL = {
    "id": "group-1",
    "title": "原标题",
    "status": "awaiting_start",
    "stop_reason": None,
    "round": 0,
    "max_rounds": 3,
    "budget_strawberries": 500,
    "spent_strawberries": 0,
    "output_version": 0,
    "created_at": "2026-11-15 10:00:00",
    "updated_at": "2026-11-15 10:00:00",
    "request": "帮我查清楚这件事值不值得做",
    "last_error": None,
    "reserved_strawberries": 0,
    "plan_revision": 7,
    "plan": {
        "title": "原标题",
        "goal": "把这件事查清楚",
        "deliverable": {"kind": "report", "outline": ["背景", "发现", "建议"]},
        "criteria": [
            {"id": "C1", "text": "标准一"},
            {"id": "C2", "text": "标准二"},
            {"id": "C3", "text": "标准三"},
        ],
        "picks": [
            {"role": "market", "name": "市场与行业", "does": "查市场", "focus": "查规模"},
            {"role": "tech", "name": "技术与可行性", "does": "查技术", "focus": "查成熟度"},
        ],
        "questions": ["先做哪个市场？"],
    },
    "members": [
        {"role": "host", "name": "主持人", "kind": "core", "does": "",
         "model": "dashscope:qwen3.8-max", "working": False},
        {"role": "market", "name": "市场与行业", "kind": "lens", "does": "查市场",
         "focus": "查规模", "model": "deepseek:deepseek-flash", "working": False},
        {"role": "tech", "name": "技术与可行性", "kind": "lens", "does": "查技术",
         "focus": "查成熟度", "model": "deepseek:deepseek-flash", "working": False},
        {"role": "critic", "name": "反方质疑", "kind": "core", "does": "",
         "model": "ark:doubao-seed-2-1-pro-260915", "working": False},
        {"role": "writer", "name": "撰稿人", "kind": "core", "does": "",
         "model": "dashscope:qwen3.8-max", "working": False},
        {"role": "acceptor", "name": "验收人", "kind": "core", "does": "",
         "model": "ark:doubao-seed-2-1-pro-260915", "working": False},
        {"role": "avatar", "name": "小菲", "kind": "avatar", "does": "",
         "model": "dashscope:qwen3.8-max", "working": False},
    ],
    "messages": [],
    "output": None,
    "pending_notes": 0,
    "answers": "旧回答",
}


def plan_draft():
    return {
        "title": DETAIL["title"],
        "criteria": [item["text"] for item in DETAIL["plan"]["criteria"]],
        "picks": copy.deepcopy(DETAIL["plan"]["picks"]),
        "identities": [
            {
                "role": "host",
                "name": "主持人",
                "persona": "",
                "default_name": "主持人",
                "default_persona": "",
            },
            {
                "role": "critic",
                "name": "反方质疑",
                "persona": "",
                "default_name": "反方质疑",
                "default_persona": "",
            },
            {
                "role": "writer",
                "name": "撰稿人",
                "persona": "",
                "default_name": "撰稿人",
                "default_persona": "",
            },
            {
                "role": "acceptor",
                "name": "验收人",
                "persona": "",
                "default_name": "验收人",
                "default_persona": "",
            },
        ],
        "budget_strawberries": 500,
        "max_rounds": 3,
        "avatar": True,
        "models": {member["role"]: member["model"] for member in DETAIL["members"]},
        "answers": "旧回答",
    }


def test_status_labels_cover_every_state_pause_reason_and_done_variant():
    groups = [
        {"status": "planning", "stop_reason": None},
        {"status": "awaiting_start", "stop_reason": None},
        {"status": "running", "stop_reason": None},
        {"status": "awaiting_user", "stop_reason": "rounds_exhausted"},
        {"status": "paused", "stop_reason": "user"},
        {"status": "done", "stop_reason": "accepted_by_user"},
        {"status": "failed", "stop_reason": "step_failed"},
        {"status": "closed", "stop_reason": "user"},
        {"status": "archived", "stop_reason": None},
    ]
    paused = [
        {"status": "paused", "stop_reason": reason}
        for reason in (
            "user", "budget", "insufficient_strawberries", "byok_unavailable",
            "step_failed", "search_unavailable", "server_restart_failed",
            "unexpected_reason", None,
        )
    ]
    done = [
        {"status": "done", "stop_reason": "accepted_by_user"},
        {"status": "done", "stop_reason": "rounds_exhausted"},
        {"status": "done", "stop_reason": None},
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify({
  labels: payload.groups.map(group => logic.discussStatusLabel(group)),
  paused: payload.paused.map(group => logic.discussStatusLabel(group)),
  done: payload.done.map(group => logic.discussStatusLabel(group)),
}));
""", {"groups": groups, "paused": paused, "done": done})
    assert result["labels"] == [
        "立项中", "等你开工", "讨论中", "等你决定",
        "已暂停", "你已接受", "出错了", "已结束", "archived",
    ]
    assert result["paused"] == [
        "已暂停", "预算用完", "草莓不足", "自带模型不可用",
        "有一步没跑通", "联网搜索暂不可用", "恢复失败", "已暂停", "已暂停",
    ]
    assert result["done"] == ["你已接受", "验收通过", "验收通过"]


def test_stop_hints_cover_every_status_and_pause_reason():
    cases = [
        {"status": "awaiting_start", "stop_reason": None},
        {"status": "awaiting_user", "stop_reason": "rounds_exhausted"},
        {"status": "paused", "stop_reason": "budget"},
        {"status": "paused", "stop_reason": "insufficient_strawberries"},
        {"status": "paused", "stop_reason": "byok_unavailable"},
        {"status": "paused", "stop_reason": "step_failed"},
        {"status": "paused", "stop_reason": "search_unavailable"},
        {"status": "paused", "stop_reason": "server_restart_failed"},
        {"status": "paused", "stop_reason": "user"},
        {"status": "paused", "stop_reason": "unknown_reason"},
        {"status": "failed", "stop_reason": "step_failed"},
        {"status": "done", "stop_reason": "accepted_by_user"},
        {"status": "done", "stop_reason": "rounds_exhausted"},
        {"status": "planning", "stop_reason": None},
        {"status": "running", "stop_reason": None},
        {"status": "closed", "stop_reason": "user"},
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(group => logic.discussStopHint(group))));
""", {"cases": cases})
    assert result == [
        "方案已经出来了。看一眼、改一改，回答主持人的问题，然后开工。",
        "轮数用完了，验收还没通过。你可以接受现在的成果，或者追加轮数让它继续。",
        "预算用完了。继续之前先追加预算。",
        "草莓不够了。补充草莓后点继续。",
        "自带模型用不了。到设置里检查后点继续。",
        "有一步连着几次没跑通。点继续会从断的地方接着跑。",
        "联网搜索暂时拿不到结果。过一会儿点继续。",
        "服务重启后没能自动接上。点继续会从断的地方接着跑。",
        "",
        "",
        "出了意料之外的错误。点继续会从断的地方接着跑。",
        "",
        "验收通过了。想再改，先在群聊里写下意见，再点按意见返工。",
        "",
        "",
        "",
    ]


def test_active_and_needs_author_follow_status_only():
    statuses = [
        "planning", "awaiting_start", "running", "awaiting_user",
        "paused", "done", "failed", "closed", "unknown",
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify({
  active: payload.statuses.map(status => logic.discussIsActive(status)),
  needsAuthor: payload.statuses.map(status => logic.discussNeedsAuthor({status})),
}));
""", {"statuses": statuses})
    assert result["active"] == [
        True, False, True, False, False, False, False, False, False,
    ]
    assert result["needsAuthor"] == [
        False, True, False, True, True, False, True, False, False,
    ]


def test_actions_for_all_states_and_output_versions():
    cases = [
        {"status": "planning", "output_version": 0},
        {"status": "awaiting_start", "output_version": 0},
        {"status": "running", "output_version": 0},
        {"status": "paused", "output_version": 0},
        {"status": "paused", "output_version": 1},
        {"status": "awaiting_user", "output_version": 0},
        {"status": "awaiting_user", "output_version": 1},
        {"status": "done", "output_version": 0},
        {"status": "done", "output_version": 1},
        {"status": "failed", "output_version": 0},
        {"status": "closed", "output_version": 0},
        {"status": "closed", "output_version": 2},
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(group => logic.discussActions(group))));
""", {"cases": cases})
    assert result == [
        ["pause", "delete"],
        ["start", "close", "delete"],
        ["pause", "delete"],
        ["resume", "close", "delete"],
        ["resume", "accept", "close", "export", "delete"],
        ["continue", "close", "delete"],
        ["continue", "accept", "close", "export", "delete"],
        ["rework", "delete"],
        ["rework", "export", "delete"],
        ["resume", "close", "delete"],
        ["delete"],
        ["export", "delete"],
    ]
    assert "close" not in result[7], "done 状态没有 close"


def test_default_tab_for_each_rule():
    cases = [
        {"status": "awaiting_start", "output_version": 0},
        {"status": "awaiting_start", "output_version": 5},
        {"status": "awaiting_user", "output_version": 0},
        {"status": "awaiting_user", "output_version": 1},
        {"status": "done", "output_version": 0},
        {"status": "done", "output_version": 2},
        {"status": "closed", "output_version": 0},
        {"status": "closed", "output_version": 1},
        {"status": "planning", "output_version": 5},
        {"status": "running", "output_version": 5},
        {"status": "paused", "output_version": 5},
        {"status": "failed", "output_version": 5},
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(group => logic.discussDefaultTab(group))));
""", {"cases": cases})
    assert result == [
        "plan", "plan",
        "chat", "output",
        "chat", "output",
        "chat", "output",
        "chat", "chat", "chat", "chat",
    ]


def test_kind_labels_are_complete_and_unknown_is_empty():
    kinds = [
        "plan", "brief", "note", "notice", "critique", "decision",
        "draft", "view", "verdict", "rework", "user", "unknown", "",
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.kinds.map(kind => logic.discussKindLabel(kind))));
""", {"kinds": kinds})
    assert result == [
        "方案", "主人背景", "调研笔记", "说明", "质疑", "裁决",
        "成稿", "主人视角", "验收", "返工安排", "插话", "", "",
    ]


def test_merge_messages_dedupes_by_id_sorts_and_keeps_inputs_untouched():
    current = [
        {"id": 3, "content": "old-3"},
        {"id": 1, "content": "old-1"},
        {"id": 2, "content": "old-2"},
    ]
    incoming = [
        {"id": 2, "content": "new-2"},
        {"id": 4, "content": "new-4"},
        {"id": 4, "content": "newer-4"},
    ]
    result = run_logic("""
const beforeCurrent = JSON.stringify(payload.current);
const beforeIncoming = JSON.stringify(payload.incoming);
const merged = logic.mergeDiscussMessages(payload.current, payload.incoming);
process.stdout.write(JSON.stringify({
  merged,
  currentUnchanged: JSON.stringify(payload.current) === beforeCurrent,
  incomingUnchanged: JSON.stringify(payload.incoming) === beforeIncoming,
  fresh: merged !== payload.current && merged !== payload.incoming,
}));
""", {"current": current, "incoming": incoming})
    assert [message["id"] for message in result["merged"]] == [1, 2, 3, 4]
    assert result["merged"][1] == {"id": 2, "content": "new-2"}
    assert result["merged"][3] == {"id": 4, "content": "newer-4"}
    assert result["currentUnchanged"] is True
    assert result["incomingUnchanged"] is True
    assert result["fresh"] is True


def test_apply_pending_notes_marks_latest_user_messages_unread():
    messages = [
        {"id": 3, "sender": "user", "consumed": True},
        {"id": 1, "sender": "user", "consumed": True},
        {"id": 4, "sender": "host", "consumed": None},
        {"id": 2, "sender": "user", "consumed": True},
    ]
    result = run_logic("""
const before = JSON.stringify(payload.messages);
function applied(pending) {
  return logic.applyPendingNotes(payload.messages, pending)
    .map(message => ({id: message.id, consumed: message.consumed}));
}
process.stdout.write(JSON.stringify({
  zero: applied(0),
  one: applied(1),
  three: applied(3),
  moreThanNotes: applied(5),
  negative: applied(-1),
  fractional: applied(1.5),
  numericString: applied("3"),
  nan: applied(NaN),
  inputUnchanged: JSON.stringify(payload.messages) === before,
}));
""", {"messages": messages})
    def flags(ids):
        return {item["id"]: item["consumed"] for item in ids}
    zero = flags(result["zero"])
    assert zero == {1: True, 2: True, 3: True, 4: None}
    assert flags(result["one"]) == {1: True, 2: True, 3: False, 4: None}
    assert flags(result["three"]) == {1: False, 2: False, 3: False, 4: None}
    assert flags(result["moreThanNotes"]) == {1: False, 2: False, 3: False, 4: None}
    for key in ("negative", "fractional", "numericString", "nan"):
        assert flags(result[key]) == {1: True, 2: True, 3: True, 4: None}
    assert result["inputUnchanged"] is True


def test_rounds_group_only_adjacent_messages():
    cases = [
        [],
        [
            {"id": 1, "round": 0},
            {"id": 2, "round": 0},
            {"id": 3, "round": 1},
            {"id": 4, "round": 1},
            {"id": 5, "round": 1},
            {"id": 6, "round": 0},
            {"id": 7, "round": 2},
        ],
        [
            {"id": 8, "round": 2},
            {"id": 9, "round": 1},
        ],
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(messages =>
  logic.groupDiscussRounds(messages).map(group => ({
    round: group.round, label: group.label, ids: group.messages.map(m => m.id),
  }))
)));
""", {"cases": cases})
    assert result[0] == []
    assert result[1] == [
        {"round": 0, "label": "立项", "ids": [1, 2]},
        {"round": 1, "label": "第 1 轮", "ids": [3, 4, 5]},
        {"round": 0, "label": "立项", "ids": [6]},
        {"round": 2, "label": "第 2 轮", "ids": [7]},
    ]
    assert result[2] == [
        {"round": 2, "label": "第 2 轮", "ids": [8]},
        {"round": 1, "label": "第 1 轮", "ids": [9]},
    ]


def test_split_document_tables_fences_padding_and_plain_text():
    cases = [
        "第一段\n\n第二段",
        "\n \n",
        "前文\n\n| 名称 | 值 |\n|---|---|\n| A | 1 |\n\n后文",
        "| 名称 | 值 |\n| --- | --- |\n| A | 1 | 多 |\n| B |",
        "```\n| a | b |\n|---|---|\n| 1 | 2 |\n```",
        "| a | b |\n| c | d |",
        "  | 缩进 | 表头 |\n  |---|---|---|\n  | 1 | 2 |",
        "|a|b|\n|---|---|\n|1|2|\n|c|d|\n|---|---|\n|3|4|",
        None,
        42,
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(text => logic.splitDiscussDocument(text))));
""", {"cases": cases})
    assert result[0] == [{"kind": "markdown", "text": "第一段\n\n第二段"}]
    assert result[1] == []
    assert result[2] == [
        {"kind": "markdown", "text": "前文\n"},
        {"kind": "table", "header": ["名称", "值"], "rows": [["A", "1"]]},
        {"kind": "markdown", "text": "\n后文"},
    ]
    assert result[3] == [
        {"kind": "table", "header": ["名称", "值"], "rows": [["A", "1"], ["B", ""]]},
    ]
    assert result[4] == [
        {"kind": "markdown", "text": "```\n| a | b |\n|---|---|\n| 1 | 2 |\n```"},
    ]
    assert result[5] == [{"kind": "markdown", "text": "| a | b |\n| c | d |"}]
    assert result[6] == [
        {"kind": "table", "header": ["缩进", "表头"], "rows": [["1", "2"]]},
    ]
    assert result[7] == [
        {
            "kind": "table",
            "header": ["a", "b"],
            "rows": [["1", "2"], ["c", "d"], ["---", "---"], ["3", "4"]],
        },
    ]
    assert result[8] == []
    assert result[9] == []


def test_split_citations_accepts_only_four_digit_uppercase_ids():
    cases = [
        "没有编号的一整段",
        "[S1]开头",
        "前[S26]后",
        "结尾[S119]",
        "[S1][S2]",
        "a[S12345]b[s3]c[S]d",
        "",
        "[S0001]",
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(text => logic.splitDiscussCitations(text))));
""", {"cases": cases})
    assert result[0] == [{"kind": "text", "text": "没有编号的一整段"}]
    assert result[1] == [
        {"kind": "cite", "id": "S1"},
        {"kind": "text", "text": "开头"},
    ]
    assert result[2] == [
        {"kind": "text", "text": "前"},
        {"kind": "cite", "id": "S26"},
        {"kind": "text", "text": "后"},
    ]
    assert result[3] == [
        {"kind": "text", "text": "结尾"},
        {"kind": "cite", "id": "S119"},
    ]
    assert result[4] == [
        {"kind": "cite", "id": "S1"},
        {"kind": "cite", "id": "S2"},
    ]
    assert result[5] == [{"kind": "text", "text": "a[S12345]b[s3]c[S]d"}]
    assert result[6] == []
    assert result[7] == [{"kind": "cite", "id": "S0001"}]


def test_safe_external_url_only_allows_http_and_https():
    cases = [
        "https://example.com/a?b=1",
        "http://example.com",
        "https://example.com",
        "javascript:alert(1)",
        "data:text/html,<b>x</b>",
        "ftp://example.com/x",
        "/discuss",
        "",
        None,
        42,
        {"url": "https://example.com"},
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(url => logic.safeExternalUrl(url))));
""", {"cases": cases})
    assert result == [
        "https://example.com/a?b=1",
        "http://example.com/",
        "https://example.com/",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ]


def test_validate_create_reports_each_rule_exactly_once():
    cases = [
        (create_form(request="太短"), "诉求需要 10–2000 字"),
        (create_form(request="字" * 2001), "诉求需要 10–2000 字"),
        (create_form(materials="m" * 20001), "补充材料最多 20000 字"),
        (create_form(budget_strawberries=99), "预算需要 100–20000 颗"),
        (create_form(budget_strawberries=20001), "预算需要 100–20000 颗"),
        (create_form(budget_strawberries=500.5), "预算需要 100–20000 颗"),
        (create_form(max_rounds=0), "轮数需要 1–6 轮"),
        (create_form(max_rounds=7), "轮数需要 1–6 轮"),
        (create_form(max_rounds=2.5), "轮数需要 1–6 轮"),
        (create_form(lenses=[lens(selected=False)]), "调研成员需要 1–5 位"),
        (
            create_form(lenses=[
                lens(role=f"lens{index}", name=f"角色{index}") for index in range(6)
            ]),
            "调研成员需要 1–5 位",
        ),
        (create_form(custom_members=[custom(name="")]), "自定义成员要写名字和职责"),
        (create_form(custom_members=[custom(does="")]), "自定义成员要写名字和职责"),
        (create_form(lenses=[lens(name="名" * 13)]), "名字最多 12 字"),
        (
            create_form(custom_members=[custom(does="职" * 201)]),
            "职责最多 200 字",
        ),
        (
            create_form(lenses=[
                lens(role="market", name="同名"),
                lens(
                    role="user", name="同名",
                    default_name="用户与需求", default_does="查用户需求",
                ),
            ]),
            "成员的名字不能重复",
        ),
        (
            create_form(identities=[
                identity("host", name="名" * 13),
                identity("critic"), identity("writer"), identity("acceptor"),
            ]),
            "固定席位的名字最多 12 字",
        ),
        (
            create_form(identities=[
                identity("host"),
                identity("critic", persona="设" * 301),
                identity("writer"), identity("acceptor"),
            ]),
            "身份设定最多 300 字",
        ),
        (create_form(), ""),
    ]
    payload = [{"form": form, "limits": LIMITS} for form, _ in cases]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.map(item =>
  logic.validateDiscussCreate(item.form, item.limits))));
""", payload)
    assert result == [expected for _, expected in cases]


def test_validate_create_takes_every_number_from_limits():
    limits = dict(
        LIMITS,
        request_min=3, request_max=5,
        materials_max=50,
        budget_min=10, budget_max=20,
        rounds_min=2, rounds_max=4,
        members_min=2, members_max=3,
        name_max=5,
        persona_max=6,
        custom_does_max=7,
    )
    base = create_form(request="查清楚", budget_strawberries=15)
    cases = [
        (dict(base, request="ab"), "诉求需要 3–5 字"),
        (dict(base, materials="m" * 51), "补充材料最多 50 字"),
        (dict(base, budget_strawberries=9), "预算需要 10–20 颗"),
        (dict(base, max_rounds=5), "轮数需要 2–4 轮"),
        (dict(base, lenses=[lens()]), "调研成员需要 2–3 位"),
        (
            dict(base, lenses=[
                lens(role="market", name="一二三四五六"),
                lens(role="user", default_name="用户与需求", default_does="查用户需求"),
            ]),
            "名字最多 5 字",
        ),
        (
            dict(base, custom_members=[custom(does="一二三四五六七八")]),
            "职责最多 7 字",
        ),
        (
            dict(base, lenses=[
                lens(role="market", name="同名"),
                lens(
                    role="user", name="同名",
                    default_name="用户与需求", default_does="查用户需求",
                ),
            ]),
            "成员的名字不能重复",
        ),
        (
            dict(base, identities=[
                identity("host", name="一二三四五六"),
                identity("critic"), identity("writer"), identity("acceptor"),
            ]),
            "固定席位的名字最多 5 字",
        ),
        (
            dict(base, identities=[
                identity("host", persona="一二三四五六七"),
                identity("critic"), identity("writer"), identity("acceptor"),
            ]),
            "身份设定最多 6 字",
        ),
    ]
    # 成员数下限 2：除成员数自身外，其余用例补足两位成员。
    for form, _ in cases:
        if len([item for item in form["lenses"] if item["selected"]]) + len(
                form["custom_members"]) < 2:
            form["custom_members"] = form["custom_members"] + [custom()]
    cases[4][0]["custom_members"] = []
    cases[4][0]["lenses"] = [lens()]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(item =>
  logic.validateDiscussCreate(item.form, item.limits))));
""", {"cases": [{"form": form, "limits": limits} for form, _ in cases]})
    assert result == [expected for _, expected in cases]


def test_validate_create_returns_the_first_error_in_order():
    cases = [
        (
            create_form(request="短", materials="m" * 20001),
            "诉求需要 10–2000 字",
        ),
        (
            create_form(materials="m" * 20001, budget_strawberries=1),
            "补充材料最多 20000 字",
        ),
        (
            create_form(budget_strawberries=1, max_rounds=0),
            "预算需要 100–20000 颗",
        ),
        (
            create_form(lenses=[], max_rounds=0),
            "轮数需要 1–6 轮",
        ),
        (
            create_form(custom_members=[custom(name="")] * 6),
            "调研成员需要 1–5 位",
        ),
        (
            create_form(custom_members=[custom(name=""), custom(name="名" * 13)]),
            "自定义成员要写名字和职责",
        ),
        (
            create_form(
                lenses=[lens(name="名" * 13)],
                custom_members=[custom(does="职" * 201)],
            ),
            "名字最多 12 字",
        ),
        (
            create_form(custom_members=[
                custom(name="同名", does="职" * 201),
                custom(name="同名"),
            ]),
            "职责最多 200 字",
        ),
        (
            create_form(identities=[
                identity("host", persona="设" * 301),
                identity("critic", name="名" * 13),
                identity("writer"), identity("acceptor"),
            ]),
            "固定席位的名字最多 12 字",
        ),
        (
            create_form(identities=[
                identity("host", name="名" * 13, persona="设" * 301),
                identity("critic"), identity("writer"), identity("acceptor"),
            ]),
            "固定席位的名字最多 12 字",
        ),
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(item =>
  logic.validateDiscussCreate(item.form, item.limits))));
""", {"cases": [{"form": form, "limits": LIMITS} for form, _ in cases]})
    assert result == [expected for _, expected in cases]


def test_build_create_body_members_models_and_identities():
    host_form = create_form(
        team="host",
        request="  清理后的诉求  ",
        materials="  补充材料  ",
        lenses=[lens(selected=True, model="dashscope:qwen3.8-max")],
        custom_members=[custom(model="dashscope:qwen3.8-max")],
    )
    self_form = create_form(
        lenses=[
            lens(role="market"),
            lens(
                role="user", name=" 用户研究 ", does=" 查真实需求 ",
                default_name="用户与需求", default_does="查用户需求",
            ),
        ],
        custom_members=[custom(name=" 成本顾问 ", does=" 查成本 ")],
    )
    model_form = create_form(
        lenses=[lens(model="dashscope:qwen3.8-max")],
        custom_members=[
            custom(name="甲", model="dashscope:qwen3.8-max"),
            custom(name="乙"),
        ],
        identities=[
            identity("host", model="deepseek:deepseek-flash"),
            identity("critic"), identity("writer"), identity("acceptor"),
        ],
        avatar_model="deepseek:deepseek-flash",
    )
    identity_form = create_form(
        team="host",
        identities=[
            identity("host", name="  主持甲  "),
            identity("critic", persona="更严格地质疑"),
            identity("writer"),
            identity("acceptor", name="验收官", persona="逐条核对"),
        ],
    )
    result = run_logic("""
process.stdout.write(JSON.stringify({
  host: logic.buildDiscussCreateBody(payload.host),
  self: logic.buildDiscussCreateBody(payload.self),
  model: logic.buildDiscussCreateBody(payload.model),
  identity: logic.buildDiscussCreateBody(payload.identity),
}));
""", {
        "host": host_form,
        "self": self_form,
        "model": model_form,
        "identity": identity_form,
    })
    assert result["host"] == {
        "request": "清理后的诉求",
        "materials": "补充材料",
        "budget_strawberries": 500,
        "max_rounds": 3,
        "avatar": True,
    }
    assert result["self"]["members"] == [
        {"role": "market"},
        {"role": "user", "name": "用户研究", "does": "查真实需求"},
        {"name": "成本顾问", "does": "查成本"},
    ]
    assert result["self"]["request"] == create_form()["request"]
    assert result["self"]["models"] == {"custom1": "deepseek:deepseek-flash"}
    assert "identities" not in result["self"]

    assert result["model"]["members"] == [
        {"role": "market"},
        {"name": "甲", "does": "查成本"},
        {"name": "乙", "does": "查成本"},
    ]
    assert result["model"]["models"] == {
        "market": "dashscope:qwen3.8-max",
        "custom1": "dashscope:qwen3.8-max",
        "custom2": "deepseek:deepseek-flash",
        "host": "deepseek:deepseek-flash",
        "avatar": "deepseek:deepseek-flash",
    }

    assert "members" not in result["identity"]
    assert result["identity"]["identities"] == {
        "host": {"name": "主持甲"},
        "critic": {"persona": "更严格地质疑"},
        "acceptor": {"name": "验收官", "persona": "逐条核对"},
    }
    assert "models" not in result["identity"]


def test_advance_cursor_only_moves_on_server_reads():
    result = run_logic("""
process.stdout.write(JSON.stringify({
  afterServerTwoThree: logic.advanceDiscussCursor(1, [{id: 2}, {id: 3}]),
  emptyReadKeeps: logic.advanceDiscussCursor(5, []),
  lowerReadKeeps: logic.advanceDiscussCursor(5, [{id: 3}, {id: 4}]),
  zeroCursor: logic.advanceDiscussCursor(0, []),
}));
""", {})
    assert result == {
        "afterServerTwoThree": 3,
        "emptyReadKeeps": 5,
        "lowerReadKeeps": 5,
        "zeroCursor": 0,
    }


def test_custom_member_default_model_uses_lens_default():
    catalog = {
        "roles": [
            {"id": "host", "name": "主持人", "does": "立项", "kind": "core"},
            {"id": "critic", "name": "反方质疑", "does": "挑错", "kind": "core"},
            {"id": "writer", "name": "撰稿人", "does": "写稿", "kind": "core"},
            {"id": "acceptor", "name": "验收人", "does": "验收", "kind": "core"},
            {"id": "market", "name": "市场与行业", "does": "查市场", "kind": "lens"},
            {"id": "user", "name": "用户与需求", "does": "查用户", "kind": "lens"},
            {"id": "avatar", "name": "分身", "does": "代表主人", "kind": "avatar"},
        ],
        "defaults": {
            "host": "dashscope:qwen3.8-max",
            "critic": "ark:doubao-seed-2-1-pro-260915",
            "writer": "dashscope:qwen3.8-max",
            "acceptor": "ark:doubao-seed-2-1-pro-260915",
            "market": "deepseek:deepseek-flash",
            "user": "deepseek:deepseek-flash",
            "avatar": "dashscope:qwen3.8-max",
        },
    }
    result = run_logic("""
process.stdout.write(JSON.stringify(logic.defaultDiscussCustomMemberModel(payload.catalog)));
""", {"catalog": catalog})
    assert result == "deepseek:deepseek-flash"


def test_member_focus_visibility_covers_lens_and_custom():
    cases = [
        {"kind": "lens", "focus": "查规模"},
        {"kind": "custom", "focus": "查成本"},
        {"kind": "custom", "focus": ""},
        {"kind": "lens", "focus": "   "},
        {"kind": "core", "focus": "查规模"},
        {"kind": "avatar", "focus": "查规模"},
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(item =>
  logic.discussMemberShowsFocus(item))));
""", {"cases": cases})
    assert result == [True, True, False, False, False, False]


def test_table_min_width_is_eight_em_per_column():
    result = run_logic("""
process.stdout.write(JSON.stringify([0, 1, 2, 3, 10].map(count =>
  logic.discussTableMinWidth(count))));
""", {})
    assert result == [8, 8, 16, 24, 80]


def test_build_plan_patch_only_sends_changed_fields():
    unchanged = plan_draft()

    titled = plan_draft()
    titled["title"] = "新标题"

    focus = plan_draft()
    focus["picks"][0] = dict(focus["picks"][0], focus="改后的规模")

    added = plan_draft()
    added["picks"].append(
        {"name": "成本顾问", "does": "查成本", "focus": "查成本结构"})

    swapped = plan_draft()
    swapped["picks"] = [swapped["picks"][1], swapped["picks"][0]]

    everything = plan_draft()
    everything["title"] = "改标题"
    everything["criteria"] = ["新一", "新二", "新三", "新四"]
    everything["identities"][0] = dict(
        everything["identities"][0], name="主持人甲")
    everything["identities"][1] = dict(
        everything["identities"][1], persona="更严格地质疑")
    everything["budget_strawberries"] = 800
    everything["max_rounds"] = 5
    everything["avatar"] = False
    everything["models"] = dict(everything["models"], host="deepseek:deepseek-flash")
    everything["answers"] = "新回答"

    cleared = plan_draft()
    cleared["identities"][0] = dict(cleared["identities"][0], name="")

    result = run_logic("""
process.stdout.write(JSON.stringify({
  unchanged: logic.buildDiscussPlanPatch(payload.detail, payload.drafts.unchanged),
  titled: logic.buildDiscussPlanPatch(payload.detail, payload.drafts.titled),
  focus: logic.buildDiscussPlanPatch(payload.detail, payload.drafts.focus),
  added: logic.buildDiscussPlanPatch(payload.detail, payload.drafts.added),
  swapped: logic.buildDiscussPlanPatch(payload.detail, payload.drafts.swapped),
  everything: logic.buildDiscussPlanPatch(payload.detail, payload.drafts.everything),
  cleared: logic.buildDiscussPlanPatch(payload.detail, payload.drafts.cleared),
}));
""", {
        "detail": DETAIL,
        "drafts": {
            "unchanged": unchanged,
            "titled": titled,
            "focus": focus,
            "added": added,
            "swapped": swapped,
            "everything": everything,
            "cleared": cleared,
        },
    })
    assert result["unchanged"] == {"expected_revision": 7}

    assert result["titled"] == {"expected_revision": 7, "title": "新标题"}

    assert result["focus"] == {
        "expected_revision": 7,
        "picks": [
            {"role": "market", "name": "市场与行业", "does": "查市场", "focus": "改后的规模"},
            {"role": "tech", "name": "技术与可行性", "does": "查技术", "focus": "查成熟度"},
        ],
    }
    assert result["added"] == {
        "expected_revision": 7,
        "picks": [
            {"role": "market", "name": "市场与行业", "does": "查市场", "focus": "查规模"},
            {"role": "tech", "name": "技术与可行性", "does": "查技术", "focus": "查成熟度"},
            {"name": "成本顾问", "does": "查成本", "focus": "查成本结构"},
        ],
    }
    assert "role" not in result["added"]["picks"][2]
    assert result["swapped"] == {
        "expected_revision": 7,
        "picks": [
            {"role": "tech", "name": "技术与可行性", "does": "查技术", "focus": "查成熟度"},
            {"role": "market", "name": "市场与行业", "does": "查市场", "focus": "查规模"},
        ],
    }

    assert result["everything"] == {
        "expected_revision": 7,
        "title": "改标题",
        "criteria": ["新一", "新二", "新三", "新四"],
        "identities": {
            "host": {"name": "主持人甲"},
            "critic": {"persona": "更严格地质疑"},
        },
        "budget_strawberries": 800,
        "max_rounds": 5,
        "avatar": False,
        "models": {"host": "deepseek:deepseek-flash"},
        "answers": "新回答",
    }
    assert result["cleared"] == {
        "expected_revision": 7,
        "identities": {"host": {"name": ""}},
    }

    empty = run_logic("""
process.stdout.write(JSON.stringify({
  unchanged: logic.discussPlanPatchIsEmpty(payload.unchanged),
  titled: logic.discussPlanPatchIsEmpty(payload.titled),
  everything: logic.discussPlanPatchIsEmpty(payload.everything),
}));
""", {
        "unchanged": result["unchanged"],
        "titled": result["titled"],
        "everything": result["everything"],
    })
    assert empty == {"unchanged": True, "titled": False, "everything": False}


def test_error_message_reads_plain_properties_only():
    cases = [
        {"status": 404, "message": "Not Found"},
        {"status": 403, "message": "讨论群暂未对该账号开放"},
        {"status": 409, "message": "你有一个讨论群正在进行，等它停下来再建新的"},
        {"status": 500, "message": "Internal Server Error"},
        "boom",
        None,
        {"status": 404, "message": "讨论群不存在"},
        {"message": "只有中文文案"},
        {"status": 403},
    ]
    result = run_logic("""
process.stdout.write(JSON.stringify(payload.cases.map(error => logic.discussErrorMessage(error))));
""", {"cases": cases})
    assert result == [
        "讨论群尚未开放",
        "你的账号暂未开通讨论群",
        "你有一个讨论群正在进行，等它停下来再建新的",
        "请求未完成，请稍后重试。",
        "请求未完成，请稍后重试。",
        "请求未完成，请稍后重试。",
        "讨论群不存在",
        "只有中文文案",
        "你的账号暂未开通讨论群",
    ]


def test_href_and_model_labels():
    result = run_logic("""
process.stdout.write(JSON.stringify({
  hrefs: [
    logic.discussHref("/discuss", false),
    logic.discussHref("/discuss", true),
    logic.discussHref("/discuss/new?draft=1", true),
    logic.discussHref("/discuss/abc?x=1", false),
    logic.discussHref("/discuss?embed=0", true),
  ],
  models: [
    "dashscope:qwen3.8-max",
    "deepseek:deepseek-flash",
    "ark:doubao-seed-2-1-pro-260915",
    "byok:self",
    "unknown:model",
  ].map(id => logic.discussModelLabel(id)),
}));
""", {})
    assert result["hrefs"] == [
        "/discuss",
        "/discuss?embed=1",
        "/discuss/new?draft=1&embed=1",
        "/discuss/abc?x=1",
        "/discuss?embed=0&embed=1",
    ]
    assert result["models"] == [
        "千问 3.8 Max",
        "DeepSeek Flash",
        "豆包 Seed 2.1 Pro",
        "我的模型",
        "unknown:model",
    ]
