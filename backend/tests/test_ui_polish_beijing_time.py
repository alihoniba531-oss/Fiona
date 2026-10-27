"""Beijing-time displays and UTC+8 arithmetic, verified under two device time zones."""

import json
import os
import re
import socket
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
BEIJING_TIME = FRONTEND / "lib/beijingTime.ts"

# T4 table: every file and the Beijing-time helpers it must use after the polish.
T4_REQUIRED_HELPERS = {
    "frontend/components/ChatBubble.tsx": ["formatBeijingTime("],
    "frontend/app/page.tsx": ["formatBeijingDateLong(", "formatBeijingDateTime(", "beijingDateKey("],
    "frontend/lib/chineseDate.ts": ["beijingParts("],
    "frontend/components/ConversationPicker.tsx": ["beijingDayNumber(", "formatBeijingTime(", "beijingParts("],
    "frontend/app/history/page.tsx": ["@/lib/beijingTime", "formatBeijingTime("],
    "frontend/components/LocalWatchSection.tsx": ["formatBeijingDateTime(date, true)"],
    "frontend/app/plaza/page.tsx": ["formatBeijingTime(", "formatBeijingDateTime(updateDate, true)"],
    "frontend/components/AgentExchangeWorkspace.tsx": ["beijingDayNumber(", "beijingParts(", "formatBeijingTime("],
}

