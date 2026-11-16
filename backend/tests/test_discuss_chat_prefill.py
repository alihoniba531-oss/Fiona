"""讨论群任务卡在新建页的预填：静态守卫与 Node 纯函数契约。

离线运行。缺 frontend 依赖或 node 时只在 Node 用例里 skip，静态用例照常跑。
所有断言都针对真实实现；坏副本对照证明去掉任务卡提交或去掉夹取时会被抓到。
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
LOGIC = FRONTEND / "lib" / "discussLogic.ts"
NEW_PAGE = FRONTEND / "app" / "discuss" / "new" / "page.tsx"
FORM = FRONTEND / "components" / "discuss" / "DiscussCreateForm.tsx"
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


def read(path):
    assert path.is_file(), f"缺少文件：{path.relative_to(ROOT)}"
    text = path.read_text(encoding="utf-8")
    assert text, f"{path.relative_to(ROOT)} 是空的"
    return text


GROUP_ID_GUARD = "        if (card.task.group_id) {"
USABLE_ELSE = "        } else {"


def form_task_guard_branches(source):
    """按原文切出「已建群」分支与「可预填」else 分支，供分支内断言使用。"""
    guard = GROUP_ID_GUARD + "\n"
    assert guard in source, "表单缺少完整的 `if (card.task.group_id) {` 行"
    group_start = source.index(guard) + len(guard)
    else_line = USABLE_ELSE + "\n"
    assert else_line in source[group_start:], "已建群分支后缺少可预填的 else 分支"
    group_end = source.index(else_line, group_start)
    usable_start = group_end + len(else_line)
    branch_close = "        }\n"
    assert branch_close in source[usable_start:], "可预填的 else 分支缺少收尾"
    usable_end = source.index(branch_close, usable_start)
    return source[group_start:group_end], source[usable_start:usable_end]


def assert_new_page_contract(source):
    assert 'useSearchParams().get("task")' in source
    assert re.search(r"/\^\[0-9a-f-\]\{36\}\$/", source), (
        "新建页必须用 ^[0-9a-f-]{36}$ 校验 task 参数"
    )
    assert ".test(taskParam)" in source, "必须真正用正则校验 task 参数"
    assert "taskId={taskId}" in source, "新建页必须把校验后的 taskId 传给表单"


def assert_form_contract(source):
    assert "taskId?: string" in source
    assert "getDiscussTaskCard(taskId, request.signal)" in source
    assert "applyDiscussTaskPrefill(nextForm, card.task, next.limits)" in source
    assert "任务卡不存在，可以直接新建。" in source
    assert "这张任务卡已经建成" in source
    assert "这张任务卡已经用过。" in source
    assert "card.task.group.title" in source
    assert "body.task_id = submitTaskId;" in source
    assert "setBudgetText(String(nextForm.budget_strawberries));" in source
    assert "error.status === 404 || error.status === 403" in source

    group_branch, usable_branch = form_task_guard_branches(source)
    assert "这张任务卡已经建成" in group_branch, (
        "「这张任务卡已经建成」必须写在 if (card.task.group_id) 分支内"
    )
    assert "这张任务卡已经用过。" in group_branch, (
        "「这张任务卡已经用过。」必须写在 if (card.task.group_id) 分支内"
    )
    assert "applyDiscussTaskPrefill" not in group_branch, (
        "已建过群的任务卡不能再次预填"
    )
    assert "setSubmitTaskId" not in group_branch, (
        "已建过群的任务卡不能记下 task_id"
    )
    assert "applyDiscussTaskPrefill" in usable_branch, (
        "未建群的任务卡必须在 else 可用分支里预填"
    )
    assert 'setSubmitTaskId(taskId ?? "");' in usable_branch, (
        "未建群的任务卡必须在 else 可用分支里记下 task_id"
    )
    assert "if (submitTaskId) body.task_id = submitTaskId;" in source, (
        "提交时只应在可用分支记下 task_id 后带上它"
    )
    assert "body.task_id = submitTaskId;" not in group_branch, (
        "已建过群时提交不能带 task_id"
    )
    assert source.index("body.task_id = submitTaskId;") > source.index(GROUP_ID_GUARD), (
        "body.task_id 的赋值必须在已建群判断之后"
    )


def test_new_page_only_passes_thirty_six_char_task_ids():
    source = read(NEW_PAGE)
    assert_new_page_contract(source)

    bad = source.replace("taskId={taskId}", "", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        assert_new_page_contract(bad)

    pattern = re.compile("^[0-9a-f-]{36}$")
    assert pattern.fullmatch("01234567-89ab-cdef-0123-456789abcdef")
    assert pattern.fullmatch("0" * 36)
    assert not pattern.fullmatch("0" * 35)
    assert not pattern.fullmatch("0" * 37)
    assert not pattern.fullmatch("javascript:alert(1)")
    assert not pattern.fullmatch("01234567-89ab-cdef-0123-456789abcdeG")


def test_form_reads_task_card_prefills_and_submits_task_id():
    source = read(FORM)
    assert_form_contract(source)

    bad = source.replace("body.task_id = submitTaskId;", "", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        assert_form_contract(bad)
    print("坏副本已抓到：提交时去掉 task_id 后静态契约失败")


def test_form_built_task_guard_bad_copy_is_detected():
    source = read(FORM)
    assert_form_contract(source)

    bad = source.replace(GROUP_ID_GUARD, "        if (false) {", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        assert_form_contract(bad)
    print("坏副本已抓到：把已建群判断改成 if (false) 后静态契约失败")


def test_form_built_task_notice_outside_guard_is_detected():
    source = read(FORM)
    assert_form_contract(source)

    group_branch, _ = form_task_guard_branches(source)
    notice = (
        "          setTaskNotice(card.task.group\n"
        "            ? `这张任务卡已经建成《${card.task.group.title}》。`\n"
        '            : "这张任务卡已经用过。");\n'
    )
    assert notice in group_branch, "已建群提示应整段写在 if (card.task.group_id) 分支内"
    bad = source.replace(notice, "", 1)
    assert bad != source
    bad = bad.replace(
        '          setSubmitTaskId(taskId ?? "");\n',
        '          setSubmitTaskId(taskId ?? "");\n' + notice,
        1,
    )
    assert bad != source and "这张任务卡已经建成" in bad
    with pytest.raises(AssertionError):
        assert_form_contract(bad)
    print("坏副本已抓到：把已建群提示挪出判断分支后静态契约失败")


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


def run_prefill(source_path, form, task, limits):
    require_node_dependencies()
    assert source_path.is_file(), f"缺少文件：{source_path}"
    payload = {"form": form, "task": task, "limits": limits}
    script = NODE_LOADER + "\nconst payload = " + json.dumps(
        payload, ensure_ascii=False) + ";\n" + """
