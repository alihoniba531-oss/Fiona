"""Offline SSR and event probes for the director picker and script trial."""
from test_studio_frontend_components import probe
from test_studio_frontend_shell import probe as shell_probe, SETUP as SHELL_SETUP


SETUP = r"""
const lib=load('lib/studio.ts'), brain=load('components/studio/BrainTrial.tsx');
const providers=[{id:'claude',label:'Claude',available:true,model:'claude-sonnet-5-5'},
 {id:'qwen',label:'千问',available:true,model:'qwen3.8-max'},
 {id:'deepseek',label:'DeepSeek',available:true,model:'deepseek-v4-pro'}];
const brainJob=(provider='claude',extra={})=>({id:provider+'-read',provider,task:'read_through',model:provider==='claude'?'claude-sonnet-5-5':provider,
 status:'queued',output:null,warnings:[],usage:null,cost:{currency:provider==='claude'?'USD':'CNY',amount:.2},latency_s:null,
 parent_job_id:null,error_code:null,error_message:null,...extra});
const trialQuote={totals:{CNY:1.2,USD:.4},items:providers.map(p=>({provider:p.id,task:'read_through',model:p.model,currency:p.id==='claude'?'USD':'CNY',amount:.2}))};
const trialProps={projectId:'project-1',owner:env.owner,provider:'claude',providers,busy:false,
 onProviderChange:async()=>{},onBusyChange:()=>{},onChanged:async()=>{},onPoll:async()=>{}};
const fillTrial=page=>{const textarea=all(page.tree,n=>n.type==='textarea')[0];textarea.props.onChange({target:{value:'他收起信，走向窗边。'}});};
"""


def test_director_picker_availability_model_and_single_patch():
    assert probe(SETUP + r"""
let patched=[];lib.patchStudioProject=async(id,provider)=>{patched.push(provider);};
const props={providers:[{...providers[0],available:false,reason:'请先启用 Claude BYOK'},...providers.slice(1)],current:'claude',busy:false,onChange:provider=>lib.patchStudioProject('project',provider)};
const page=mount(brain.BrainProviderPicker,props);
const unavailable=all(page.tree,n=>n.type==='button'&&text(n).includes('Claude'))[0];
assert.equal(unavailable.props.disabled,true);assert(text(page.tree).includes('claude-sonnet-5-5'));assert(text(page.tree).includes('请先启用 Claude BYOK'));
assert(unavailable.props['aria-describedby']);button(page,'千问').props.onClick();await flush();assert.deepEqual(patched,['qwen']);assert.equal(env.calls.length,0);
page.close();process.stdout.write('true');
""") is True


def test_trial_quotes_before_confirm_and_cancel_never_submits():
    assert probe(SETUP + r"""
let quotes=[],submissions=[];
lib.quoteBrainTrial=async(id,input)=>{quotes.push(input);return trialQuote;};
lib.startBrainTrial=async(id,input)=>{submissions.push(input);return {group_id:'g',jobs:[brainJob()]};};
const page=mount(brain.AccountBrainTrial,trialProps);
assert.equal(all(page.tree,n=>n.type==='input'&&n.props.type==='checkbox'&&n.props.checked).length,3);
fillTrial(page);await flush();button(page,'三家都跑（对比）').props.onClick();await flush();
assert.equal(quotes.length,1);assert.equal(quotes[0].providers,'all');assert.equal(quotes[0].tasks.length,3);assert.equal(submissions.length,0);
const element=named(page,'BrainQuoteDialog'),dialog=mount(element.type,element.props);
assert(text(dialog.tree).includes('¥1.20'));assert(text(dialog.tree).includes('$0.40'));assert.equal(env.modalOpened,1);
button(dialog,'取消').props.onClick();await flush();assert.equal(submissions.length,0);assert(!named(page,'BrainQuoteDialog'));dialog.close();
button(page,'用当前导演模型试读').props.onClick();await flush();assert.equal(quotes[1].providers,'current');
const next=named(page,'BrainQuoteDialog'),confirmation=mount(next.type,next.props);
const click=button(confirmation,'确认花费，开始试读').props.onClick;click();click();await flush();
assert.equal(submissions.length,1);assert.deepEqual(submissions[0],quotes[1]);assert(!named(page,'BrainQuoteDialog'));
page.close();confirmation.close();process.stdout.write('true');
""") is True


