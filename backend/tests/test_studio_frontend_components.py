"""Offline SSR and event probes for the studio composer, quote and shot cards."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
DRIVER = r"""
const fs=require('fs'), path=require('path'), assert=require('assert/strict');
const root=process.argv[1], frontend=path.join(root,'frontend');
const ts=require(path.join(frontend,'node_modules/typescript'));
const realReact=require(path.join(frontend,'node_modules/react'));
const realRuntime=require(path.join(frontend,'node_modules/react/jsx-runtime'));
const {renderToStaticMarkup}=require(path.join(frontend,'node_modules/react-dom/server'));
const env={mode:'hooks',owner:'studio-author',calls:[],timers:new Map(),nextTimer:1,listeners:new Map(),
  modalOpened:0,modalClosed:0,created:[],revoked:[],failure:null,pending:null};
global.fetch=()=>{throw Error('Real network is forbidden in studio probes');};
let current=null;
const equal=(a,b)=>a&&b&&a.length===b.length&&a.every((x,i)=>Object.is(x,b[i]));
function slot(init){const i=current.index++;if(!(i in current.hooks))current.hooks[i]=init();return current.hooks[i];}
const React={
 useState(initial){const instance=current,s=slot(()=>({value:typeof initial==='function'?initial():initial}));
  return [s.value,next=>{const v=typeof next==='function'?next(s.value):next;if(!Object.is(v,s.value)){s.value=v;instance.schedule();}}];},
 useRef:value=>slot(()=>({current:value})),
 useMemo(fn,deps){const s=slot(()=>({}));if(!equal(s.deps,deps)){s.deps=deps;s.value=fn();}return s.value;},
 useEffect(fn,deps){const instance=current,s=slot(()=>({}));if(!equal(s.deps,deps)){s.deps=deps;instance.pending.push(()=>{s.cleanup?.();s.cleanup=fn();});}},
 useId:()=>React.useRef('studio-probe-id').current,
};
React.useCallback=(fn,deps)=>React.useMemo(()=>fn,deps);
React.useSyncExternalStore=(subscribe,snapshot)=>{const instance=current;React.useEffect(()=>subscribe(()=>instance.schedule()),[subscribe]);return snapshot();};
const jsx=(type,props,key)=>({type,props:props??{},key}), runtime={jsx,jsxs:jsx,Fragment:'fragment'};
function all(tree,predicate){const result=[];function walk(node){if(Array.isArray(node)){node.forEach(walk);return;}
 if(!node||typeof node!=='object')return;if(predicate(node))result.push(node);walk(node.props?.children);}walk(tree);return result;}
function bindRefs(tree){for(const node of all(tree,n=>typeof n.type==='string'&&n.props.ref)){
 const ref=node.props.ref;if(!ref.current)ref.current={showModal(){env.modalOpened++;},close(){env.modalClosed++;},click(){}};}}
function mount(Component,props={}){const instance={hooks:[],pending:[],index:0,tree:null,props,dead:false,scheduled:false,
 schedule(){if(this.scheduled||this.dead)return;this.scheduled=true;queueMicrotask(()=>{this.scheduled=false;if(!this.dead)this.render();});},
 render(){this.index=0;current=this;try{this.tree=Component(this.props);}finally{current=null;}bindRefs(this.tree);for(const fn of this.pending.splice(0))fn();},
 close(){this.dead=true;for(const h of this.hooks)h.cleanup?.();}};instance.render();return instance;}
const text=node=>Array.isArray(node)?node.map(text).join(''):node&&typeof node==='object'?text(node.props?.children):node==null?'':String(node);
const button=(instance,label)=>{const result=all(instance.tree,n=>n.type==='button'&&text(n)===label)[0];assert(result,`Missing button: ${label}`);return result;};
const named=(instance,name)=>all(instance.tree,n=>n.type?.name===name)[0];
const field=(instance,id)=>{const result=all(instance.tree,n=>n.props?.id===id)[0];assert(result,id);return result;};
const error=instance=>all(instance.tree,n=>n.type?.name==='ErrorNotice').map(n=>n.props.message).join(' ');
async function flush(){for(let i=0;i<15;i++)await new Promise(setImmediate);}
global.setTimeout=(fn,delay)=>{const id=env.nextTimer++;env.timers.set(id,{fn,delay});return id;};
global.clearTimeout=id=>env.timers.delete(id);
global.document={hidden:false,activeElement:null,addEventListener(name,fn){if(!env.listeners.has(name))env.listeners.set(name,new Set());env.listeners.get(name).add(fn);},
 removeEventListener(name,fn){env.listeners.get(name)?.delete(fn);}};
