"""Offline WO3c component, SSR, and request-contract probes."""
from pathlib import Path
import json
import shutil
import subprocess

import pytest
from test_studio_frontend_components import DRIVER as COMPONENT_DRIVER

ROOT = Path(__file__).resolve().parents[2]
DEPENDENCIES = {"typescript": "typescript/lib/typescript.js", "react": "react/index.js", "react/jsx-runtime": "react/jsx-runtime.js", "react-dom/server": "react-dom/server.js"}
DRIVER = COMPONENT_DRIVER.replace("if(name==='lucide-react')", """if(name==='next/link')return {__esModule:true,default:function Link(props){return (env.mode==='ssr'?realRuntime:runtime).jsx('a',props);}};
 if(name==='@/components/Glaze')return {__esModule:true,default:function Glaze(props){return (env.mode==='ssr'?realRuntime:runtime).jsx('section',{children:props.children,className:props.className});}};
 if(name==='lucide-react')""")


def probe(script):
    missing = [name for name, entry in DEPENDENCIES.items() if not (ROOT / "frontend/node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")
    result = subprocess.run(["node", "-e", DRIVER + "\n(async()=>{\n" + script + "\n})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});", str(ROOT)], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout or "null")


@pytest.mark.parametrize("missing", DEPENDENCIES)
def test_dependency_guard_skips_before_starting_node(monkeypatch, tmp_path, missing):
    for name, entry in DEPENDENCIES.items():
        file = tmp_path / "frontend/node_modules" / entry
        file.parent.mkdir(parents=True, exist_ok=True)
        if name != missing:
            file.write_text("", encoding="utf-8")
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Node must not start without dependencies"))
    with pytest.raises(pytest.skip.Exception, match="frontend dependencies unavailable: " + missing):
        probe("")


SETUP = r"""
const project={id:'p',title:'渡船',brain_provider:'qwen',source_kind:'paste',snapshot_no:2,episode_seconds_min:180,episode_seconds_max:240};
const providers=['claude','qwen','deepseek'].map(id=>({id,label:id,available:true}));
const chunk={id:'c',no:1,task:'text_map',source:{label:'第 1 块 · 通读'},provider:'qwen',status:'failed',warnings:['原文未找到锚点'],job_id:'job',cost:{currency:'CNY',amount:.01}};
const breakdown={id:'b',status:'partial',snapshot_no:1,outdated:1,chunks:[chunk,{...chunk,id:'ep',no:2,task:'episode_plan',status:'blocked',source:{label:'第 1–5 块 · 分集'}}],synopsis:{logline:'渡船员在雾中等来信人。',synopsis:'他决定留下旧船。',genre:'剧情',tone:'克制',themes:['守候']},units_count:3,totals:{CNY:.01}};
const entry={id:'person',kind:'character',name:'阿川',aliases:['小川'],role:'main',description:'',appearance:'',appearance_source:'none',excerpt:'',needs_author:1,first_unit:1,first_appearance:'第 1 块第 1 场',episodes:[1,2,3,5]};
const episode={id:'ep1',no:1,title:'渡口',unit_from:1,unit_to:2,change:'阿川决定出发',hook:'远处有人招手',notes:'',target_min:null,target_max:null,est_seconds:400,est_shots:114,source_range:'第 1 块第 1 场 – 第 1 块第 2 场（0–800）',characters:['阿川'],warnings:['时长偏离目标']};
const plan={episodes:[episode,{...episode,id:'ep2',no:2,title:'来信',unit_from:3,unit_to:3,est_seconds:200,est_shots:57,warnings:[]}],units:[{seq:1,label:'渡口第一场'},{seq:2,label:'渡口第二场'},{seq:3,label:'来信第一场'}],unassigned:[{unit_from:4,unit_to:4,source_range:'第 2 块第 1 场'}],plan_revision:3,plan_approved_revision:2,g0_approved:false,total_seconds:600};
const costQuote={id:'q',provider:'qwen',expires_at:'2099-01-01T00:00:00Z',total_min:.02,total_max:.04,currency:'CNY',task_counts:{text_map:2,episode_plan:1,synopsis:1},total_chunks:4};
"""


def test_panel_ssr_unquoted_partial_outdated_and_running():
    assert probe(SETUP + r"""
env.mode='ssr';const Panel=load('components/studio/BreakdownPanel.tsx').default;const props={project,providers,busy:false,onQuote:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}};
const empty=renderToStaticMarkup(realReact.createElement(Panel,{...props,breakdown:null}));for(const value of ['最短秒数','最长秒数','大约几集','当前导演模型：千问','>报价</button>','约 3.0–4.0 分钟'])assert(empty.includes(value),value);assert(empty.includes('placeholder="可不填"'));assert(!empty.includes('大约几集（可不填）'));
const partial=renderToStaticMarkup(realReact.createElement(Panel,{...props,breakdown}));for(const value of ['拆解基于快照第 1 版，作品已同步到第 2 版','重新拆解','部分完成','取消拆解','第 1–5 块 · 分集','重跑（先报价）','原文未找到锚点','拆解总进度'])assert(partial.includes(value),value);assert(partial.includes('<details open=""'));assert(partial.includes('以下批次需要重跑：第 1 块 · 通读（失败）'));assert(partial.includes('完成后「第 1–5 块 · 分集」会自动继续'));assert(partial.includes('role="progressbar"'));assert(partial.includes('aria-valuenow="0"'));assert.equal((empty.match(/block w-28/g)||[]).length,3);assert(!empty.includes('flex-1 basis-32'));
const active=renderToStaticMarkup(realReact.createElement(Panel,{...props,breakdown:{...breakdown,status:'running',chunks:[{...chunk,status:'running'}]}}));assert(active.includes('正在拆解'));assert(active.includes('取消拆解'));process.stdout.write('true');
""") is True


def test_quote_counts_currency_countdown_and_expiry():
    assert probe(SETUP + r"""
env.mode='ssr';const Dialog=load('components/studio/BreakdownQuoteDialog.tsx').default;let html=renderToStaticMarkup(realReact.createElement(Dialog,{quote:costQuote,busy:false,onConfirm:async()=>{},onClose:()=>{}}));for(const value of ['确认拆解报价','通读 2 批','分集 1 批','梗概 1 批','¥0.0200','¥0.0400','报价剩余有效时间','确认开始'])assert(html.includes(value),value);html=renderToStaticMarkup(realReact.createElement(Dialog,{quote:{...costQuote,expires_at:'2000-01-01T00:00:00Z'},busy:false,onConfirm:async()=>{},onClose:()=>{}}));assert(html.includes('报价已过期'));assert(/<button type="submit"[^>]*disabled/.test(html));process.stdout.write('true');
""") is True


def test_chunk_shows_cumulative_settled_cost_across_provider_currencies():
    assert probe(SETUP + r"""
env.mode='ssr';const Row=load('components/studio/BreakdownPanel.tsx').BreakdownChunkRow;const html=renderToStaticMarkup(realReact.createElement(Row,{chunk:{...chunk,totals:{CNY:.02,USD:.03}},providers,busy:false,onRetry:async()=>{},onRelease:async()=>{}}));assert(html.includes('累计已结算 ¥0.0200 / $0.0300'));process.stdout.write('true');
""") is True


def test_cancelled_plan_cannot_be_approved_in_the_ui():
    assert probe(SETUP + r"""
env.mode='ssr';const Plan=load('components/studio/EpisodePlan.tsx').default;const html=renderToStaticMarkup(realReact.createElement(Plan,{plan:{...plan,status:'cancelled'},busy:false,onOperate:async()=>{},onApprove:async()=>{},onExport:async()=>{}}));assert(/<button[^>]*disabled[^>]*>批准分集方案/.test(html));assert(html.includes('本次拆解已取消'));process.stdout.write('true');
""") is True


def test_settings_validation_retry_provider_and_uncertain_release():
    assert probe(SETUP + r"""
let quoted=[];const Panel=load('components/studio/BreakdownPanel.tsx').default;const panel=mount(Panel,{project,breakdown:null,providers,busy:false,onQuote:async(...args)=>quoted.push(args),onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}});let inputs=all(panel.tree,n=>n.type==='input');inputs[0].props.onChange({target:{value:'500'}});await flush();assert(button(panel,'报价').props.disabled);all(panel.tree,n=>n.type==='input')[1].props.onChange({target:{value:'600'}});await flush();all(panel.tree,n=>n.type==='input')[2].props.onChange({target:{value:'8'}});await flush();await button(panel,'报价').props.onClick();assert.deepEqual(quoted,[[500,600,8]]);panel.close();
let cancelled=0;const partial=mount(Panel,{project,breakdown,providers,busy:false,onQuote:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{cancelled++;}});button(partial,'取消拆解').props.onClick();await flush();assert.equal(named(partial,'BreakdownDialog').props.title,'取消本次拆解');await named(partial,'BreakdownDialog').props.onConfirm();assert.equal(cancelled,1);partial.close();
let retried=[],released=0;const Row=load('components/studio/BreakdownPanel.tsx').BreakdownChunkRow;const row=mount(Row,{chunk,providers,busy:false,onRetry:async(...args)=>retried.push(args),onRelease:async()=>{}});all(row.tree,n=>n.type==='select')[0].props.onChange({target:{value:'deepseek'}});await flush();await button(row,'重跑（先报价）').props.onClick();assert.equal(retried[0][1],'deepseek');row.close();const uncertain=mount(Row,{chunk:{...chunk,status:'uncertain'},providers,busy:false,onRetry:async()=>assert.fail(),onRelease:async()=>{released++;}});assert(text(uncertain.tree).includes('可能已扣费'));assert(!all(uncertain.tree,n=>n.type==='button'&&text(n).includes('重跑')).length);button(uncertain,'释放').props.onClick();await flush();await named(uncertain,'BreakdownDialog').props.onConfirm();assert.equal(released,1);uncertain.close();process.stdout.write('true');
""") is True


def test_bible_missing_badge_inline_edit_and_merge():
    assert probe(SETUP + r"""
env.mode='ssr';const Table=load('components/studio/BibleTable.tsx').default;const base={entries:[entry,{...entry,id:'other',name:'川哥'}],busy:false,onSave:async()=>{},onAdd:async()=>{},onMerge:async()=>{},onArchive:async()=>{}};const html=renderToStaticMarkup(realReact.createElement(Table,base));for(const value of ['待作者补充','只看待补充','小川','第 1 块第 1 场','主要人物','第 1–3、5 集'])assert(html.includes(value),value);
env.mode='hooks';cache.clear();let saved=[];const HookTable=load('components/studio/BibleTable.tsx').default;const row=mount(load('components/studio/BibleTable.tsx').BibleTableRow,{entry,selected:false,busy:false,onSelect:()=>{},onSave:async fields=>saved.push(fields),onArchive:()=>{}});button(row,'修改').props.onClick();await flush();let editor=named(row,'BibleFieldsEditor');editor.props.onChange({...editor.props.fields,appearance:'灰布短衫，肩头落着水珠。'});await flush();all(row.tree,n=>n.type==='form')[0].props.onSubmit({preventDefault(){}});await flush();assert.deepEqual(saved,[{appearance:'灰布短衫，肩头落着水珠。'}]);assert(!named(row,'BibleFieldsEditor'));row.close();let merged=[];const table=mount(HookTable,{...base,onMerge:async(...args)=>merged.push(args)});all(table.tree,n=>n.type?.name==='BibleTableRow')[0].props.onSelect();await flush();all(table.tree,n=>n.type?.name==='BibleTableRow')[1].props.onSelect();await flush();button(table,'合并所选（2）').props.onClick();await flush();await named(table,'BreakdownDialog').props.onConfirm();assert.deepEqual(merged,[['person',['other']]]);assert.equal(all(table.tree,n=>n.props?.role==='tab')[0].props.tabIndex,0);table.close();process.stdout.write('true');
""") is True


def test_episode_ssr_timing_menus_approval_and_narrow_cards():
    assert probe(SETUP + r"""
env.mode='ssr';const Plan=load('components/studio/EpisodePlan.tsx').default;const props={plan,busy:false,onOperate:async()=>{},onApprove:async()=>{},onExport:async()=>{}};const html=renderToStaticMarkup(realReact.createElement(Plan,props));for(const value of ['方案第 3 版','待批准','总预估时长 10 分 0 秒','超出目标区间 ±15%','预估镜头数','目标时长','更多','未纳入','建成一集','导出 Markdown','data-testid="episode-cards"','@[640px]:hidden','overflow-x-auto'])assert(html.includes(value),value);const partial=renderToStaticMarkup(realReact.createElement(Plan,{...props,partial:true}));assert(/<button[^>]*disabled[^>]*>批准分集方案/.test(partial));const approved=renderToStaticMarkup(realReact.createElement(Plan,{...props,plan:{...plan,g0_approved:true,plan_approved_revision:3}}));assert(approved.includes('已批准（第 3 版）'));assert(approved.includes('G0 已批准'));assert(html.includes('min-w-[1040px]'));assert(!html.includes('min-w-[1180px]'));const thClass=(html.match(/<th[^>]*class="([^"]*)"[^>]*>操作<\/th>/)||[])[1]||'';for(const token of ['sticky','right-0','z-10','bg-[color:var(--paper)]','border-l','border-[color:var(--carve)]'])assert(thClass.includes(token),token);const tdClasses=[...html.matchAll(/<td class="([^"]+)">(?=<button[^>]*aria-label="第 \d+ 集更多操作")/g)].map(match=>match[1]);assert.equal(tdClasses.length,plan.episodes.length);for(const value of tdClasses)for(const token of ['sticky','right-0','z-10','bg-[color:var(--paper)]'])assert(value.includes(token),value);process.stdout.write('true');
""") is True


def test_episode_operations_revision_split_points_and_approval_dialog():
    assert probe(SETUP + r"""
const ops=[],approved=[];const page=mount(load('components/studio/EpisodePlan.tsx').default,{plan,busy:false,onOperate:async op=>ops.push(op),onApprove:async revision=>approved.push(revision),onExport:async()=>{}});let menu=all(page.tree,n=>n.type?.name==='EpisodeMoreMenu')[0];await menu.props.onOperate({op:'merge',no:1});assert.deepEqual(ops[0],{op:'merge',no:1,expected_revision:3});menu.props.onSplit();await flush();let dialog=named(page,'BreakdownDialog');assert.equal(dialog.props.title,'拆分第 1 集');assert(text(dialog.props.children).includes('渡口第二场'));await dialog.props.onConfirm();assert.deepEqual(ops[1],{op:'split',no:1,at_unit:2,expected_revision:3});await flush();button(page,'批准分集方案').props.onClick();await flush();dialog=named(page,'BreakdownDialog');assert(text(dialog.props.children).includes('批准后再改会生成新版本、需要重新批准'));await dialog.props.onConfirm();assert.deepEqual(approved,[3]);page.close();process.stdout.write('true');
""") is True


def test_episode_editor_target_validation_and_fields():
    assert probe(SETUP + r"""
let saved=[];const page=mount(load('components/studio/EpisodePlan.tsx').EpisodeEditDialog,{episode,busy:false,onSave:async value=>saved.push(value),onClose:()=>{}});assert(!named(page,'BreakdownDialog').props.disabled);let numbers=all(page.tree,n=>n.type==='input'&&n.props.type==='number');numbers[0].props.onChange({target:{value:'30'}});await flush();assert(named(page,'BreakdownDialog').props.disabled);all(page.tree,n=>n.type==='input'&&n.props.type==='number')[0].props.onChange({target:{value:'120'}});await flush();all(page.tree,n=>n.type==='input'&&n.props.type==='number')[1].props.onChange({target:{value:'180'}});await flush();await named(page,'BreakdownDialog').props.onConfirm();assert.equal(saved[0].target_min,120);assert.equal(saved[0].target_max,180);page.close();process.stdout.write('true');
""") is True


def test_synopsis_structured_field_errors_and_preservation():
    assert probe(SETUP + r"""
let saved=[];const source={compass:{logline:'河畔来信',theme:'守候',core_conflict:'去留',hidden:'保留罗盘',main_threads:[{id:'T1',name:'回信',summary:'送信人迟到',hidden:'保留主线'}]},arc_summaries:[{summary:'渡船离岸',hidden:'保留分段'}],extra:'保留'};const page=mount(load('components/studio/SynopsisPanel.tsx').default,{synopsis:source,novel:true,busy:false,onSave:async value=>saved.push(value)});button(page,'修改梗概').props.onClick();await flush();all(page.tree,n=>n.type==='textarea')[3].props.onChange({target:{value:'broken'}});await flush();all(page.tree,n=>n.type==='form')[0].props.onSubmit({preventDefault(){}});await flush();assert(text(page.tree).includes('主线格式不正确'));assert.equal(saved.length,0);all(page.tree,n=>n.type==='textarea')[3].props.onChange({target:{value:'回信｜送信人归来'}});await flush();all(page.tree,n=>n.type==='form')[0].props.onSubmit({preventDefault(){}});await flush();assert.equal(saved[0].extra,'保留');assert.deepEqual(saved[0].compass.main_threads,[{id:'T1',name:'回信',summary:'送信人归来',hidden:'保留主线'}]);assert.equal(saved[0].compass.hidden,'保留罗盘');assert.deepEqual(saved[0].arc_summaries,source.arc_summaries);page.close();process.stdout.write('true');
""") is True


def test_requests_quote_retry_revision_and_markdown_download():
    assert probe(SETUP + r"""
const lib=load('lib/studio-breakdown.ts');let calls=[];agents.apiJson=async(url,init={})=>{calls.push({url,...init});return {};};await lib.quoteStudioBreakdown('p',8);await lib.startStudioBreakdown('p','q');await lib.quoteBreakdownRetry('b','c','deepseek');await lib.retryBreakdownChunk('b','c','rq');await lib.operateStudioEpisodes('p',{expected_revision:3,op:'edit',no:1,fields:{title:'新标题'}});await lib.approveStudioEpisodes('p',4);await lib.patchStudioSynopsis('p',{logline:'来信'});assert.equal(calls[0].url,'/api/studio/projects/p/breakdown/quote');assert.deepEqual(JSON.parse(calls[0].body),{target_episodes:8});assert.deepEqual(JSON.parse(calls[1].body),{quote_id:'q'});assert.deepEqual(JSON.parse(calls[2].body),{provider:'deepseek'});assert.deepEqual(JSON.parse(calls[3].body),{quote_id:'rq'});assert.equal(JSON.parse(calls[4].body).expected_revision,3);assert.deepEqual(JSON.parse(calls[5].body),{expected_revision:4});assert.equal(calls[6].url,'/api/studio/projects/p/breakdown/synopsis');let downloaded;document.createElement=()=>({click(){downloaded=this.download;}});auth.apiFetch=async()=>({ok:true,headers:{get:()=>"attachment; filename*=UTF-8''%E6%B8%A1%E8%88%B9.md"},blob:async()=>new Blob(['梗概'])});await lib.downloadStudioBreakdown('p');assert.equal(downloaded,'渡船.md');assert.equal(env.created.length,1);assert.deepEqual(env.revoked,[env.created[0].url]);process.stdout.write('true');
""") is True


STAGE_SETUP = SETUP + r"""
let breakdownReads=0,posts=[];agents.apiJson=async(url,init={})=>{if(init.method&&init.method!=='GET'){posts.push({url,body:JSON.parse(init.body??'{}')});return costQuote;}if(url.endsWith('/breakdown')){breakdownReads++;return JSON.parse(JSON.stringify(breakdown));}if(url.endsWith('/bible'))return [entry];if(url.endsWith('/episodes'))return plan;throw Error('Unexpected route '+url);};const props={project,owner:env.owner,providers,busy:false,onBusyChange:()=>{},onChanged:async()=>{}};
"""


def test_stage_quote_confirm_and_409_refresh():
    assert probe(STAGE_SETUP + r"""
const page=mount(load('components/studio/BreakdownStage.tsx').default,props);await flush();assert.equal(breakdownReads,1);await named(page,'BreakdownPanel').props.onQuote(180,240,8);await flush();let modal=named(page,'BreakdownQuoteDialog');assert(modal);assert.equal(posts.length,1);await modal.props.onConfirm();await flush();assert.equal(posts[1].url,'/api/studio/projects/p/breakdown/start');assert.deepEqual(posts[1].body,{quote_id:'q'});const original=agents.apiJson;agents.apiJson=async(url,init)=>{if(url.endsWith('/episodes/ops'))throw new ApiError('分集方案已更新，请刷新',409);return original(url,init);};const before=breakdownReads;await assert.rejects(()=>named(page,'EpisodePlan').props.onOperate({expected_revision:3,op:'merge',no:1}));await flush();assert(breakdownReads>before);assert(error(page).includes('分集方案已被更新'));page.close();process.stdout.write('true');
""") is True


def test_stage_inflight_polling_visibility_terminal_and_account_guards():
    assert probe(STAGE_SETUP + r"""
breakdown.status='running';breakdown.chunks=[{...chunk,status:'running'}];const page=mount(load('components/studio/BreakdownStage.tsx').default,props);await flush();assert.equal([...env.timers.values()].filter(t=>t.delay===5000).length,1);let pair=[...env.timers].find(([,t])=>t.delay===5000);env.timers.delete(pair[0]);await pair[1].fn();await flush();assert.equal(breakdownReads,2);document.hidden=true;for(const fn of env.listeners.get('visibilitychange'))fn();assert.equal([...env.timers.values()].filter(t=>t.delay===5000).length,0);breakdown.status='done';breakdown.chunks[0].status='succeeded';document.hidden=false;for(const fn of env.listeners.get('visibilitychange'))fn();await flush();assert.equal(breakdownReads,3);assert.equal([...env.timers.values()].filter(t=>t.delay===5000).length,0);env.owner='other';await named(page,'BreakdownPanel').props.onQuote(180,240);await flush();assert.equal(posts.length,0);page.close();process.stdout.write('true');
""") is True


def test_f4_ssr_only_newest_project_is_primary_with_local_date():
    assert probe(r"""
env.mode='ssr';const lib=load('components/studio/SourceChoices.tsx');const projects=[{id:'old',title:'旧项目',snapshot_no:1,created_at:'2026-10-15 10:00:00'},{id:'new',title:'新项目',snapshot_no:1,created_at:'2026-10-16 11:30:00'},{id:'middle',title:'中间项目',snapshot_no:1,created_at:'2026-10-16 10:00:00'}];const html=renderToStaticMarkup(realReact.createElement(lib.ExistingSourceProjects,{projects,embedded:true,primary:true}));assert.equal((html.match(/btn-primary/g)||[]).length,1);assert.equal((html.match(/btn-quiet/g)||[]).length,2);assert(html.indexOf('新项目')<html.indexOf('中间项目'));assert(html.includes(lib.sourceProjectCreatedDate(projects[1].created_at)));assert(html.includes('href="/studio/new?embed=1"'));assert(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(lib.sourceProjectCreatedDate(projects[1].created_at)));assert.equal(projects[0].id,'old');process.stdout.write('true');
""") is True


def test_stage_reads_derived_tables_after_breakdown_publication():
    assert probe(STAGE_SETUP + r"""
let release,reads=[];agents.apiJson=async url=>{reads.push(url);if(url.endsWith('/breakdown'))return new Promise(resolve=>{release=()=>resolve(breakdown);});if(url.endsWith('/bible'))return [entry];if(url.endsWith('/episodes'))return plan;throw Error(url);};const page=mount(load('components/studio/BreakdownStage.tsx').default,props);await flush();assert.deepEqual(reads,['/api/studio/projects/p/breakdown']);release();await flush();assert.equal(reads.length,3);assert(named(page,'EpisodePlan'));page.close();process.stdout.write('true');
""") is True


def test_more_native_dialog_closes_before_each_action_and_disables_invalid_boundaries():
    assert probe(SETUP + r"""
let actions=[];const Menu=load('components/studio/EpisodePlan.tsx').EpisodeMoreMenu;const props={episode,next:plan.episodes[1],busy:false,onEdit:()=>actions.push(['edit',!!all(menu.tree,n=>n.type==='dialog').length]),onSplit:()=>actions.push(['split',!!all(menu.tree,n=>n.type==='dialog').length]),onDelete:()=>{},onOperate:async op=>actions.push(op)};const menu=mount(Menu,props);assert(!all(menu.tree,n=>n.type==='dialog').length);button(menu,'更多').props.onClick();await flush();let modal=all(menu.tree,n=>n.type==='dialog')[0];assert(modal);assert(modal.props['aria-labelledby']);assert(text(modal).includes('第 1 集 · 操作'));for(const label of ['修改','与下一集合并','拆分','边界前移一场','边界后移一场','删除（变为未纳入）','关闭'])button(menu,label);assert(!button(menu,'边界前移一场').props.disabled);assert(button(menu,'边界后移一场').props.disabled);const closedBefore=env.modalClosed;button(menu,'修改').props.onClick();assert(env.modalClosed>closedBefore);await flush();assert(!all(menu.tree,n=>n.type==='dialog').length);assert.equal(actions[0][0],'edit');button(menu,'更多').props.onClick();await flush();let prevented=0;all(menu.tree,n=>n.type==='dialog')[0].props.onCancel({preventDefault(){prevented++;}});await flush();assert.equal(prevented,1);assert(!all(menu.tree,n=>n.type==='dialog').length);
menu.props={...props,episode:{...episode,unit_from:2,unit_to:2},next:{...plan.episodes[1],unit_from:4,unit_to:5}};menu.render();button(menu,'更多').props.onClick();await flush();assert(button(menu,'拆分').props.disabled);assert(button(menu,'边界前移一场').props.disabled);assert(button(menu,'边界后移一场').props.disabled);button(menu,'关闭').props.onClick();await flush();menu.props={...props,next:undefined};menu.render();button(menu,'更多').props.onClick();await flush();for(const label of ['与下一集合并','边界前移一场','边界后移一场'])assert(button(menu,label).props.disabled,label);menu.close();process.stdout.write('true');
""") is True


def test_readable_synopsis_aliases_line_edit_parser_and_role_ranges():
    assert probe(SETUP + r"""
const mod=load('components/studio/SynopsisPanel.tsx');assert.equal(mod.synopsisItemText('main_threads',{title:'归家',description:'找到灯'}),'归家 —— 找到灯');for(const range of [{from:1,to:2},{start_chapter:1,end_chapter:2},{from_chapter:1,to_chapter:2}])assert.equal(mod.synopsisItemText('arc_summaries',{...range,summary:'离岸'}),'第 1–2 章：离岸');assert.equal(mod.synopsisItemText('arc_summaries',{summary:'离岸'}),'离岸');const original=[{id:'A',title:'归家',description:'找到灯',extra:9}];assert.deepEqual(mod.parseSynopsisField('main_threads','归乡｜找到船\n新线｜新事',original),[{id:'A',title:'归乡',description:'找到船',extra:9},{name:'新线',description:'新事'}]);assert.deepEqual(mod.parseSynopsisField('main_threads','',original),[]);assert.throws(()=>mod.parseSynopsisField('arc_summaries','4–2｜错序',[]));assert.deepEqual(mod.parseSynopsisField('arc_summaries','2–4｜续篇',[{start_chapter:1,end_chapter:2,summary:'离岸',extra:8}]),[{start_chapter:2,end_chapter:4,summary:'续篇',extra:8}]);const lib=load('lib/studio-breakdown.ts');assert.equal(lib.formatEpisodeRanges([10,6,5,1,3,2,2]),'第 1–3、5–6、10 集');assert.equal(lib.formatEpisodeRanges([]),'未纳入');assert.equal(lib.roleLabel('supporting'),'配角');assert.equal(lib.roleLabel('major'),'重要');assert.equal(lib.roleLabel('minor'),'次要');assert.equal(lib.roleLabel('船工'),'船工');env.mode='ssr';cache.clear();const html=renderToStaticMarkup(realReact.createElement(load('components/studio/SynopsisPanel.tsx').default,{synopsis:{logline:'归家',theme:'守候',main_threads:original,arc_summaries:[{from:1,to:2,summary:'离岸'}]},novel:true}));assert(html.includes('归家 —— 找到灯'));assert(html.includes('第 1–2 章：离岸'));assert(!html.includes('结束章节'));assert(!html.includes('姓名'));process.stdout.write('true');
""") is True


def test_running_partial_and_rebreakdown_keep_old_g0_but_disable_editing():
    assert probe(SETUP + r"""
const Plan=load('components/studio/EpisodePlan.tsx').default;for(const status of ['running','partial']){const page=mount(Plan,{plan:{...plan,status:'done',active_breakdown_status:status},busy:false,onOperate:async()=>assert.fail(),onApprove:async()=>assert.fail(),onExport:async()=>{}});assert(text(page.tree).includes('补跑完成后分集方案会按新结果重新生成'));assert(button(page,'批准分集方案').props.disabled);assert(button(page,'建成一集').props.disabled);assert(all(page.tree,n=>n.type?.name==='EpisodeMoreMenu').every(node=>node.props.busy));page.close();}const page=mount(Plan,{plan:{...plan,status:'done',active_breakdown_status:'running',rebreakdown_pending:true,g0_approved:true,plan_approved_revision:3},busy:false,onOperate:async()=>assert.fail(),onApprove:async()=>assert.fail(),onExport:async()=>{}});assert(text(page.tree).includes('已批准（第 3 版）'));assert(text(page.tree).includes('上一次已发布的分集方案与 G0 状态'));assert(text(page.tree).includes('新的拆解进行中，完成后会替换此方案'));assert(text(page.tree).includes('渡口'));assert(button(page,'G0 已批准').props.disabled);page.close();process.stdout.write('true');
""") is True


def test_quote_does_not_patch_settings_and_confirmation_explains_old_plan_changes():
    assert probe(STAGE_SETUP + r"""
plan.g0_approved=true;plan.plan_approved_revision=3;plan.status='done';const page=mount(load('components/studio/BreakdownStage.tsx').default,props);await flush();await named(page,'BreakdownPanel').props.onQuote(120,180,8);await flush();assert.equal(posts.length,1);assert.equal(posts[0].url,'/api/studio/projects/p/breakdown/quote');assert.deepEqual(posts[0].body,{target_episodes:8,episode_seconds_min:120,episode_seconds_max:180});const quoteModal=named(page,'BreakdownQuoteDialog');assert.equal(quoteModal.props.targetMin,120);assert.equal(quoteModal.props.targetMax,180);assert(quoteModal.props.affectsApproved);assert(quoteModal.props.replacesPartial);assert.equal(plan.plan_approved_revision,3);quoteModal.props.onClose();await flush();await named(page,'BreakdownPanel').props.onSettings(120,180);await flush();assert.equal(posts.length,1);const warning=named(page,'BreakdownDialog');assert(warning);assert(text(warning.props.children).includes('生成新版本并退回待批准'));await warning.props.onConfirm();await flush();assert.equal(posts[1].url,'/api/studio/projects/p');assert.deepEqual(posts[1].body,{episode_seconds_min:120,episode_seconds_max:180});page.close();env.mode='ssr';cache.clear();const html=renderToStaticMarkup(realReact.createElement(load('components/studio/BreakdownQuoteDialog.tsx').default,{quote:costQuote,targetMin:120,targetMax:180,affectsApproved:true,replacesPartial:true,busy:false,onConfirm:async()=>{},onClose:()=>{}}));assert(html.includes('每集目标时长将保存为 120–180 秒'));assert(html.includes('新方案发布后会退回待批准'));assert(html.includes('上一次拆解未执行的批次将取消并释放预留'));process.stdout.write('true');
""") is True


def test_partial_reports_retryable_batches_and_uncertain_release_before_blocked_segments():
    assert probe(SETUP + r"""
env.mode='ssr';const html=renderToStaticMarkup(realReact.createElement(load('components/studio/BreakdownPanel.tsx').default,{project,breakdown:{...breakdown,retry_needed:[{label:'第 11–14 章 · 补全',status:'rejected'},{label:'第 1–10 章 · 补全',status:'uncertain'}],blocked_segments:['第 11–14 章 · 分集']},providers,busy:false,onQuote:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}}));assert(html.includes('第 11–14 章 · 补全（被拒绝）'));assert(html.includes('第 1–10 章 · 补全（结果不确定，需先核账释放）'));assert(html.includes('完成后「第 11–14 章 · 分集」会自动继续'));assert(!html.includes('以下分段待重跑'));process.stdout.write('true');
""") is True


def test_cancelled_unpublished_rerun_allows_using_previous_published_plan():
    assert probe(SETUP + r"""
const page=mount(load('components/studio/EpisodePlan.tsx').default,{plan:{...plan,status:'done',active_breakdown_status:'cancelled',rebreakdown_pending:false},busy:false,onOperate:async()=>{},onApprove:async()=>{},onExport:async()=>{}});assert(!button(page,'批准分集方案').props.disabled);assert(all(page.tree,n=>n.type?.name==='EpisodeMoreMenu').every(node=>!node.props.busy));page.close();process.stdout.write('true');
""") is True


def test_published_plan_retains_previous_default_target_during_new_breakdown():
    assert probe(SETUP + r"""
const mod=load('components/studio/EpisodePlan.tsx');assert.deepEqual(mod.episodeTiming({...episode,effective_target_min:100,effective_target_max:200},300,400),{min:100,max:200,outside:true});env.mode='ssr';cache.clear();const html=renderToStaticMarkup(realReact.createElement(load('components/studio/EpisodePlan.tsx').default,{plan:{...plan,status:'done',active_breakdown_status:'running',rebreakdown_pending:true,settings:{episode_seconds_min:180,episode_seconds_max:240}},defaultMin:60,defaultMax:90,busy:false,onOperate:async()=>{},onApprove:async()=>{},onExport:async()=>{}}));assert(html.includes('180–240 秒'));assert(!html.includes('60–90 秒'));process.stdout.write('true');
""") is True