def test_trial_input_limits_and_task_selection():
    assert probe(SETUP + r"""
let input;lib.quoteBrainTrial=async(id,value)=>{input=value;return trialQuote;};
const page=mount(brain.AccountBrainTrial,trialProps);
assert.equal(button(page,'用当前导演模型试读').props.disabled,true);
all(page.tree,n=>n.type==='textarea')[0].props.onChange({target:{value:'文'.repeat(20001)}});await flush();
assert.equal(all(page.tree,n=>n.type==='textarea')[0].props.value.length,20000);assert(text(page.tree).includes('20000 / 20000 字'));
const checks=all(page.tree,n=>n.type==='input'&&n.props.type==='checkbox');checks[0].props.onChange({target:{checked:false}});await flush();
button(page,'用当前导演模型试读').props.onClick();await flush();assert.deepEqual(input.tasks,['style_proposals','bible_extract']);
page.close();process.stdout.write('true');
""") is True


def test_claude_unavailable_alternatives_only_patch_without_rerun():
    assert probe(SETUP + r"""
let switches=[],submitted=0;lib.patchStudioProject=async(id,provider)=>switches.push(provider);lib.startBrainTrial=async()=>submitted++;
const page=mount(brain.AccountBrainTrial,{...trialProps,providers:[{...providers[0],available:false,reason:'BYOK 尚未启用'},...providers.slice(1)],onProviderChange:provider=>lib.patchStudioProject('project',provider)});
button(page,'改用千问').props.onClick();button(page,'改用 DeepSeek').props.onClick();await flush();
assert.deepEqual(switches,['qwen','deepseek']);assert.equal(submitted,0);assert.equal(env.calls.length,0);page.close();process.stdout.write('true');
""") is True


def test_stale_claude_availability_quote_rejection_offers_patch_without_trial():
    assert probe(SETUP + r"""
let submissions=0;lib.quoteBrainTrial=async()=>{throw new ApiError('Claude：BYOK 已关闭',409);};lib.startBrainTrial=async()=>submissions++;
const props={...trialProps,onProviderChange:provider=>lib.patchStudioProject('project-1',provider)};
const page=mount(brain.AccountBrainTrial,props);
assert(providers[0].available);assert(!all(page.tree,node=>node.type==='button'&&text(node)==='改用千问').length);
fillTrial(page);await flush();button(page,'用当前导演模型试读').props.onClick();await flush();
assert(!named(page,'BrainResults'));assert(error(page).includes('BYOK 已关闭'));
assert(text(page.tree).includes('本次试读未完成，可手动更换导演模型后再试读'));
button(page,'改用千问').props.onClick();await flush();
assert.deepEqual(env.calls.map(call=>[call.method,call.url]),[['PATCH','/api/studio/projects/project-1']]);
assert.deepEqual(JSON.parse(env.calls[0].body),{brain_provider:'qwen'});assert.equal(submissions,0);
props.provider='qwen';page.render();await flush();props.provider='claude';page.render();await flush();
assert(!all(page.tree,node=>node.type==='button'&&text(node)==='改用千问').length);page.close();process.stdout.write('true');
""") is True


