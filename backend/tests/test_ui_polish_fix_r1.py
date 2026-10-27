"""R1 regression checks for Markdown search highlighting and safe behavior."""

import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
MESSAGE_TEXT = FRONTEND / "components/MessageText.tsx"
PARSER = FRONTEND / "lib/messageMarkdown.ts"
HISTORY = FRONTEND / "app/history/page.tsx"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("R1 frontend tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


NODE_RUNNER = r"""
const fs = require('fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function compile(source, jsx) {
  return ts.transpileModule(source, {
    compilerOptions: {
      jsx,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2019,
      esModuleInterop: true,
    },
  }).outputText;
}

const parserModule = { exports: {} };
new Function('exports', 'module', compile(fs.readFileSync(process.argv[1], 'utf8')))(
  parserModule.exports, parserModule,
);
const parser = parserModule.exports;

const messageModule = { exports: {} };
const messageRequire = id => {
  if (id === 'react') return React;
  if (id === '@/lib/messageMarkdown') return parser;
  throw new Error('Unexpected import: ' + id);
};
new Function('React', 'exports', 'module', 'require', compile(
  fs.readFileSync(process.argv[2], 'utf8'), ts.JsxEmit.React,
))(React, messageModule.exports, messageModule, messageRequire);
const MessageText = messageModule.exports.default;

function render(props) {
  return renderToStaticMarkup(React.createElement(MessageText, props));
}

const emphasized = render({text: '简单说：**给我装个插件（Skill/Tool）**', highlight: 'SKILL'});
const markCount = (emphasized.match(/<mark\b/g) || []).length;
if (markCount !== 1) throw new Error('expected exactly one mark: ' + emphasized);
const emOpen = emphasized.indexOf('<em');
const markOpen = emphasized.indexOf('<mark');
const emClose = emphasized.indexOf('</em>');
if (!(emOpen >= 0 && emOpen < markOpen && markOpen < emClose)) {
  throw new Error('mark is not inside em: ' + emphasized);
}

const parenthesis = render({text: '简单说：**给我装个插件（Skill/Tool）**', highlight: '('});
if (!parenthesis.includes('（Skill/Tool）')) {
  throw new Error('escaped parenthesis changed the text: ' + parenthesis);
}

const baselineText = '**A** 和 `B`\n\n```\nC\n```';
const noHighlight = render({text: baselineText});
if (render({text: baselineText, highlight: ''}) !== noHighlight) {
  throw new Error('empty highlight changed the markup');
}
if (render({text: baselineText, highlight: '   '}) !== noHighlight) {
  throw new Error('whitespace-only highlight changed the markup');
}

const code = render({text: '行内 `Skill` 代码\n\n```\nBlock Skill\n```', highlight: 'skill'});
if ((code.match(/<mark\b/g) || []).length !== 2) {
  throw new Error('expected inline and block code highlights: ' + code);
}
if (!/<code\b[^>]*>[\s\S]*?<mark\b[\s\S]*?<\/mark>[\s\S]*?<\/code>/.test(code)) {
  throw new Error('inline code was not highlighted: ' + code);
}
if (!/<pre\b[^>]*>[\s\S]*?<mark\b[\s\S]*?<\/mark>[\s\S]*?<\/pre>/.test(code)) {
  throw new Error('fenced code was not highlighted: ' + code);
}

process.stdout.write(JSON.stringify({
  markCount,
  emContainsMark: true,
  parenthesisSafe: true,
  emptyMatchesAbsent: true,
  codeHighlights: 2,
}));
"""


def require_node_runtime():
    if shutil.which("node") is None:
        pytest.skip("Node.js is unavailable; the history/source assertion still runs")
    probe = r"""
const packages = ['typescript', 'react', 'react-dom/server'];
const missing = packages.filter(name => {
  try {
    require.resolve(name, {paths: [process.argv[1]]});
    return false;
  } catch {
    return true;
  }
});
process.stdout.write(JSON.stringify(missing));
"""
    try:
        result = subprocess.run(
            ["node", "-e", probe, str(FRONTEND)],
            capture_output=True, text=True, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("Node/TypeScript/React SSR is unavailable; the source assertion still runs")
    try:
        missing = json.loads(result.stdout)
    except ValueError:
        pytest.skip("Node dependency probe failed; the source assertion still runs")
    if missing:
        pytest.skip("Frontend SSR dependencies unavailable: " + ", ".join(missing))


def test_message_text_highlights_em_code_and_fenced_code():
    require_node_runtime()
    completed = subprocess.run(
        ["node", "-e", NODE_RUNNER, str(PARSER), str(MESSAGE_TEXT)],
        cwd=FRONTEND, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result == {
        "markCount": 1,
        "emContainsMark": True,
        "parenthesisSafe": True,
        "emptyMatchesAbsent": True,
        "codeHighlights": 2,
    }


def test_history_passes_query_to_message_text():
    source = HISTORY.read_text(encoding="utf-8")
    assert "<MessageText text={msg.content} highlight={query} />" in source