global.window={addEventListener:document.addEventListener,removeEventListener:document.removeEventListener};
URL.createObjectURL=blob=>{const url=`blob:studio-${env.created.length}`;env.created.push({url,blob});return url;};
URL.revokeObjectURL=url=>env.revoked.push(url);
const params={first_frame_asset_id:'frame-1',prompt:'人物抬头看向窗外',provider:'wan',model:'wan3.0-video',resolution:'480P',duration:5,audio:true,duration_min_s:5,duration_max_s:5};
const quote={id:'quote-1',project_id:'project-1',items:[{id:'item-1',params,provider:'wan',model:'wan3.0-video',est_min_cny:1.05,est_max_cny:1.5}],
 total_min_cny:1.05,total_max_cny:1.5,expires_at:'2099-01-01T00:00:00Z',today:{committed_cny:3,remaining_cny:47}};
const job=(status,extra={})=>({id:'job-1',project_id:'project-1',owner:env.owner,provider:'wan',model:'wan3.0-video',params,status,
 task_id:null,est_min_cny:1.05,est_max_cny:1.5,reserved_cny:1.5,actual_cny:null,needs_recheck:0,usage:null,result_asset_id:null,
 error_code:'poll_timeout',error_message:null,created_at:'2026-10-16T00:00:00Z',updated_at:'2026-10-16T00:00:00Z',...extra});
class ApiError extends Error{constructor(message,status){super(message);this.status=status;}}
async function http(url,init={}){const call={url,method:init.method??'GET',body:init.body,signal:init.signal};env.calls.push(call);
 if(env.pending)return env.pending(call);
 if(env.failure)return {ok:false,status:env.failure.status,json:async()=>({detail:env.failure.detail})};
 const data=url.endsWith('/clips/quote')?quote:{id:'frame-uploaded'};
 return {ok:true,status:200,json:async()=>data,blob:async()=>new Blob(['image'],{type:'image/png'})};}
const auth={apiFetch:http,getUsername:()=>env.owner,ensureAccountIdentity:async()=>env.owner};
const agents={ApiError,apiJson:async(url,init)=>{const response=await http(url,init),data=await response.json();if(!response.ok)throw new ApiError(data.detail,response.status);return data;}};
const cache=new Map();
function load(relative){const filename=path.resolve(frontend,relative);assert(filename.startsWith(frontend+path.sep));if(cache.has(filename))return cache.get(filename).exports;
 const compiled=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const module={exports:{}};cache.set(filename,module);
 function localRequire(name){if(name==='react')return env.mode==='ssr'?realReact:React;if(name==='react/jsx-runtime')return env.mode==='ssr'?realRuntime:runtime;
  if(name==='lucide-react')return new Proxy({},{get:()=>()=>null});if(name==='@/lib/auth')return auth;if(name==='@/lib/agents')return agents;if(name==='@/lib/config')return {API_BASE:'/api'};
  let base=name.startsWith('@/')?path.join(frontend,name.slice(2)):name.startsWith('.')?path.resolve(path.dirname(filename),name):null;assert(base,`Unmocked import ${name}`);
  if(!path.extname(base))base+=fs.existsSync(base+'.tsx')?'.tsx':'.ts';return load(path.relative(frontend,base));}
 new Function('require','module','exports',compiled)(localRequire,module,module.exports);return module.exports;}
