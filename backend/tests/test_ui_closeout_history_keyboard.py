"""UI closeout T2: history date chips take keyboard focus, native inputs leave the Tab order.

Blind spot 1 from the third batch: the old test only counted each
``aria-label`` once, so swapping the two labels between the two date inputs
still passed. These checks pair every label with its own value / data-chip /
ref, and every visible chip button with its own input ref.
"""

import re
import socket
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "frontend/app/history/page.tsx"

INPUT_TAG = re.compile(r"<input\b.*?/>", re.DOTALL)

FROM_INPUT_LABEL = 'aria-label="从（开始日期）"'
TO_INPUT_LABEL = 'aria-label="到（结束日期）"'
FROM_BUTTON_LABEL = "aria-label={`从（开始日期）：${dayFace(dateFrom)}`}"
TO_BUTTON_LABEL = "aria-label={`到（结束日期）：${dayFace(dateTo)}`}"
FROM_BUTTON_ONCLICK = (
    "onClick={() => { if (dateFromRef.current) openDatePicker(dateFromRef.current); }}"
)
TO_BUTTON_ONCLICK = (
    "onClick={() => { if (dateToRef.current) openDatePicker(dateToRef.current); }}"
)
RAW_CHIP_UPDATE = 'setRawChip(input.dataset.chip === "to" ? "to" : "from");'


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("History keyboard tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def read_history() -> str:
    return HISTORY.read_text(encoding="utf-8")


def check_date_chip_keyboard_contract(source: str) -> None:
    """The native inputs leave the Tab order; the chip buttons own the focus ring."""
    assert source.count("tabIndex={-1}") == 2, "both native date inputs must leave the Tab order"
    assert source.count('data-chip="from"') == 1, "the from chip must tag its own native input"
    assert source.count('data-chip="to"') == 1, "the to chip must tag its own native input"
    assert source.count("ref={dateFromRef}") == 1, "the from input must keep its ref"
    assert source.count("ref={dateToRef}") == 1, "the to input must keep its ref"
    assert source.count('aria-hidden="true"') >= 6, "four visible labels plus two native inputs"
    assert source.count("onBlur={() => setRawChip(null)}") == 2, "both raw inputs hide on blur"

    # The fallback branch must show the corresponding raw input and focus it.
    assert source.count(RAW_CHIP_UPDATE) == 1
    assert "input.focus();" in source
    catch_at = source.index("catch {")
    catch_end = source.index("};", catch_at)
    fallback = source[catch_at:catch_end]
    assert RAW_CHIP_UPDATE in fallback, "the fallback must reveal the input matching data-chip"
    assert "input.focus();" in fallback, "the fallback must move focus onto the raw date input"


def check_date_input_pairing(source: str) -> None:
    """Blind spot 1: each native date input carries only its own chip's binding."""
    date_tags = [tag for tag in INPUT_TAG.findall(source) if 'type="date"' in tag]
    assert len(date_tags) == 2, f"expected exactly two native date inputs, found {len(date_tags)}"

    from_tags = [tag for tag in date_tags if FROM_INPUT_LABEL in tag]
    to_tags = [tag for tag in date_tags if TO_INPUT_LABEL in tag]
    assert len(from_tags) == 1, "the from date label must belong to exactly one native input"
    assert len(to_tags) == 1, "the to date label must belong to exactly one native input"

    for expected in (
        "value={dateFrom}",
        'data-chip="from"',
        "ref={dateFromRef}",
        'aria-hidden="true"',
        "tabIndex={-1}",
        "onBlur={() => setRawChip(null)}",
        'rawChip === "from"',
    ):
        assert expected in from_tags[0], (
            f"the input labeled 「从（开始日期）」 must carry {expected}, not the other chip's binding"
        )
    for expected in (
        "value={dateTo}",
        'data-chip="to"',
        "ref={dateToRef}",
        'aria-hidden="true"',
        "tabIndex={-1}",
        "onBlur={() => setRawChip(null)}",
        'rawChip === "to"',
    ):
        assert expected in to_tags[0], (
            f"the input labeled 「到（结束日期）」 must carry {expected}, not the other chip's binding"
        )


def _check_chip_button(lines: list[str], label: str, onclick: str, name: str) -> None:
    hits = [index for index, line in enumerate(lines) if label in line]
    assert len(hits) == 1, f"the {name} chip button label must appear on exactly one line"
    index = hits[0]
    assert index + 1 < len(lines), f"the {name} chip button is missing its click handler line"
    assert lines[index + 1].strip() == onclick, (
        f"the {name} chip button must open the {name} input's ref, not the other chip's ref"
    )


def check_date_button_pairing(source: str) -> None:
    """Blind spot 1, button half: each visible chip opens its own native input."""
    assert source.count(FROM_BUTTON_LABEL) == 1, "the from chip button label must appear exactly once"
    assert source.count(TO_BUTTON_LABEL) == 1, "the to chip button label must appear exactly once"
    lines = source.splitlines()
    _check_chip_button(lines, FROM_BUTTON_LABEL, FROM_BUTTON_ONCLICK, "从（开始日期）")
    _check_chip_button(lines, TO_BUTTON_LABEL, TO_BUTTON_ONCLICK, "到（结束日期）")


def check_date_buttons_stay_in_tab_order(source: str) -> None:
    """The chip buttons own the Tab stop; the native inputs carry no keyboard affordance."""
    lines = source.splitlines()
    for label, name in ((FROM_BUTTON_LABEL, "从（开始日期）"), (TO_BUTTON_LABEL, "到（结束日期）")):
        hits = [index for index, line in enumerate(lines) if label in line]
        assert len(hits) == 1, f"the {name} chip button label must appear on exactly one line"
        label_index = hits[0]
        starts = [index for index in range(label_index, -1, -1) if lines[index].strip() == "<button"]
        ends = [index for index in range(label_index, len(lines)) if lines[index].strip() == "/>"]
        assert starts, f"the {name} chip button must open with a bare <button line"
        assert ends, f"the {name} chip button must close with a bare /> line"
        start, end = starts[0], ends[0]
        assert start < label_index < end, f"the {name} chip button label must sit inside its tag"
        tag = "\n".join(lines[start:end + 1])
        assert "tabIndex" not in tag, f"the {name} chip button must stay in the Tab order"
        assert "aria-hidden" not in tag, f"the {name} chip button must not be hidden from AT"


def _swap(source: str, left: str, right: str) -> str:
    assert left in source and right in source
    marker = "\x00ui-closeout-swap\x00"
    return source.replace(left, marker).replace(right, left).replace(marker, right)


def test_date_chip_keyboard_contract() -> None:
    check_date_chip_keyboard_contract(read_history())


def test_date_inputs_pair_with_their_own_chips() -> None:
    check_date_input_pairing(read_history())


def test_date_buttons_pair_with_their_own_inputs() -> None:
    check_date_button_pairing(read_history())


def test_date_buttons_stay_in_tab_order() -> None:
    check_date_buttons_stay_in_tab_order(read_history())


def test_selfcheck_swapped_labels_are_rejected() -> None:
    source = read_history()
    check_date_input_pairing(source)
    check_date_button_pairing(source)

    # Swapping the two literal native-input labels must break the pairing check.
    swapped_inputs = _swap(source, FROM_INPUT_LABEL, TO_INPUT_LABEL)
    with pytest.raises(AssertionError):
        check_date_input_pairing(swapped_inputs)

    # Swapping the two visible chip button labels must break the button check.
    swapped_buttons = _swap(source, FROM_BUTTON_LABEL, TO_BUTTON_LABEL)
    with pytest.raises(AssertionError):
        check_date_button_pairing(swapped_buttons)


def test_selfcheck_inputs_without_aria_hidden_are_rejected() -> None:
    source = read_history()
    check_date_input_pairing(source)
    old = 'aria-hidden="true"\n                  tabIndex={-1}'
    assert source.count(old) == 2
    broken = source.replace(old, "tabIndex={-1}")
    assert broken != source
    with pytest.raises(AssertionError):
        check_date_input_pairing(broken)


def test_selfcheck_tabindex_moved_to_buttons_is_rejected() -> None:
    source = read_history()
    check_date_input_pairing(source)
    check_date_buttons_stay_in_tab_order(source)
    old_tabindex = "                  tabIndex={-1}\n"
    old_button = '                  type="button"\n'
    assert source.count(old_tabindex) == 2
    assert source.count(old_button) == 2
    broken = source.replace(old_tabindex, "")
    broken = broken.replace(old_button, old_button + "                  tabIndex={-1}\n")
    assert broken.count("tabIndex={-1}") == 2
    with pytest.raises(AssertionError):
        check_date_input_pairing(broken)
    with pytest.raises(AssertionError):
        check_date_buttons_stay_in_tab_order(broken)


def test_selfcheck_swapped_raw_chip_keys_are_rejected() -> None:
    source = read_history()
    check_date_input_pairing(source)
    broken = _swap(source, 'rawChip === "from"', 'rawChip === "to"')
    with pytest.raises(AssertionError):
        check_date_input_pairing(broken)
