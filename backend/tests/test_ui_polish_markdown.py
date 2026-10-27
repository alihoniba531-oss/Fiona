"""Offline checks for the Markdown subset parser and the MessageText renderer."""

import json
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
PARSER = FRONTEND / "lib/messageMarkdown.ts"
MESSAGE_TEXT = FRONTEND / "components/MessageText.tsx"
CHAT_BUBBLE = FRONTEND / "components/ChatBubble.tsx"

PARSE_CASES = {
    "unordered": {"text": "- 苹果\n- 香蕉"},
    "ordered": {"text": "3. 三\n4. 四"},
    "ordered_cn": {"text": "1、第一\n2、第二"},
    "decimal_not_list": {"text": "1.5 倍"},
    "depth": {"text": "- 一级\n  - 二级\n  - 另一个二级\n- 回到一级"},
    "list_then_para": {"text": "- 项目\n普通行"},
    "continuation": {"text": "- 第一行\n  第二行\n- 下一项"},
    "headings": {"text": "# 一\n## 二\n### 三\n#### 四\n##### 五\n###### 六"},
    "quote": {"text": "> 第一行\n> 第二行\n\n普通"},
    "fence": {"text": "```ts\nconst a = 1;\n- 不是列表\n```"},
    "fence_unclosed": {"text": "```\n未闭合\n仍然代码"},
    "rule": {"text": "---\n\n* * *"},
    "list_then_rule": {"text": "- 项目\n* * *\n- 后续"},
    "emphasis": {"text": "这是**重点**内容"},
    "emphasis_newline": {"text": "**第一\n第二**"},
    "single_star_snake": {"text": "2 * 3 = 6，snake_case 与 __dunder__"},
    "inline_code": {"text": "用 `code` 结束"},
    "inline_code_no_newline": {"text": "`第一\n第二`"},
    "not_link": {"text": "[t](u) <span>x</span>"},
    "typing_unpaired": {"text": "正在**强调", "options": {"typing": True}},
    "not_typing_unpaired": {"text": "正在**强调", "options": {"typing": False}},
    "typing_paired": {"text": "完成**重点**", "options": {"typing": True}},
    "typing_backtick": {"text": "看 `代码", "options": {"typing": True}},
    "code_is_not_emphasis": {"text": "`**x**`"},
    "empty": {"text": ""},
    "paragraph_newlines": {"text": "第一行\n第二行"},
    "crlf": {"text": "# 标题\r\n\r\n- 一\r\n- 二"},
    "unpaired_stars": {"text": "**"},
    "unpaired_backtick": {"text": "`"},
    "lone_fence": {"text": "```"},
    "seven_hashes": {"text": "#######"},
    "empty_quote": {"text": ">"},
}

