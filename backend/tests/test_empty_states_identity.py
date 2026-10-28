"""Offline source and behavior checks for the account-identity pending hook.

Each behavior probe runs a fresh Node process, so the module-level
``identityRecoverySettled`` flag can never leak from one scenario to the next.
TypeScript is transpiled in-process and executed against a tiny hand-written
React stand-in plus a controllable ``@/lib/auth`` stand-in.
"""

import json
import re
import socket
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
SOURCE = FRONTEND / "lib" / "useAccountIdentity.ts"
NEW_CODE_MARKER = "// 身份是否还没确认"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("identity pending tests forbid sockets and DNS")

    for name in ("connect", "connect_ex"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def require_node_and_dependencies():
    probe = """
const packages = ['typescript', 'react'];
const missing = packages.filter(name => {
  try { require.resolve(name, {paths: [process.argv[1]]}); return false; }
  catch { return true; }
});
process.stdout.write(JSON.stringify(missing));
"""
    try:
        result = subprocess.run(
            ["node", "-e", probe, str(FRONTEND)],
            capture_output=True, text=True, check=True, timeout=30,
        )
    except FileNotFoundError:
        pytest.skip("Node.js is required for the identity hook behavior probes")
    except subprocess.TimeoutExpired:
        pytest.skip("Node.js dependency probe timed out")
    except subprocess.CalledProcessError as exc:
        pytest.skip("Node.js dependency probe failed: " + (exc.stderr or "").strip())
    missing = json.loads(result.stdout)
    if missing:
        pytest.skip("Frontend dependencies unavailable: " + ", ".join(missing))


NODE_RUNNER = r"""
const fs = require('fs');
const ts = require('typescript');

const sourcePath = process.argv[1];
const config = JSON.parse(process.argv[2]);
const source = fs.readFileSync(sourcePath, 'utf8');

const windowListeners = new Map();
globalThis.window = {
  addEventListener(type, listener) {
    if (!windowListeners.has(type)) windowListeners.set(type, new Set());
    windowListeners.get(type).add(listener);
  },
  removeEventListener(type, listener) {
    const listeners = windowListeners.get(type);
    if (listeners) listeners.delete(listener);
  },
};

const calls = { ensure: 0 };
const authState = { username: config.username || '' };
let resolveRecovery = null;
const recovery = new Promise(resolve => { resolveRecovery = resolve; });
const auth = {
  getUsername: () => authState.username,
  ensureAccountIdentity: () => {
    calls.ensure += 1;
    return recovery;
  },
};

let currentRender = null;
const snapshots = { latestGetSnapshot: null, notifySnapshots: [] };
const react = {
  useEffect(effect) {
    if (!currentRender) throw new Error('useEffect called outside a render');
    currentRender.effects.push(effect);
  },
  useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot) {
    if (!currentRender) throw new Error('useSyncExternalStore called outside a render');
    const render = currentRender;
    if (render.server) return getServerSnapshot();
    const value = getSnapshot();
    snapshots.latestGetSnapshot = getSnapshot;
    subscribe(() => {
      render.notified += 1;
      // React rereads the snapshot synchronously when the store notifies.
      snapshots.notifySnapshots.push(getSnapshot());
    });
    return value;
  },
  useCallback(fn) { return fn; },
  useRef(value) { return { current: value }; },
};

const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    esModuleInterop: true,
  },
}).outputText;

const moduleObject = { exports: {} };
const customRequire = name => {
  if (name === 'react') return react;
  if (name === '@/lib/auth') return auth;
  throw new Error('unexpected module import: ' + name);
};
new Function('require', 'module', 'exports', compiled)(
  customRequire, moduleObject, moduleObject.exports,
);
const moduleExports = moduleObject.exports;

function renderHook(server) {
  const render = { server: !!server, effects: [], notified: 0, error: null };
  currentRender = render;
  let value;
  try {
    value = moduleExports.useAccountIdentityPending();
  } catch (error) {
    render.error = String((error && error.stack) || error);
  } finally {
    currentRender = null;
  }
  if (render.error) throw new Error(render.error);
  if (!render.server) {
    for (const effect of render.effects) effect();
  }
  return { value, render };
}

const tick = () => new Promise(resolve => setImmediate(resolve));

(async () => {
  const output = { ok: true };
  if (typeof moduleExports.useAccountIdentityPending !== 'function') {
    throw new Error('useAccountIdentityPending is not exported');
  }

  if (config.mode === 'server') {
    const first = renderHook(true);
    output.serverSnapshot = first.value;
    output.ensureCalls = calls.ensure;
  } else if (config.mode === 'pending') {
    const first = renderHook(false);
    output.initial = first.value;
    output.ensureCallsAfterRender = calls.ensure;
    await tick();
    const during = renderHook(false);
    output.duringRecovery = during.value;
  } else if (config.mode === 'settled') {
    const first = renderHook(false);
    output.initial = first.value;
    await tick();
    authState.username = 'alice';
    resolveRecovery('alice');
    await tick();
    const after = renderHook(false);
    output.afterSettle = after.value;
    output.notified = first.render.notified;
    output.ensureCalls = calls.ensure;
  } else if (config.mode === 'settled_empty') {
    // Recovery failed: the username stays empty, and the promise settles with
    // an empty string. This must run in its own Node process because the
    // module-level settled flag only goes from false to true.
    const first = renderHook(false);
    output.initial = first.value;
    await tick();
    resolveRecovery('');
    await tick();
    output.notifySnapshots = snapshots.notifySnapshots;
    output.notified = first.render.notified;
    output.afterSettleSnapshot = snapshots.latestGetSnapshot();
    output.ensureCalls = calls.ensure;
  } else if (config.mode === 'username') {
    authState.username = 'alice';
    const first = renderHook(false);
    output.initial = first.value;
    await tick();
    const later = renderHook(false);
    output.later = later.value;
  } else {
    throw new Error('unknown mode: ' + config.mode);
  }

  process.stdout.write(JSON.stringify(output));
})().catch(error => {
  process.stdout.write(JSON.stringify({
    ok: false,
    error: String((error && error.stack) || error),
  }));
  process.exitCode = 1;
});
"""


def probe(mode, **config):
    require_node_and_dependencies()
    payload = {"mode": mode, **config}
    result = subprocess.run(
        ["node", "-e", NODE_RUNNER, str(SOURCE), json.dumps(payload, ensure_ascii=False)],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        timeout=60,
    )
    stdout = result.stdout.strip()
    assert stdout, (
        "identity hook probe produced no output "
        f"(exit {result.returncode}): {result.stderr.strip()}"
    )
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"identity hook probe emitted invalid JSON: {stdout!r}\n{result.stderr.strip()}"
        )
    assert data.get("ok") is True, data.get("error", "identity hook probe failed")
    return data


