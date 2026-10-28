"""T7 history date filter: Chinese date chips over the native date inputs (v1.2)."""

import re
import socket
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "frontend/app/history/page.tsx"

# T7-2 v1.2: an unparseable value keeps its raw text instead of silently
# collapsing to 「不限」 (the filter is still applied, so 「不限」 would lie).
DAY_FACE = (
    'const dayFace = (key: string) => '
    '(key ? formatBeijingDateLong(beijingDayStart(key)) || key : "不限");'
)

# The whole history page is scanned (comments included): the filter must keep
# using Beijing-time helpers, never the device time zone.
DEVICE_TIME_PATTERN = re.compile(
    r"toLocaleString|toLocaleDateString|toLocaleTimeString|toDateString\("
    r"|getHours\(|getMinutes\(|getDate\(|getDay\(|getMonth\(|getFullYear\("
)


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("History date-filter tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def read_history():
    return HISTORY.read_text(encoding="utf-8")


def test_date_chips_open_native_picker_and_bound_each_other():
    source = read_history()

    # HEAD-failing: HEAD has no picker wrapper at all.
    assert source.count("showPicker(") == 1, "showPicker() must appear exactly once"
    assert re.search(
        r"try\s*\{\s*input\.showPicker\(\);\s*\}\s*catch\s*\{",
        source,
    ), "openDatePicker must call showPicker() inside try and keep a catch fallback"

    # Two chips × (click + keyboard) = exactly four call sites.
    assert source.count("openDatePicker(e.currentTarget)") == 4
    assert source.count("onClick={e => openDatePicker(e.currentTarget)}") == 2

    # HEAD-failing: v1.1 only bounded the "from" chip's max when a "to" value
    # existed, and left the "to" chip without any max.
    assert 'max={dateTo || "9999-12-31"}' in source
    assert 'min={dateFrom || undefined} max="9999-12-31"' in source
    assert "max={dateTo || undefined}" not in source

    for expected in (
        "has-[:focus-visible]:outline",
        "has-[:focus-visible]:outline-1",
        "has-[:focus-visible]:outline-offset-2",
        "has-[:focus-visible]:outline-[color:var(--ink)]",
    ):
        assert expected in source, f"missing date-chip focus contract: {expected}"

    assert 'e.key === "Enter"' in source and 'e.key === " "' in source
    assert source.count('dateFrom && "chip-on"') == 1
    assert source.count('dateTo && "chip-on"') == 1
    assert not DEVICE_TIME_PATTERN.search(source), "date filter must not use the device time zone"


def test_date_chips_render_chinese_day_faces_and_drop_native_placeholder():
    source = read_history()

    assert "formatBeijingDateLong(" in source
    assert '"不限"' in source
    assert "dayFace(dateFrom)" in source
    assert "dayFace(dateTo)" in source
    assert "{dayFace(dateFrom)} 至 {dayFace(dateTo)}" in source

    # T7-2 v1.2, exact line: unparseable values fall back to the raw value.
    day_face = [
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith("const dayFace")
    ]
    assert len(day_face) == 1, "dayFace must be defined exactly once"
    assert day_face[0] == DAY_FACE, "dayFace must fall back to the raw value, not 「不限」"

    assert 'text-[10px] text-muted-foreground">至<' not in source
    assert '<div className="text-center text-[10px] text-muted-foreground">至</div>' not in source
    assert '{dateFrom || "—"} 至 {dateTo || "—"}' not in source


def test_all_quick_filter_requires_empty_date_bounds():
    source = read_history()

    assert (
        'quick === key && (key !== "all" || (!dateFrom && !dateTo))' in source
    ), "「全部」must only highlight when neither date bound is set"
    assert 'quick === key && dateFrom === (key === "all" ? "" : dateFrom)' not in source


def test_date_labels_stay_accessible_and_existing_history_contracts_survive():
    source = read_history()

    # HEAD-failing: the visible 「从」/「到」 chip labels are aria-hidden, so the
    # accessible name must still contain them (WCAG 2.5.3).
    assert source.count('aria-label="从（开始日期）"') == 1
    assert source.count('aria-label="到（结束日期）"') == 1
    assert 'aria-label="开始日期"' not in source
    assert 'aria-label="结束日期"' not in source

    # Regression: the native inputs stay invisible overlays inside the chips.
    assert source.count(
        'className="absolute inset-0 h-full w-full cursor-pointer opacity-0"'
    ) == 2
    assert source.count('<label className={cn("chip relative') == 2
    assert source.count('type="date"') == 2
    assert source.count("aria-label=") >= 5

    assert "@/lib/beijingTime" in source
    assert "formatBeijingTime(" in source
    assert "<MessageText text={msg.content} highlight={query} />" in source
    assert not DEVICE_TIME_PATTERN.search(source)
