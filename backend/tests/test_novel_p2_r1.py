"""R1 behavior probes: transpile checkout TS in memory, with no browser or network.

The small hook driver renders just the owning component (children stay elements),
so real effects, event handlers and request wrappers run against an in-memory API.
"""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from novel.schemas import compact

ROOT = Path(__file__).resolve().parents[2]

DRIVER = r"""
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const root = process.argv[1], frontend = path.join(root, 'frontend');
const ts = require(path.join(frontend, 'node_modules/typescript'));
const env = { owner: 'r1-author', calls: [], instances: [], timers: new Map(), nextTimer: 1,
  failures: new Map(), listeners: new Map(), search: '', pushes: [] };
let current = null;
const equal = (a,b) => a && b && a.length === b.length && a.every((x,i) => Object.is(x,b[i]));
function slot(init) { const i=current.index++; if (!(i in current.hooks)) current.hooks[i]=init(); return current.hooks[i]; }
const React = {
  useState(initial) {
    const instance=current;
    const state=slot(()=>{const s={value:typeof initial==='function'?initial():initial};
      s.set=next=>{const value=typeof next==='function'?next(s.value):next;
        if(!Object.is(value,s.value)){s.value=value;instance.schedule();}};return s;});
    return [state.value,state.set];
  },
  useRef: value=>slot(()=>({current:value})),
  useMemo(fn,deps) {const memo=slot(()=>({}));if(!equal(memo.deps,deps)){memo.value=fn();memo.deps=deps;}return memo.value;},
  useEffect(fn,deps) {const instance=current, effect=slot(()=>({}));if(!equal(effect.deps,deps)){
    effect.deps=deps;instance.pending.push(()=>{effect.cleanup?.();effect.cleanup=fn();});}},
  useId: ()=>React.useRef('r1-test-id').current,
};
React.useCallback=(fn,deps)=>React.useMemo(()=>fn,deps);
React.useSyncExternalStore=(subscribe,snapshot)=>{React.useEffect(()=>subscribe(()=>{}),[subscribe]);return snapshot();};
const jsx=(type,props,key)=>({type,props:props??{},key});
const runtime={jsx,jsxs:jsx,Fragment:'fragment'};
function mount(Component,props={}) {
  const instance={hooks:[],pending:[],scheduled:false,dead:false,index:0,tree:null,
    schedule(){if(!this.scheduled&&!this.dead){this.scheduled=true;queueMicrotask(()=>{this.scheduled=false;if(!this.dead)this.render();});}},
    render(){this.index=0;current=this;try{this.tree=Component(props);}finally{current=null;}
      const effects=this.pending.splice(0);for(const effect of effects)effect();},
    close(){this.dead=true;for(const h of this.hooks)h.cleanup?.();}};
  env.instances.push(instance);instance.render();return instance;
}
global.setTimeout=(fn,delay)=>{const id=env.nextTimer++;env.timers.set(id,{fn,delay});return id;};
global.clearTimeout=id=>env.timers.delete(id);
global.document={hidden:false,activeElement:null,querySelector:()=>null,
  addEventListener:(name,fn)=>{if(!env.listeners.has(name))env.listeners.set(name,new Set());env.listeners.get(name).add(fn);},
  removeEventListener:(name,fn)=>env.listeners.get(name)?.delete(fn)};
global.window={location:{origin:'http://local.invalid'},addEventListener:()=>{},removeEventListener:()=>{}};
window.parent=window;
const clone=value=>JSON.parse(JSON.stringify(value));
env.catalog={agents:[
 ['editor',true],['writer',true],['archivist',true],['reviewer',false],['plot_architect',false],
 ['character_advocate',false],['reader_rep',false],['twist_designer',false],['pacing_advisor',false],['adaptation_advisor',false]
].map(([id,required])=>({id,name:id,description:id,category:'deliberation',required})),
 models:['dashscope:qwen3.8-max','deepseek:deepseek-flash','ark:doubao-seed-2-1-pro-260915'].map(id=>({id,price:{input:2,output:6}})),
 allowed_models:{editor:['dashscope:qwen3.8-max','ark:doubao-seed-2-1-pro-260915','byok:self'],
 writer:['deepseek:deepseek-flash','dashscope:qwen3.8-max','byok:self'],
 archivist:['dashscope:qwen3.8-max'],reviewer:['dashscope:qwen3.8-max']},byok:null,notice:'说明'};
env.book={id:'r1-book',title:'书',status:'completed',pause_reason:null,bible_version:1,chapters_done:60,words_done:60000,
 max_chapters:70,budget_strawberries:10000,spent_strawberries:8000,reserved_strawberries:0,pending_notes:0,
 created_at:'2026-01-01 00:00:00',updated_at:'2026-01-01 00:00:00',completed_at:null,last_error:null,compass:{logline:'梗概'},
 config:{seed_idea:'思路',agents:{editor:'dashscope:qwen3.8-max',writer:'deepseek:deepseek-flash',archivist:'dashscope:qwen3.8-max'},
 panel_mode:'critique',automation:'per_batch',batch_size:5,target:{min_chapters:50,max_chapters:70,chapter_words:2000},
 adaptation:{max_main_characters:6,max_scenes_per_chapter:3},budget_strawberries:10000},
 chapters:Array.from({length:60},(_,i)=>({chapter:i+1,title:`第${i+1}章 章名`,status:'completed',words:1000,flags:[],edited_by_user:false}))};
env.bible={version:1,compass:env.book.compass,locked:{characters:[],world_rules:[],style_guide:{}},dynamic:{foreshadowing:[],character_states:{}}};
env.notes=[];
async function http(url,init={}) {
 const method=init.method??'GET';env.calls.push(`${method} ${url}`);
 const failure=env.failures.get(`${method} ${url}`);
 if(failure) return {ok:false,status:failure.status,json:async()=>({detail:failure.message})};
 let data;
 if(url==='/api/novels')data=method==='GET'?[env.book]:env.book;
 else if(url==='/api/novels/catalog')data=env.catalog;
 else if(url==='/api/strawberry')data={username:env.owner,balance:50000};
 else if(url==='/api/novels/estimate')data={per_chapter:{min:10,max:20},total:{min:500,max:1400},method:'baseline'};
 else if(url.endsWith('/bible'))data=env.bible;
 else if(url.endsWith('/notes')){if(method==='POST')env.notes.push({id:1,text:'留言',status:'pending',created_at:'2026-01-01 00:00:00',adopted:null,response:null,delivered_chapter:null});data=method==='GET'?env.notes:{status:'pending'};}
 else if(/\/chapters\/\d+$/.test(url)){
  const number=Number(url.split('/').at(-1));const summary=env.book.chapters.find(c=>c.chapter===number);
  if(method==='PUT'){summary.edited_by_user=true;data={message:'已保存',rearchiving:false};}
  else data={...summary,novel_id:env.book.id,body:'# 第'+number+'章 章名\n正文',review:[],review_summary:{retained:0,discarded:0},meeting:{},archive:{},updated_at:'now'};
 } else data=env.book;
 return {ok:true,status:200,json:async()=>clone(data),headers:{get:()=> 'text/markdown'},blob:async()=>new Blob(['正文'])};
}
class ApiError extends Error {constructor(message,status){super(message);this.status=status;}}
const agents={ApiError,apiJson:async(url,init)=>{const r=await http(url,init),data=await r.json();if(!r.ok)throw new ApiError(data.detail,r.status);if(data===null)throw Error('服务器未返回完整数据');return data;}};
const auth={getUsername:()=>env.owner,ensureAccountIdentity:async()=>env.owner,apiFetch:http};
const cache=new Map();
function load(relative) {
 const filename=path.resolve(frontend,relative);assert(filename.startsWith(frontend+path.sep));
 if(cache.has(filename))return cache.get(filename).exports;
 const source=fs.readFileSync(filename,'utf8');
 const compiled=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const module={exports:{}};cache.set(filename,module);
 const localRequire=name=>{
  if(name==='react')return React;if(name==='react/jsx-runtime')return runtime;
  if(name==='next/link')return {__esModule:true,default:function Link(){}};
  if(name==='next/navigation')return {useRouter:()=>({push:x=>env.pushes.push(x)}),useSearchParams:()=>new URLSearchParams(env.search)};
  if(name==='lucide-react')return new Proxy({},{get:(_,key)=>function Icon(){return jsx('svg',{'data-icon':String(key)});}});
  if(name==='@/lib/agents')return agents;if(name==='@/lib/auth')return auth;if(name==='@/lib/config')return {API_BASE:'/api'};
  if(['@/components/Sidebar','@/components/Glaze','@/components/InkLandscape'].includes(name))return {__esModule:true,default:function Framework(){}};
  let base=name.startsWith('@/')?path.join(frontend,name.slice(2)):name.startsWith('.')?path.resolve(path.dirname(filename),name):null;
  assert(base,`Unmocked external import: ${name}`);
  if(!path.extname(base))base+=fs.existsSync(base+'.tsx')?'.tsx':'.ts';
  return load(path.relative(frontend,base));
 };
 new Function('require','module','exports',compiled)(localRequire,module,module.exports);return module.exports;
}
function all(tree,predicate) {const found=[];function visit(node){if(Array.isArray(node)){node.forEach(visit);return;}if(!node||typeof node!=='object')return;if(predicate(node))found.push(node);visit(node.props?.children);}visit(tree);return found;}
const named=(instance,name)=>all(instance.tree,n=>n.type?.name===name)[0];
const id=(instance,value)=>all(instance.tree,n=>n.props?.id===value)[0];
const count=path=>env.calls.filter(x=>x===`GET /api/novels/r1-book/${path}`).length;
async function flush(){for(let i=0;i<25;i++)await new Promise(setImmediate);}
async function timer(delay){const pair=[...env.timers].find(([,t])=>t.delay===delay);assert(pair,`No ${delay}ms timer`);env.timers.delete(pair[0]);await pair[1].fn();await flush();}
async function screen(relative,props={}){const outer=mount(load(relative).default,props);await flush();const inner=mount(outer.tree.type,outer.tree.props);await flush();while([...env.timers.values()].some(t=>t.delay===0))await timer(0);return inner;}
async function clickTab(instance,controls){const button=all(instance.tree,n=>n.type==='button'&&n.props['aria-controls']===controls)[0];assert(button,controls);button.props.onClick();await flush();}
"""


