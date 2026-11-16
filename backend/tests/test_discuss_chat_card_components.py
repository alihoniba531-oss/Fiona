"""讨论群聊天卡片组件的静态契约。

只读 frontend/components 下的两个新组件源码，不启动 Node、不访问网络、
不依赖浏览器或数据库。用例先确认文件存在且非空，再检查规格 4.10.5、
4.10.6 要求的文案、路径、分支与设计令牌，最后用坏副本证明断言不是恒真。
"""

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
TASK_CARD = FRONTEND / "components" / "DiscussTaskCard.tsx"
NOTE_CARD = FRONTEND / "components" / "DiscussNoteCard.tsx"

FORBIDDEN_TYPE_STYLE = re.compile(
    r"font-medium|font-semibold|font-bold|font-extrabold|font-black"
    r"|fontWeight|font-weight|font-\[\d|<(?:b|strong)\b",
    re.IGNORECASE,
)
NATIVE_DIALOG = re.compile(
    r"(^|[^.A-Za-z_])(window\.)?(confirm|alert)\(\s*[`\"']",
    re.MULTILINE,
)


def read_component(path):
    assert path.is_file(), f"{path.name} 尚未实现"
    source = path.read_text(encoding="utf-8")
    assert source.strip(), f"{path.name} 是空的"
    return source


def note_send_catch_body(source):
    """只取 send() 里外层 catch 的正文，证明后端文案确实写进了 catch 分支。"""
    send_start = source.find("const send = async () => {")
    assert send_start >= 0, "DiscussNoteCard.tsx 缺少 send()"
    catch_marker = "} catch (error) {"
    catch_start = source.find(catch_marker, send_start)
    assert catch_start >= 0, "DiscussNoteCard.tsx 的 send() 缺少 catch 分支"
    catch_start += len(catch_marker)
    finally_start = source.find("} finally {", catch_start)
    assert finally_start >= 0, "DiscussNoteCard.tsx 的 send() 缺少 finally 分支"
    return source[catch_start:finally_start]


def check_no_forbidden_style_or_html(source, name):
    assert not FORBIDDEN_TYPE_STYLE.search(source), (
        f"{name} 不允许出现字重写法：" + repr(FORBIDDEN_TYPE_STYLE.search(source).group(0))
    )
    assert "dangerouslySetInnerHTML" not in source, f"{name} 不允许 dangerouslySetInnerHTML"
    assert not NATIVE_DIALOG.search(source), f"{name} 不允许原生确认框或提示框"


def check_task_card_contract(source):
    for text in (
        '"use client";',
        "interface DiscussTaskCardProps",
        "onOpenDiscuss?: (path: string) => void;",
        "getDiscussTaskCard(taskId, controller.signal)",
        "AbortController",
        "controller.abort()",
        "正在读取任务卡…",
        "任务卡已不存在",
        "任务卡暂时读不到",
        "重新读取",
        "讨论群任务",
        ".slice(0, 80)",
        "……",
        "建议 ${maxRounds} 轮 · 预算 ${budget} 颗",
        "建议 ${maxRounds} 轮",
        "预算 ${budget} 颗",
        "去讨论群建群",
        "/discuss/new?embed=1&task=",
        'onOpenDiscuss("/discuss/new?embed=1&task=" + card.id)',
        "建群后主持人立项会调用模型并扣草莓。",
        "已建群《",
        "》 · ",
        "discussStatusLabel(group)",
        "打开",
        "/discuss/",
        'onOpenDiscuss("/discuss/" + group.id + "?embed=1")',
        "?embed=1",
        "ceramic-card",
        "w-[340px]",
        "btn btn-primary min-h-10",
        "btn btn-quiet",
        "text-fs-13",
        "var(--ink2)",
        "var(--carve)",
    ):
        assert text in source, f"DiscussTaskCard.tsx 缺少 {text!r}"

    stripped_lines = {line.strip() for line in source.splitlines()}
    budget_only = "if (budget !== null) return `预算 ${budget} 颗`;"
    rounds_only = "if (maxRounds !== null) return `建议 ${maxRounds} 轮`;"
    assert budget_only in stripped_lines, (
        "DiscussTaskCard.tsx 只有预算时必须写完整行 "
        f"{budget_only!r}（含反引号），不能写成「建议 … 颗」"
    )
    assert "if (budget !== null) return `建议 ${budget} 颗`;" not in source, (
        "DiscussTaskCard.tsx 只有预算时不能写「建议 … 颗」"
    )
    assert rounds_only in stripped_lines, (
        "DiscussTaskCard.tsx 只有轮数时必须写完整行 "
        f"{rounds_only!r}（含反引号）"
    )
    assert "if (maxRounds !== null) return `预算 ${maxRounds} 轮`;" not in source, (
        "DiscussTaskCard.tsx 只有轮数时不能写「预算 … 轮」"
    )

    assert "error.status === 404" in source and "error.status === 403" in source
    assert 'view.status === "missing"' in source
    assert 'view.status === "error"' in source
    assert "return () => controller.abort();" in source
    assert "setInterval" not in source, "任务卡不允许轮询"
    assert source.count("getDiscussTaskCard(") == 1, "任务卡应只读取一次"
    assert "if (group)" in source, "任务卡缺少已建群分支"
    assert source.count("{onOpenDiscuss &&") == 2, "任务卡的两个按钮都应受 onOpenDiscuss 控制"
    check_no_forbidden_style_or_html(source, "DiscussTaskCard.tsx")


