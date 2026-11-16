"""Offline navigation probes for the discussion-group bookmark and drawer.

The Sidebar cases execute the checkout's real ``Sidebar.tsx`` with a tiny React
stand-in, following ``test_studio_frontend_navigation.py``.  The home-page cases
are source contracts, so they run everywhere.  Everything is offline.
"""

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
        raise AssertionError("Discuss navigation tests forbid sockets and DNS")

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
const env={owner:'author',status:200,fail:false,pathname:'/',calls:[],listeners:new Map(),timers:new Map(),next:1};
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
 assert.equal(url,'/api/studio/access','Sidebar may only ask for strawberry and studio access');
 if(env.fail)throw Error('offline');
 return {ok:env.status===200,status:env.status,json:async()=>({})};
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
  if(name==='next/navigation')return {usePathname:()=>env.pathname};
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
const navs=instance=>all(instance.tree,node=>node.type==='nav');
const desktopNav=instance=>navs(instance).find(node=>String(node.props?.className).includes('mt-10'));
const mobile=instance=>navs(instance).find(node=>String(node.props?.className).includes('mobile-tabbar'));
const desktopTitles=instance=>desktopNav(instance).props.children.map(node=>node.props.title);
const discussEntries=instance=>all(instance.tree,node=>node.props?.title==='讨论群');
async function flush(){for(let i=0;i<12;i++)await new Promise(setImmediate);}
"""


def probe(script):
    if not (ROOT / "frontend" / "node_modules" / "typescript/lib/typescript.js").is_file():
        pytest.skip("frontend dependencies unavailable: typescript")
    if not shutil.which("node"):
        pytest.skip("node is unavailable")
    result = subprocess.run(
        ["node", "-e", DRIVER + "\n(async()=>{\n" + script + "\n})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});", str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


def read(relative):
    path = ROOT / relative
    assert path.resolve().is_relative_to(ROOT.resolve())
    return path.read_text(encoding="utf-8")


def test_discuss_bookmark_is_appended_last_only_when_allowed():
    assert probe(r"""
const Sidebar=load('components/Sidebar.tsx').default;
const allowed=mount(Sidebar,{studioAccessAllowed:true,onStudioClick:()=>{},discussAccessAllowed:true,onDiscussClick:()=>{}});
assert.equal(JSON.stringify(desktopTitles(allowed)),JSON.stringify(['对话','分身','广场','世界','设置','书斋','工作室','讨论群']));
allowed.close();
for(const value of [false,undefined]){
 const props={studioAccessAllowed:true,onStudioClick:()=>{}};
 if(value!==undefined)props.discussAccessAllowed=value;
 const instance=mount(Sidebar,props);
 assert.equal(JSON.stringify(desktopTitles(instance)),JSON.stringify(['对话','分身','广场','世界','设置','书斋','工作室']));
 assert.equal(discussEntries(instance).length,0);
 instance.close();
}
process.stdout.write(JSON.stringify(true));
""") is True


def test_mobile_tabbar_stays_six_links_without_discuss():
    assert probe(r"""
const Sidebar=load('components/Sidebar.tsx').default;
for(const value of [true,false,undefined]){
 const props={};
 if(value!==undefined)props.discussAccessAllowed=value;
 const instance=mount(Sidebar,props);await flush();
 assert.equal(all(mobile(instance),node=>node.type?.name==='Link').length,6);
 assert.equal(all(mobile(instance),node=>node.props?.title==='讨论群').length,0);
 instance.close();
}
assert(env.calls.every(call=>!call.url.includes('/api/discuss/')),'Sidebar must never request discuss access');
process.stdout.write(JSON.stringify(true));
""") is True


def test_discuss_bookmark_highlights_and_invokes_callback():
    assert probe(r"""
let clicks=0;
const instance=mount(load('components/Sidebar.tsx').default,{discussAccessAllowed:true,discussActive:true,onDiscussClick:()=>clicks++});
await flush();
const entries=discussEntries(instance);
assert.equal(entries.length,1);
const entry=entries[0];
assert.equal(entry.type,'button');
assert.equal(entry.props['aria-controls'],'discuss-drawer');
assert.equal(entry.props['aria-expanded'],true);
assert.equal(entry.props['aria-current'],'page');
assert(entry.props.className.includes('text-[color:var(--ink)]'));
entry.props.onClick();assert.equal(clicks,1);
instance.close();
process.stdout.write(JSON.stringify(true));
""") is True


def test_discuss_bookmark_highlights_on_its_own_pages():
    assert probe(r"""
