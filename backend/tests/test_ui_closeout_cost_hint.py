"""T1 cost-hint closeout: first-visit and low-balance display, offline.

Reads only ``frontend/app/page.tsx``.  The real test feeds the checked-in
source to ``check_cost_hint_contract``; every self-check first proves the
checked-in source passes, then mutates one contract point and requires an
``AssertionError``.  On HEAD the untouched source already fails the contract,
so every test in this file fails for that same reason.
"""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend/app/page.tsx"
BOM = "\ufeff"

BALANCE_PROP = "balance: number | null;"
BALANCE_PASS = "balance={strawberryBalance}"
MARK_SEEN = "function markCostHintSeen(username: string): boolean {"
STORAGE_KEY = "`fiona_cost_hint_seen:${encodeURIComponent(username)}`"
LOW_BALANCE = "const lowBalance = balance !== null && balance < 30;"
SHOW_COST = "const showCost = firstVisit || lowBalance;"
HAS_CONTENT = "const hasContent = (chatMode && !!config) || showCost || (chatMode && !!error);"
PLATFORM_SPAN = (
    ': showCost && <span className={cn("min-w-0 truncate", lowBalance && '
    '"text-[color:var(--seal)]")} title={labelTitle}>{label}'
)
IMAGE_SPAN_PREFIX = (
    '</div> : showCost && <span className={cn(lowBalance && '
    '"text-[color:var(--seal)]")}>每条消息消耗 '
)
BALANCE_SUFFIX = '，还剩 <span className="readout font-normal">{balance}</span> 颗'
FIRST_VISIT_GUARD = (
    "if (firstVisitDecided.current === null) "
    "firstVisitDecided.current = markCostHintSeen(username);"
)
FIRST_VISIT_SET = "setFirstVisit(firstVisitDecided.current);"
LOW_BALANCE_SUFFIX = (
    '{lowBalance && <>，还剩 <span className="readout font-normal">{balance}</span> 颗</>}'
)
FOOTER_CONTAINER_TOKEN = "border-t border-[color:var(--carve)] pt-2"
ENTER_HINT = (
    '<span className="shrink-0 max-md:hidden">Enter 发送，Shift + Enter 换行</span>'
)


def check_cost_hint_contract(source: str) -> None:
    """Every v1.1 cost-hint contract point, in one pure-source check."""
    assert source.count(BALANCE_PROP) == 1, "the footer must accept a nullable balance prop"
    assert source.count(BALANCE_PASS) == 1, "the page must pass strawberryBalance into the footer"
    assert source.count(MARK_SEEN) == 1, "the first-visit marker function must exist exactly once"
    assert source.count(STORAGE_KEY) == 1, "the per-account first-visit storage key must exist once"

    assert source.count(LOW_BALANCE) == 1
    assert source.count(SHOW_COST) == 1
    assert source.count(HAS_CONTENT) == 1

    assert source.count(PLATFORM_SPAN) == 1, "the platform-model cost text must be guarded by showCost"
    assert source.count(IMAGE_SPAN_PREFIX) == 1, "the image-mode cost text must be guarded by showCost"
    assert source.count(BALANCE_SUFFIX) == 2, "both low-balance branches must show the balance"
    assert source.count(FIRST_VISIT_GUARD) == 1, (
        "the first-visit ref guard must wrap the storage write"
    )
    assert source.count(FIRST_VISIT_SET) == 1, (
        "the effect must set firstVisit from the decided ref"
    )
    assert source.count(LOW_BALANCE_SUFFIX) == 2, (
        "both low-balance branches must guard the balance with lowBalance"
    )

    lines = source.splitlines()
    footer_lines = [index for index, line in enumerate(lines) if FOOTER_CONTAINER_TOKEN in line]
    assert len(footer_lines) == 1, "the footer container line must be unique"
    footer_index = footer_lines[0]
    assert '!hasContent && "max-md:hidden"' in lines[footer_index], (
        "the footer container must hide on mobile when it has no content"
    )
    assert footer_index + 1 < len(lines), "the footer container must have an Enter hint line"
    assert lines[footer_index + 1].strip() == ENTER_HINT, (
        "the Enter hint must be the line immediately after the footer container"
    )

    assert source.count('className="readout font-normal"') == 4, (
        "two existing readout numbers plus both balance digits"
    )

    calls = [line for line in lines if "<ChatModelFooter " in line]
    assert len(calls) == 1, "ChatModelFooter must be rendered exactly once"
    assert BALANCE_PASS in calls[0], "the ChatModelFooter call must pass the balance"

    assert source.startswith(BOM), "page.tsx must keep its UTF-8 BOM"


def _read_source() -> str:
    return PAGE.read_text(encoding="utf-8")


def _replace_once(source: str, old: str, new: str) -> str:
    assert source.count(old) == 1, f"self-check replacement must be unique: {old!r}"
    return source.replace(old, new, 1)


def test_cost_hint_contract() -> None:
    check_cost_hint_contract(_read_source())


def test_selfcheck_missing_show_cost_guard_is_rejected() -> None:
    source = _read_source()
    check_cost_hint_contract(source)
    broken = _replace_once(
        source,
        PLATFORM_SPAN,
        PLATFORM_SPAN.replace(": showCost && ", ": ", 1),
    )
    with pytest.raises(AssertionError):
        check_cost_hint_contract(broken)


def test_selfcheck_balance_digits_are_rejected_when_not_readout() -> None:
    source = _read_source()
    check_cost_hint_contract(source)
    broken = source.replace(
        BALANCE_SUFFIX,
        '，还剩 <span className="readout">{balance}</span> 颗',
        1,
    )
    assert broken != source
    with pytest.raises(AssertionError):
        check_cost_hint_contract(broken)


def test_selfcheck_moved_enter_hint_is_rejected() -> None:
    source = _read_source()
    check_cost_hint_contract(source)
    broken = source.replace(ENTER_HINT, ENTER_HINT + "。", 1)
    assert broken != source
    with pytest.raises(AssertionError):
        check_cost_hint_contract(broken)


def test_selfcheck_missing_bom_is_rejected() -> None:
    source = _read_source()
    check_cost_hint_contract(source)
    broken = source[1:]
    assert not broken.startswith(BOM)
    with pytest.raises(AssertionError):
        check_cost_hint_contract(broken)


def test_selfcheck_first_visit_always_false_is_rejected() -> None:
    source = _read_source()
    check_cost_hint_contract(source)
    assert source.count(FIRST_VISIT_SET) == 1
    broken = source.replace(FIRST_VISIT_SET, "setFirstVisit(false);", 1)
    assert broken != source
    with pytest.raises(AssertionError):
        check_cost_hint_contract(broken)


def test_selfcheck_missing_first_visit_ref_guard_is_rejected() -> None:
    source = _read_source()
    check_cost_hint_contract(source)
    guard_prefix = "if (firstVisitDecided.current === null) "
    assert source.count(guard_prefix) == 1
    broken = source.replace(guard_prefix, "", 1)
    assert broken != source
    with pytest.raises(AssertionError):
        check_cost_hint_contract(broken)


def test_selfcheck_first_low_balance_guard_is_rejected() -> None:
    source = _read_source()
    check_cost_hint_contract(source)
    old = "{lowBalance && <>，还剩"
    assert source.count(old) == 2
    broken = source.replace(old, "{<>，还剩", 1)
    assert broken != source
    with pytest.raises(AssertionError):
        check_cost_hint_contract(broken)