def check_note_card_contract(source):
    for text in (
        '"use client";',
        "interface DiscussNoteCardProps",
        "onOpenDiscuss?: (path: string) => void;",
        "getDiscussNoteCard(noteId, controller.signal)",
        "sendDiscussNoteCard(noteId, signal)",
        "AbortController",
        "controller.abort()",
        "正在读取意见卡…",
        "意见卡已不存在",
        "意见卡暂时读不到",
        "重新读取",
        "给《{title}》的意见",
        "discussStatusLabel(group)",
        "whitespace-pre-wrap",
        "这个讨论群已经删除。",
        "这个群已经结束，不能再插话。",
        "group.status === \"closed\"",
        "group.status === \"failed\"",
        "group.pending_notes >= 5",
        "disabled={busy || pendingFull}",
        "还有 5 条插话没被读到，等主持人回应后再送。",
        "busyRef",
        "if (busyRef.current) return;",
        "sendDiscussNoteCard(noteId, signal)",
        "await sendDiscussNoteCard(noteId, signal)",
        "setBusy",
        "ApiError",
        "error instanceof ApiError && error.message",
        "送进群失败，请稍后再试。",
        "送进群",
        "送出后还要到群里点『按意见返工』才会继续。",
        "已送进群",
        "已送进群{message ?",
        "message.consumed",
        "主持人已读到",
        "主持人还没读到",
        "打开讨论群",
        "/discuss/",
        'onOpenDiscuss("/discuss/" + group.id + "?embed=1")',
        "?embed=1",
        "ceramic-card",
        "w-[420px]",
        "btn btn-primary min-h-10",
        "btn btn-quiet min-h-10",
        "text-fs-13",
        "var(--ink2)",
        "var(--carve)",
    ):
        assert text in source, f"DiscussNoteCard.tsx 缺少 {text!r}"

    assert "setActionError(message);" in source, (
        "DiscussNoteCard.tsx 送进群失败时必须把后端文案放进报错"
    )
    catch_body = note_send_catch_body(source)
    assert "setActionError(message);" in catch_body, (
        "DiscussNoteCard.tsx 的 setActionError(message); 必须在 send() 的 catch 分支里"
    )
    assert "const message = error instanceof ApiError && error.message" in catch_body, (
        "DiscussNoteCard.tsx 的报错文案必须来自 catch 分支里的 ApiError.message"
    )
    assert source.count("setActionError(message);") == 1, (
        "DiscussNoteCard.tsx 只应有一处 setActionError(message);"
    )

    read_state = 'message.consumed ? "，主持人已读到" : "，主持人还没读到"'
    swapped_read_state = 'message.consumed ? "，主持人还没读到" : "，主持人已读到"'
    assert read_state in source, (
        "DiscussNoteCard.tsx 必须含精确表达式 " + repr(read_state)
    )
    assert swapped_read_state not in source, (
        "DiscussNoteCard.tsx 已读与未读文案不能对调"
    )

    live_group_title = "(group ? group.title : view.group_title)"
    assert live_group_title in source, (
        "DiscussNoteCard.tsx 必须含精确表达式 " + repr(live_group_title)
    )
    assert "const title = (view.group_title).trim()" not in source, (
        "DiscussNoteCard.tsx 群还在时不能总用卡上记的 view.group_title"
    )

    assert "error.status === 404" in source and "error.status === 403" in source
    assert 'current.kind === "missing"' in source
    assert 'current.kind === "error"' in source
    assert "return () => controller.abort();" in source
    assert "if (busyRef.current) return;" in source, "意见卡缺少 busyRef 防重复守卫"
    assert "setInterval" not in source, "意见卡不允许轮询"
    assert source.count("getDiscussNoteCard(") == 2, "意见卡只在加载与失败后各读一次"
    assert source.count("getDiscussNoteCard(noteId, controller.signal)") == 1
    assert source.count("getDiscussNoteCard(noteId, signal)") == 1
    assert source.count("sendDiscussNoteCard(") == 1, "意见卡只应有一个送出请求"
    assert "group === null ?" in source, "意见卡缺少群已删除分支"
    assert "sent ?" in source, "意见卡缺少已送出分支"
    assert "ended ?" in source, "意见卡缺少群已结束分支"
    assert 'group.status === "done"' in source, "意见卡缺少 done 提示"
    assert "view.sent_at !== null" in source, "意见卡应按 sent_at 判断已送出"
    assert "view.message !== null" in source, "意见卡应按 message 判断插话是否还在"
    assert "{group && onOpenDiscuss &&" in source, "打开讨论群按钮应受群与 onOpenDiscuss 控制"
    check_no_forbidden_style_or_html(source, "DiscussNoteCard.tsx")


