"""Offline workbench navigation probes against the checkout's real TS modules."""

import json
from pathlib import Path
import re
import shutil
import socket
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module", autouse=True)
def block_real_network():
    patch = pytest.MonkeyPatch()

    def forbidden(*args, **kwargs):
        raise AssertionError("Studio navigation tests forbid sockets and DNS")

    for name in ("connect", "connect_ex", "sendto", "bind", "listen"):
        patch.setattr(socket.socket, name, forbidden)
    for name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        patch.setattr(socket, name, forbidden)
    yield
    patch.undo()


DRIVER = r"""
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const frontend=path.join(process.argv[1],'frontend');
const ts=require(path.join(frontend,'node_modules/typescript'));
const env={owner:'author',status:200,defer:false,fail:false,calls:[],requests:[],listeners:new Map(),timers:new Map(),next:1};
let current=null;
const equal=(a,b)=>a&&b&&a.length===b.length&&a.every((value,index)=>Object.is(value,b[index]));
function slot(initial){const index=current.index++;if(!(index in current.hooks))current.hooks[index]=initial();return current.hooks[index];}
const React={
 useState(initial){const instance=current,s=slot(()=>({value:typeof initial==='function'?initial():initial}));
  s.set??=(value)=>{const next=typeof value==='function'?value(s.value):value;if(!Object.is(next,s.value)){s.value=next;instance.schedule();}};
  return [s.value,s.set];},
 useRef:value=>slot(()=>({current:value})),
 useMemo(fn,deps){const memo=slot(()=>({}));if(!equal(memo.deps,deps)){memo.value=fn();memo.deps=deps;}return memo.value;},
 useEffect(fn,deps){const instance=current,effect=slot(()=>({}));if(!equal(effect.deps,deps)){effect.deps=deps;instance.pending.push(()=>{effect.cleanup?.();effect.cleanup=fn();});}},
};
React.useCallback=(fn,deps)=>React.useMemo(()=>fn,deps);
React.useSyncExternalStore=(subscribe,snapshot)=>{const instance=current;React.useEffect(()=>subscribe(()=>instance.schedule()),[subscribe]);return snapshot();};
const jsx=(type,props,key)=>({type,props:props??{},key});
const runtime={jsx,jsxs:jsx,Fragment:'fragment'};
function listen(name,fn){if(!env.listeners.has(name))env.listeners.set(name,new Set());env.listeners.get(name).add(fn);}
function unlisten(name,fn){env.listeners.get(name)?.delete(fn);}
global.window={addEventListener:listen,removeEventListener:unlisten};
global.setInterval=(fn,delay)=>{const id=env.next++;env.timers.set(id,{fn,delay});return id;};
global.clearInterval=id=>env.timers.delete(id);
function dispatch(name,event={}){for(const fn of [...(env.listeners.get(name)??[])])fn(event);}
async function http(url,init={}){
 env.calls.push({url,signal:init.signal});
 if(url==='/api/strawberry')return {ok:true,status:200,json:async()=>({balance:100})};
 assert.equal(url,'/api/studio/access');
 if(env.fail)throw Error('offline');
 const status=env.status;
 if(env.defer)return await new Promise(resolve=>env.requests.push({resolve,status,signal:init.signal}));
 return {ok:status===200,status,json:async()=>({})};
}
const auth={getUsername:()=>env.owner,ensureAccountIdentity:async()=>env.owner,apiFetch:http,updateBalance:()=>{}};
const cache=new Map();
function load(relative){
 const filename=path.resolve(frontend,relative);assert(filename.startsWith(frontend+path.sep));
 if(cache.has(filename))return cache.get(filename).exports;
 const compiled=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const module={exports:{}};cache.set(filename,module);
 const localRequire=name=>{
  if(name==='react')return React;if(name==='react/jsx-runtime')return runtime;
  if(name==='next/link')return {__esModule:true,default:function Link(){}};
  if(name==='next/navigation')return {usePathname:()=>'/'};
  if(name==='@/components/Glaze')return {__esModule:true,default:function Glaze(){}};
  if(name==='@/lib/useTheme')return {useTheme:()=>({dark:false,toggleTheme:()=>{}})};
  if(name==='@/lib/utils')return {cn:(...values)=>values.filter(Boolean).join(' ')};
  if(name==='@/lib/auth')return auth;if(name==='@/lib/config')return {API_BASE:'/api'};
  let base=name.startsWith('@/')?path.join(frontend,name.slice(2)):name.startsWith('.')?path.resolve(path.dirname(filename),name):null;
  assert(base,`Unmocked import ${name}`);
  if(!path.extname(base))base+=fs.existsSync(base+'.tsx')?'.tsx':'.ts';
  return load(path.relative(frontend,base));
 };
 new Function('require','module','exports',compiled)(localRequire,module,module.exports);return module.exports;
}
function mount(Component,props={}){const instance={index:0,hooks:[],pending:[],scheduled:false,dead:false,
 schedule(){if(!this.scheduled&&!this.dead){this.scheduled=true;queueMicrotask(()=>{this.scheduled=false;if(!this.dead)this.render();});}},
 render(){this.index=0;current=this;try{this.tree=Component(props);}finally{current=null;}for(const effect of this.pending.splice(0))effect();},
 close(){this.dead=true;for(const hook of this.hooks)hook.cleanup?.();}};instance.render();return instance;}
function all(tree,predicate){const result=[];function visit(node){if(Array.isArray(node)){node.forEach(visit);return;}if(!node||typeof node!=='object')return;if(predicate(node))result.push(node);visit(node.props?.children);}visit(tree);return result;}
const links=instance=>all(instance.tree,node=>node.props?.title==='工作室');
const mobile=instance=>all(instance.tree,node=>node.type==='nav'&&node.props.className.includes('mobile-tabbar'))[0];
async function flush(){for(let i=0;i<12;i++)await new Promise(setImmediate);}
function resolve(request){request.resolve({ok:request.status===200,status:request.status,json:async()=>({})});}
"""


