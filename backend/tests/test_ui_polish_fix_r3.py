"""R3 checks for plain-text parity and the VoiceButton click-after-pointerup window."""

import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
PARSER = FRONTEND / "lib/messageMarkdown.ts"
VOICE = FRONTEND / "components/VoiceButton.tsx"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("R3 frontend tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


STRIP_RUNNER = r"""
const fs = require('fs');
const ts = require('typescript');
const source = fs.readFileSync(process.argv[1], 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const loaded = { exports: {} };
new Function('exports', 'module', compiled)(loaded.exports, loaded);
const api = loaded.exports;
const special = String.fromCharCode(0xE000);
const privateInput = 'x ' + special + ' y';
process.stdout.write(JSON.stringify({
  paired: api.stripMessageMarkdown('2**10**3'),
  privateInput,
  privateOutput: api.stripMessageMarkdown(privateInput),
  inlineCode: api.stripMessageMarkdown('2**10 和 `x`'),
  emphasis: api.stripMessageMarkdown('**重点**'),
  spaced: api.stripMessageMarkdown('a ** b'),
}));
"""


def require_node_typescript():
    if shutil.which("node") is None:
        pytest.skip("Node.js is unavailable; source-only R3 assertions still run")
    probe = """
const packages = ['typescript'];
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
            capture_output=True, text=True, check=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pytest.skip("Node.js/TypeScript is unavailable; source-only R3 assertions still run")
    if json.loads(result.stdout):
        pytest.skip("TypeScript is unavailable in frontend/node_modules")


def require_voice_runtime():
    if shutil.which("node") is None:
        pytest.skip("Node.js is unavailable; source-only R3 assertions still run")
    probe = """
const packages = ['typescript', 'react'];
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
            capture_output=True, text=True, check=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pytest.skip("Node/TypeScript/React is unavailable; source-only R3 assertions still run")
    if json.loads(result.stdout):
        pytest.skip("VoiceButton runtime dependencies unavailable: " + ", ".join(json.loads(result.stdout)))


def test_strip_message_markdown_matches_rendered_text_and_preserves_private_use():
    require_node_typescript()
    completed = subprocess.run(
        ["node", "-e", STRIP_RUNNER, str(PARSER)],
        cwd=FRONTEND, capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["paired"] == "2103"
    assert result["privateOutput"] == result["privateInput"]
    assert result["inlineCode"] == "2**10 和 x"
    assert result["emphasis"] == "重点"
    assert result["spaced"] == "a ** b"


def test_parser_has_no_private_use_placeholder():
    source = PARSER.read_text(encoding="utf-8")
    assert "LITERAL_DOUBLE_STAR" not in source
    assert chr(0xE000).encode("utf-8") not in PARSER.read_bytes()


VOICE_RUNNER = r"""
const fs = require('fs');
const { createRequire } = require('module');
const ts = require('typescript');
const realReact = require('react');

const localRequire = createRequire(process.argv[1]);
const fakeReact = {
  ...realReact,
  useState: initial => [initial, () => {}],
  useRef: initial => ({ current: initial }),
  useEffect: () => {},
};

function loadVoiceButton(filename) {
  let source = fs.readFileSync(filename, 'utf8');
  source = source.replace(
    'import { cn } from "@/lib/utils";',
    'const cn = (...values) => values.filter(Boolean).join(" ");',
  );
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      jsx: ts.JsxEmit.React,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2019,
      esModuleInterop: true,
    },
  }).outputText;
  const module = { exports: {} };
  const requireShim = name => name === 'react' ? fakeReact : localRequire(name);
  new Function('React', 'exports', 'module', 'require', compiled)(
    realReact, module.exports, module, requireShim,
  );
  return module.exports.default;
}

const VoiceButton = loadVoiceButton(process.argv[1]);
const HOLD_DELAY_MS = 20;
const CLICK_WAIT_MS = 650;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

function memoryStorage() {
  const store = new Map();
  return {
    getItem: key => store.has(key) ? store.get(key) : null,
    setItem: (key, value) => store.set(key, String(value)),
  };
}

function render() {
  global.localStorage = memoryStorage();
  const calls = { tap: 0, start: 0, end: 0 };
  const element = VoiceButton({
    disabled: false,
    dictating: false,
    holding: false,
    holdDelayMs: HOLD_DELAY_MS,
    onTap: () => { calls.tap += 1; },
    onHoldStart: () => { calls.start += 1; },
    onHoldEnd: () => { calls.end += 1; },
  });
  const button = element.props.children.find(
    child => realReact.isValidElement(child) && child.type === 'button',
  );
  return { button, calls };
}

function pointerTarget() {
  let captured = false;
  return {
    target: {
      setPointerCapture: () => { captured = true; },
      hasPointerCapture: () => captured,
      releasePointerCapture: () => { captured = false; },
    },
  };
}

function pointerEvent(target) {
  return {
    button: 0,
    pointerId: 7,
    currentTarget: target,
    preventDefault: () => {},
  };
}

async function longPressThenLost(waitAfterLost) {
  const pressed = render();
  const target = pointerTarget();
  pressed.button.props.onPointerDown(pointerEvent(target.target));
  await sleep(HOLD_DELAY_MS + 30);
  pressed.button.props.onPointerUp(pointerEvent(target.target));
  pressed.button.props.onLostPointerCapture();
  await sleep(waitAfterLost);
  return pressed;
}

async function main() {
  const results = {};

  const afterLongKeyboard = await longPressThenLost(CLICK_WAIT_MS);
  afterLongKeyboard.button.props.onClick({ detail: 0 });
  results.afterLongKeyboard = { ...afterLongKeyboard.calls };

  const afterLongReader = await longPressThenLost(CLICK_WAIT_MS);
  afterLongReader.button.props.onClick({ detail: 1 });
  results.afterLongReader = { ...afterLongReader.calls };

  const immediateShort = render();
  const shortTarget = pointerTarget();
  immediateShort.button.props.onPointerDown(pointerEvent(shortTarget.target));
  immediateShort.button.props.onPointerUp(pointerEvent(shortTarget.target));
  immediateShort.button.props.onClick({ detail: 1 });
  results.immediateShort = { ...immediateShort.calls };

  const immediateLong = await longPressThenLost(0);
  immediateLong.button.props.onClick({ detail: 1 });
  results.immediateLong = { ...immediateLong.calls };

  const staleShort = render();
  const staleTarget = pointerTarget();
  staleShort.button.props.onPointerDown(pointerEvent(staleTarget.target));
  staleShort.button.props.onPointerUp(pointerEvent(staleTarget.target));
  await sleep(CLICK_WAIT_MS);
  staleShort.button.props.onClick({ detail: 1 });
  results.staleShort = { ...staleShort.calls };

  process.stdout.write(JSON.stringify(results), () => process.exit(0));
}

main().catch(error => {
  process.stderr.write(String(error && error.stack || error));
  process.exit(1);
});
"""


def test_voice_click_after_pointerup_is_time_limited():
    require_voice_runtime()
    completed = subprocess.run(
        ["node", "-e", VOICE_RUNNER, str(VOICE)],
        cwd=FRONTEND, capture_output=True, text=True, timeout=120,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    result = json.loads(completed.stdout)
    assert result["afterLongKeyboard"] == {"tap": 1, "start": 1, "end": 1}
    assert result["afterLongReader"] == {"tap": 1, "start": 1, "end": 1}
    assert result["immediateShort"] == {"tap": 1, "start": 0, "end": 0}
    assert result["immediateLong"] == {"tap": 0, "start": 1, "end": 1}
    assert result["staleShort"] == {"tap": 2, "start": 0, "end": 0}


def test_voice_click_window_source_contract():
    source = VOICE.read_text(encoding="utf-8")
    assert "const CLICK_AFTER_POINTERUP_MS = 500;" in source
    start = source.index("const handleClick = () => {")
    body = source[start:source.index("\n  };", start)]
    assert "if (pointerUpHandledRef.current) {" in body
    assert "performance.now()" in body
    assert "CLICK_AFTER_POINTERUP_MS" in body
    assert "event.detail" not in body
