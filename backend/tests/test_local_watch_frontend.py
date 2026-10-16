"""Package-free, offline contracts for local watch settings and alert delivery."""

import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LOGIC = ROOT / "frontend/lib/localWatch.ts"
PAGE = ROOT / "frontend/app/page.tsx"
SETTINGS = ROOT / "frontend/components/LocalWatchSection.tsx"
PRIVACY = "监控程序只在你的 Mac 上截图并识别文字，截图和整页文字不会上传；只有窗口里新出现的文字会发给 Fiona 用于判断，不落日志。AI 判断规则会把新出现的文字发给阿里云千问（选 Claude 时发给 Anthropic）。只会保存提醒摘要。"


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Local watch frontend tests forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


def function_body(name):
    source = LOGIC.read_text(encoding="utf-8")
    start = source.index("export function " + name)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[opening + 1:end - 1]


def run_logic(script):
    if not shutil.which("node"):
        pytest.skip("node is unavailable; these tests need no npm packages")
    poller = function_body("createLocalWatchPoller").replace(
        "let active: AbortController | null", "let active"
    )
    message = function_body("localWatchMessage")
    append = function_body("appendLocalWatchMessages")
    runner = "function createLocalWatchPoller(options) {" + poller + "}\n"
    runner += "function localWatchMessage(alert) {" + message + "}\n"
    runner += "function appendLocalWatchMessages(messages, alerts, conversationId, busy) {" + append + "}\n"
    runner += "function localWatchNotificationsEnabled(username) {" + function_body("localWatchNotificationsEnabled") + "}\n"
    runner += "function setLocalWatchNotifications(username, enabled) {" + function_body("setLocalWatchNotifications") + "}\n"
    runner += "\n(async () => {\n" + script + "\n})().catch(e => {process.stderr.write(e.stack);process.exitCode=1;});"
    result = subprocess.run(["node", "-e", runner], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def run_rule_payload(script):
    if not shutil.which("node"):
        pytest.skip("node is unavailable; these tests need no npm packages")
    runner = "function localWatchRulePayload(draft) {" + function_body("localWatchRulePayload") + "}\n"
    runner += "function localWatchDraft(rule) {" + function_body("localWatchDraft") + "}\n"
    runner += script
    result = subprocess.run(["node", "-e", runner], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_editing_get_response_strips_metadata_from_runtime_draft_and_request():
    actual = run_rule_payload("""
      const response={id:12,username:'alice',created_at:'today',updated_at:'today',name:' 工作 ',
        app_match:' WeChat ',title_match:' 群聊 ',kind:'keyword',params:{keywords:['@我']},
        interval_seconds:3,cooldown_seconds:60,enabled:true,conversation_id:'current'};
      const draft=localWatchDraft(response);const payload=localWatchRulePayload({...draft,id:12,username:'alice'});
      process.stdout.write(JSON.stringify({draft,payload}));
    """)
    expected_fields = {"name", "app_match", "title_match", "kind", "params", "interval_seconds", "cooldown_seconds", "enabled", "conversation_id"}
    assert set(actual["draft"]) == set(actual["payload"]) == expected_fields
    assert actual["payload"]["name"] == "工作" and actual["payload"]["app_match"] == "WeChat"
    assert actual["payload"]["params"] == {"keywords": ["@我"]}


def test_switching_rule_types_sends_only_selected_types_parameter_fields():
    actual = run_rule_payload("""
      const draft=localWatchDraft();const mixed={keywords:['@我'],label:'价格',op:'>=',threshold:100,
        condition:'下载完成或出现报错时提醒我',model:'claude',extra:'metadata'};
      const payloads=['keyword','number','ai'].map(kind=>localWatchRulePayload({...draft,kind,params:mixed}));
      process.stdout.write(JSON.stringify(payloads));
    """)
    assert [item["params"] for item in actual] == [
        {"keywords": ["@我"]}, {"label": "价格", "op": ">=", "threshold": 100},
        {"condition": "下载完成或出现报错时提醒我", "model": "claude"},
    ]
    source = SETTINGS.read_text(encoding="utf-8")
    assert "setDraft(localWatchDraft(rule))" in source
    assert "JSON.stringify(localWatchRulePayload(" in source


def test_first_load_records_latest_id_across_pages_without_replaying_history():
    actual = run_logic("""
      const calls=[], delivered=[];
      const poller=createLocalWatchPoller({isVisible:()=>true,
        fetchPage:async after=>{calls.push(after);return {status:200,alerts:
          after===0 ? Array.from({length:50},(_,i)=>({id:i+1})) : after===50 ? [{id:51},{id:52}] : [{id:53}]};},
        onAlerts:alerts=>delivered.push(alerts.map(a=>a.id))});
      await poller.tick(); const baseline=delivered.slice(); await poller.tick();
      process.stdout.write(JSON.stringify({calls,baseline,delivered}));
    """)
    assert actual == {"calls": [0, 50, 52], "baseline": [], "delivered": [[53]]}


def test_hidden_page_pauses_and_404_permanently_stops_polling():
    actual = run_logic("""
      let visible=false, calls=0;
      const poller=createLocalWatchPoller({isVisible:()=>visible,
        fetchPage:async()=>{calls++;return {status:404,alerts:[]};},onAlerts:()=>{throw Error('unexpected');}});
      await poller.tick(); const hidden=calls; visible=true; await poller.tick(); await poller.tick();
      process.stdout.write(JSON.stringify({hidden,calls}));
    """)
    assert actual == {"hidden": 0, "calls": 1}


def test_in_flight_requests_do_not_overlap_and_disposed_response_is_ignored():
    actual = run_logic("""
      let calls=0, resolve, delivered=0;
      const poller=createLocalWatchPoller({isVisible:()=>true,
        fetchPage:()=>{calls++;return new Promise(r=>resolve=r);},onAlerts:()=>{delivered++;}});
      const first=poller.tick(); await poller.tick(); poller.dispose(); resolve({status:200,alerts:[{id:9}]});
      await first; await poller.tick(); process.stdout.write(JSON.stringify({calls,delivered}));
    """)
    assert actual == {"calls": 1, "delivered": 0}


def test_failed_baseline_is_retried_without_delivering_partial_history():
    actual = run_logic("""
      let failed=false; const calls=[], delivered=[];
      const poller=createLocalWatchPoller({isVisible:()=>true,fetchPage:async after=>{
        calls.push(after);if(after===50&&!failed){failed=true;throw Error('offline');}
        return {status:200,alerts:after===0?Array.from({length:50},(_,i)=>({id:i+1})):[]};},onAlerts:a=>delivered.push(a)});
      await poller.tick();await poller.tick();process.stdout.write(JSON.stringify({calls,delivered}));
    """)
    assert actual == {"calls": [0, 50, 0, 50], "delivered": []}


def test_hidden_in_flight_alert_does_not_advance_cursor_and_is_delivered_on_resume():
    actual = run_logic("""
      let visible=true, resolve, delayed=false;const calls=[],delivered=[];
      const poller=createLocalWatchPoller({isVisible:()=>visible,fetchPage:async after=>{
        calls.push(after);if(!calls.slice(0,-1).length)return {status:200,alerts:[]};
        if(!delayed){delayed=true;return new Promise(r=>resolve=r);}
        return {status:200,alerts:[{id:1}]};},onAlerts:a=>delivered.push(a.map(item=>item.id))});
      await poller.tick();const pending=poller.tick();visible=false;poller.pause();
      resolve({status:200,alerts:[{id:1}]});await pending;visible=true;await poller.tick();
      process.stdout.write(JSON.stringify({calls,delivered}));
    """)
    assert actual == {"calls": [0, 0, 0], "delivered": [[1]]}


def test_notification_preference_defaults_off_and_is_account_scoped():
    actual = run_logic("""
      const values=new Map();global.localStorage={getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value)};
      const defaultOff=localWatchNotificationsEnabled('alice');setLocalWatchNotifications('alice',true);
      const enabled=localWatchNotificationsEnabled('alice'),otherUser=localWatchNotificationsEnabled('bob');
      setLocalWatchNotifications('alice',false);const revoked=localWatchNotificationsEnabled('alice');
      global.localStorage={getItem:()=>{throw Error('blocked')}};const unavailable=localWatchNotificationsEnabled('alice');
      process.stdout.write(JSON.stringify({defaultOff,enabled,otherUser,revoked,unavailable}));
    """)
    assert actual == {"defaultOff": False, "enabled": True, "otherUser": False, "revoked": False, "unavailable": False}


def test_current_conversation_alert_inserted_once_and_busy_reply_kept_safe():
    actual = run_logic("""
      const existing=[{id:'db-2',dbId:2,role:'assistant',content:'existing'}];
      const alerts=[{id:3,message_id:3,conversation_id:'current',rule_name:'下载',summary:'下载完成',content:'【本机提醒 · Safari】下载完成（规则：下载）',created_at:'2026-10-11 12:00:00'},
        {id:4,message_id:4,conversation_id:'other',rule_name:'股价',summary:'价格上涨',content:'【本机提醒 · 行情】价格上涨（规则：股价）',created_at:'2026-10-11 12:00:00'}];
      const inserted=appendLocalWatchMessages(existing,alerts,'current',false);
      const repeated=appendLocalWatchMessages(inserted,alerts,'current',false);
      const busy=appendLocalWatchMessages(existing,alerts,'current',true);
      process.stdout.write(JSON.stringify({inserted,repeated,busy}));
    """)
    assert len(actual["inserted"]) == len(actual["repeated"]) == 2
    assert actual["busy"] == actual["inserted"][:1]
    message = actual["inserted"][1]
    assert message["role"] == "assistant" and message["dbId"] == 3
    assert message["content"] == "【本机提醒 · Safari】下载完成（规则：下载）"
    assert message["timestamp"].endswith("Z")


def test_settings_privacy_and_notification_opt_in_and_claude_gate():
    source = SETTINGS.read_text(encoding="utf-8")
    assert PRIVACY in source
    assert "mkdir -p ~/.fiona && umask 077 && pbpaste > ~/.fiona/watcher.token" in source
    assert 'Notification.requestPermission()' in source
    assert "允许浏览器通知" in source
    assert 'disabled={!claudeAvailable}' in source
    assert "最近发现的窗口" in source and "app_match: window.app_name" in source
    assert "生成设备令牌" in source and "令牌只显示一次" in source
    assert "LocalWatchSection" in (ROOT / "frontend/app/settings/page.tsx").read_text(encoding="utf-8")


def test_chat_polling_visibility_interval_account_scope_and_cross_conversation_notice():
    source = PAGE.read_text(encoding="utf-8")
    assert "createLocalWatchPoller" in source and "10_000" in source
    assert 'document.visibilityState === "visible"' in source
    assert 'document.addEventListener("visibilitychange", onVisibility)' in source
    assert "poller.dispose()" in source
    assert "readStoredUsername() === username" in source
    assert "appendLocalWatchMessages" in source
    assert "setLocalWatchInbox" in source and "getSelectionVersion()" in source
    assert "有新的本机提醒" in source and "handleSelectConversation(alert.conversation_id)" in source
    assert "localWatchNotificationsEnabled(username)" in source
    assert 'Notification.permission === "granted"' in source
    assert 'Notification.requestPermission()' not in source