STRIP_CASES = {
    "mixed": "# 标题\n\n- 第一\n- 第二\n\n> 引用\n\n**重点** 与 `code`\n\n```\nblock\n```",
    "ordered": "2. 第二\n3. 第三",
    "rule_removed": "前\n\n---\n\n后",
    "nested": "- 一\n  - 二",
}


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("UI polish Markdown tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


PARSER_RUNNER = r"""
const fs = require('fs');
const ts = require('typescript');
const source = fs.readFileSync(process.argv[1], 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const loaded = { exports: {} };
new Function('exports', 'module', compiled)(loaded.exports, loaded);
const api = loaded.exports;
const requests = JSON.parse(process.argv[2]);
const results = requests.map(item => {
  if (Object.prototype.hasOwnProperty.call(item, 'strip')) return api.stripMessageMarkdown(item.strip);
  return api.parseMessageMarkdown(item.text, item.options);
});
process.stdout.write(JSON.stringify(results));
"""


def require_node_typescript():
    if shutil.which("node") is None:
        pytest.skip("Node.js is unavailable; source-only Markdown assertions still run")
    probe = """
const packages = ['typescript'];
const missing = packages.filter(name => {
  try { require.resolve(name, {paths: [process.argv[1]]}); return false; }
  catch { return true; }
});
process.stdout.write(JSON.stringify(missing));
"""
    try:
        result = subprocess.run(
            ["node", "-e", probe, str(FRONTEND)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("Node.js/TypeScript is unavailable; source-only Markdown assertions still run")
    missing = json.loads(result.stdout)
    if missing:
        pytest.skip("Frontend dependencies unavailable: " + ", ".join(missing))


def run_parser(requests):
    completed = subprocess.run(
        ["node", "-e", PARSER_RUNNER, str(PARSER), json.dumps(requests, ensure_ascii=False)],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.fixture(scope="module")
def markdown_runtime():
    require_node_typescript()
    parse_names = list(PARSE_CASES)
    parse_requests = [
        {"text": PARSE_CASES[name]["text"], "options": PARSE_CASES[name].get("options", {})}
        for name in parse_names
    ]
    strip_names = list(STRIP_CASES)
    strip_requests = [{"strip": STRIP_CASES[name]} for name in strip_names]
    results = run_parser(parse_requests + strip_requests)
    return {
        "parse": dict(zip(parse_names, results[: len(parse_names)])),
        "strip": dict(zip(strip_names, results[len(parse_names) :])),
    }


def plain_text(inlines):
    return "".join(inline["text"] for inline in inlines)


def test_unordered_list(markdown_runtime):
    blocks = markdown_runtime["parse"]["unordered"]
    assert len(blocks) == 1
    block = blocks[0]
    assert block["kind"] == "list"
    assert block["ordered"] is False
    assert block["start"] == 1
    assert [item["depth"] for item in block["items"]] == [0, 0]
    assert [plain_text(item["inlines"]) for item in block["items"]] == ["苹果", "香蕉"]


def test_ordered_list_start_and_chinese_separator(markdown_runtime):
    block = markdown_runtime["parse"]["ordered"][0]
    assert block["kind"] == "list"
    assert block["ordered"] is True
    assert block["start"] == 3
    assert [plain_text(item["inlines"]) for item in block["items"]] == ["三", "四"]

    block = markdown_runtime["parse"]["ordered_cn"][0]
    assert block["kind"] == "list"
    assert block["ordered"] is True
    assert block["start"] == 1
    assert [plain_text(item["inlines"]) for item in block["items"]] == ["第一", "第二"]


def test_decimal_is_not_a_list(markdown_runtime):
    blocks = markdown_runtime["parse"]["decimal_not_list"]
    assert len(blocks) == 1
    assert blocks[0]["kind"] == "para"
    assert plain_text(blocks[0]["inlines"]) == "1.5 倍"


def test_list_depth(markdown_runtime):
    block = markdown_runtime["parse"]["depth"][0]
    assert block["kind"] == "list"
    assert [item["depth"] for item in block["items"]] == [0, 1, 1, 0]
    assert [plain_text(item["inlines"]) for item in block["items"]] == [
        "一级",
        "二级",
        "另一个二级",
        "回到一级",
    ]


def test_unindented_line_ends_list(markdown_runtime):
    blocks = markdown_runtime["parse"]["list_then_para"]
    assert [block["kind"] for block in blocks] == ["list", "para"]
    assert plain_text(blocks[1]["inlines"]) == "普通行"


def test_indented_continuation_joins_previous_item(markdown_runtime):
    blocks = markdown_runtime["parse"]["continuation"]
    assert len(blocks) == 1
    items = blocks[0]["items"]
    assert [plain_text(item["inlines"]) for item in items] == ["第一行\n第二行", "下一项"]


def test_heading_levels(markdown_runtime):
    blocks = markdown_runtime["parse"]["headings"]
    assert [block["kind"] for block in blocks] == ["heading"] * 6
    assert [block["level"] for block in blocks] == [1, 1, 2, 3, 3, 3]
    assert [plain_text(block["inlines"]) for block in blocks] == ["一", "二", "三", "四", "五", "六"]


def test_quote_joins_lines(markdown_runtime):
    blocks = markdown_runtime["parse"]["quote"]
    assert [block["kind"] for block in blocks] == ["quote", "para"]
    assert plain_text(blocks[0]["inlines"]) == "第一行\n第二行"
    assert plain_text(blocks[1]["inlines"]) == "普通"


def test_fenced_code_keeps_content_verbatim(markdown_runtime):
    blocks = markdown_runtime["parse"]["fence"]
    assert blocks == [{"kind": "code", "text": "const a = 1;\n- 不是列表"}]
    unclosed = markdown_runtime["parse"]["fence_unclosed"]
    assert unclosed == [{"kind": "code", "text": "未闭合\n仍然代码"}]


def test_rule(markdown_runtime):
    assert markdown_runtime["parse"]["rule"] == [{"kind": "rule"}, {"kind": "rule"}]
    blocks = markdown_runtime["parse"]["list_then_rule"]
    assert [block["kind"] for block in blocks] == ["list", "rule", "list"]


def test_double_asterisk_emphasis_only(markdown_runtime):
    para = markdown_runtime["parse"]["emphasis"][0]
    assert para["kind"] == "para"
    assert para["inlines"] == [
        {"kind": "text", "text": "这是"},
        {"kind": "em", "text": "重点"},
        {"kind": "text", "text": "内容"},
    ]
    multiline = markdown_runtime["parse"]["emphasis_newline"][0]
    assert multiline["inlines"] == [{"kind": "em", "text": "第一\n第二"}]
    plain = markdown_runtime["parse"]["single_star_snake"][0]
    assert plain["inlines"] == [
        {"kind": "text", "text": "2 * 3 = 6，snake_case 与 __dunder__"}
    ]
    link = markdown_runtime["parse"]["not_link"][0]
    assert link["inlines"] == [{"kind": "text", "text": "[t](u) <span>x</span>"}]


def test_inline_code(markdown_runtime):
    para = markdown_runtime["parse"]["inline_code"][0]
    assert para["inlines"] == [
        {"kind": "text", "text": "用 "},
        {"kind": "code", "text": "code"},
        {"kind": "text", "text": " 结束"},
    ]
    coded = markdown_runtime["parse"]["code_is_not_emphasis"][0]
    assert coded["inlines"] == [{"kind": "code", "text": "**x**"}]
    no_newline = markdown_runtime["parse"]["inline_code_no_newline"][0]
    assert no_newline["inlines"] == [{"kind": "text", "text": "`第一\n第二`"}]


def test_typing_drops_only_the_last_unpaired_delimiter(markdown_runtime):
    typed = markdown_runtime["parse"]["typing_unpaired"]
    assert typed == [{"kind": "para", "inlines": [{"kind": "text", "text": "正在强调"}]}]
    untyped = markdown_runtime["parse"]["not_typing_unpaired"]
    assert untyped == [{"kind": "para", "inlines": [{"kind": "text", "text": "正在**强调"}]}]
    paired = markdown_runtime["parse"]["typing_paired"]
    assert paired == [
        {
            "kind": "para",
            "inlines": [{"kind": "text", "text": "完成"}, {"kind": "em", "text": "重点"}],
        }
    ]
    backtick = markdown_runtime["parse"]["typing_backtick"]
    assert backtick == [{"kind": "para", "inlines": [{"kind": "text", "text": "看 代码"}]}]


def test_empty_text_returns_no_blocks(markdown_runtime):
    assert markdown_runtime["parse"]["empty"] == []


def test_paragraph_keeps_line_breaks(markdown_runtime):
    para = markdown_runtime["parse"]["paragraph_newlines"][0]
    assert para == {"kind": "para", "inlines": [{"kind": "text", "text": "第一行\n第二行"}]}


def test_crlf_is_normalized(markdown_runtime):
    blocks = markdown_runtime["parse"]["crlf"]
    assert [block["kind"] for block in blocks] == ["heading", "list"]
    assert plain_text(blocks[0]["inlines"]) == "标题"
    assert [plain_text(item["inlines"]) for item in blocks[1]["items"]] == ["一", "二"]


def test_parser_never_raises_and_keeps_literal_markers(markdown_runtime):
    assert markdown_runtime["parse"]["unpaired_stars"] == [
        {"kind": "para", "inlines": [{"kind": "text", "text": "**"}]}
    ]
    assert markdown_runtime["parse"]["unpaired_backtick"] == [
        {"kind": "para", "inlines": [{"kind": "text", "text": "`"}]}
    ]
    assert markdown_runtime["parse"]["lone_fence"] == [{"kind": "code", "text": ""}]
    assert markdown_runtime["parse"]["seven_hashes"] == [
        {"kind": "para", "inlines": [{"kind": "text", "text": "#######"}]}
    ]
    assert markdown_runtime["parse"]["empty_quote"] == [{"kind": "quote", "inlines": []}]


def test_strip_message_markdown(markdown_runtime):
    stripped = markdown_runtime["strip"]
    assert stripped["mixed"] == "标题\n\n· 第一\n· 第二\n\n引用\n\n重点 与 code\n\nblock"
    assert stripped["ordered"] == "2. 第二\n3. 第三"
    assert stripped["rule_removed"] == "前\n\n后"
    assert stripped["nested"] == "· 一\n· 二"


def test_message_text_source_is_safe_and_uses_parser():
    source = MESSAGE_TEXT.read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in source
    assert not re.search(r"<a(?:\s|>)", source)
    assert not re.search(r"font-(?:semibold|bold|extrabold|black)", source)
    assert "<strong" not in source
    assert not re.search(r"<b(?:\s|>)", source)
    assert "parseMessageMarkdown(text, { typing })" in source
    assert source.count("md-block") >= 6
    assert "<h3" in source and "<h4" in source and "<h5" in source
    assert "<blockquote" in source and "<pre" in source and "<hr" in source
    assert "whitespace-pre-wrap" in source
    assert "font-mono" in source
    assert "text-[color:var(--amber-ink)]" in source
    assert "animate-[blink_1.4s_infinite]" in source
    assert 'aria-hidden="true"' in source
    assert "text-emphasis:filled_dot_var(--ink2)" in source


def test_parser_source_matches_exported_contract():
    source = PARSER.read_text(encoding="utf-8")
    assert "export type MdInline" in source
    assert "export type MdListItem" in source
    assert "export type MdBlock" in source
    assert re.search(
        r"export function parseMessageMarkdown\(\s*text: string,\s*options\?: \{ typing\?: boolean \},?\s*\): MdBlock\[\]",
        source,
    )
    assert re.search(r"export function stripMessageMarkdown\(text: string\): string", source)
    assert "dangerouslySetInnerHTML" not in source
    assert not re.search(r"from\s+[\"']react", source)
    assert "document." not in source and "window." not in source


def test_chat_bubble_ai_branch_uses_message_text():
    source = CHAT_BUBBLE.read_text(encoding="utf-8")
    assert 'import MessageText from "@/components/MessageText";' in source
    assert re.search(r"isUser\s*\?\s*message\.content\s*:\s*<MessageText", source)
