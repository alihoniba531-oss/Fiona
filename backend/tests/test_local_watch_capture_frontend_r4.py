"""Execute the settings interval path offline, without npm packages or git."""

import json
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOGIC = ROOT / "frontend/lib/localWatch.ts"
SETTINGS = ROOT / "frontend/components/LocalWatchSection.tsx"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("R4 frontend tests forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def body_at(source, marker):
    start = source.index(marker)
    opening = source.index("{", start + len(marker) - 1)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[opening + 1:end - 1]


def node_json(script):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is unavailable; these tests need no npm packages")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def settings_runner(scenario):
    source = SETTINGS.read_text(encoding="utf-8")
    timer = source.index("window.setInterval(")
    effect_start = source.rfind("useEffect(() => {", 0, timer)
    effect = body_at(source[effect_start:], "useEffect(() => {")
    refresh = body_at(source, "const refresh = useCallback(async () => {")
    # Strip only the annotations occurring in these source-extracted paths.
    effect = effect.replace("let active: AbortController | null", "let active")
    refresh = re.sub(r"localWatchRequest<[^>]+>", "localWatchRequest", refresh)
    setup = r"""
      let owner='alice', available=true;
      const username='alice', calls=[], chatCalls=[], updates=[], controllers=[];
      let interval, timerDelay, clearCount=0, mode='ready', resolvers=[];
      const document={visibilityState:'visible', listeners:{},
        addEventListener(name,fn){this.listeners[name]=fn;},
        removeEventListener(name,fn){if(this.listeners[name]===fn)delete this.listeners[name];}};
      const window={setInterval(fn,delay){interval=fn;timerDelay=delay;return 8;},
        clearInterval(id){if(id!==8)throw Error('wrong timer');clearCount++;}};
      class LocalWatchError extends Error {constructor(status){super('test');this.status=status;}}
      const localWatchErrorMessage=cause=>cause.message;
      function lane(){let active=null;return ()=>{
        if(owner!==username)return null;
        active?.abort();active=new AbortController();controllers.push(active);
        const current=active;
        return {signal:current.signal,isCurrent:()=>owner===username&&!current.signal.aborted};};}
      const beginRead=lane(), beginRulesRead=lane();
      function localWatchRequest(path,init){
        calls.push({path,signal:init.signal});
        const data=path==='/devices'?[{id:1,name:'Mac'}]
          :path==='/windows'?[{app_name:'Safari',title:'Docs'}]:[{id:7,capture:{ok:false,neutral:true,message:'等待首次截图'}}];
        if(mode==='404')return Promise.reject(new LocalWatchError(404));
        if(mode==='pending')return new Promise(resolve=>resolvers.push(()=>resolve(data)));
        return Promise.resolve(data);
      }
      const getChatModel=signal=>{chatCalls.push(signal);return Promise.resolve({available:true,
        config:{enabled:true,provider:'anthropic',status:'ok'}});};
      const API='local';const apiFetch=async(path,init)=>{
        calls.push({path,signal:init.signal});return {ok:true,json:async()=>({conversations:[{id:'chat'}]})};};
      const setDevices=value=>updates.push(['devices',value]);
      const setRules=value=>updates.push(['rules',value]);
      const setWindows=value=>updates.push(['windows',value]);
      const setConversations=value=>updates.push(['conversations',value]);
      const setAvailable=value=>{available=value;updates.push(['available',value]);};
      const setClaudeAvailable=value=>updates.push(['claude',value]);
      const setNotifications=value=>updates.push(['notifications',value]);
      const setError=value=>updates.push(['error',value]);
      const setLoading=value=>updates.push(['loading',value]);
      const localWatchNotificationsEnabled=()=>false;
      const flush=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
    """
    return node_json(setup + "\nconst refresh=async()=>{" + refresh + "};\n"
                     + "const cleanup=(()=>{" + effect + "})();\n"
                     + "(async()=>{" + scenario + "})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});")


def test_neutral_capture_is_optional_and_still_read_only_metadata():
    source = LOGIC.read_text(encoding="utf-8")
    capture = source.split("export interface LocalWatchCapture {", 1)[1].split("}", 1)[0]
    assert re.search(r"\bneutral\?\s*:\s*boolean\b", capture)
    assert 'Omit<LocalWatchRule, "id" | "capture">' in source


@pytest.mark.parametrize("capture,expected", [
    ({"ok": False, "neutral": True, "message": "已停用"}, "已停用"),
    ({"ok": False, "neutral": True, "message": "等待首次截图"}, "等待首次截图"),
    ({"ok": True, "message": "后端正常状态"}, "监控中"),
    ({"ok": False, "message": "监控程序未在运行"}, "监控程序未在运行"),
])
def test_neutral_status_preserves_backend_message_and_keeps_healthy_behavior(capture, expected):
    body = body_at(LOGIC.read_text(encoding="utf-8"), "export function localWatchCaptureMessage(")
    script = "function localWatchCaptureMessage(rule){" + body + "}\n"
    script += "process.stdout.write(JSON.stringify(localWatchCaptureMessage({capture:" + json.dumps(capture, ensure_ascii=False) + "})));"
    assert node_json(script) == expected


@pytest.mark.parametrize("capture,ordinary", [
    ({"ok": True, "message": "监控中"}, True),
    ({"ok": False, "neutral": True, "message": "已停用"}, True),
    ({"ok": False, "neutral": True, "message": "等待首次截图"}, True),
    ({"ok": False, "message": "监控程序未在运行"}, False),
    ({"ok": False, "message": "截图失败，请查看监控程序日志"}, False),
])
def test_real_rule_row_uses_ordinary_color_for_neutral_status(capture, ordinary):
    source = SETTINGS.read_text(encoding="utf-8")
    row = source.split("{rules.map(rule =>", 1)[1].split("</li>)}</ul>", 1)[0]
    status = row.split("{localWatchCaptureMessage(rule)}", 1)[0].rsplit("<p", 1)[1]
    assert 'role="status"' in status and "break-all" in status
    expression = status.split("${", 1)[1].split("}", 1)[0]
    script = "const noteClass='ordinary',rule={capture:" + json.dumps(capture) + "};\n"
    script += "process.stdout.write(JSON.stringify(" + expression + "));"
    actual = node_json(script)
    assert (actual == "ordinary") is ordinary
    if not ordinary:
        assert "text-[color:var(--seal)]" in actual


def test_actual_visible_interval_fetches_only_rules():
    actual = settings_runner("""
      interval();await flush();interval();await flush();cleanup();
      process.stdout.write(JSON.stringify({paths:calls.map(call=>call.path),chat:chatCalls.length,
        timerDelay,ruleUpdates:updates.filter(item=>item[0]==='rules').length,clearCount}));
    """)
    assert actual == {"paths": ["/rules", "/rules"], "chat": 0, "timerDelay": 10000,
                      "ruleUpdates": 2, "clearCount": 1}


def test_poll_does_not_cancel_slow_initial_full_refresh():
    actual = settings_runner("""
      mode='pending';const initial=refresh();const first=calls[0].signal;
      interval();await flush();const aborted=first.aborted;
      resolvers.splice(0).forEach(resolve=>resolve());await initial;await flush();cleanup();
      process.stdout.write(JSON.stringify({aborted,paths:calls.map(call=>call.path),chat:chatCalls.length,
        received:updates.filter(item=>['devices','windows','conversations','claude'].includes(item[0])).map(item=>item[0])}));
    """)
    assert actual["aborted"] is False
    assert actual["paths"] == ["/devices", "/rules", "/windows", "local/conversations", "/rules"]
    assert actual["chat"] == 1
    assert actual["received"] == ["devices", "windows", "claude", "conversations"]


def test_pending_intervals_never_overlap_or_queue_more_requests():
    actual = settings_runner("""
      mode='pending';interval();interval();interval();await flush();const pending=calls.length;
      resolvers.splice(0).forEach(resolve=>resolve());await flush();mode='ready';interval();await flush();cleanup();
      process.stdout.write(JSON.stringify({pending,paths:calls.map(call=>call.path)}));
    """)
    assert actual == {"pending": 1, "paths": ["/rules", "/rules"]}


def test_hidden_page_cancels_pending_poll_and_resumes_with_rules_only():
    actual = settings_runner("""
      document.visibilityState='hidden';interval();await flush();const initial=calls.length;
      document.visibilityState='visible';document.listeners.visibilitychange?.();await flush();
      mode='pending';interval();await flush();const signal=calls.at(-1).signal;
      document.visibilityState='hidden';document.listeners.visibilitychange?.();interval();
      resolvers.splice(0).forEach(resolve=>resolve());await flush();
      const hiddenUpdates=updates.filter(item=>item[0]==='rules').length;
      mode='ready';document.visibilityState='visible';document.listeners.visibilitychange?.();await flush();cleanup();
      process.stdout.write(JSON.stringify({initial,aborted:signal.aborted,hiddenUpdates,
        paths:calls.map(call=>call.path),listeners:Object.keys(document.listeners)}));
    """)
    assert actual == {"initial": 0, "aborted": True, "hiddenUpdates": 1,
                      "paths": ["/rules", "/rules", "/rules"], "listeners": []}


@pytest.mark.parametrize("stop", ["unmount", "account"])
def test_old_account_or_unmounted_poll_cannot_publish_a_late_response(stop):
    stopping = "cleanup();" if stop == "unmount" else "owner='bob';controllers.forEach(controller=>controller.abort());"
    actual = settings_runner("""
      mode='pending';interval();await flush();const signal=calls[0].signal;
    """ + stopping + """
      resolvers.splice(0).forEach(resolve=>resolve());await flush();interval();await flush();
      process.stdout.write(JSON.stringify({aborted:signal.aborted,paths:calls.map(call=>call.path),
        rules:updates.filter(item=>item[0]==='rules').length}));
    """)
    assert actual == {"aborted": True, "paths": ["/rules"], "rules": 0}


def test_404_stops_actual_interval_and_marks_feature_unavailable():
    actual = settings_runner("""
      mode='404';interval();await flush();interval();await flush();
      process.stdout.write(JSON.stringify({paths:calls.map(call=>call.path),available,clearCount}));
    """)
    assert actual == {"paths": ["/rules"], "available": False, "clearCount": 1}


def test_transient_poll_failure_retries_next_tick():
    actual = settings_runner("""
      const original=localWatchRequest;localWatchRequest=()=>{calls.push({path:'/rules'});return Promise.reject(Error('offline'));};
      interval();await flush();localWatchRequest=original;interval();await flush();cleanup();
      process.stdout.write(JSON.stringify({paths:calls.map(call=>call.path),available,
        rules:updates.filter(item=>item[0]==='rules').length}));
    """)
    assert actual == {"paths": ["/rules", "/rules"], "available": True, "rules": 1}


def test_poll_uses_separate_account_lane_and_dependencies():
    source = SETTINGS.read_text(encoding="utf-8")
    assert "const { beginRequest: beginRulesRead } = useAccountRequest(username);" in source
    assert "[available, beginRulesRead, username]" in source
    assert "[beginRead, username]" in source
