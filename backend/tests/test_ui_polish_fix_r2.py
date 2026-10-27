"""R2 regression checks for typing delimiters, linear headings and literal asterisks."""

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

TYPING_CASES = {
    "multi_para": "2**3 是幂\n\n正在**强",
    "multi_item_list": "- 2**10\n- 正在**强",
    "before_code": "正在**强\n\n```\ncode",
    "backtick_before_para": "看 `代码\n\n下一段",
    "single_emphasis": "正在**强调",
    "single_backtick": "看 `代码",
    "single_paired": "完成**重点**",
    "heading_last": "前文**保留\n\n# 正在**强",
    "quote_last": "前文**保留\n\n> 正在**强",
    "rule_last": "正在**强\n\n---",
}

HEADING_CASES = {
    "sharp_c": "# 学习 C#",
    "trailing_hashes": "## 标题 ##",
    "literal_trailing_hash": "# 标题#",
    "no_space": "#标题",
    "empty_content": "# ",
    "only_hashes": "# ###",
}

STRIP_CASES = {
    "unmatched": "2**10",
    "paired": "**重点**",
    "spaced": "a ** b",
    "combined": "2**10 和 `x`",
}

# Fixed typing:false snapshot of PARSE_CASES, captured before the R2 parser change.
EXPECTED_TYPING_FALSE_SNAPSHOT = json.loads(
    r'''{"unordered":[{"kind":"list","ordered":false,"start":1,"items":[{"depth":0,"inlines":[{"kind":"text","text":"苹果"}]},{"depth":0,"inlines":[{"kind":"text","text":"香蕉"}]}]}],"ordered":[{"kind":"list","ordered":true,"start":3,"items":[{"depth":0,"inlines":[{"kind":"text","text":"三"}]},{"depth":0,"inlines":[{"kind":"text","text":"四"}]}]}],"ordered_cn":[{"kind":"list","ordered":true,"start":1,"items":[{"depth":0,"inlines":[{"kind":"text","text":"第一"}]},{"depth":0,"inlines":[{"kind":"text","text":"第二"}]}]}],"decimal_not_list":[{"kind":"para","inlines":[{"kind":"text","text":"1.5 倍"}]}],"depth":[{"kind":"list","ordered":false,"start":1,"items":[{"depth":0,"inlines":[{"kind":"text","text":"一级"}]},{"depth":1,"inlines":[{"kind":"text","text":"二级"}]},{"depth":1,"inlines":[{"kind":"text","text":"另一个二级"}]},{"depth":0,"inlines":[{"kind":"text","text":"回到一级"}]}]}],"list_then_para":[{"kind":"list","ordered":false,"start":1,"items":[{"depth":0,"inlines":[{"kind":"text","text":"项目"}]}]},{"kind":"para","inlines":[{"kind":"text","text":"普通行"}]}],"continuation":[{"kind":"list","ordered":false,"start":1,"items":[{"depth":0,"inlines":[{"kind":"text","text":"第一行\n第二行"}]},{"depth":0,"inlines":[{"kind":"text","text":"下一项"}]}]}],"headings":[{"kind":"heading","level":1,"inlines":[{"kind":"text","text":"一"}]},{"kind":"heading","level":1,"inlines":[{"kind":"text","text":"二"}]},{"kind":"heading","level":2,"inlines":[{"kind":"text","text":"三"}]},{"kind":"heading","level":3,"inlines":[{"kind":"text","text":"四"}]},{"kind":"heading","level":3,"inlines":[{"kind":"text","text":"五"}]},{"kind":"heading","level":3,"inlines":[{"kind":"text","text":"六"}]}],"quote":[{"kind":"quote","inlines":[{"kind":"text","text":"第一行\n第二行"}]},{"kind":"para","inlines":[{"kind":"text","text":"普通"}]}],"fence":[{"kind":"code","text":"const a = 1;\n- 不是列表"}],"fence_unclosed":[{"kind":"code","text":"未闭合\n仍然代码"}],"rule":[{"kind":"rule"},{"kind":"rule"}],"list_then_rule":[{"kind":"list","ordered":false,"start":1,"items":[{"depth":0,"inlines":[{"kind":"text","text":"项目"}]}]},{"kind":"rule"},{"kind":"list","ordered":false,"start":1,"items":[{"depth":0,"inlines":[{"kind":"text","text":"后续"}]}]}],"emphasis":[{"kind":"para","inlines":[{"kind":"text","text":"这是"},{"kind":"em","text":"重点"},{"kind":"text","text":"内容"}]}],"emphasis_newline":[{"kind":"para","inlines":[{"kind":"em","text":"第一\n第二"}]}],"single_star_snake":[{"kind":"para","inlines":[{"kind":"text","text":"2 * 3 = 6，snake_case 与 __dunder__"}]}],"inline_code":[{"kind":"para","inlines":[{"kind":"text","text":"用 "},{"kind":"code","text":"code"},{"kind":"text","text":" 结束"}]}],"inline_code_no_newline":[{"kind":"para","inlines":[{"kind":"text","text":"`第一\n第二`"}]}],"not_link":[{"kind":"para","inlines":[{"kind":"text","text":"[t](u) <span>x</span>"}]}],"typing_unpaired":[{"kind":"para","inlines":[{"kind":"text","text":"正在**强调"}]}],"not_typing_unpaired":[{"kind":"para","inlines":[{"kind":"text","text":"正在**强调"}]}],"typing_paired":[{"kind":"para","inlines":[{"kind":"text","text":"完成"},{"kind":"em","text":"重点"}]}],"typing_backtick":[{"kind":"para","inlines":[{"kind":"text","text":"看 `代码"}]}],"code_is_not_emphasis":[{"kind":"para","inlines":[{"kind":"code","text":"**x**"}]}],"empty":[],"paragraph_newlines":[{"kind":"para","inlines":[{"kind":"text","text":"第一行\n第二行"}]}],"crlf":[{"kind":"heading","level":1,"inlines":[{"kind":"text","text":"标题"}]},{"kind":"list","ordered":false,"start":1,"items":[{"depth":0,"inlines":[{"kind":"text","text":"一"}]},{"depth":0,"inlines":[{"kind":"text","text":"二"}]}]}],"unpaired_stars":[{"kind":"para","inlines":[{"kind":"text","text":"**"}]}],"unpaired_backtick":[{"kind":"para","inlines":[{"kind":"text","text":"`"}]}],"lone_fence":[{"kind":"code","text":""}],"seven_hashes":[{"kind":"para","inlines":[{"kind":"text","text":"#######"}]}],"empty_quote":[{"kind":"quote","inlines":[]}]}'''
)


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("R2 frontend tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


NODE_RUNNER = r"""
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
  if (item.op === 'strip') return api.stripMessageMarkdown(item.text);
  if (item.op === 'timing') {
    const started = Date.now();
    const blocks = api.parseMessageMarkdown(item.text, item.options || {});
    return { ms: Date.now() - started, blocks };
  }
  return api.parseMessageMarkdown(item.text, item.options || {});
});
process.stdout.write(JSON.stringify(results));
"""


def require_node_typescript():
    if shutil.which("node") is None:
        pytest.skip("Node.js is unavailable; source-only R2 assertions still run")
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
        pytest.skip("Node.js/TypeScript is unavailable; source-only R2 assertions still run")
    if json.loads(result.stdout):
        pytest.skip("Frontend dependencies unavailable: typescript")


def run_parser(requests):
    completed = subprocess.run(
        ["node", "-e", NODE_RUNNER, str(PARSER), json.dumps(requests, ensure_ascii=False)],
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
    keys = []
    requests = []
    for name in PARSE_CASES:
        keys.append(("snapshot", name))
        requests.append({"op": "parse", "text": PARSE_CASES[name]["text"], "options": {"typing": False}})
    for name, text in TYPING_CASES.items():
        keys.append(("typing", name))
        requests.append({"op": "parse", "text": text, "options": {"typing": True}})
    for name, text in HEADING_CASES.items():
        keys.append(("heading", name))
        requests.append({"op": "parse", "text": text})
    keys.append(("timing", "long_heading"))
    requests.append({"op": "timing", "text": "# a" + " " * 5000 + "b"})
    for name, text in STRIP_CASES.items():
        keys.append(("strip", name))
        requests.append({"op": "strip", "text": text})
    results = run_parser(requests)
    return dict(zip(keys, results))


def plain_text(inlines):
    return "".join(inline["text"] for inline in inlines)


def test_typing_drops_only_the_very_last_unpaired_marker(markdown_runtime):
    blocks = markdown_runtime[("typing", "multi_para")]
    assert blocks == [
        {"kind": "para", "inlines": [{"kind": "text", "text": "2**3 是幂"}]},
        {"kind": "para", "inlines": [{"kind": "text", "text": "正在强"}]},
    ]


def test_typing_only_changes_the_last_list_item(markdown_runtime):
    blocks = markdown_runtime[("typing", "multi_item_list")]
    assert len(blocks) == 1
    assert blocks[0]["kind"] == "list"
    assert [plain_text(item["inlines"]) for item in blocks[0]["items"]] == [
        "2**10",
        "正在强",
    ]
    assert blocks[0]["items"][0]["inlines"] == [{"kind": "text", "text": "2**10"}]


def test_typing_keeps_marker_before_unclosed_code(markdown_runtime):
    blocks = markdown_runtime[("typing", "before_code")]
    assert blocks == [
        {"kind": "para", "inlines": [{"kind": "text", "text": "正在**强"}]},
        {"kind": "code", "text": "code"},
    ]


def test_typing_keeps_backtick_before_later_paragraph(markdown_runtime):
    blocks = markdown_runtime[("typing", "backtick_before_para")]
    assert plain_text(blocks[0]["inlines"]) == "看 `代码"
    assert plain_text(blocks[1]["inlines"]) == "下一段"


def test_typing_single_block_results_are_unchanged(markdown_runtime):
    assert markdown_runtime[("typing", "single_emphasis")] == [
        {"kind": "para", "inlines": [{"kind": "text", "text": "正在强调"}]}
    ]
    assert markdown_runtime[("typing", "single_backtick")] == [
        {"kind": "para", "inlines": [{"kind": "text", "text": "看 代码"}]}
    ]
    assert markdown_runtime[("typing", "single_paired")] == [
        {
            "kind": "para",
            "inlines": [
                {"kind": "text", "text": "完成"},
                {"kind": "em", "text": "重点"},
            ],
        }
    ]


def test_typing_recomputes_only_a_trailing_heading(markdown_runtime):
    blocks = markdown_runtime[("typing", "heading_last")]
    assert plain_text(blocks[0]["inlines"]) == "前文**保留"
    assert blocks[1] == {
        "kind": "heading",
        "level": 1,
        "inlines": [{"kind": "text", "text": "正在强"}],
    }


def test_typing_recomputes_only_a_trailing_quote(markdown_runtime):
    blocks = markdown_runtime[("typing", "quote_last")]
    assert plain_text(blocks[0]["inlines"]) == "前文**保留"
    assert blocks[1] == {
        "kind": "quote",
        "inlines": [{"kind": "text", "text": "正在强"}],
    }


def test_typing_keeps_marker_when_a_rule_is_last(markdown_runtime):
    assert markdown_runtime[("typing", "rule_last")] == [
        {"kind": "para", "inlines": [{"kind": "text", "text": "正在**强"}]},
        {"kind": "rule"},
    ]


def test_typing_false_output_matches_fixed_snapshot(markdown_runtime):
    assert set(EXPECTED_TYPING_FALSE_SNAPSHOT) == set(PARSE_CASES)
    for name in PARSE_CASES:
        assert markdown_runtime[("snapshot", name)] == EXPECTED_TYPING_FALSE_SNAPSHOT[name], name


def test_long_heading_line_parses_in_linear_time(markdown_runtime):
    result = markdown_runtime[("timing", "long_heading")]
    assert result["ms"] < 200, f"long heading line took {result['ms']}ms"
    assert result["blocks"] == [
        {
            "kind": "heading",
            "level": 1,
            "inlines": [{"kind": "text", "text": "a" + " " * 5000 + "b"}],
        }
    ]


def test_heading_keeps_literal_trailing_hash(markdown_runtime):
    assert markdown_runtime[("heading", "sharp_c")] == [
        {"kind": "heading", "level": 1, "inlines": [{"kind": "text", "text": "学习 C#"}]}
    ]


def test_heading_strips_only_a_closing_hash_run(markdown_runtime):
    assert markdown_runtime[("heading", "trailing_hashes")] == [
        {"kind": "heading", "level": 1, "inlines": [{"kind": "text", "text": "标题"}]}
    ]
    assert markdown_runtime[("heading", "literal_trailing_hash")] == [
        {"kind": "heading", "level": 1, "inlines": [{"kind": "text", "text": "标题#"}]}
    ]


def test_heading_requires_whitespace_after_hashes(markdown_runtime):
    assert markdown_runtime[("heading", "no_space")] == [
        {"kind": "para", "inlines": [{"kind": "text", "text": "#标题"}]}
    ]


def test_heading_with_empty_cleaned_content_is_still_a_heading(markdown_runtime):
    assert markdown_runtime[("heading", "empty_content")] == [
        {"kind": "heading", "level": 1, "inlines": []}
    ]
    assert markdown_runtime[("heading", "only_hashes")] == [
        {"kind": "heading", "level": 1, "inlines": []}
    ]


def test_strip_keeps_literal_double_asterisks(markdown_runtime):
    assert markdown_runtime[("strip", "unmatched")] == "2**10"
    assert markdown_runtime[("strip", "spaced")] == "a ** b"
    assert markdown_runtime[("strip", "paired")] == "重点"
    # The unpaired `**` stays literal while inline code loses only its markers.
    assert markdown_runtime[("strip", "combined")] == "2**10 和 x"


def test_parse_blocks_has_a_single_typing_recompute_call_site():
    source = PARSER.read_text(encoding="utf-8")
    match = re.search(r"function parseBlocks\(.*?\n\}", source, re.S)
    assert match, "parseBlocks is missing from the parser"
    body = match.group(0)
    assert len(re.findall(r"parseInline\([^)]*,\s*true\)", body)) == 1
    assert len(re.findall(r"parseInline\([^)]*,\s*false\)", body)) >= 3
    assert not re.search(r"parseInline\([^)]*,\s*typing\)", body)
    list_match = re.search(r"function parseList\(.*?\n\}", source, re.S)
    assert list_match, "parseList is missing from the parser"
    assert "parseInline(item.text, false)" in list_match.group(0)


def test_heading_source_uses_linear_regex_and_string_cleanup():
    source = PARSER.read_text(encoding="utf-8")
    heading_lines = [line for line in source.splitlines() if line.startswith("const HEADING_RE")]
    assert len(heading_lines) == 1
    assert r"/^\s{0,3}(#{1,6})[ \t]+(.*)$/" in heading_lines[0]
    assert ".+?" not in heading_lines[0]
    assert r"\s*#" not in heading_lines[0]
    assert "headingContent(" in source


def test_inlines_to_plain_text_is_verbatim_in_source():
    source = PARSER.read_text(encoding="utf-8")
    match = re.search(r"function inlinesToPlainText\(.*?\n\}", source, re.S)
    assert match, "inlinesToPlainText is missing from the parser"
    body = match.group(0)
    assert 'replace(/\\*\\*/g, "")' not in body
    assert "inline.text" in body