def test_three_provider_results_ssr_cards_tables_warnings_and_repair_costs():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();const output={characters:[{name:'阿岚',role:'主角',description:'送信人',appearance_status:'needs_author',appearance_excerpt:''}],locations:[{name:'旧站台',description:'雨中的站台'}],props:[{name:'信',description:'未署名'}]};
const jobs=providers.map(p=>brainJob(p.id,{id:p.id+'-bible',task:'bible_extract',status:'succeeded',output,warnings:['外形待作者确定'],latency_s:1.5}));
const component=load('components/studio/BrainTrial.tsx');
const html=renderToStaticMarkup(realReact.createElement(component.BrainResults,{group:{group_id:'g',jobs},busy:false,onRelease:()=>{}}));
assert(html.includes('@[960px]:grid-cols-3'));for(const label of ['Claude','千问','DeepSeek'])assert(html.includes(label));
assert.equal((html.match(/待作者补充/g)||[]).length,3);assert.equal((html.match(/<table/g)||[]).length,9);assert(html.includes('警告：外形待作者确定'));assert(html.includes('1.5 秒'));assert(html.includes('$0.2000'));assert(html.includes('¥0.2000'));
const repaired=renderToStaticMarkup(realReact.createElement(component.BrainResultCard,{attempts:[brainJob('claude',{status:'invalid_output',error_message:'输出不合格'}),brainJob('claude',{id:'fix',parent_job_id:'claude-read',status:'succeeded',repaired:true,output:{logline:'雨夜来信',synopsis:'送信',genre:'剧情',tone:'克制',theme:'告别',pacing:'缓慢',adaptation_risks:['外景需雨效']}})],busy:false,onRelease:()=>{}}));
for(const label of ['原始调用','修正调用','已修正','一句话梗概','雨夜来信','改编风险','外景需雨效'])assert(repaired.includes(label));
process.stdout.write('true');
""") is True


def test_style_proposals_are_individual_cards_and_failures_are_chinese():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();const component=load('components/studio/BrainTrial.tsx');
const html=renderToStaticMarkup(realReact.createElement(component.BrainOutput,{task:'style_proposals',output:{proposals:[{name:'水墨',visual_style:'留白',palette:'墨色',camera:'固定',lighting:'侧光',rationale:'呼应情绪'},{name:'木偶',visual_style:'手作',palette:'陶色',camera:'缓推',lighting:'窗光',rationale:'角色质感'}]}}));
for(const label of ['水墨','木偶','留白','呼应情绪','角色质感'])assert(html.includes(label));assert.equal((html.match(/<section/g)||[]).length,2);
const rejected=renderToStaticMarkup(realReact.createElement(component.BrainResultCard,{attempts:[brainJob('claude',{status:'rejected',error_message:'模型配置不可用'})],busy:false,onRelease:()=>{}}));assert(rejected.includes('模型配置不可用'));process.stdout.write('true');
""") is True


def test_unsettled_costs_render_reserve_and_monthly_budget():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();const component=load('components/studio/BrainTrial.tsx');
for(const status of ['queued','running','uncertain']){
 const html=renderToStaticMarkup(realReact.createElement(component.BrainResultCard,{attempts:[brainJob('claude',{status,cost:{currency:'USD',amount:null},reserved_amount:'1.2345'})],busy:false,onRelease:()=>{}}));
 assert(html.includes('预留 $1.2345'));if(status==='uncertain')assert(html.includes('可能已扣费'));
}
const budget=render('components/studio/StudioBudget.tsx',{access:{today:{committed_cny:2,remaining_cny:298},caps:{daily_cny:300,brain_month_used_usd:1.25,brain_monthly_usd:40}}});
assert(budget.includes('Claude 本月'));assert(budget.includes('$1.25 / $40.00'));process.stdout.write('true');
""") is True


def test_quote_rejection_displays_reason_without_creating_group():
    assert probe(SETUP + r"""
let submissions=0;lib.quoteBrainTrial=async()=>{throw Error('Claude：请先启用 BYOK；千问：超出今日上限');};lib.startBrainTrial=async()=>submissions++;
const page=mount(brain.AccountBrainTrial,trialProps);fillTrial(page);await flush();button(page,'三家都跑（对比）').props.onClick();await flush();
assert(error(page).includes('超出今日上限'));assert(error(page).includes('请先启用 BYOK'));assert(!named(page,'BrainQuoteDialog'));assert.equal(submissions,0);page.close();process.stdout.write('true');
""") is True


def test_uncertain_release_requires_second_confirmation_and_shows_one_error():
    assert probe(SETUP + r"""
lib.quoteBrainTrial=async()=>trialQuote;lib.startBrainTrial=async()=>({group_id:'g',jobs:[brainJob('claude',{status:'uncertain'})]});
let released=0;lib.releaseStudioJob=async()=>{released++;throw Error('释放失败');};
const page=mount(brain.AccountBrainTrial,trialProps);fillTrial(page);await flush();button(page,'用当前导演模型试读').props.onClick();await flush();await named(page,'BrainQuoteDialog').props.onConfirm();await flush();
const results=named(page,'BrainResults');assert(results);results.props.onRelease(brainJob('claude',{status:'uncertain'}));await flush();assert.equal(released,0);
const element=named(page,'BrainReleaseDialog'),dialog=mount(element.type,element.props);assert(text(dialog.tree).includes('可能已扣费'));
button(dialog,'我已核实未扣费，释放额度').props.onClick();await flush();assert.equal(released,1);assert.equal(all(page.tree,n=>n.type?.name==='ErrorNotice').length,0);
assert.equal(named(page,'BrainReleaseDialog').props.error,'释放失败');page.close();dialog.close();process.stdout.write('true');
""") is True


def test_brain_polling_every_three_seconds_pauses_hidden_busy_and_stops_terminal():
    assert probe(SETUP + r"""
