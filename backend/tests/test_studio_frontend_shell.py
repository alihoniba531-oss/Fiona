"""Offline probes run real request helpers, shell hooks and polling effects."""
from pathlib import Path
import json
import shutil
import subprocess

import pytest

from test_novel_p2_r1 import DRIVER

ROOT = Path(__file__).resolve().parents[2]
STUDIO_DRIVER = DRIVER.replace("if(url==='/api/novels')", """if(url==='/api/studio/access')data=env.access;
 else if(url==='/api/studio/projects/project')data=env.project;
 else if(url==='/api/studio/projects/project/jobs')data=env.jobs;
 else if(url==='/api/studio/projects')data=[env.project];
 else if(url==='/api/novels')""")


def probe(script):
    if not (ROOT / "frontend/node_modules/typescript/lib/typescript.js").is_file():
        pytest.skip("frontend dependencies unavailable: typescript")
    if not shutil.which("node"):
        pytest.skip("node is unavailable")
    result = subprocess.run(
        ["node", "-e", STUDIO_DRIVER + "\n(async()=>{\n" + script + "\n})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});", str(ROOT)],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


def test_probe_skips_when_frontend_dependencies_are_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(globals(), "ROOT", tmp_path)

    def unexpected_render(*args, **kwargs):
        pytest.fail("rendering must not run without frontend dependencies")

    monkeypatch.setattr(subprocess, "run", unexpected_render)
    with pytest.raises(pytest.skip.Exception, match="frontend dependencies unavailable: typescript"):
        probe("process.stdout.write('true');")


SETUP = r"""
env.access={enabled:true,caps:{daily_cny:100,max_quote_cny:20,inflight:{wan:1,seedance:1}},today:{committed_cny:2,remaining_cny:98}};
env.project={id:'project',title:'试拍',aspect:'16:9',created_at:'2026-01-01 00:00:00',updated_at:'2026-01-01 00:00:00'};
env.jobs=[{id:'job',status:'queued'}];
"""


def test_workbench_polling_visibility_busy_terminal_and_account_cleanup():
    assert probe(SETUP + r"""
const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:true});await flush();
const requests=()=>env.calls.filter(x=>x==='GET /api/studio/projects/project/jobs').length;
assert.equal(requests(),1);await timer(5000);assert.equal(requests(),2);
const composer=named(page,'ClipComposer');assert(composer);
composer.props.onBusyChange(true);await flush();await timer(5000);assert.equal(requests(),2);
composer.props.onBusyChange(false);await flush();
document.hidden=true;for(const f of env.listeners.get('visibilitychange'))f();
assert.equal([...env.timers.values()].filter(t=>t.delay===5000).length,0);await flush();assert.equal(requests(),2);
document.hidden=false;for(const f of env.listeners.get('visibilitychange'))f();await flush();assert.equal(requests(),3);
env.jobs=[{id:'job',status:'downloaded'}];await timer(5000);assert.equal(requests(),4);
assert.equal([...env.timers.values()].filter(t=>t.delay===5000).length,0);
env.owner='another-account';await named(page,'ClipComposer').props.onChanged();await flush();assert.equal(requests(),4);
page.close();process.stdout.write('true');
""") is True


def test_workbench_stages_and_access_404_do_not_fetch_project():
    assert probe(SETUP + r"""
const Workbench=load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench;
let page=mount(Workbench,{id:'project',owner:env.owner,embedded:false});await flush();
const tabs=all(page.tree,n=>n.props?.role==='tab');assert.equal(tabs.length,5);assert.equal(tabs[3].props['aria-selected'],true);
assert.equal(all(page.tree,n=>n.props?.role==='tabpanel'&&!n.props.hidden).length,1);
tabs[0].props.onClick();await flush();
assert.equal(named(page,'SourcePanel').props.projectId,'project');assert.equal(named(page,'SourcePanel').props.owner,env.owner);assert.equal(all(page.tree,n=>n.props?.role==='tabpanel'&&!n.props.hidden).length,1);
page.close();env.calls=[];env.failures.set('GET /api/studio/access',{status:404,message:'Not Found'});
page=mount(Workbench,{id:'project',owner:env.owner,embedded:false});await flush();assert.equal(env.calls.some(x=>x.includes('/projects/')),false);
assert(all(page.tree,n=>n.props?.children==='暂未开放').length);page.close();process.stdout.write('true');
""") is True


def test_request_layer_sends_only_writable_parsed_parameters_and_labels():
    assert probe(SETUP + r"""
const lib=load('lib/studio.ts');
const statuses=['queued','submitting','submitted','running','succeeded','downloaded','rejected','uncertain','failed','filtered','expired','cancelled','released'];
assert.equal(new Set(statuses.map(lib.studioStatusLabel)).size,13);assert.equal(lib.studioErrorCodeLabel('unknown_error'),'unknown_error');
for(const code of ['restart_during_submission','submission_interrupted','submission_error','poll_timeout','short_output','not_charged'])assert(/[\u3400-\u9fff]/.test(lib.studioErrorCodeLabel(code)));
assert.equal(lib.studioHref('/studio/project',true),'/studio/project?embed=1');assert.equal(lib.studioHref('/studio?a=b',true),'/studio?a=b&embed=1');assert.equal(lib.studioHref('/studio',false),'/studio');
let body;agents.apiJson=async(url,init)=>{body=JSON.parse(init.body);return {};};
await lib.quoteStudioClip('project',{first_frame_asset_id:'asset',prompt:'画面',provider:'wan',resolution:'480P',duration:5,audio:true,duration_min_s:5,duration_max_s:5});
assert(!('duration_min_s' in body));assert(!('duration_max_s' in body));assert.equal(body.first_frame_asset_id,'asset');process.stdout.write('true');
""") is True


def test_notice_poller_baseline_retry_pagination_visibility_and_permanent_404():
    assert probe(r"""
const {createStudioNoticePoller}=load('lib/studio.ts');let visible=true,delivered=[],calls=[],pages=[],failure=false;
const poller=createStudioNoticePoller({isVisible:()=>visible,fetchPage:async(after,signal)=>{calls.push(after);if(failure)throw Error('offline');return pages.shift();},onNotices:n=>delivered.push(...n)});
visible=false;await poller.tick();assert.equal(calls.length,0);visible=true;
pages=[{status:200,notices:Array.from({length:50},(_,i)=>({id:i+1}))},{status:200,notices:[{id:51}]}];await poller.tick();assert.deepEqual(calls,[0,50]);assert.equal(delivered.length,0);
failure=true;await poller.tick();assert.equal(calls.at(-1),51);failure=false;
pages=[{status:500,notices:[]}];await poller.tick();assert.equal(calls.at(-1),51);
pages=[{status:200,notices:[{id:51},{id:52}]}];await poller.tick();assert.deepEqual(delivered,[{id:52}]);
pages=[{status:404,notices:[]}];await poller.tick();const last=calls.length;await poller.tick();assert.equal(calls.length,last);poller.dispose();
let round=0,cursors=[];
const baseline=createStudioNoticePoller({isVisible:()=>true,fetchPage:async(after)=>{cursors.push(after);round++;if(round===1)return {status:200,notices:Array.from({length:50},(_,i)=>({id:i+1}))};if(round===2)throw Error('offline');return {status:200,notices:[]};},onNotices:()=>assert.fail('historical notice delivered')});
await baseline.tick();await baseline.tick();assert.deepEqual(cursors,[0,50,0]);baseline.dispose();
let signal;const pending=createStudioNoticePoller({isVisible:()=>true,fetchPage:async(after,s)=>{signal=s;await new Promise(resolve=>s.addEventListener('abort',resolve));return {status:200,notices:[]};},onNotices:()=>assert.fail()});
const promise=pending.tick();await flush();pending.pause();await promise;assert(signal.aborted);pending.dispose();process.stdout.write('true');
""") is True


def test_notices_merge_dbid_shape_and_dedupe_within_batch():
    assert probe(r"""
const {mergeStudioNotices}=load('lib/studio.ts');const notice={id:1,conversation_id:'default',message_id:7,content:'完成提醒',created_at:'2026-10-16 10:00:00'};
const initial=[{id:'other',dbId:6,role:'assistant',content:'已存在',timestamp:new Date()}];
const merged=mergeStudioNotices(initial,[notice,{...notice,id:2},{...notice,id:3,message_id:8,conversation_id:'other'}],'default');
assert.equal(merged.length,2);assert.equal(merged[1].id,'db-7');assert.equal(merged[1].dbId,7);assert.equal(merged[1].role,'assistant');assert.equal(merged[1].content,'完成提醒');assert(merged[1].timestamp instanceof Date);
assert.equal(mergeStudioNotices(merged,[notice],'default'),merged);assert.equal(mergeStudioNotices(initial,[notice],undefined),initial);process.stdout.write('true');
""") is True


def test_embedded_shell_close_uses_native_dialog_guard_and_omits_navigation():
    assert probe(r"""
let listener,sent=[];window.parent={postMessage:(message,origin)=>sent.push([message,origin])};window.addEventListener=(name,fn)=>{if(name==='keydown')listener=fn;};window.removeEventListener=()=>{};
const embedded=mount(load('components/studio/StudioShell.tsx').default,{embedded:true,children:'工作室'});assert(!all(embedded.tree,n=>n.type?.name==='Framework').length);
listener({key:'Escape',defaultPrevented:false,isComposing:false});assert.deepEqual(sent,[[{type:'fiona-studio-close'},'http://local.invalid']]);
document.querySelector=()=>({});listener({key:'Escape'});assert.equal(sent.length,1);embedded.close();process.stdout.write('true');
""") is True


def test_visibility_change_during_pending_read_keeps_one_polling_chain():
    assert probe(SETUP + r"""
const lib=load('lib/studio.ts');const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:true});await flush();
let finish;lib.listStudioJobs=()=>new Promise(resolve=>{finish=()=>resolve(env.jobs);});
const pair=[...env.timers].find(([,t])=>t.delay===5000);assert(pair);env.timers.delete(pair[0]);const pending=pair[1].fn();await flush();
document.hidden=true;for(const f of env.listeners.get('visibilitychange'))f();document.hidden=false;for(const f of env.listeners.get('visibilitychange'))f();await flush();
finish();await pending;await flush();assert.equal([...env.timers.values()].filter(t=>t.delay===5000).length,1);page.close();assert.equal([...env.timers.values()].filter(t=>t.delay===5000).length,0);process.stdout.write('true');
""") is True


def test_task_mutations_refresh_immediately_and_use_confirmation_payload():
    assert probe(SETUP + r"""
const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:true});await flush();let posted;
const original=agents.apiJson;agents.apiJson=async(url,init)=>{if(init?.method==='POST')posted={url,body:init.body};return original(url,init);};
const before=env.calls.filter(x=>x==='GET /api/studio/projects/project/jobs').length;
await named(page,'ShotWall').props.onRelease({id:'job'});await flush();assert.deepEqual(posted,{url:'/api/studio/jobs/job/release',body:'{"not_charged":true}'});assert.equal(env.calls.filter(x=>x==='GET /api/studio/projects/project/jobs').length,before+1);
const beforeReuse=env.calls.length;named(page,'ShotWall').props.onRefill({prompt:'同样参数',first_frame_asset_id:'asset'});await flush();assert.equal(env.calls.length,beforeReuse);assert.equal(named(page,'ClipComposer').props.refill.params.prompt,'同样参数');page.close();process.stdout.write('true');
""") is True


def test_shelf_loads_budget_projects_and_hides_chat_back_link_when_embedded():
    assert probe(SETUP + r"""
env.search='embed=1';const shelf=await screen('components/studio/StudioShelf.tsx');assert.equal(named(shelf,'StudioBudget').props.access.today.remaining_cny,98);assert(all(shelf.tree,n=>n.props?.href==='/studio/project?embed=1').length);assert(!all(shelf.tree,n=>n.props?.href==='/').length);
const create=all(shelf.tree,n=>n.type==='button'&&JSON.stringify(n.props.children).includes('新建项目'))[0];assert(create);create.props.onClick();await flush();assert(named(shelf,'CreateProjectDialog'));shelf.close();process.stdout.write('true');
""") is True


@pytest.mark.parametrize("source_kind", ["novel", "upload", "paste", "exchange"])
def test_source_project_lands_on_source_stage_once(source_kind):
    assert probe(SETUP + "env.project.source_kind=" + json.dumps(source_kind) + r""";env.project.snapshot_no=1;
const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:true});await flush();
const tabs=()=>all(page.tree,n=>n.props?.role==='tab');
assert.equal(tabs()[0].props['aria-selected'],true);assert.equal(tabs()[3].props['aria-selected'],false);
assert.equal(named(page,'SourcePanel').props.projectId,'project');assert.equal(named(page,'SourcePanel').props.owner,env.owner);
assert.equal(all(page.tree,n=>n.props?.role==='tabpanel'&&!n.props.hidden)[0].props.id,'studio-panel-0');
// Project and job refreshes leave the initial stage intact.
await named(page,'ClipComposer').props.onChanged();await flush();await timer(5000);
assert.equal(tabs()[0].props['aria-selected'],true);page.close();process.stdout.write('true');
""") is True


@pytest.mark.parametrize("interaction", ["mouse", "keyboard"])
def test_project_refresh_preserves_manually_selected_stage(interaction):
    assert probe(SETUP + "const interaction=" + json.dumps(interaction) + r""";env.project.source_kind='novel';env.project.snapshot_no=1;
const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:false});await flush();
const tabs=()=>all(page.tree,n=>n.props?.role==='tab');assert.equal(tabs()[0].props['aria-selected'],true);
let prevented=0,focused=0;
if(interaction==='mouse')tabs()[2].props.onClick();else tabs()[0].props.onKeyDown({key:'ArrowRight',preventDefault(){prevented++;},currentTarget:{parentElement:{querySelectorAll:()=>tabs().map(()=>({focus(){focused++;}}))}}});
await flush();const chosen=interaction==='mouse'?2:1;assert.equal(tabs()[chosen].props['aria-selected'],true);
if(interaction==='keyboard'){assert.equal(prevented,1);assert.equal(focused,1);}
// Both full refreshes and the job poll must preserve the chosen stage.
await named(page,'ClipComposer').props.onChanged();await flush();await timer(5000);
assert.equal(tabs()[chosen].props['aria-selected'],true);assert.equal(tabs()[0].props['aria-selected'],false);assert(!named(page,'SourcePanel'));
// A later source metadata change must never initialize the stage again.
env.project.source_kind='paste';env.project.snapshot_no=2;await named(page,'ClipComposer').props.onChanged();await flush();
assert.equal(tabs()[chosen].props['aria-selected'],true);page.close();process.stdout.write('true');
""") is True


def test_blank_project_does_not_reinitialize_stage_if_source_appears_on_later_refresh():
    assert probe(SETUP + r"""
env.project.source_kind=null;const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:false});await flush();
const tabs=()=>all(page.tree,n=>n.props?.role==='tab');assert.equal(tabs()[3].props['aria-selected'],true);
env.project.source_kind='novel';env.project.snapshot_no=1;await named(page,'ClipComposer').props.onChanged();await flush();
assert.equal(tabs()[3].props['aria-selected'],true);assert.equal(tabs()[0].props['aria-selected'],false);page.close();process.stdout.write('true');
""") is True