def test_source_contract_keeps_pending_hook_and_original_code():
    source = SOURCE.read_text()
    start = source.find(NEW_CODE_MARKER)
    new_code = source[start:] if start >= 0 else source
    failures = []
    if start < 0:
        failures.append("missing identity pending block")
    if "export function useAccountIdentityPending(): boolean {" not in new_code:
        failures.append("missing useAccountIdentityPending export")
    for token in ("useId", "dispatchEvent", "location", "document"):
        if re.search(rf"\b{token}\b", new_code):
            failures.append(f"new code contains forbidden token: {token}")
    if 'import { ensureAccountIdentity, getUsername } from "@/lib/auth";' not in source:
        failures.append("original @/lib/auth import changed")
    if "  return useSyncExternalStore(subscribeAccount, getUsername, serverIdentity);" not in source:
        failures.append("original useAccountIdentity snapshot call changed")
    assert not failures, "\n".join(failures)


def test_server_snapshot_is_pending():
    data = probe("server")
    assert data["serverSnapshot"] is True
    assert data["ensureCalls"] == 0


def test_client_without_username_stays_pending_until_recovery():
    data = probe("pending", username="")
    assert data["initial"] is True
    assert data["duringRecovery"] is True
    assert data["ensureCallsAfterRender"] >= 1


def test_recovery_settle_flips_to_false_and_notifies_subscribers():
    data = probe("settled", username="")
    assert data["initial"] is True
    assert data["afterSettle"] is False
    assert data["notified"] >= 1


def test_failed_recovery_with_empty_username_never_reports_pending():
    # A failed recovery settles with an empty username. Every notification must
    # already see the settled flag, and the snapshot stays false afterwards.
    data = probe("settled_empty", username="")
    assert data["initial"] is True
    assert data["notified"] >= 1
    assert len(data["notifySnapshots"]) >= 1
    assert all(snapshot is False for snapshot in data["notifySnapshots"])
    assert data["afterSettleSnapshot"] is False
    assert data["ensureCalls"] >= 1


def test_known_username_is_not_pending():
    data = probe("username", username="alice")
    assert data["initial"] is False
    assert data["later"] is False