def probe(script):
    if not (ROOT / "frontend" / "node_modules" / "typescript").exists():
        pytest.skip("frontend/node_modules/typescript is unavailable")
    if not shutil.which("node"):
        pytest.skip("node is unavailable")
    result = subprocess.run(
        ["node", "-e", DRIVER + "\n(async()=>{\n" + script + "\n})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});", str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


def test_r1_error_mapping_title_display_and_local_dates():
    result = probe(r"""
const lib=load('lib/novels.ts');
assert.equal(lib.novelErrorMessage(new ApiError('Not Found',404)),'小说工坊尚未开放');
assert.equal(lib.novelErrorMessage(new ApiError('小说不存在',404),true),'小说不存在');
assert.equal(lib.novelErrorMessage(new ApiError('其他原因',403)),'你的账号暂未开通小说工坊');
for(const title of ['第二章 最后的底片','第2章：最后的底片','第两百〇二章、 最后的底片'])assert.equal(lib.displayNovelChapterTitle(title),'最后的底片');
assert.equal(lib.displayNovelChapterTitle('第二章'),'第二章');
assert.equal(lib.displayNovelChapterTitle('第三章节的秘密'),'第三章节的秘密');
assert.equal(lib.displayNovelChapterTitle('第十二夜'),'第十二夜');
assert.equal(lib.displayNovelChapterTitle(''), '');
assert.equal(lib.formatNovelDate('2026-01-01 12:00:00'),new Date('2026-01-01T12:00:00Z').toLocaleString('zh-CN',{hour12:false}));
assert.equal(lib.formatNovelDate('not-a-date'),'not-a-date');
process.stdout.write(JSON.stringify(true));
""")
    assert result is True


def test_r1_catalog_order_defaults_and_fallback():
    assert probe(r"""
const lib=load('lib/novels.ts'), {defaultNovelAgents}=load('components/novel/NovelWizard.tsx');
const selection=defaultNovelAgents(env.catalog);
assert.deepEqual(selection,{editor:'dashscope:qwen3.8-max',writer:'deepseek:deepseek-flash',archivist:'dashscope:qwen3.8-max',reviewer:'dashscope:qwen3.8-max',plot_architect:'dashscope:qwen3.8-max',character_advocate:'ark:doubao-seed-2-1-pro-260915',twist_designer:'deepseek:deepseek-flash'});
env.catalog.allowed_models.editor=['ark:doubao-seed-2-1-pro-260915','dashscope:qwen3.8-max'];
assert.deepEqual(lib.novelModelOptions(env.catalog,'editor').map(x=>x.value),env.catalog.allowed_models.editor);
env.catalog.allowed_models.writer=['dashscope:qwen3.8-max'];
assert.equal(defaultNovelAgents(env.catalog).writer,'dashscope:qwen3.8-max');
assert.deepEqual(lib.novelModelOptions(env.catalog,'reader_rep').map(x=>x.value),env.catalog.models.map(x=>x.id));
process.stdout.write(JSON.stringify(true));
""") is True


def test_r1_setup_compact_matches_backend_and_budget_is_strict():
    cases = ['“甲”' * 10, '甲乙' * 10, "  … … ...... ", "「甲」『乙』\"丙\"'丁'", "\x1c\x85甲\u3000乙\ufeff", "😀" * 20]
    expected = [compact(value) for value in cases]
    actual = probe("const values=" + json.dumps(cases) + r""";
const setup=load('components/novel/SetupEditor.tsx');
const settings=load('components/novel/NovelSettingsDialog.tsx');
for(const [budget,spent] of [[100,80],[100,99],[200,80],[1,1]]){
 const min=settings.minimumNovelResumeBudget(budget,spent);
 assert.equal(min,Math.max(budget+1,Math.ceil(spent*1.25)+1));
 assert(spent*5<min*4);assert(min>budget);
}
assert.equal(settings.minimumNovelResumeBudget(100,50,1000),1001);
for(const invalid of [NaN,Infinity,-1])assert.equal(settings.minimumNovelResumeBudget(100,80,invalid),101);
process.stdout.write(JSON.stringify(values.map(setup.compactSetupText)));
""")
    assert actual == expected


def test_r1_shelf_reads_only_one_list_per_round():
    assert probe(r"""
env.book.status='running';
await screen('components/novel/NovelShelf.tsx');
assert.deepEqual(env.calls,['GET /api/novels']);
for(let i=0;i<3;i++)await timer(3000);
assert.equal(env.calls.length,4);assert(env.calls.every(x=>x==='GET /api/novels'));
process.stdout.write(JSON.stringify(true));
""") is True


def test_r1_completed_workbench_does_not_fetch_all_chapters():
    assert probe(r"""
await screen('components/novel/NovelWorkbench.tsx',{id:'r1-book'});
assert.deepEqual(env.calls.filter(x=>/GET .*\/chapters\//.test(x)),['GET /api/novels/r1-book/chapters/60']);
assert(![...env.timers.values()].some(t=>t.delay===3000));
process.stdout.write(JSON.stringify(true));
""") is True


def test_r1_workbench_reads_by_change_visibility_and_saves_chapter_once():
    assert probe(r"""
env.book.status='running';
const work=await screen('components/novel/NovelWorkbench.tsx',{id:'r1-book'});
assert.equal(env.calls.filter(x=>/GET .*\/chapters\//.test(x)).length,1);
assert.equal(count('bible'),1);
const initialNotes=count('notes');
for(let i=0;i<3;i++)await timer(3000);
assert.equal(count('bible'),1);assert.equal(count('notes'),initialNotes);assert.equal(count('chapters/60'),1);
env.book.bible_version++;await timer(3000);assert.equal(count('bible'),2);
env.book.chapters[59].words++;await timer(3000);assert.equal(count('chapters/60'),2);
await clickTab(work,'novel-details');await clickTab(work,'novel-detail-notes');const notesVisible=count('notes');assert(notesVisible>initialNotes);
await timer(3000);assert(count('notes')>notesVisible);
await clickTab(work,'novel-detail-meeting');
const beforeSave=count('chapters/60');
assert.equal(await named(work,'ChapterReader').props.onSave('正文改稿'),'已保存');await flush();
assert.equal(count('chapters/60')-beforeSave,1);
const controls=all(work.tree,n=>n.props?.['aria-controls']).map(n=>n.props['aria-controls']);
const ids=new Set(all(work.tree,n=>n.props?.id).map(n=>n.props.id));
assert(controls.every(value=>ids.has(value)));
for(const name of ['novel-directory','novel-reader','novel-details'])assert.equal(id(work,name).props.role,'tabpanel');
document.hidden=true;for(const fn of env.listeners.get('visibilitychange')??[])fn();
assert(![...env.timers.values()].some(t=>t.delay===3000));
process.stdout.write(JSON.stringify(true));
""") is True


def test_r1_local_error_is_not_duplicated_and_global_error_survives_poll():
    assert probe(r"""
env.book.status='running';
const work=await screen('components/novel/NovelWorkbench.tsx',{id:'r1-book'});
env.failures.set('PUT /api/novels/r1-book/chapters/60',{status:409,message:'章节正在改稿'});
await assert.rejects(()=>named(work,'ChapterReader').props.onSave('改稿'),/章节正在改稿/);await flush();
assert(!all(work.tree,n=>n.type?.name==='ErrorNotice').some(n=>n.props.message==='章节正在改稿'));
env.failures.set('POST /api/novels/r1-book/pause',{status:409,message:'现在不能暂停'});
await assert.rejects(()=>named(work,'GateBanner').props.onAction('pause'),/现在不能暂停/);await flush();
assert.equal(all(work.tree,n=>n.type?.name==='ErrorNotice').filter(n=>n.props.message==='现在不能暂停').length,1);
await timer(3000);
assert.equal(all(work.tree,n=>n.type?.name==='ErrorNotice').filter(n=>n.props.message==='现在不能暂停').length,1);
process.stdout.write(JSON.stringify(true));
""") is True


def test_r1_budget_input_does_not_request_another_estimate():
    assert probe(r"""
const wizard=await screen('components/novel/NovelWizard.tsx');
id(wizard,'novel-seed').props.onChange({target:{value:'失落信件的故事'}});await flush();
const next=()=>all(wizard.tree,n=>n.type==='form')[0].props.onSubmit({preventDefault(){}});
next();await flush();next();await flush();await timer(600);
const estimates=()=>env.calls.filter(x=>x==='POST /api/novels/estimate').length;
assert.equal(estimates(),1);
id(wizard,'novel-budget').props.onChange({target:{value:'50000'}});await flush();
assert(![...env.timers.values()].some(t=>t.delay===600));assert.equal(estimates(),1);
id(wizard,'novel-batch').props.onChange({target:{value:'3'}});await flush();await timer(600);
assert.equal(estimates(),2);
process.stdout.write(JSON.stringify(true));
""") is True


def test_r1_escape_respects_editable_focus_composition_and_dialog():
    assert probe(r"""
const {canCloseNovelDrawer}=load('components/novel/NovelShell.tsx');
const event={key:'Escape',defaultPrevented:false,isComposing:false};
assert(canCloseNovelDrawer(event,null,false));
for(const tag of ['input','textarea','select','contenteditable'])assert(!canCloseNovelDrawer(event,{closest:()=>({tag})},false));
assert(!canCloseNovelDrawer({...event,isComposing:true},null,false));
assert(!canCloseNovelDrawer({...event,defaultPrevented:true},null,false));
assert(!canCloseNovelDrawer(event,null,true));
assert(!canCloseNovelDrawer({...event,key:'Enter'},null,false));
process.stdout.write(JSON.stringify(true));
""") is True


@pytest.mark.parametrize("file,path", [
    ("NovelShelf", "/api/novels"),
    ("NovelWizard", "/api/novels/catalog"),
    ("NovelWorkbench", "/api/novels/r1-book"),
])
def test_r1_all_pages_map_closed_workshop_404(file, path):
    assert probe("env.failures.set(" + json.dumps("GET " + path) + r""",{status:404,message:'Not Found'});
const page=await screen('components/novel/""" + file + r""".tsx',{id:'r1-book'});
assert.equal(all(page.tree,n=>n.type?.name==='ErrorNotice').filter(n=>n.props.message==='小说工坊尚未开放').length,1);
process.stdout.write(JSON.stringify(true));
""") is True


def test_r1_mobile_prices_and_content_details_are_rendered():
    assert probe(r"""
function plain(node){if(Array.isArray(node))return node.map(plain).join('');if(node==null||typeof node==='boolean')return '';if(typeof node!=='object')return String(node);return plain(node.props?.children);}
const fields=load('components/novel/NovelModelFields.tsx').default;
const selected=load('components/novel/NovelWizard.tsx').defaultNovelAgents(env.catalog);
let tree=fields({catalog:env.catalog,agents:selected,onChange(){},allowRoleChanges:true});
let prices=all(tree,n=>n.type==='p'&&n.props.className?.includes('mobile:block'));
assert.equal(prices.length,10);assert(prices.every(n=>plain(n).includes('每千 token 输入/输出约 2/6 草莓')));
assert(prices.every(n=>all(n,child=>child.props?.className==='readout').length===1));
env.catalog.byok={provider:'anthropic',model:'claude-example'};selected.editor='byok:self';
tree=fields({catalog:env.catalog,agents:selected,onChange(){},allowRoleChanges:true});
assert(all(tree,n=>n.type==='p'&&n.props.className?.includes('mobile:block')).some(n=>plain(n).includes('我的模型（Anthropic·claude-example）· 不扣草莓')));
const chapter={chapter:2,title:'第二章 最后的底片',status:'completed',words:1000,flags:['stale'],edited_by_user:true,body:'正文',review:[],review_summary:{retained:0,discarded:0}};
tree=load('components/novel/ChapterList.tsx').default({chapters:[chapter],selectedChapter:2,onSelect(){}});
assert.equal(all(tree,n=>n.type==='button')[0].props['aria-current'],'true');assert(!plain(tree).includes('第二章'));
const reader=mount(load('components/novel/ChapterReader.tsx').default,{chapter,loading:false,busy:false,onSave:async()=>null});
assert(!plain(all(reader.tree,n=>n.type==='h2')[0]).includes('第二章'));
const note={id:1,text:'留言',status:'pending',created_at:'2026-01-01 12:00:00',adopted:null,response:null,delivered_chapter:null};
const notes=mount(load('components/novel/NotesPanel.tsx').default,{notes:[note],loading:false,busy:false,onSubmit:async()=>{}});
const time=all(notes.tree,n=>n.type==='time')[0];assert.equal(time.props.dateTime,'2026-01-01T12:00:00Z');assert.equal(plain(time),load('lib/novels.ts').formatNovelDate(note.created_at));
env.bible.dynamic.foreshadowing=[{id:'F1',description:'信',planted_chapter:0,status:'open'}];
tree=load('components/novel/BiblePanel.tsx').default({bible:env.bible,loading:false});
assert(plain(tree).includes('立项时'));assert(!plain(tree).includes('第 0 章'));
process.stdout.write(JSON.stringify(true));
""") is True


def test_r1_budget_and_setup_validation_stop_invalid_requests_locally():
    assert probe(r"""
let saves=0;
env.book.status='paused';env.book.pause_reason='budget_80';env.book.budget_strawberries=100;env.book.spent_strawberries=50;env.book.config._budget_at_pause=1000;
const dialog=mount(load('components/novel/NovelSettingsDialog.tsx').default,{book:env.book,catalog:env.catalog,busy:false,resumeAfter:true,onSave:async()=>{saves++;},onClose(){}});
const save=()=>all(dialog.tree,n=>n.type==='button'&&n.props.className?.includes('btn-primary'))[0].props.onClick();
save();await flush();assert.equal(saves,0);
assert.equal(id(dialog,'novel-adjust-budget-error').props.children,'预算至少要 1001 草莓才能继续');
all(dialog.tree,n=>n.type==='input'&&n.props.type==='number')[0].props.onChange({target:{value:'1001'}});await flush();
save();await flush();assert.equal(saves,1);
const setup=load('components/novel/SetupEditor.tsx');
const compass={title:'书名',logline:'梗概',theme:'主题',candidate_endings:[{summary:'结局一'},{summary:'结局二'}],main_threads:[{id:'T1',name:'主线',description:'追查'}]};
const locked={characters:[{id:'C1',name:'人物',appearance:'“甲”'.repeat(10),personality:'',motivation:''}],world_rules:['规则'],style_guide:{pov:'三人称',tense:'过去',voice:'克制',banned_phrases:['甲','乙','丙','丁','戊']}};
assert(setup.validateSetupFields(compass,locked)['character-0-appearance']);
locked.characters[0].appearance='😀'.repeat(20);assert.deepEqual(setup.validateSetupFields(compass,locked),{});
const editor=mount(setup.default,{bible:{version:1,compass,locked,dynamic:{}},busy:false,onApprove:async()=>{throw new ApiError('填写的信息不符合要求',422);}});
all(editor.tree,n=>n.type==='textarea')[0].props.onChange({target:{value:'新书名'}});await flush();
all(editor.tree,n=>n.type==='button')[0].props.onClick();await flush();
assert.equal(all(editor.tree,n=>n.type==='textarea')[0].props['aria-invalid'],true);
assert(id(editor,'setup-title'));assert(!named(editor,'ErrorNotice'));
process.stdout.write(JSON.stringify(true));
""") is True