def probe(script):
    if not shutil.which("node") or not (ROOT / "frontend/node_modules/typescript").exists():
        pytest.skip("node and the existing frontend dependencies are needed")
    result = subprocess.run(
        ["node", "-e", DRIVER + "\n(async()=>{\n" + script + "\n})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});", str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


@pytest.mark.parametrize("status,allowed", [(200, True), (404, False), (403, False), (500, False)])
def test_sidebar_access_gate_and_six_mobile_items(status, allowed):
    assert probe("env.status=" + str(status) + ";const expected=" + json.dumps(allowed) + r""";
const instance=mount(load('components/Sidebar.tsx').default);
assert.equal(links(instance).length,0,'The bookmark must wait for access');
await flush();assert.equal(links(instance).length,expected?1:0);
assert.equal(env.calls.filter(call=>call.url==='/api/studio/access').length,1);
assert.equal(all(mobile(instance),node=>node.type?.name==='Link').length,6);
assert.equal(all(mobile(instance),node=>node.props?.title==='工作室').length,0);
instance.close();process.stdout.write(JSON.stringify(true));
""") is True


def test_sidebar_network_failure_hides_entry_and_disposes_access_request():
    assert probe(r"""
env.fail=true;const instance=mount(load('components/Sidebar.tsx').default);await flush();
assert.equal(links(instance).length,0);instance.close();
const access=env.calls.find(call=>call.url==='/api/studio/access');assert(access.signal.aborted);
process.stdout.write(JSON.stringify(true));
""") is True


def test_sidebar_account_switch_cancels_and_ignores_old_access():
    assert probe(r"""
env.defer=true;const instance=mount(load('components/Sidebar.tsx').default);await flush();
const old=env.requests[0];assert(old);env.owner='reader';env.status=404;
dispatch('fiona-user-changed');assert(old.signal.aborted);await flush();
assert.equal(links(instance).length,0);resolve(old);await flush();assert.equal(links(instance).length,0);
resolve(env.requests[1]);await flush();assert.equal(links(instance).length,0);
instance.close();process.stdout.write(JSON.stringify(true));
""") is True


def test_sidebar_preserves_static_items_and_studio_drawer_callback():
    source = (ROOT / "frontend/components/Sidebar.tsx").read_text()
    nav = source.split("const navItems = [", 1)[1].split("];", 1)[0]
    assert re.findall(r'label: "([^"]+)"', nav) == ["对话", "分身", "广场", "世界", "设置", "书斋"]
    assert probe(r"""
let clicks=0;const instance=mount(load('components/Sidebar.tsx').default,{onChatClick:()=>{},onStudioClick:()=>clicks++,studioActive:true});await flush();
const entry=links(instance)[0];assert.equal(entry.type,'button');assert.equal(entry.props['aria-controls'],'studio-drawer');
assert.equal(entry.props['aria-expanded'],true);entry.props.onClick();assert.equal(clicks,1);
instance.close();process.stdout.write(JSON.stringify(true));
""") is True


def test_home_studio_drawer_is_gated_keeps_frame_and_checks_message_sender():
    source = (ROOT / "frontend/app/page.tsx").read_text()
    assert '"studio" | "novel" | null' in source
    drawer = source.split('id="studio-drawer"', 1)[1].split("</Glaze>", 1)[0]
    for contract in ('studioAllowed ? <iframe', 'key={username}', 'src="/studio?embed=1"',
                     'aria-hidden={!studioOpen}', 'inert={!studioOpen}', '...drawerStyle(studioOpen)',
                     'focusVisibleDrawerTrigger("studio-drawer")', 'event.key === "Escape"'):
        assert contract in drawer
    assert not re.search(r"studioOpen\s*&&\s*<iframe", drawer)
    listener = source.split("const closeStudio =", 1)[1].split('}, []);', 1)[0]
    assert "event.origin !== window.location.origin" in listener
    assert "event.source !== studioFrameRef.current?.contentWindow" in listener
    assert 'event.data?.type !== "fiona-studio-close"' in listener
    assert 'if (studioAllowed) toggleDrawer("studio")' in source


def test_home_notice_delivery_keeps_busy_account_and_selection_guards():
    source = (ROOT / "frontend/app/page.tsx").read_text()
    poll = source.split("const poller = createStudioNoticePoller({", 1)[1].split("}, [hydrated, username, refreshList]);", 1)[0]
    for contract in ('document.visibilityState === "visible"', "readStoredUsername() === username",
                     "10_000", "poller.pause()", "poller.dispose()", "setStudioInbox",
                     "localWatchNotificationsEnabled(username)"):
        assert contract in poll
    delivery = source.split("const notices = studioInbox.notices.filter", 1)[1].split("const selectedReferenceImages", 1)[0]
    assert "selectionVersion !== getSelectionVersion()" in delivery
    assert "readStoredUsername() !== username" in delivery
    assert "mergeStudioNotices(previous, notices, conversationId)" in delivery
    assert "conversationLocked || conversationLoading || studioInbox.owner !== username" in source
    assert "有新的工作室提醒 · {notice.project_title}" in source
    assert "void handleSelectConversation(notice.conversation_id)" in source