const callbacks=()=>({onCancel:async()=>{},onRecheck:async()=>{},onLinkTask:async()=>{},onRelease:async()=>{},onRefill:()=>{}});
function render(relative,props){env.mode='ssr';return renderToStaticMarkup(realReact.createElement(load(relative).default,props));}
function composer(props={}){const outer=mount(load('components/studio/ClipComposer.tsx').default,{owner:env.owner,projectId:'project-1',onQuote:()=>{},...props});return mount(outer.tree.type,outer.tree.props);}
"""


def probe(script):
    dependencies = {
        "typescript": "typescript/lib/typescript.js",
        "react": "react/index.js",
        "react/jsx-runtime": "react/jsx-runtime.js",
        "react-dom/server": "react-dom/server.js",
    }
    missing = [
        name for name, entry in dependencies.items()
        if not (ROOT / "frontend" / "node_modules" / entry).is_file()
    ]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")
    result = subprocess.run(
        ["node", "-e", DRIVER + "\n(async()=>{\n" + script + "\n})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1;});", str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


def test_shot_card_ssr_all_thirteen_statuses_and_actions():
    assert probe(r"""
const cases={queued:['排队中',['取消']],submitting:['提交中',[]],submitted:['已提交',['重新查询']],running:['生成中',['重新查询']],
 succeeded:['下载中',[]],downloaded:['已完成',[]],rejected:['被拒绝（未扣费）',['用同样参数重新报价']],
 uncertain:['结果不确定',['关联任务号','确认未扣费，释放额度']],failed:['失败',['用同样参数重新报价']],
 filtered:['被内容审核拦截（未扣费）',['用同样参数重新报价']],expired:['结果已过期',['用同样参数重新报价']],
 cancelled:['已取消',['用同样参数重新报价']],released:['已释放（确认未扣费）',['用同样参数重新报价']]};
const knownActions=['取消','重新查询','用同样参数重新报价','关联任务号','确认未扣费，释放额度'];
for(const [status,[label,actions]] of Object.entries(cases)){
 const html=render('components/studio/ShotCard.tsx',{job:job(status),...callbacks()});
 assert(html.includes(`class="tag">${label}</span>`),`${status} label`);
 for(const action of knownActions)assert.equal(new RegExp('>'+action+'</button>').test(html),actions.includes(action),`${status}: ${action}`);
 if(status==='uncertain')assert(html.includes('可能已扣费，请勿直接重试，去控制台核对'));
 if(actions.includes('用同样参数重新报价'))assert(html.includes('查询超时，请重新查询'));
}
for(const extra of [{task_id:'task-1'},{needs_recheck:1}]){
 const html=render('components/studio/ShotCard.tsx',{job:job('uncertain',extra),...callbacks()});assert(html.includes('>重新查询</button>'));
}
const recheck=render('components/studio/ShotCard.tsx',{job:job('succeeded',{needs_recheck:1}),...callbacks()});assert(recheck.includes('>重新查询</button>'));
assert.equal(env.calls.length,0);process.stdout.write('true');
""") is True


def test_shot_card_ssr_video_and_settled_money():
    assert probe(r"""
const html=render('components/studio/ShotCard.tsx',{job:job('downloaded',{result_asset_id:'result-7',actual_cny:1.2}),...callbacks()});
assert(html.includes('<video'));assert(html.includes('controls=""'));assert(html.includes('preload="metadata"'));
assert(html.includes('src="/api/studio/assets/result-7/file"'));assert(html.includes('实付'));assert(html.includes('¥1.20'));
assert(!html.includes('预留'));assert.equal(env.calls.length,0);process.stdout.write('true');
""") is True


def test_shot_card_retry_only_refills_and_release_requires_confirmation():
    assert probe(r"""
