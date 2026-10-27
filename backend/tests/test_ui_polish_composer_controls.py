"""Offline contracts for the unified composer image menu and merged voice button."""

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

BOLD = re.compile(
    r"font-(?:semibold|bold|extrabold|black)"
    r"|font-weight\s*:\s*(?:[6-9]00|[1-9]\d{3})"
    r"|<strong\b|<b[ >]",
    re.IGNORECASE,
)


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("UI polish tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def test_composer_image_menu_source_contract():
    source = MENU.read_text()
    assert 'role="menu"' in source
    assert 'role="menuitem"' in source
    assert 'aria-haspopup="menu"' in source
    assert "aria-expanded={isOpen}" in source
    assert 'aria-label="图片：发图给 Chloe 看、生成图片或改一张图"' in source
    assert source.count("<ImagePlus") == 1
    assert "<span>图片</span>" in source
    assert "btn btn-quiet h-8 px-2 text-xs max-md:h-10" in source
    assert "active && \"text-[color:var(--ink)]\"" in source
    assert "const allDisabled = items.every((item) => item.disabled);" in source
    assert "const triggerDisabled = disabled || allDisabled;" in source
    assert "disabled={triggerDisabled}" in source
    assert "absolute bottom-full left-0 z-[60] mb-2" in source
    assert "w-[min(280px,calc(100vw-32px))]" in source
    assert "ceramic-card absolute" in source
    assert "p-1.5" in source
    assert 'backdropFilter: "var(--bd)"' in source
    assert 'WebkitBackdropFilter: "var(--bd)"' in source
    assert "min-h-11 w-full rounded-[8px] px-3 py-2 text-left" in source
    assert "hover:bg-[color:var(--fill)]" in source
    assert "disabled:opacity-45 disabled:cursor-not-allowed" in source
    assert "text-sm text-[color:var(--ink)]" in source
    assert "text-xs text-[color:var(--ink2)]" in source
    assert "disabled={item.disabled}" in source
    assert "title={item.title}" in source


def test_composer_image_menu_interaction_source_contract():
    source = MENU.read_text()
    assert '"Escape"' in source
    assert '"ArrowDown"' in source
    assert '"ArrowUp"' in source
    assert '"Tab"' in source
    assert "event.preventDefault();" in source
    assert "triggerRef.current?.focus();" in source
    assert "const firstEnabledIndex = items.findIndex((item) => !item.disabled);" in source
    assert "itemRefs.current[firstEnabledIndex]?.focus();" in source
    assert "const enabledItems = itemRefs.current.filter((item): item is HTMLButtonElement => !!item && !item.disabled);" in source
    assert "(currentIndex + step + enabledItems.length) % enabledItems.length" in source
    assert 'document.addEventListener("pointerdown", handlePointerDown);' in source
    assert 'document.removeEventListener("pointerdown", handlePointerDown);' in source
    assert "rootRef.current.contains(event.target as Node)" in source
    assert "setOpen(false);\n    item.onSelect();" in source
    assert "setTimeout" not in source
    assert "requestAnimationFrame" not in source


def test_voice_button_source_contract():
    source = VOICE.read_text()
    assert 'chloe-voice-hint-v1' in source
    assert "localStorage.getItem(HINT_KEY) !== null" in source
    assert 'localStorage.setItem(HINT_KEY, "1");' in source
    assert source.count("try {") == 1 and source.count("} catch {") == 1
    assert "setShowHint(true);" in source
    assert "HINT_DURATION_MS = 4000" in source
    assert 'role="status"' in source
    assert "也可以按住说话，松开就发送" in source
    assert "ceramic-card absolute bottom-full" in source
    assert "btn btn-quiet h-8 px-2.5 text-xs max-md:h-10 max-md:w-10 max-md:px-0 select-none" in source
    assert "text-[color:var(--rec)] bg-[color:var(--rec-soft)]" in source
    assert "语音：轻点开始录音，再点一下发送；按住说话，松开发送" in source
    assert "正在录音，轻点发送" in source
    assert "正在录音，松开发送" in source
    assert '"语音"' in source and '"点此发送"' in source and '"松开发送"' in source
    assert "<span className=\"max-md:hidden\">{shortLabel}</span>" in source
    assert 'aria-label={stateLabel}' in source
    assert "title={stateLabel}" in source
    assert "disabled={disabled}" in source
    assert 'onContextMenu={handleContextMenu}' in source
    assert "event.preventDefault();" in source
    assert "if (pointerUpHandledRef.current) {" in source
    assert "pointerUpHandledRef.current = false;" in source


def test_voice_button_pointer_state_machine_source_contract():
    source = VOICE.read_text()
    assert "if (disabled || event.button !== 0) return;" in source
    assert "event.currentTarget.setPointerCapture(event.pointerId);" in source
    assert "if (dictating) return;" in source
    assert "holdTimerRef.current = setTimeout(() => {" in source
    assert "longPressRef.current = true;" in source
    assert "onHoldStart();" in source
    assert "const wasLongPress = longPressRef.current;" in source
    assert "if (wasLongPress) onHoldEnd();\n    else handleTap();" in source
    assert "event.currentTarget.releasePointerCapture(event.pointerId);" in source
    assert "onPointerDown={handlePointerDown}" in source
    assert "onPointerUp={handlePointerUp}" in source
    assert "onPointerCancel={handlePointerCancel}" in source
    assert "onLostPointerCapture={handleLostPointerCapture}" in source
    assert "onClick={handleClick}" in source
    assert "onHoldEnd();" in source
    assert source.count("onHoldEnd();") == 3
    assert "if (holdTimerRef.current !== null) clearTimeout(holdTimerRef.current);" in source
    assert "if (hintTimerRef.current !== null) clearTimeout(hintTimerRef.current);" in source


def test_new_composer_controls_have_no_bold_or_html_injection():
    for source in (MENU.read_text(), VOICE.read_text()):
        assert not BOLD.search(source), f"bold UI text in {source}"
        assert "dangerouslySetInnerHTML" not in source
        assert "<strong" not in source and "<b " not in source and "<b>" not in source
        imports = set(re.findall(r'^import .* from "([^"]+)";$', source, re.MULTILINE))
        assert imports <= {"react", "lucide-react", "@/lib/utils"}


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
        pytest.skip("Composer control SSR needs Node.js; source contracts still run")
    missing = json.loads(result.stdout) if result.stdout else []
    if missing:
        pytest.skip("Composer control SSR dependencies unavailable: " + ", ".join(missing))


def run_node(script, *args):
    try:
        result = subprocess.run(
            ["node", "-e", script, *args],
            cwd=FRONTEND, capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        pytest.skip("Composer control checks need Node.js; source contracts still run")
    except subprocess.CalledProcessError as error:
        pytest.fail(f"Node harness failed:\n{error.stdout}\n{error.stderr}")
    return result.stdout


MENU_SSR_RUNNER = r"""
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const localRequire = createRequire(path.join(process.cwd(), 'index.js'));

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
  const factory = new Function('React', 'exports', 'require', 'module', compiled);
  factory(React, module.exports, localRequire, module);
  return module.exports.default;
}

const Component = loadComponent(process.argv[1]);
const props = JSON.parse(process.argv[2]);
const noop = () => {};
process.stdout.write(renderToStaticMarkup(React.createElement(Component, {
  ...props,
  onSelect: noop,
  onTap: noop,
  onHoldStart: noop,
  onHoldEnd: noop,
})));
"""


def render_control(path, props):
    require_rendering_dependencies()
    return run_node(MENU_SSR_RUNNER, str(path), json.dumps(props))


def test_image_menu_ssr_trigger_state():
    html = render_control(MENU, {
        "disabled": False,
        "active": False,
        "items": [
            {"key": "see", "label": "发图给 Chloe 看", "description": "Chloe 看图后回答", "disabled": False},
            {"key": "generate", "label": "生成图片", "description": "用文字描述画一张新图", "disabled": False},
            {"key": "edit", "label": "改一张图", "description": "上传 1–3 张参考图，再说明怎么改", "disabled": True, "title": "先移除待发送图片"},
        ],
    })
    assert 'aria-haspopup="menu"' in html
    assert 'aria-expanded="false"' in html
    assert 'aria-label="图片：发图给 Chloe 看、生成图片或改一张图"' in html
    assert ">图片</span>" in html
    assert 'class="btn btn-quiet h-8 px-2 text-xs max-md:h-10"' in html
    assert 'role="menu"' not in html
    assert "用文字描述画一张新图" not in html
    assert "Chloe 看图后回答" not in html

    active = render_control(MENU, {"disabled": False, "active": True, "items": []})
    assert "text-[color:var(--ink)]" in active

    disabled = render_control(MENU, {"disabled": True, "active": False, "items": []})
    assert re.search(r'<button[^>]*disabled=""', disabled)
    all_disabled = render_control(MENU, {"disabled": False, "active": False, "items": [
        {"key": "see", "label": "发图给 Chloe 看", "description": "Chloe 看图后回答", "disabled": True},
    ]})
    assert re.search(r'<button[^>]*disabled=""', all_disabled)


def test_voice_button_ssr_states():
    idle = render_control(VOICE, {"disabled": False, "dictating": False, "holding": False})
    assert 'aria-label="语音：轻点开始录音，再点一下发送；按住说话，松开发送"' in idle
    assert 'title="语音：轻点开始录音，再点一下发送；按住说话，松开发送"' in idle
    assert ">语音</span>" in idle
    assert ">点此发送</span>" not in idle
    assert ">松开发送</span>" not in idle
    assert "text-[color:var(--rec)]" not in idle

    dictating = render_control(VOICE, {"disabled": False, "dictating": True, "holding": False})
    assert 'aria-label="正在录音，轻点发送"' in dictating
    assert ">点此发送</span>" in dictating
    assert "text-[color:var(--rec)] bg-[color:var(--rec-soft)]" in dictating

    holding = render_control(VOICE, {"disabled": False, "dictating": False, "holding": True})
    assert 'aria-label="正在录音，松开发送"' in holding
    assert ">松开发送</span>" in holding
    assert "text-[color:var(--rec)] bg-[color:var(--rec-soft)]" in holding


VOICE_STATE_RUNNER = r"""
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

function render(overrides, storage) {
  global.localStorage = storage;
  const calls = { tap: 0, start: 0, end: 0 };
  const element = VoiceButton({
    disabled: false,
    dictating: false,
    holding: false,
    holdDelayMs: HOLD_DELAY_MS,
    onTap: () => { calls.tap += 1; },
    onHoldStart: () => { calls.start += 1; },
    onHoldEnd: () => { calls.end += 1; },
    ...overrides,
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
    captured: () => captured,
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

  const shortTap = render({}, memoryStorage());
  const shortTarget = pointerTarget();
  shortTap.button.props.onPointerDown(pointerEvent(shortTarget.target));
  const capturedDuringShortTap = shortTarget.captured();
  shortTap.button.props.onPointerUp(pointerEvent(shortTarget.target));
  results.shortTap = {
    ...shortTap.calls,
    capturedDuringShortTap,
    capturedAfterUp: shortTarget.captured(),
    hint: global.localStorage.getItem('chloe-voice-hint-v1'),
  };

  const longPress = render({}, memoryStorage());
  const longTarget = pointerTarget();
  longPress.button.props.onPointerDown(pointerEvent(longTarget.target));
  const capturedDuringLongPress = longTarget.captured();
  await sleep(HOLD_DELAY_MS + 30);
  longPress.button.props.onPointerUp(pointerEvent(longTarget.target));
  results.longPress = {
    ...longPress.calls,
    capturedDuringLongPress,
    capturedAfterUp: longTarget.captured(),
  };

  const dictating = render({ dictating: true }, memoryStorage());
  const dictatingTarget = pointerTarget();
  dictating.button.props.onPointerDown(pointerEvent(dictatingTarget.target));
  await sleep(HOLD_DELAY_MS + 30);
  dictating.button.props.onPointerUp(pointerEvent(dictatingTarget.target));
  results.dictating = {
    ...dictating.calls,
    hint: global.localStorage.getItem('chloe-voice-hint-v1'),
  };

  const keyboard = render({}, memoryStorage());
  keyboard.button.props.onClick({ detail: 0 });
  keyboard.button.props.onClick({ detail: 1 });
  results.keyboard = {
    ...keyboard.calls,
    hint: global.localStorage.getItem('chloe-voice-hint-v1'),
  };

  const context = render({}, memoryStorage());
  let contextPrevented = false;
  context.button.props.onContextMenu({ preventDefault: () => { contextPrevented = true; } });
  results.contextMenu = { prevented: contextPrevented };

  const cancelledShort = render({}, memoryStorage());
  cancelledShort.button.props.onPointerDown(pointerEvent(pointerTarget().target));
  cancelledShort.button.props.onPointerCancel();
  results.cancelledShort = { ...cancelledShort.calls };

  const lostShort = render({}, memoryStorage());
  lostShort.button.props.onPointerDown(pointerEvent(pointerTarget().target));
  lostShort.button.props.onLostPointerCapture();
  results.lostShort = { ...lostShort.calls };

  const cancelledLong = render({}, memoryStorage());
  cancelledLong.button.props.onPointerDown(pointerEvent(pointerTarget().target));
  await sleep(HOLD_DELAY_MS + 30);
  cancelledLong.button.props.onPointerCancel();
  results.cancelledLong = { ...cancelledLong.calls };

  const lostLong = render({}, memoryStorage());
  lostLong.button.props.onPointerDown(pointerEvent(pointerTarget().target));
  await sleep(HOLD_DELAY_MS + 30);
  lostLong.button.props.onLostPointerCapture();
  results.lostLong = { ...lostLong.calls };

  const disabled = render({ disabled: true }, memoryStorage());
  const disabledTarget = pointerTarget();
  let disabledPrevented = false;
  disabled.button.props.onPointerDown(pointerEvent(disabledTarget.target, {
    preventDefault: () => { disabledPrevented = true; },
  }));
  await sleep(HOLD_DELAY_MS + 30);
  results.disabled = {
    ...disabled.calls,
    captured: disabledTarget.captured(),
    prevented: disabledPrevented,
  };

  // Second tap is not a first-time hint, but it still starts recording.
  const storage = memoryStorage();
  const first = render({}, storage);
  first.button.props.onClick({ detail: 0 });
  const afterFirst = storage.getItem('chloe-voice-hint-v1');
  const second = render({}, storage);
  second.button.props.onClick({ detail: 0 });
  results.hint = {
    afterFirst,
    afterSecond: storage.getItem('chloe-voice-hint-v1'),
    secondTapCount: second.calls.tap,
  };

  process.stdout.write(JSON.stringify(results), () => process.exit(0));
}

main().catch(error => {
  process.stderr.write(String(error && error.stack || error));
  process.exit(1);
});
"""


def test_voice_button_pointer_state_machine_runs():
    require_rendering_dependencies()
    result = json.loads(run_node(VOICE_STATE_RUNNER, str(VOICE)))
    assert result["shortTap"] == {
        "tap": 1, "start": 0, "end": 0,
        "capturedDuringShortTap": True, "capturedAfterUp": False,
        "hint": "1",
    }
    assert result["longPress"] == {
        "tap": 0, "start": 1, "end": 1,
        "capturedDuringLongPress": True, "capturedAfterUp": False,
    }
    assert result["dictating"] == {"tap": 1, "start": 0, "end": 0, "hint": None}
    assert result["keyboard"] == {"tap": 2, "start": 0, "end": 0, "hint": "1"}
    assert result["contextMenu"] == {"prevented": True}
    assert result["cancelledShort"] == {"tap": 0, "start": 0, "end": 0}
    assert result["lostShort"] == {"tap": 0, "start": 0, "end": 0}
    assert result["cancelledLong"] == {"tap": 0, "start": 1, "end": 1}
    assert result["lostLong"] == {"tap": 0, "start": 1, "end": 1}
    assert result["disabled"] == {"tap": 0, "start": 0, "end": 0, "captured": False, "prevented": False}
    assert result["hint"] == {"afterFirst": "1", "afterSecond": "1", "secondTapCount": 1}