const Sidebar=load('components/Sidebar.tsx').default;
for(const pathname of ['/discuss','/discuss/abc']){
 env.pathname=pathname;
 const instance=mount(Sidebar,{discussAccessAllowed:true});await flush();
 const entries=discussEntries(instance);
 assert.equal(entries.length,1);
 assert.equal(entries[0].props.href,'/discuss');
 assert.equal(entries[0].props['aria-current'],'page');
 instance.close();
}
process.stdout.write(JSON.stringify(true));
""") is True


def test_sidebar_source_has_no_discuss_request_helper():
    source = read("frontend/components/Sidebar.tsx")
    assert "@/lib/discuss" not in source
    assert "/api/discuss" not in source
    assert "discussAccessAllowed" in source
    nav = source.split("const navItems = [", 1)[1].split("];", 1)[0]
    assert re.findall(r'label: "([^"]+)"', nav) == ["对话", "分身", "广场", "世界", "设置", "书斋"]
    mobile_filter = source.split("items.filter(item =>", 1)[1].split(").map", 1)[0]
    assert 'item.href !== "/studio"' in mobile_filter
    assert 'item.href !== "/discuss"' in mobile_filter
    for contract in ("discussActive", 'pathname.startsWith("/discuss/")', '"discuss-drawer"'):
        assert contract in source


def test_page_drawer_type_and_discuss_access_scope():
    source = read("frontend/app/page.tsx")
    assert '"studio" | "novel" | null' in source
    declaration = re.search(r"type DrawerName = ([^;]+);", source)
    assert declaration
    names = re.findall(r'"([^"]+)"', declaration.group(1))
    assert names.index("discuss") == names.index("studio") - 1
    effect = source.split("const [discussAccess", 1)[1].split(
        "}, [hydrated, username, beginDiscussAccessRequest]);", 1
    )[0]
    for contract in (
        "checkDiscussAccess(request.signal)",
        "if (!request.isCurrent()) return;",
        "setDiscussAccess({ owner: username, allowed });",
        "setDiscussAccess({ owner: username, allowed: false });",
    ):
        assert contract in effect
    assert effect.count('current === "discuss" ? null : current') == 2
    assert 'import { checkDiscussAccess } from "@/lib/discuss";' in source
    assert 'const discussAllowed = discussAccess.owner === username && discussAccess.allowed;' in source
    for contract in (
        'onDiscussClick={() => { if (discussAllowed) toggleDrawer("discuss"); }}',
        "discussActive={discussOpen}",
        "discussAccessAllowed={discussAllowed}",
    ):
        assert contract in source


def test_page_discuss_drawer_gates_iframe_and_matches_studio_shell():
    source = read("frontend/app/page.tsx")
    assert source.index('id="studio-drawer"') < source.index('id="discuss-drawer"')
    drawer = source.split('id="discuss-drawer"', 1)[1].split("</Glaze>", 1)[0]
    for contract in (
        'aria-label="讨论群"',
        "aria-hidden={!discussOpen}",
        "inert={!discussOpen}",
        "...drawerStyle(discussOpen)",
        'if (event.key === "Escape") { closeDrawer(); focusVisibleDrawerTrigger("discuss-drawer"); }',
        "discussAllowed ? <iframe",
        "key={username}",
        'title="讨论群工作区"',
        'src="/discuss?embed=1"',
        'title="收起讨论群"',
        'aria-label="收起讨论群"',
        "暂未开放",
        '"calc((100vw - var(--rail-w) - 12px) * 2 / 3)"',
        "fixed top-3 bottom-3 right-3 z-[55] flex flex-col overflow-hidden outline-none",
        "drawer-panel",
    ):
        assert contract in drawer
    assert not re.search(r"discussOpen\s*&&\s*<iframe", drawer)
    # 讨论群抽屉和既有抽屉一样直接写完整的 drawer-panel 类名。
    assert source.count("drawer-panel") == 7
    assert "drawerPanelClass" not in source
    assert '"drawer" + "-panel"' not in source


def test_sidebar_scrollbar_hide_uses_important():
    source = read("frontend/components/Sidebar.tsx")
    assert "[scrollbar-width:none]!" in source
    assert "[&::-webkit-scrollbar]:hidden!" in source


def test_page_discuss_close_message_checks_origin_and_source():
    source = read("frontend/app/page.tsx")
    listener = source.split("const closeDiscuss =", 1)[1].split(
        'window.addEventListener("message", closeDiscuss);', 1
    )[0]
    for contract in (
        "event.origin !== window.location.origin",
        "event.source !== discussFrameRef.current?.contentWindow",
        'event.data?.type !== "fiona-discuss-close"',
        'setDrawer(current => current === "discuss" ? null : current)',
        'focusVisibleDrawerTrigger("discuss-drawer")',
    ):
        assert contract in listener
    assert 'window.removeEventListener("message", closeDiscuss)' in source
