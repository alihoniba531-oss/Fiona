"""Offline contracts for the mobile-only voice button status bubble."""

import json
import re
import socket
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
VOICE = FRONTEND / "components/VoiceButton.tsx"

STATUS_SPAN = re.compile(r'<span data-voice-status[^>]*>([^<]*)</span>')


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Voice status bubble tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


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
            capture_output=True, text=True, check=True, timeout=60,
        )
    except FileNotFoundError:
        pytest.skip("Voice status SSR needs Node.js; source contracts still run")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        pytest.skip(f"Voice status SSR dependency probe unavailable: {error}")
    missing = json.loads(result.stdout) if result.stdout else []
    if missing:
        pytest.skip("Voice status SSR dependencies unavailable: " + ", ".join(missing))


def run_node(script, *args):
    try:
        result = subprocess.run(
            ["node", "-e", script, *args],
            cwd=FRONTEND, capture_output=True, text=True, check=True, timeout=60,
        )
    except FileNotFoundError:
        pytest.skip("Voice status checks need Node.js; source contracts still run")
    except subprocess.CalledProcessError as error:
        pytest.fail(f"Node harness failed:\n{error.stdout}\n{error.stderr}")
    except subprocess.TimeoutExpired as error:
        pytest.fail(f"Node harness timed out after {error.timeout} seconds")
    return result.stdout


VOICE_SSR_RUNNER = r"""
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
  onTap: noop,
  onHoldStart: noop,
  onHoldEnd: noop,
})));
"""


def render_voice(props):
    require_rendering_dependencies()
    return run_node(VOICE_SSR_RUNNER, str(VOICE), json.dumps(props))


def test_voice_status_bubble_ssr_states():
    holding = render_voice({"disabled": False, "dictating": False, "holding": True})
    match = STATUS_SPAN.search(holding)
    assert match is not None
    assert match.group(1) == "松开发送"

    dictating = render_voice({"disabled": False, "dictating": True, "holding": False})
    match = STATUS_SPAN.search(dictating)
    assert match is not None
    assert match.group(1) == "再点一下发送"

    idle = render_voice({"disabled": False, "dictating": False, "holding": False})
    assert STATUS_SPAN.search(idle) is None


VOICE_HINT_RUNNER = r"""
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');
const ts = require('typescript');
const realReact = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const localRequire = createRequire(path.join(process.cwd(), 'index.js'));

let source = fs.readFileSync(process.argv[1], 'utf8');
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

function renderWithHint(showHint, holding, dictating) {
  const fakeReact = {
    ...realReact,
    useState: () => [showHint, () => {}],
    useRef: initial => ({ current: initial }),
    useEffect: () => {},
  };
  const module = { exports: {} };
  const requireShim = name => name === 'react' ? fakeReact : localRequire(name);
  const factory = new Function('React', 'exports', 'require', 'module', compiled);
  factory(fakeReact, module.exports, requireShim, module);
  const Component = module.exports.default;
  const noop = () => {};
  return renderToStaticMarkup(Component({
    disabled: false,
    dictating,
    holding,
    onTap: noop,
    onHoldStart: noop,
    onHoldEnd: noop,
  }));
}

process.stdout.write(JSON.stringify({
  firstUse: renderWithHint(false, true, false),
  afterHint: renderWithHint(true, true, false),
  hintWhileDictating: renderWithHint(true, false, true),
}));
"""


def test_voice_status_bubble_respects_first_use_hint():
    require_rendering_dependencies()
    result = json.loads(run_node(VOICE_HINT_RUNNER, str(VOICE)))
    first_use = STATUS_SPAN.search(result["firstUse"])
    assert first_use is not None
    assert first_use.group(1) == "松开发送"
    assert STATUS_SPAN.search(result["afterHint"]) is None
    assert STATUS_SPAN.search(result["hintWhileDictating"]) is None


def test_voice_status_bubble_source_contract():
    source = VOICE.read_text(encoding="utf-8")
    match = re.search(r"<span data-voice-status[^>]*>", source)
    assert match is not None
    opening = match.group(0)
    assert 'aria-hidden="true"' in opening
    assert "pointer-events-none" in opening
    assert re.search(r"(?<![\w-])md:hidden", opening)
    assert source.count("try {") == 1

    self_source = Path(__file__).read_text(encoding="utf-8")
    # Build the needles at runtime so this assertion does not count itself.
    run_call = "subprocess." + "run("
    timeout_arg = "timeout=" + "60"
    assert self_source.count(run_call) == 2
    assert self_source.count(timeout_arg) == self_source.count(run_call)