# Spec T4 grep. Numeric `toLocaleString` ("字数千分位") stays; scrub those receivers first.
DEVICE_TIME_PATTERN = re.compile(
    r"toLocale(?:Date|Time)?String|getHours\(|getMinutes\(|getDate\(|getDay\(|getMonth\(|getFullYear\(|toDateString\("
)
NUMERIC_TO_LOCALE_PATTERN = re.compile(
    r"(?:\.length|\blength|\btopicLimit)\.toLocaleString\("
)


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("UI polish frontend tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


NODE_RUNNER = r"""
const fs = require('fs');
const path = require('path');
const ts = require('typescript');
const frontend = process.argv[1];

function compile(relativePath) {
  const source = fs.readFileSync(path.join(frontend, relativePath), 'utf8');
  return ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017 },
  }).outputText;
}

function load(relativePath, resolveImport) {
  const module = { exports: {} };
  const localRequire = id => {
    const resolved = resolveImport(id);
    if (resolved === undefined) throw new Error('Unexpected import: ' + id);
    return resolved;
  };
  new Function('exports', 'module', 'require', compile(relativePath))(module.exports, module, localRequire);
  return module.exports;
}

const beijing = load('lib/beijingTime.ts', () => undefined);
const chineseDate = load('lib/chineseDate.ts', id => id === '@/lib/beijingTime' ? beijing : undefined);

const date = new Date('2026-10-22T01:56:24Z');
const beforeMidnight = new Date('2026-10-21T15:59:59Z');
const atMidnight = new Date('2026-10-21T16:00:00Z');
const invalid = new Date(NaN);
const parts = beijing.beijingParts(date);
const invalidParts = beijing.beijingParts(invalid);

process.stdout.write(JSON.stringify({
  deviceOffsetMinutes: date.getTimezoneOffset(),
  formatBeijingTime: beijing.formatBeijingTime(date),
  formatBeijingDateTime: beijing.formatBeijingDateTime(date),
  formatBeijingDateTimeSeconds: beijing.formatBeijingDateTime(date, true),
  beijingDateKey: beijing.beijingDateKey(date),
  formatBeijingDateLong: beijing.formatBeijingDateLong(date),
  parts,
  weekday: parts.weekday,
  dayStart: beijing.beijingDayStart('2026-10-22').toISOString(),
  dayNumberBefore: beijing.beijingDayNumber(beforeMidnight),
  dayNumberAfter: beijing.beijingDayNumber(atMidnight),
  beijingDateKeyBefore: beijing.beijingDateKey(beforeMidnight),
  beijingDateKeyAfter: beijing.beijingDateKey(atMidnight),
  invalidFormatTime: beijing.formatBeijingTime(invalid),
  invalidFormatDateTime: beijing.formatBeijingDateTime(invalid),
  invalidFormatDateTimeSeconds: beijing.formatBeijingDateTime(invalid, true),
  invalidFormatDateLong: beijing.formatBeijingDateLong(invalid),
  invalidDateKey: beijing.beijingDateKey(invalid),
  invalidDayNumberIsNaN: Number.isNaN(beijing.beijingDayNumber(invalid)),
  invalidDayStartBadKey: Number.isNaN(beijing.beijingDayStart('not-a-date').getTime()),
  invalidDayStartImpossible: Number.isNaN(beijing.beijingDayStart('2026-02-30').getTime()),
  invalidPartsAllNaN: Object.values(invalidParts).every(value => Number.isNaN(value)),
  chineseDate: chineseDate.formatChineseDate(date),
  chineseDateWithYear: chineseDate.formatChineseDate(date, true),
  chineseDateBeforeMidnight: chineseDate.formatChineseDate(beforeMidnight),
  chineseDateAtMidnight: chineseDate.formatChineseDate(atMidnight),
}));
"""


def require_node_typescript():
    probe = (
        "const missing = ['typescript'].filter(name => {"
        "try { require.resolve(name, {paths: [process.argv[1]]}); return false; }"
        "catch { return true; }"
        "}); process.stdout.write(JSON.stringify(missing));"
    )
    try:
        result = subprocess.run(
            ["node", "-e", probe, str(FRONTEND)],
            capture_output=True, text=True, check=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        pytest.skip("Node.js is unavailable; source-only Beijing-time contracts still run")
    except OSError:
        pytest.skip("Node.js is unavailable; source-only Beijing-time contracts still run")
    try:
        missing = json.loads(result.stdout)
    except ValueError:
        pytest.skip("Node.js probe failed; source-only Beijing-time contracts still run")
    if missing:
        pytest.skip("TypeScript is unavailable in frontend/node_modules; source-only Beijing-time contracts still run")


def run_under_device_timezones():
    require_node_typescript()
    outputs = []
    for timezone in ("America/New_York", "Asia/Shanghai"):
        environment = dict(os.environ)
        environment["TZ"] = timezone
        try:
            result = subprocess.run(
                ["node", "-e", NODE_RUNNER, str(FRONTEND)],
                cwd=FRONTEND, capture_output=True, text=True, check=True,
                env=environment, timeout=120,
            )
        except FileNotFoundError:
            pytest.skip("Node.js is unavailable; source-only Beijing-time contracts still run")
        except subprocess.CalledProcessError as error:
            pytest.fail(f"Beijing-time module failed under TZ={timezone}: {error.stderr.strip()}")
        outputs.append(json.loads(result.stdout))
    return outputs


def test_time_cases_are_identical_under_new_york_and_shanghai_device_timezones():
    new_york, shanghai = run_under_device_timezones()
    assert new_york["deviceOffsetMinutes"] == 240, "TZ=America/New_York must reach the node process"
    assert shanghai["deviceOffsetMinutes"] == -480, "TZ=Asia/Shanghai must reach the node process"
    for key, value in shanghai.items():
        if key == "deviceOffsetMinutes":
            continue
        assert new_york[key] == value, f"{key} depends on the device time zone"

    assert shanghai["formatBeijingTime"] == "09:56"
    assert shanghai["beijingDateKey"] == "2026-10-22"
    assert shanghai["formatBeijingDateLong"] == "2026年10月22日"
    assert shanghai["formatBeijingDateTime"] == "2026/10/22 09:56"
    assert shanghai["formatBeijingDateTimeSeconds"] == "2026/10/22 09:56:24"
    assert shanghai["parts"] == {
        "year": 2026, "month": 10, "day": 22, "hour": 9, "minute": 56, "second": 24, "weekday": 4,
    }
    assert shanghai["weekday"] == 4
    assert shanghai["dayStart"] == "2026-10-21T16:00:00.000Z"
    assert shanghai["dayNumberAfter"] - shanghai["dayNumberBefore"] == 1
    assert shanghai["beijingDateKeyBefore"] == "2026-10-21"
    assert shanghai["beijingDateKeyAfter"] == "2026-10-22"


def test_invalid_dates_never_throw_and_return_empty_or_nan():
    _, shanghai = run_under_device_timezones()
    assert shanghai["invalidFormatTime"] == ""
    assert shanghai["invalidFormatDateTime"] == ""
    assert shanghai["invalidFormatDateTimeSeconds"] == ""
    assert shanghai["invalidFormatDateLong"] == ""
    assert shanghai["invalidDateKey"] == ""
    assert shanghai["invalidDayNumberIsNaN"] is True
    assert shanghai["invalidDayStartBadKey"] is True
    assert shanghai["invalidDayStartImpossible"] is True
    assert shanghai["invalidPartsAllNaN"] is True


def test_chinese_date_uses_beijing_calendar_day():
    _, shanghai = run_under_device_timezones()
    assert shanghai["chineseDate"] == "十月二十二日"
    assert shanghai["chineseDateWithYear"] == "2026年十月二十二日"
    assert shanghai["chineseDateBeforeMidnight"] == "十月二十一日"
    assert shanghai["chineseDateAtMidnight"] == "十月二十二日"


def test_beijing_time_module_uses_utc_arithmetic_only():
    source = BEIJING_TIME.read_text(encoding="utf-8")
    assert "BEIJING_OFFSET_MS = 8 * 3600_000" in source
    for name in (
        "BEIJING_OFFSET_MS", "beijingParts", "beijingDayNumber", "beijingDateKey",
        "beijingDayStart", "formatBeijingTime", "formatBeijingDateTime", "formatBeijingDateLong",
    ):
        assert name in source
    assert "getUTC" in source
    assert "Intl" not in source
    assert not re.search(
        r"toLocale|getHours\(|getMinutes\(|getDate\(|getDay\(|getMonth\(|getFullYear\(",
        source,
    )


@pytest.mark.parametrize("relative_path", sorted(T4_REQUIRED_HELPERS))
def test_t4_table_file_uses_beijing_time_helpers(relative_path):
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    missing = [snippet for snippet in T4_REQUIRED_HELPERS[relative_path] if snippet not in source]
    assert not missing, f"{relative_path} does not use the T4 Beijing-time helper(s): {missing}"


@pytest.mark.parametrize("relative_path", sorted(T4_REQUIRED_HELPERS))
def test_t4_table_file_has_no_device_timezone_date_display(relative_path):
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    findings = []
    for number, line in enumerate(source.splitlines(), 1):
        remaining = NUMERIC_TO_LOCALE_PATTERN.sub("", line)
        if DEVICE_TIME_PATTERN.search(remaining):
            findings.append(f"line {number}: {line.strip()}")
    assert not findings, f"{relative_path} still formats dates in the device time zone:\n" + "\n".join(findings)


def test_agent_exchange_page_heading_is_hidden_only_when_embedded():
    source = (ROOT / "frontend/components/AgentExchangeWorkspace.tsx").read_text(encoding="utf-8")
    headings = [line for line in source.splitlines() if "<h1" in line and "广场" in line]
    assert len(headings) == 1, "广场 page must keep exactly one <h1>"
    heading = headings[0]
    assert "embedded" in heading and "sr-only" in heading
    assert "text-[30px] font-medium tracking-[.24em]" in heading
    assert 'aria-label="刷新分身与交流记录"' in source
    assert not re.search(r"\{!embedded\b[^}]*aria-label=\"刷新分身与交流记录\"", source)
