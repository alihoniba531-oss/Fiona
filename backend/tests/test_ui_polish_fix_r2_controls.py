"""Offline contracts for the R2 image-menu details and screen-reader voice clicks."""

import json
import re
import socket
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
MENU = FRONTEND / "components/ComposerImageMenu.tsx"
VOICE = FRONTEND / "components/VoiceButton.tsx"

ENABLED_ITEM_TITLE = "选择 PNG、JPEG 或 WebP；每张不超过5MB，发送修改要求时才上传"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("UI polish R2 control tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def test_image_menu_disabled_effect_resets_open():
    source = MENU.read_text()
    effects = re.findall(
        r"useEffect\(\(\) => \{\n(.*?)\n  \}, \[([^\]]*)\]\);",
        source,
        re.DOTALL,
    )
    matching = [
        body for body, dependencies in effects
        if "setOpen(false)" in body and dependencies.strip() == "triggerDisabled"
    ]
    assert matching, "setOpen(false) must run in a useEffect that depends on triggerDisabled"
    body = " ".join(matching[0].split())
    assert body.startswith("if (!triggerDisabled) return;")
    assert "setOpen(false);" in body


def test_image_menu_escape_stops_propagation():
    source = MENU.read_text()
    start = source.index('if (event.key === "Escape")')
    body = source[start:source.index("\n    }", start)]
    assert "event.preventDefault();" in body
    assert "event.stopPropagation();" in body
    assert "setOpen(false);" in body
    assert "triggerRef.current?.focus();" in body


def test_image_menu_handle_select_selects_then_returns_focus():
    source = MENU.read_text()
    start = source.index("const handleSelect")
    body = source[start:source.index("\n\n  return (", start)]
    assert "setTimeout" not in body
    assert "requestAnimationFrame" not in body
    assert body.index("setOpen(false);") < body.index("item.onSelect();")
    assert body.index("item.onSelect();") < body.index("triggerRef.current?.focus();")


def test_image_menu_items_always_carry_title():
    source = MENU.read_text()
    assert "title={item.title}" in source
    assert "item.disabled ? item.title" not in source


def test_voice_button_pointerup_click_ref_source_contract():
    source = VOICE.read_text()
    assert "const pointerUpHandledRef = useRef(false);" in source
    assert "event.detail" not in source

    up_start = source.index("const handlePointerUp")
    up_body = source[up_start:source.index("\n  };", up_start)]
    assert "if (wasLongPress) onHoldEnd();\n    else handleTap();" in up_body
    assert up_body.index("else handleTap();") < up_body.index("pointerUpHandledRef.current = true;")

    click_start = source.index("const handleClick = () => {")
    click_body = source[click_start:source.index("\n  };", click_start)]
    guard = click_body.index("if (pointerUpHandledRef.current) {")
    reset = click_body.index("pointerUpHandledRef.current = false;", guard)
    assert reset > guard
    assert click_body.index("handleTap();", reset) > reset

    for handler in ("const handlePointerCancel", "const handleLostPointerCapture"):
        start = source.index(handler)
        body = source[start:source.index("\n  };", start)]
        assert "pointerUpHandledRef.current = false;" in body, handler


def require_rendering_dependencies():
    probe = """
const packages = ['typescript', 'react', 'react-dom/server', 'lucide-react'];
const missing = packages.filter(name => {
  try { require.resolve(name, {paths: [process.argv[1]]}); return false; }
  catch { return true; }
});
process.stdout.write(JSON.stringify(missing));
"""
    try:
        result = subprocess.run(
            ["node", "-e", probe, str(FRONTEND)],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        pytest.skip("R2 composer control checks need Node.js; source contracts still run")
    missing = json.loads(result.stdout) if result.stdout else []
    if missing:
        pytest.skip("R2 composer control dependencies unavailable: " + ", ".join(missing))


def run_node(script, *args):
    try:
        result = subprocess.run(
            ["node", "-e", script, *args],
            cwd=FRONTEND, capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        pytest.skip("R2 composer control checks need Node.js; source contracts still run")
    except subprocess.CalledProcessError as error:
        pytest.fail(f"Node harness failed:\n{error.stdout}\n{error.stderr}")
    return result.stdout


OPEN_MENU_RUNNER = r"""
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');
const ts = require('typescript');
const realReact = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const localRequire = createRequire(path.join(process.cwd(), 'index.js'));
const fakeReact = {
  ...realReact,
  useState: () => [true, () => {}],
  useRef: initial => ({ current: initial }),
  useEffect: () => {},
};

function loadComponent(filename) {
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
  const factory = new Function('React', 'exports', 'require', 'module', compiled);
  factory(fakeReact, module.exports, requireShim, module);
  return module.exports.default;
}

const Component = loadComponent(process.argv[1]);
const noop = () => {};
const element = Component({
  items: [
    {
      key: 'see',
      label: '发图给 Chloe 看',
      description: 'Chloe 看图后回答',
      disabled: false,
      title: process.argv[2],
      onSelect: noop,
    },
    {
      key: 'generate',
      label: '生成图片',
      description: '用文字描述画一张新图',
      disabled: false,
      onSelect: noop,
    },
    {
      key: 'edit',
      label: '改一张图',
      description: '上传 1–3 张参考图，再说明怎么改',
      disabled: true,
      onSelect: noop,
    },
  ],
  disabled: false,
  active: false,
});
process.stdout.write(renderToStaticMarkup(element));
"""


def test_open_image_menu_shows_title_on_enabled_item():
    require_rendering_dependencies()
    html = run_node(OPEN_MENU_RUNNER, str(MENU), ENABLED_ITEM_TITLE)
    assert 'role="menu"' in html
    assert 'role="menuitem"' in html
    assert html.count(f'title="{ENABLED_ITEM_TITLE}"') == 1
    title_at = html.index(f'title="{ENABLED_ITEM_TITLE}"')
    tag_start = html.rindex("<button", 0, title_at)
    tag_end = html.index(">", title_at)
    opening_tag = html[tag_start:tag_end]
    assert not re.search(r' disabled(?:=""|>)', opening_tag)
    item_end = html.index("</button>", tag_end)
    assert "发图给 Chloe 看" in html[tag_end:item_end]


VOICE_CLICK_RUNNER = r"""
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');
const ts = require('typescript');
const realReact = require('react');

const localRequire = createRequire(path.join(process.cwd(), 'index.js'));
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
  const factory = new Function('React', 'exports', 'require', 'module', compiled);
  factory(fakeReact, module.exports, requireShim, module);
  return module.exports.default;
}

const VoiceButton = loadVoiceButton(process.argv[1]);
const HOLD_DELAY_MS = 20;
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

function pointerEvent(target, overrides = {}) {
  return {
    button: 0,
    pointerId: 7,
    currentTarget: target,
    preventDefault: () => {},
    ...overrides,
  };
}

async function main() {
  const results = {};

  // (a) A pointer short tap followed by the browser's click must tap exactly once.
  const shortTapThenClick = render();
  const shortTarget = pointerTarget();
  shortTapThenClick.button.props.onPointerDown(pointerEvent(shortTarget.target));
  shortTapThenClick.button.props.onPointerUp(pointerEvent(shortTarget.target));
  shortTapThenClick.button.props.onClick({ detail: 1 });
  results.shortTapThenClick = { ...shortTapThenClick.calls };

  // (b) Screen-reader/programmatic click with detail >= 1 and no pointer events.
  const directClick = render();
  directClick.button.props.onClick({ detail: 1 });
  results.directClick = { ...directClick.calls };

  // (c) Keyboard Enter/Space click has detail 0.
  const keyboardClick = render();
  keyboardClick.button.props.onClick({ detail: 0 });
  results.keyboardClick = { ...keyboardClick.calls };

  // (d) Long press, pointerup and the following click: hold callbacks only.
  const longPress = render();
  const longTarget = pointerTarget();
  longPress.button.props.onPointerDown(pointerEvent(longTarget.target));
  await sleep(HOLD_DELAY_MS + 30);
  longPress.button.props.onPointerUp(pointerEvent(longTarget.target));
  longPress.button.props.onClick({ detail: 1 });
  results.longPressThenClick = { ...longPress.calls };

  // Chrome's real order is pointerup -> lostpointercapture -> click; the click
  // from that same pointer operation must still be swallowed exactly once.
  const shortTapThenLostThenClick = render();
  const shortLostTarget = pointerTarget();
  shortTapThenLostThenClick.button.props.onPointerDown(pointerEvent(shortLostTarget.target));
  shortTapThenLostThenClick.button.props.onPointerUp(pointerEvent(shortLostTarget.target));
  shortTapThenLostThenClick.button.props.onLostPointerCapture();
  shortTapThenLostThenClick.button.props.onClick({ detail: 1 });
  results.shortTapThenLostThenClick = { ...shortTapThenLostThenClick.calls };

  const longPressThenLostThenClick = render();
  const longLostTarget = pointerTarget();
  longPressThenLostThenClick.button.props.onPointerDown(pointerEvent(longLostTarget.target));
  await sleep(HOLD_DELAY_MS + 30);
  longPressThenLostThenClick.button.props.onPointerUp(pointerEvent(longLostTarget.target));
  longPressThenLostThenClick.button.props.onLostPointerCapture();
  longPressThenLostThenClick.button.props.onClick({ detail: 1 });
  results.longPressThenLostThenClick = { ...longPressThenLostThenClick.calls };

  // A keyboard click after the pointer click must still tap normally.
  shortTapThenLostThenClick.button.props.onClick({ detail: 0 });
  results.keyboardAfterPointer = { ...shortTapThenLostThenClick.calls };

  process.stdout.write(JSON.stringify(results), () => process.exit(0));
}

main().catch(error => {
  process.stderr.write(String(error && error.stack || error));
  process.exit(1);
});
"""


def test_voice_button_pointer_click_state_machine_runs():
    require_rendering_dependencies()
    result = json.loads(run_node(VOICE_CLICK_RUNNER, str(VOICE)))
    assert result["shortTapThenClick"] == {"tap": 1, "start": 0, "end": 0}
    assert result["directClick"] == {"tap": 1, "start": 0, "end": 0}
    assert result["keyboardClick"] == {"tap": 1, "start": 0, "end": 0}
    assert result["longPressThenClick"] == {"tap": 0, "start": 1, "end": 1}
    assert result["shortTapThenLostThenClick"] == {"tap": 1, "start": 0, "end": 0}
    assert result["longPressThenLostThenClick"] == {"tap": 0, "start": 1, "end": 1}
    assert result["keyboardAfterPointer"] == {"tap": 2, "start": 0, "end": 0}
