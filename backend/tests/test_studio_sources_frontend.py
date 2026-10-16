"""Offline component and SSR coverage for studio source entry points."""
from pathlib import Path
import json
import shutil
import subprocess
import pytest
from test_studio_frontend_components import DRIVER as COMPONENT_DRIVER
from test_novel_p2_r1 import DRIVER as NOVEL_DRIVER

ROOT = Path(__file__).resolve().parents[2]
DEPENDENCIES = {"typescript": "typescript/lib/typescript.js", "react": "react/index.js", "react/jsx-runtime": "react/jsx-runtime.js", "react-dom/server": "react-dom/server.js"}
DRIVER = COMPONENT_DRIVER.replace("if(name==='lucide-react')", """if(name==='next/link')return {__esModule:true,default:function Link(props){return realRuntime.jsx('a',props);}};
 if(name==='next/navigation')return {useRouter:()=>({push:url=>(env.pushes??=[]).push(url)})};
 if(name==='lucide-react')""")
NOVEL_DRIVER = NOVEL_DRIVER.replace("if(url==='/api/novels')", "if(url==='/api/studio/access')data={enabled:true};else if(url==='/api/novels')")


def probe(script, driver=DRIVER):
    missing = [name for name, entry in DEPENDENCIES.items() if not (ROOT / "frontend/node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")
    result = subprocess.run(["node", "-e", driver + "\n(async()=>{\n" + script + "\n})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});", str(ROOT)], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


@pytest.mark.parametrize("missing", DEPENDENCIES)
def test_probe_skips_before_node_for_each_missing_dependency(monkeypatch, tmp_path, missing):
    for name, entry in DEPENDENCIES.items():
        path = tmp_path / "frontend/node_modules" / entry
        path.parent.mkdir(parents=True, exist_ok=True)
        if name != missing:
            path.write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Node must not start without dependencies"))
    with pytest.raises(pytest.skip.Exception, match="frontend dependencies unavailable: " + missing):
        probe("")


SETUP = r"""
const candidate={id:'book-1',title:'春山',status:'completed',chapters_done:6,words_done:15000,completed_at:'2026-10-16T00:00:00Z',updated_at:'2026-10-16T00:00:00Z',drama_adaptation:true,eligible:true,reason:null,
 flagged:[{chapter:3,title:'渡口',flags:['length_out_of_range','review_degraded','review_unresolved','locked_conflict','deviation']}],projects:[{id:'old-project',title:'已有项目',snapshot_no:1,created_at:'2026-10-16T00:00:00Z'}]};
const blocked={...candidate,id:'book-2',title:'未完结',eligible:false,reason:'作品尚未完结',projects:[]};const sources={enabled:true,books:[candidate,blocked]};
const requests=[];agents.apiJson=async(url,init={})=>{requests.push({url,...init});if(url==='/api/studio/sources/novels')return sources;if(url==='/api/studio/sources/exchanges')return [];return {id:'new-project'};};
"""


def test_dialog_loads_filters_defaults_and_submits_strict_input():
    assert probe(SETUP + r"""
let created=[];const dialog=mount(load('components/studio/CreateProjectDialog.tsx').CreateProjectDialog,{owner:env.owner,embedded:true,busy:false,onCreate:async input=>created.push(input),onClose:()=>{}});
assert(named(dialog,'LoadingState'));assert(button(dialog,'创建项目').props.disabled);await flush();assert.equal(requests.length,2);assert(!named(dialog,'LoadingState'));
button(dialog,'小说工坊').props.onClick();await flush();let choices=all(dialog.tree,n=>n.type?.name==='NovelSourceChoice');assert.equal(choices.length,2);assert.equal(choices[1].props.book.eligible,false);choices[0].props.onSelect();await flush();assert.equal(field(dialog,'studio-source-title').props.value,'春山');assert(!button(dialog,'创建项目').props.disabled);
await button(dialog,'创建项目').props.onClick();await flush();assert.deepEqual(created,[{title:'春山',aspect:'16:9',kind:'novel',book_id:'book-1'}]);
all(dialog.tree,n=>n.type==='input'&&!n.props.id)[0].props.onChange({target:{value:'没有的书'}});await flush();assert(named(dialog,'EmptyState'));
button(dialog,'创意搭档成稿').props.onClick();await flush();assert(text(named(dialog,'EmptyState')).includes('还没有可导入的成稿'));assert(button(dialog,'创建项目').props.disabled);dialog.close();process.stdout.write('true');
""") is True


def test_dialog_file_text_caps_error_and_busy_states():
    assert probe(SETUP + r"""
const module=load('components/studio/CreateProjectDialog.tsx');assert.equal(module.validateStudioSourceFile({name:'正文.DOCX',size:10*1024*1024}),'');assert(module.validateStudioSourceFile({name:'正文.txt',size:10*1024*1024+1}).includes('10 MB'));assert(module.validateStudioSourceFile({name:'正文.pdf',size:1}).includes('仅支持'));
let calls=0;const dialog=mount(module.CreateProjectDialog,{owner:env.owner,busy:false,onCreate:async()=>{calls++;throw new ApiError('作品正在修改，请稍后再试',409);},onClose:()=>{}});await flush();button(dialog,'上传文件').props.onClick();await flush();const upload=all(dialog.tree,n=>n.type==='input'&&n.props.type==='file')[0];assert.equal(upload.props.accept,'.txt,.md,.docx');upload.props.onChange({target:{files:[{name:'正文.txt',size:10*1024*1024+1}]}});await flush();assert(button(dialog,'创建项目').props.disabled);assert(error(dialog).includes('10 MB'));
button(dialog,'粘贴文本').props.onClick();await flush();field(dialog,'studio-source-text').props.onChange({target:{value:'字'.repeat(500001)}});await flush();assert(button(dialog,'创建项目').props.disabled);field(dialog,'studio-source-text').props.onChange({target:{value:'正文'}});await flush();await button(dialog,'创建项目').props.onClick();await flush();assert.equal(calls,1);assert(error(dialog).includes('作品正在修改'));
dialog.props.busy=true;dialog.render();assert(button(dialog,'正在建立快照…').props.disabled);assert(button(dialog,'取消').props.disabled);dialog.close();process.stdout.write('true');
""") is True


def test_dialog_novel_access_hidden_and_sources_retry():
    assert probe(SETUP + r"""
let fail=true;sources.enabled=false;agents.apiJson=async url=>{if(fail)throw new ApiError('来源加载失败',503);return url.endsWith('/novels')?sources:[];};const dialog=mount(load('components/studio/CreateProjectDialog.tsx').CreateProjectDialog,{owner:env.owner,busy:false,onCreate:async()=>{},onClose:()=>{}});await flush();assert(!all(dialog.tree,n=>n.type==='button'&&text(n)==='小说工坊').length);assert(error(dialog).includes('来源加载失败'));fail=false;named(dialog,'ErrorNotice').props.retry();await flush();assert.equal(error(dialog),'');dialog.close();process.stdout.write('true');
""") is True


def test_candidate_ssr_flags_eligibility_and_embedded_existing_links():
    assert probe(SETUP + r"""
env.mode='ssr';const Choice=load('components/studio/SourceChoices.tsx').NovelSourceChoice;const html=renderToStaticMarkup(realReact.createElement(Choice,{book:candidate,embedded:true,onSelect:()=>{}}));for(const value of ['春山','改编短剧','已完结','字数超出范围','审阅降级','审阅问题待处理','锁定设定冲突','偏离细纲','/studio/old-project?embed=1'])assert(html.includes(value),value);assert(!html.includes('ring-1'));const selected=renderToStaticMarkup(realReact.createElement(Choice,{book:candidate,embedded:true,selected:true,onSelect:()=>{}}));assert(/<article class="[^"]*ring-1 ring-\[color:var\(--ink\)\]/.test(selected));assert(selected.includes('aria-pressed="true"'));assert(html.includes('class="btn btn-quiet min-h-10"'));const denied=renderToStaticMarkup(realReact.createElement(Choice,{book:blocked,embedded:false,onSelect:()=>{}}));assert(denied.includes('disabled=""'));assert(denied.includes('作品尚未完结'));process.stdout.write('true');
""") is True


def test_panel_one_check_explicit_recheck_and_confirmed_expected_version_sync():
    assert probe(SETUP + r"""
const status={kind:'novel',title:'春山',snapshot:{no:2,created_at:'2026-10-16T00:00:00Z',chapters:6,chars:15000,flagged:candidate.flagged},drift:{state:'changed',changed:[3,7],added:[61],removed:[2],bible_changed:true,eligible:true}};let reads=0,posted,refreshes=0;agents.apiJson=async(url,init={})=>{if(init.method==='POST'){posted=JSON.parse(init.body);return {...status,snapshot:{...status.snapshot,no:3},drift:{state:'unchanged',eligible:true}};}reads++;return status;};const module=load('components/studio/SourcePanel.tsx');const panel=mount(module.default,{owner:env.owner,projectId:'project-1',onChanged:async()=>{refreshes++;}});await flush();assert.equal(reads,1);assert.equal(env.timers.size,0);assert(text(panel.tree).includes('原作有改动：第 3、7 章内容变化，新增第 61 章，移除第 2 章，故事圣经已更新'));
button(panel,'同步').props.onClick();await flush();const modal=mount(module.SyncSourceDialog,named(panel,'SyncSourceDialog').props);assert(text(modal.tree).includes('旧快照归档保留'));await button(modal,'确认同步').props.onClick();await flush();assert.deepEqual(posted,{expected_no:2});assert.equal(refreshes,1);assert(text(panel.tree).includes('原作与快照一致。'));assert(!named(panel,'SyncSourceDialog'));button(panel,'重新检查').props.onClick();await flush();assert.equal(reads,2);panel.close();modal.close();process.stdout.write('true');
""") is True


@pytest.mark.parametrize("source,expected", [
    ({"kind": None}, "这个项目没有关联作品"),
    ({"kind": "novel", "title": "书", "snapshot": {"no": 1, "created_at": "2026-10-16", "chapters": 1, "chars": 2}, "drift": {"state": "unavailable"}}, "原作已无法访问，快照仍可正常使用"),
    ({"kind": "paste", "title": "粘贴", "snapshot": {"no": 1, "created_at": "2026-10-16", "chapters": 1, "chars": 2}, "drift": {"state": "not_applicable"}}, "粘贴文本"),
])
def test_panel_empty_unavailable_secondary_states(source, expected):
    assert probe("const state=" + json.dumps(source) + ";const expected=" + json.dumps(expected) + r""";agents.apiJson=async()=>state;const panel=mount(load('components/studio/SourcePanel.tsx').default,{owner:env.owner,projectId:'project',onChanged:async()=>{}});await flush();assert(text(panel.tree).includes(expected));assert(!all(panel.tree,n=>n.type==='button'&&text(n)==='同步').length);panel.close();process.stdout.write('true');""") is True


def test_panel_ineligible_disables_sync_and_error_can_retry():
    assert probe(SETUP + r"""
let fail=true;agents.apiJson=async()=>{if(fail)throw new ApiError('读取失败',500);return {kind:'novel',title:'书',snapshot:{no:1,created_at:'2026-10-16',chapters:1,chars:1},drift:{state:'changed',changed:[1],eligible:false,reason:'作品正在修改'}};};const panel=mount(load('components/studio/SourcePanel.tsx').default,{owner:env.owner,projectId:'project',onChanged:async()=>{}});await flush();assert.equal(error(panel),'读取失败');fail=false;named(panel,'ErrorNotice').props.retry();await flush();assert(button(panel,'同步').props.disabled);assert(text(panel.tree).includes('作品正在修改'));panel.close();process.stdout.write('true');
""") is True


def test_film_dialog_existing_eligibility_and_embedded_creation():
    assert probe(SETUP + r"""
const Film=load('components/novel/NovelFilmDialog.tsx').default;const dialog=mount(Film,{owner:env.owner,bookId:'book-1',bookTitle:'春山',embedded:true,onClose:()=>{}});await flush();assert.equal(field(dialog,'novel-film-project-title').props.value,'春山');const existing=named(dialog,'ExistingSourceProjects');assert(existing);assert.equal(existing.props.primary,true);const projects=mount(existing.type,existing.props);const open=all(projects.tree,n=>n.props?.children==='打开')[0];assert.equal(open.props.className,'btn btn-primary min-h-10');assert.equal(open.props.href,'/studio/old-project?embed=1');assert.equal(button(dialog,'再建一个').props.className,'btn min-h-10');projects.close();await button(dialog,'再建一个').props.onClick();await flush();assert.deepEqual(JSON.parse(requests.at(-1).body),{book_id:'book-1',title:'春山',aspect:'16:9'});assert.deepEqual(env.pushes,['/studio/new-project?embed=1']);dialog.close();sources.books=[blocked];const denied=mount(Film,{owner:env.owner,bookId:'book-2',bookTitle:'未完结',embedded:false,onClose:()=>{}});await flush();assert(button(denied,'创建项目').props.disabled);assert.equal(button(denied,'创建项目').props.className,'btn btn-primary min-h-10');assert(text(denied.tree).includes('作品尚未完结'));denied.close();process.stdout.write('true');
""") is True


@pytest.mark.parametrize("allowed", [True, False])
def test_workbench_cached_author_access_and_shared_completed_buttons(allowed):
    assert probe("const allowed=" + json.dumps(allowed) + r""";
if(!allowed)env.failures.set('GET /api/studio/access',{status:404,message:'Not Found'});const page=await screen('components/novel/NovelWorkbench.tsx',{id:env.book.id,embedded:true});const filmButtons=()=>all(page.tree,n=>n.type==='button'&&n.props.children==='做成片');assert.equal(filmButtons().length,allowed?1:0);assert.equal(typeof named(page,'GateBanner').props.onMakeFilm,allowed?'function':'undefined');assert.equal(env.calls.filter(c=>c==='GET /api/studio/access').length,1);assert(!env.calls.some(c=>c.includes('/studio/sources')));
await named(page,'GateBanner').props.onAction('continue');await flush();assert.equal(env.calls.filter(c=>c==='GET /api/studio/access').length,1);if(allowed){filmButtons()[0].props.onClick();await flush();assert.equal(named(page,'NovelFilmDialog').props.embedded,true);}page.close();process.stdout.write('true');
""", NOVEL_DRIVER) is True


def test_incomplete_workbench_never_requests_studio():
    assert probe(r"""env.book.status='awaiting_review';const page=await screen('components/novel/NovelWorkbench.tsx',{id:env.book.id});assert(!env.calls.some(c=>c.includes('/studio/')));assert(!all(page.tree,n=>n.type==='button'&&n.props.children==='做成片').length);assert.equal(named(page,'GateBanner').props.onMakeFilm,undefined);page.close();process.stdout.write('true');""", NOVEL_DRIVER) is True


def test_request_helpers_use_multipart_and_expected_no():
    assert probe(r"""
const lib=load('lib/studio.ts');let calls=[];agents.apiJson=async(url,init)=>{calls.push({url,...init});return {};};const input={title:'正文',aspect:'9:16'};await lib.createStudioFromSource({...input,kind:'paste',text:'原文'});assert(calls[0].body instanceof FormData);assert.equal(calls[0].body.get('text'),'原文');assert.equal(calls[0].body.get('kind'),'paste');assert(!calls[0].headers);await lib.createStudioFromSource({...input,kind:'upload',file:new Blob(['正文'])});assert(calls[1].body.get('file') instanceof Blob);assert.equal(calls[1].body.get('aspect'),'9:16');await lib.syncStudioSource('project',2);assert.equal(calls[2].body,'{"expected_no":2}');process.stdout.write('true');
""") is True


def test_completed_banner_ssr_shows_film_button_only_with_author_callback():
    assert probe(SETUP + r"""
env.mode='ssr';const Banner=load('components/novel/GateBanner.tsx').default;const book={title:'春山',status:'completed',chapters_done:6,words_done:15000,config:{}};const props={book,busy:false,onAction:async()=>{},onNotes:()=>{},onSettings:()=>{},onView:()=>{},onExport:()=>{},onOpenSettings:()=>{}};
const html=renderToStaticMarkup(realReact.createElement(Banner,{...props,onMakeFilm:()=>{}}));assert(html.includes('做成片'));assert(html.indexOf('>导出</button>')<html.indexOf('>做成片</button>'));
assert(!renderToStaticMarkup(realReact.createElement(Banner,props)).includes('做成片'));assert(!renderToStaticMarkup(realReact.createElement(Banner,{...props,book:{...book,status:'awaiting_review',config:{batch_size:5}},onMakeFilm:()=>{}})).includes('做成片'));process.stdout.write('true');
""") is True