let refilled=null,releases=0;const actions={...callbacks(),onRefill:value=>{refilled=value;},onRelease:async()=>{releases++;}};
const retry=mount(load('components/studio/ShotCard.tsx').default,{job:job('failed'),...actions});
button(retry,'用同样参数重新报价').props.onClick();assert.deepEqual(refilled,params);assert.notEqual(refilled,params);assert.equal(env.calls.length,0);
const card=mount(load('components/studio/ShotCard.tsx').default,{job:job('uncertain'),...actions});
button(card,'确认未扣费，释放额度').props.onClick();await flush();assert.equal(releases,0);
const element=named(card,'ReleaseDialog');assert(element);const dialog=mount(element.type,element.props);assert.equal(env.modalOpened,1);
assert(text(dialog.tree).includes('请先在供应商控制台核对'));button(dialog,'取消').props.onClick();await flush();assert.equal(releases,0);assert(!named(card,'ReleaseDialog'));
button(card,'确认未扣费，释放额度').props.onClick();await flush();const next=named(card,'ReleaseDialog'),confirm=mount(next.type,next.props);
const click=button(confirm,'我已核实未扣费，释放额度').props.onClick;click();click();await flush();assert.equal(releases,1);assert(!named(card,'ReleaseDialog'));
assert.equal(env.calls.length,0);process.stdout.write('true');
""") is True


def test_quote_ssr_two_decimals_correct_confirmation_and_expiry():
    assert probe(r"""
const props={quote,onConfirm:async()=>{},onClose:()=>{}};
const html=render('components/studio/QuoteDialog.tsx',props);
assert(html.includes('¥1.05–¥1.50'));assert(html.includes('确认生成（最多 ¥1.50）'));assert(html.includes('¥47.00'));
assert(html.includes('万相 3.0'));assert(html.includes('480P'));assert(html.includes('5 秒'));assert(html.includes('音频开'));
const expired=render('components/studio/QuoteDialog.tsx',{...props,quote:{...quote,expires_at:'2000-01-01T00:00:00Z'}});
assert(/<button[^>]*disabled=""[^>]*>报价已过期，请重新报价<\/button>/.test(expired));assert.equal(env.calls.length,0);process.stdout.write('true');
""") is True


def test_quote_cancel_no_request_countdown_and_confirm_lock_detail():
    assert probe(r"""
let closes=0,confirms=0,finish;const component=load('components/studio/QuoteDialog.tsx').default;
const cancel=mount(component,{quote,onClose:()=>{closes++;},onConfirm:async()=>{confirms++;}});button(cancel,'取消').props.onClick();assert.equal(closes,1);assert.equal(confirms,0);assert.equal(env.calls.length,0);cancel.close();
const future={...quote,expires_at:new Date(Date.now()+60000).toISOString()};
const dialog=mount(component,{quote:future,onClose:()=>{},onConfirm:()=>{confirms++;return new Promise(resolve=>finish=resolve);}});
const click=button(dialog,'确认生成（最多 ¥1.50）').props.onClick;click();click();await flush();assert.equal(confirms,1);assert(button(dialog,'确认中…').props.disabled);finish();await flush();
const failure=mount(component,{quote,onClose:()=>{},onConfirm:async()=>{throw new ApiError('超出今日上限',409);}});button(failure,'确认生成（最多 ¥1.50）').props.onClick();await flush();assert.equal(error(failure),'超出今日上限');failure.close();
const originalNow=Date.now;Date.now=()=>new Date(future.expires_at).getTime()+1;
for(const [key,timer] of [...env.timers]){env.timers.delete(key);await timer.fn();}await flush();
assert(button(dialog,'报价已过期，请重新报价').props.disabled);Date.now=originalNow;dialog.close();process.stdout.write('true');
""") is True


def test_composer_local_validation_and_refill_do_not_request():
    assert probe(r"""
const module=load('components/studio/ClipComposer.tsx');assert.equal(module.validateStudioFirstFrame({type:'image/gif',size:10}),'首帧仅支持 PNG、JPEG、WebP 图片。');
assert.equal(module.validateStudioFirstFrame({type:'image/png',size:20*1024*1024+1}),'首帧不能超过 20MB。');
for(const type of ['image/png','image/jpeg','image/webp'])assert.equal(module.validateStudioFirstFrame({type,size:20*1024*1024}),'');
const card=composer({refill:{token:1,params}});assert.equal(field(card,'studio-prompt').props.value,params.prompt);assert.equal(field(card,'studio-duration').props.value,'5');
assert(button(card,'万相 3.0').props['aria-pressed']);assert(button(card,'480P').props['aria-pressed']);assert.equal(env.calls.length,0);
const picker=all(card.tree,n=>n.type==='input'&&n.props.type==='file')[0];assert.equal(picker.props.accept,'image/png,image/jpeg,image/webp');
await picker.props.onChange({target:{files:[{type:'image/gif',size:20}],value:'bad.gif'}});await flush();assert(error(card).includes('仅支持'));
await picker.props.onChange({target:{files:[{type:'image/png',size:20*1024*1024+1}],value:'big.png'}});await flush();assert(error(card).includes('20MB'));assert.equal(env.calls.length,0);card.close();process.stdout.write('true');
""") is True


def test_composer_quote_click_lock_chinese_422_and_account_cancellation():
    assert probe(r"""