lib.quoteBrainTrial=async()=>trialQuote;lib.startBrainTrial=async()=>({group_id:'g',jobs:[brainJob()]});
let reads=0,status='running',budgets=0;lib.getBrainGroup=async()=>{reads++;return {group_id:'g',jobs:[brainJob('claude',{status})]};};
const props={...trialProps,onPoll:async()=>budgets++},page=mount(brain.AccountBrainTrial,props);fillTrial(page);await flush();button(page,'用当前导演模型试读').props.onClick();await flush();await named(page,'BrainQuoteDialog').props.onConfirm();await flush();
const timer=async()=>{const pair=[...env.timers].find(([,value])=>value.delay===3000);assert(pair,'3-second timer');env.timers.delete(pair[0]);await pair[1].fn();await flush();};
await timer();assert.equal(reads,1);assert.equal(budgets,1);props.busy=true;page.render();await timer();assert.equal(reads,1);props.busy=false;page.render();
document.hidden=true;for(const listener of env.listeners.get('visibilitychange'))listener();assert.equal([...env.timers.values()].filter(value=>value.delay===3000).length,0);
document.hidden=false;for(const listener of env.listeners.get('visibilitychange'))listener();await flush();assert.equal(reads,2);
status='succeeded';await timer();assert.equal(reads,3);assert.equal([...env.timers.values()].filter(value=>value.delay===3000).length,0);page.close();process.stdout.write('true');
""") is True


def test_request_helpers_use_quote_trial_group_and_patch_contract():
    assert probe(SETUP + r"""
const input={text:'素材',tasks:['read_through'],providers:'all'};
await lib.quoteBrainTrial('project',input);await lib.startBrainTrial('project',input);await lib.getBrainGroup('project','group');await lib.patchStudioProject('project','qwen');
assert.deepEqual(env.calls.map(call=>[call.method,call.url]),[['POST','/api/studio/projects/project/brain/quote'],['POST','/api/studio/projects/project/brain/trial'],['GET','/api/studio/projects/project/brain/groups/group'],['PATCH','/api/studio/projects/project']]);
assert.deepEqual(JSON.parse(env.calls[0].body),input);assert.deepEqual(JSON.parse(env.calls[3].body),{brain_provider:'qwen'});process.stdout.write('true');
""") is True


def test_workbench_new_backend_mounts_trial_and_provider_patch_updates_details():
    assert shell_probe(SHELL_SETUP + r"""
env.project.brain_provider='claude';const lib=load('lib/studio.ts');
lib.getBrainProviders=async()=>[{id:'claude',label:'Claude',available:true,model:'claude-sonnet-5-5'},{id:'qwen',label:'千问',available:true,model:'qwen3.8-max'}];
let changes=[];lib.patchStudioProject=async(id,provider)=>{changes.push(provider);env.project.brain_provider=provider;};
const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:true});await flush();
assert(named(page,'BrainTrial'));assert.equal(named(page,'BrainProviderPicker').props.current,'claude');
await named(page,'BrainProviderPicker').props.onChange('qwen');await flush();assert.deepEqual(changes,['qwen']);assert.equal(named(page,'BrainProviderPicker').props.current,'qwen');assert.equal(named(page,'BrainTrial').props.provider,'qwen');
assert.equal(env.calls.filter(call=>call==='GET /api/studio/projects/project').length,2);page.close();process.stdout.write('true');
""") is True


def test_workbench_legacy_project_keeps_wo2_stage_empty_state():
    assert shell_probe(SHELL_SETUP + r"""
const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:true});await flush();
assert(!named(page,'BrainTrial'));all(page.tree,node=>node.props?.role==='tab')[0].props.onClick();await flush();
assert.equal(all(page.tree,node=>node.props?.role==='tabpanel'&&!node.props.hidden)[0].props.children.props.children,'这一阶段将在后续版本开放');
page.close();process.stdout.write('true');
""") is True