def test_both_components_exist_and_are_not_empty():
    for path in (TASK_CARD, NOTE_CARD):
        assert path.is_file(), f"{path.name} 尚未实现"
        source = path.read_text(encoding="utf-8")
        assert source.strip(), f"{path.name} 是空的"


def test_task_card_copy_paths_classes_and_branches():
    check_task_card_contract(read_component(TASK_CARD))


def test_note_card_copy_paths_classes_and_branches():
    check_note_card_contract(read_component(NOTE_CARD))


def test_note_card_has_no_confirm_dialog():
    source = read_component(NOTE_CARD)
    assert "confirm(" not in source
    assert "alert(" not in source
    check_no_forbidden_style_or_html(source, "DiscussNoteCard.tsx")


def test_task_card_is_not_polling_and_retries_by_reading_again():
    source = read_component(TASK_CARD)
    assert "setInterval" not in source and "setTimeout" not in source
    assert source.count("getDiscussTaskCard(") == 1
    assert "重新读取" in source


def test_bad_task_copy_missing_button_label_is_detected():
    source = read_component(TASK_CARD)
    bad = source.replace("去讨论群建群", "去建群", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_task_card_contract(bad)


def test_bad_task_copy_missing_excerpt_slice_is_detected():
    source = read_component(TASK_CARD)
    bad = source.replace(".slice(0, 80)", ".slice(0, 120)", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_task_card_contract(bad)


def test_bad_note_copy_restored_native_confirm_is_detected():
    source = read_component(NOTE_CARD)
    bad = source.replace(
        "const send = async () => {",
        'const send = async () => { confirm("确定要送进群吗？");',
        1,
    )
    assert bad != source
    with pytest.raises(AssertionError):
        check_note_card_contract(bad)


def test_bad_note_copy_missing_sent_label_is_detected():
    source = read_component(NOTE_CARD)
    bad = source.replace("已送进群", "已送出", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_note_card_contract(bad)


def test_bad_note_copy_missing_busy_guard_is_detected():
    source = read_component(NOTE_CARD)
    bad = source.replace("if (busyRef.current) return;", "if (false) return;", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_note_card_contract(bad)


def test_bad_task_budget_only_wording_is_detected():
    source = read_component(TASK_CARD)
    good = "if (budget !== null) return `预算 ${budget} 颗`;"
    bad_text = "if (budget !== null) return `建议 ${budget} 颗`;"
    assert good in source
    bad = source.replace(good, bad_text, 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_task_card_contract(bad)


def test_bad_task_rounds_only_wording_is_detected():
    source = read_component(TASK_CARD)
    good = "if (maxRounds !== null) return `建议 ${maxRounds} 轮`;"
    bad_text = "if (maxRounds !== null) return `预算 ${maxRounds} 轮`;"
    assert good in source
    bad = source.replace(good, bad_text, 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_task_card_contract(bad)


def test_bad_note_removed_action_error_is_detected():
    source = read_component(NOTE_CARD)
    bad = source.replace("      setActionError(message);\n", "", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_note_card_contract(bad)


def test_bad_note_action_error_outside_catch_is_detected():
    source = read_component(NOTE_CARD)
    removed = source.replace("      setActionError(message);\n", "", 1)
    marker = "  const send = async () => {\n"
    assert removed != source and marker in removed
    bad = removed.replace(marker, marker + "    setActionError(message);\n", 1)
    assert "setActionError(message);" in bad
    with pytest.raises(AssertionError):
        check_note_card_contract(bad)


def test_bad_note_swapped_read_state_wording_is_detected():
    source = read_component(NOTE_CARD)
    good = 'message.consumed ? "，主持人已读到" : "，主持人还没读到"'
    bad_text = 'message.consumed ? "，主持人还没读到" : "，主持人已读到"'
    assert good in source
    bad = source.replace(good, bad_text, 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_note_card_contract(bad)


def test_bad_note_stale_group_title_is_detected():
    source = read_component(NOTE_CARD)
    good = "(group ? group.title : view.group_title)"
    assert good in source
    bad = source.replace(good, "(view.group_title)", 1)
    assert bad != source
    with pytest.raises(AssertionError):
        check_note_card_contract(bad)