let quotes=0,finish;const card=composer({refill:{token:1,params},onQuote:()=>{quotes++;}});
env.pending=()=>new Promise(resolve=>finish=resolve);const form=all(card.tree,n=>n.type==='form')[0],event={preventDefault(){}};
form.props.onSubmit(event);form.props.onSubmit(event);await flush();assert.equal(env.calls.length,1);assert(button(card,'报价中…').props.disabled);
finish({ok:true,status:200,json:async()=>quote});await flush();assert.equal(quotes,1);
env.pending=null;env.failure={status:422,detail:'时长必须为 -1 或 2–30 的整数秒'};
field(card,'studio-duration').props.onChange({target:{value:'99'}});await flush();all(card.tree,n=>n.type==='form')[0].props.onSubmit(event);await flush();assert.equal(error(card),env.failure.detail);
env.failure=null;env.pending=()=>new Promise(resolve=>finish=resolve);all(card.tree,n=>n.type==='form')[0].props.onSubmit(event);await flush();const active=env.calls.at(-1);
env.owner='other-author';for(const listener of env.listeners.get('fiona-user-changed')??[])listener();assert(active.signal.aborted);
finish({ok:true,status:200,json:async()=>quote});await flush();assert.equal(quotes,1);card.close();process.stdout.write('true');
""") is True


def test_composer_uploads_valid_file_before_quote_and_signals_busy():
    assert probe(r"""
const events=[];let refreshed=0,quoted=null;const card=composer({onQuote:value=>quoted=value,onBusyChange:value=>events.push(value),onChanged:async()=>{refreshed++;}});
assert(button(card,'报价').props.disabled);const picker=all(card.tree,n=>n.type==='input'&&n.props.type==='file')[0];
const file=new Blob(['image'],{type:'image/webp'});await picker.props.onChange({target:{files:[file],value:'frame.webp'}});await flush();
assert.equal(env.calls.length,1);assert.equal(env.calls[0].url,'/api/studio/projects/project-1/assets');assert(env.calls[0].body instanceof FormData);
assert.equal(named(card,'StudioAssetImage').props.assetId,'frame-uploaded');assert.equal(refreshed,1);assert.deepEqual(events,[true,false]);
field(card,'studio-prompt').props.onChange({target:{value:'一阵风吹动窗帘'}});await flush();
await all(card.tree,n=>n.type==='form')[0].props.onSubmit({preventDefault(){}});await flush();
const request=env.calls.at(-1);assert.equal(request.url,'/api/studio/projects/project-1/clips/quote');
assert.equal(JSON.parse(request.body).first_frame_asset_id,'frame-uploaded');assert.equal(quoted.id,'quote-1');assert.equal(refreshed,2);assert.deepEqual(events,[true,false,true,false]);
card.close();process.stdout.write('true');
""") is True


def test_authenticated_asset_preview_releases_object_url_and_aborts():
    assert probe(r"""
const component=load('components/studio/StudioAssetImage.tsx').default;
const outer=mount(component,{assetId:'frame-1',alt:'首帧'}),image=mount(outer.tree.type,outer.tree.props);await flush();
assert.equal(env.calls[0].url,'/api/studio/assets/frame-1/file');assert(env.calls[0].signal);assert.equal(env.created.length,1);
assert.equal(all(image.tree,n=>n.type==='img')[0].props.src,'blob:studio-0');image.close();assert(env.calls[0].signal.aborted);assert.deepEqual(env.revoked,['blob:studio-0']);outer.close();process.stdout.write('true');
""") is True