const formBefore = JSON.stringify(payload.form);
const taskBefore = JSON.stringify(payload.task);
const limitsBefore = JSON.stringify(payload.limits);
const result = logic.applyDiscussTaskPrefill(payload.form, payload.task, payload.limits);
process.stdout.write(JSON.stringify({
  form: result,
  unchanged: formBefore === JSON.stringify(payload.form)
    && taskBefore === JSON.stringify(payload.task)
    && limitsBefore === JSON.stringify(payload.limits),
}));
"""
    result = subprocess.run(
        ["node", "-e", script, str(source_path)],
        cwd=FRONTEND, capture_output=True, text=True,
    )
    if result.returncode != 0:
        pytest.fail("node runner failed:\n" + result.stderr)
    return json.loads(result.stdout)


def form_values(**overrides):
    values = {
        "request": "",
        "materials": "",
        "team": "host",
        "lenses": [],
        "custom_members": [],
        "avatar": True,
        "avatar_model": "dashscope:qwen3.8-max",
        "default_avatar_model": "dashscope:qwen3.8-max",
        "budget_strawberries": 500,
        "max_rounds": 3,
        "identities": [],
    }
    values.update(overrides)
    return values


def task_values(**overrides):
    values = {
        "request": "调研东南亚 AI 短剧",
        "materials": "材料一\n材料二",
        "max_rounds": 4,
        "budget_strawberries": 888,
    }
    values.update(overrides)
    return values


LIMITS = {
    "rounds_min": 1,
    "rounds_max": 6,
    "budget_min": 100,
    "budget_max": 20000,
}


def test_prefill_keeps_request_and_materials_verbatim():
    request = "  帮我查清楚东南亚 AI 短剧\n第二行保持原样  "
    materials = "已有材料 A\n\n材料 B\t带制表符"
    result = run_prefill(
        LOGIC, form_values(), task_values(request=request, materials=materials), LIMITS)
    form = result["form"]
    assert form["request"] == request
    assert form["materials"] == materials
    assert result["unchanged"] is True


@pytest.mark.parametrize("rounds,budget", [(1, 100), (4, 888), (6, 20000)])
def test_prefill_keeps_in_range_rounds_and_budget(rounds, budget):
    result = run_prefill(
        LOGIC, form_values(),
        task_values(max_rounds=rounds, budget_strawberries=budget), LIMITS)
    form = result["form"]
    assert form["max_rounds"] == rounds
    assert form["budget_strawberries"] == budget
    assert form["team"] == "host"
    assert form["avatar"] is True
    assert form["request"] == "调研东南亚 AI 短剧"
    assert form["materials"] == "材料一\n材料二"
    assert result["unchanged"] is True


def test_prefill_clamps_values_above_maximum():
    result = run_prefill(
        LOGIC, form_values(),
        task_values(max_rounds=99, budget_strawberries=999999), LIMITS)
    form = result["form"]
    assert form["max_rounds"] == LIMITS["rounds_max"] == 6
    assert form["budget_strawberries"] == LIMITS["budget_max"] == 20000
    assert result["unchanged"] is True


def test_prefill_clamps_values_below_minimum():
    result = run_prefill(
        LOGIC, form_values(),
        task_values(max_rounds=0, budget_strawberries=1), LIMITS)
    form = result["form"]
    assert form["max_rounds"] == LIMITS["rounds_min"] == 1
    assert form["budget_strawberries"] == LIMITS["budget_min"] == 100
    assert result["unchanged"] is True


@pytest.mark.parametrize(
    "rounds,budget,expected_rounds,expected_budget",
    [
        (None, None, 3, 500),
        (4, None, 4, 500),
        (None, 888, 3, 888),
        (3.5, 500.5, 3, 500),
        ("4", "888", 3, 500),
    ],
)
def test_prefill_keeps_form_defaults_for_missing_or_non_integer_suggestions(
        rounds, budget, expected_rounds, expected_budget):
    result = run_prefill(
        LOGIC, form_values(max_rounds=3, budget_strawberries=500),
        task_values(max_rounds=rounds, budget_strawberries=budget), LIMITS)
    form = result["form"]
    assert form["max_rounds"] == expected_rounds
    assert form["budget_strawberries"] == expected_budget
    assert form["request"] == "调研东南亚 AI 短剧"
    assert form["materials"] == "材料一\n材料二"
    assert result["unchanged"] is True


def assert_rounds_clamped(result):
    assert result["form"]["max_rounds"] == LIMITS["rounds_max"]


def test_prefill_without_round_clamp_bad_copy_is_caught(tmp_path):
    source = read(LOGIC)
    marker = "Math.min(Math.max(suggestedRounds, limits.rounds_min), limits.rounds_max)"
    assert marker in source, "纯函数里找不到轮数夹取"
    bad = source.replace(marker, "suggestedRounds", 1)
    assert bad != source
    bad_path = tmp_path / "discussLogic.bad.ts"
    bad_path.write_text(bad, encoding="utf-8")

    good = run_prefill(
        LOGIC, form_values(), task_values(max_rounds=99, budget_strawberries=888), LIMITS)
    bad_result = run_prefill(
        bad_path, form_values(), task_values(max_rounds=99, budget_strawberries=888), LIMITS)
    assert_rounds_clamped(good)
    with pytest.raises(AssertionError):
        assert_rounds_clamped(bad_result)
    print("坏副本已抓到：去掉轮数夹取后 99 不再被夹到 6")
