"""Offline WO3e director-KB page, component, SSR and request-contract probes.

The shared driver transpiles the checkout TSX in memory, renders the owning
component with real effects and event handlers, and never touches the network.
"""
from pathlib import Path
import json
import re
import shutil
import subprocess

import pytest
from test_studio_frontend_components import DRIVER as COMPONENT_DRIVER

ROOT = Path(__file__).resolve().parents[2]
DEPENDENCIES = {"typescript": "typescript/lib/typescript.js", "react": "react/index.js", "react/jsx-runtime": "react/jsx-runtime.js", "react-dom/server": "react-dom/server.js"}
DRIVER = COMPONENT_DRIVER.replace("if(name==='lucide-react')", """if(name==='next/link')return {__esModule:true,default:function Link(props){return (env.mode==='ssr'?realRuntime:runtime).jsx('a',props);}};
 if(name==='next/navigation')return {useRouter:()=>({push(){},replace(){}}),useSearchParams:()=>new URLSearchParams(env.search||''),usePathname:()=>'/'};
 if(name==='@/components/Glaze')return {__esModule:true,default:function Glaze(props){return (env.mode==='ssr'?realRuntime:runtime).jsx('section',{children:props.children,className:props.className});}};
 if(name==='@/components/Sidebar'||name==='@/components/InkLandscape')return {__esModule:true,default:function Empty(){return null;}};
 if(name==='lucide-react')""")

NEW_FILES = [
    "frontend/app/studio/kb/page.tsx",
    "frontend/app/studio/page.tsx",
    "frontend/components/studio/kb/KbWorkbench.tsx",
    "frontend/components/studio/kb/KbCardBrowser.tsx",
    "frontend/components/studio/kb/KbCardDetail.tsx",
    "frontend/components/studio/kb/KbExemplars.tsx",
    "frontend/components/studio/kb/KbStatsPanel.tsx",
    "frontend/components/studio/kb/KbTrialPanel.tsx",
    "frontend/components/studio/kb/KbQuoteDialog.tsx",
    "frontend/components/studio/kb/ReviewProviderPicker.tsx",
    "frontend/lib/studio-kb.ts",
]


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
const access={enabled:true,caps:{daily_cny:100,max_quote_cny:20,brain_monthly_usd:40,brain_month_used_usd:0,inflight:{wan:1,seedance:1}},today:{committed_cny:1,remaining_cny:99}};
const projects=[
 {id:'p1',title:'渡船',aspect:'16:9',brain_provider:'qwen',created_at:'2026-10-16 00:00:00',updated_at:'2026-10-16 00:00:00'},
 {id:'p2',title:'雾港',aspect:'9:16',brain_provider:'deepseek',created_at:'2026-10-16 00:00:00',updated_at:'2026-10-16 00:00:00'}];
const grammarSummary={id:'grammar-shot-size',type:'grammar',title:'景别',summary:'九级景别与用法',tags:['shot','size']};
const cameraSummary={id:'grammar-camera-movement',type:'grammar',title:'运镜总表',summary:'推拉摇移跟升降环绕手持',tags:['camera','movement']};
const grammarCard={...grammarSummary,version:1,definition:'景别是人物在画面中的大小。',narrative_use:'控制观众与动作的距离。',safe_prompt:'中景（人物腰部以上）',avoid:['裸写 Dolly'],entries:[{name:'中景',definition:'腰部以上',safe_prompt:'中景（人物腰部以上）'}],related:['grammar-camera-angle'],sources:[{name:'作者实测',license:'own'}]};
const sceneCard={id:'scene-fight',type:'scene',title:'打斗',summary:'近身攻防',tags:['fight'],version:1,scene_type:'fight',signals:['出现实质接触'],beats:['试探','升级','收束'],coverage:['中景定场','近景受击'],pacing:{fast:{shots_per_min:[18,24],shot_seconds:[1.5,3]},mid:{shots_per_min:[12,18],shot_seconds:[3,5]},slow:{shots_per_min:[6,12],shot_seconds:[5,9]}},camera:['敏感镜头用固定机位'],sound:['击中声先于画面'],ai_risks:[{risk:'正脸撞肖像闸',fallback:'改逆光剪影'}],example:'中景｜固定｜他抬手挡住门｜2.2 秒',related_grammar:['grammar-camera-movement'],related_negative:['negative-looking-at-camera'],sources:[{name:'作者实测',license:'own'}]};
const modelCard={id:'model-seedance-2-5-photoreal',type:'model',title:'Seedance 2.5 写实',summary:'写实视频能力',tags:['seedance'],version:1,model:'seedance-2.5',style:'photoreal',facts:['480p 输出 852×480'],portrait_gate:'写实正脸会被拒绝',copyright:'形象近似 IP 会被拦',motion_risks:['环绕会编造细节'],prompt_syntax:['时间戳按版本核实'],max_characters:2,lint_rules:[{id:'seedance-portrait',when:{realism:'photoreal',shot_size_in:['中景']},level:'warn',message:'写实中景露脸建议改万相'}],sources:[{name:'厂商文档',license:'vendor-doc'}]};
const negativeCard={id:'negative-looking-at-camera',type:'negative',title:'人物看镜头',summary:'视线落在对手身上',tags:['eyeline'],version:1,wrong:'人物直视镜头',right:'视线落在对手身上，不看镜头',why:'看镜头会破坏戏剧空间',evidence:'作者实测 2026-10-17',applies_to:{scene_type:['dialogue','fight'],model:['seedance']},lint_pattern:'(?i)looks at camera',sources:[{name:'作者实测',license:'own'}]};
const cardMap={'grammar-shot-size':grammarCard,'grammar-camera-movement':{...cameraSummary,version:1,definition:'运镜是摄影机的运动。',narrative_use:'带着观众进入空间。',safe_prompt:'推轨（镜头沿地面平稳靠近）',avoid:['裸写 Dolly'],sources:[{name:'作者实测',license:'own'}]}};
const exemplar={id:'ex-1',source:'studio',scene_type:'fight',kind:'good',reason:'受击方向清楚',shot:{shot_size:'中景',angle:'平视',camera:'固定',action:'他抬手挡住门',duration_s:2.2},video_model:'seedance',tags:['fight'],created_at:'2026-10-16 00:00:00',archived:0};
const badExemplar={...exemplar,id:'ex-2',kind:'bad',reason:'正脸看镜头',shot:{shot_size:'近景',angle:'平视',camera:'推近',action:'他看向镜头',duration_s:2}};
const quote={id:'q1',kind:'kb_trial',items:[{item_id:null,name:'导演试拆 · 带知识库',versions:1,unit:0.04,est:0.04,currency:'CNY'},{item_id:null,name:'导演试拆 · 不带知识库',versions:1,unit:0.04,est:0.04,currency:'CNY'}],total:0.08,currency:'CNY',totals:{CNY:0.08,USD:0},expires_at:'2099-01-01T00:00:00Z'};
const mixedQuote={id:'q2',kind:'kb_trial',items:[
 {item_id:'with_kb:shot_plan',name:'导演试拆 · 带知识库',versions:1,unit:0.43291,est:0.43291,currency:'USD'},
 {item_id:'with_kb:cross_review',name:'交叉审核 · 带知识库',versions:1,unit:0.274296,est:0.274296,currency:'CNY'},
 {item_id:'without_kb:shot_plan',name:'导演试拆 · 不带知识库',versions:1,unit:0.43176,est:0.43176,currency:'USD'},
 {item_id:'without_kb:cross_review',name:'交叉审核 · 不带知识库',versions:1,unit:0.274296,est:0.274296,currency:'CNY'}],
 total:null,currency:'mixed',totals:{CNY:0.548592,USD:0.86467},expires_at:'2099-01-01T00:00:00Z'};
const review={provider:'qwen',model:'qwen3.8-max',status:'succeeded',verdict:'issues',summary:'第 3 镜动作过多，其余可用。',issues:[{severity:'must',kind:'storyboard',where:'第 3 镜',source_ref:'原文第 2 段',problem:'单镜动作超过 3 个',suggestion:'拆成两镜'},{severity:'should',kind:'continuity',where:'第 4 镜',problem:'道具换手',suggestion:'补一个交接动作'}]};
const modeResult={status:'succeeded',template_id:'scene-fight',deviations:'第 2 镜改为固定机位',card_ids:['scene-fight','grammar-camera-movement'],lint:[{shot_no:2,rule_id:'camera-fixed',level:'warn',message:'敏感镜头建议固定机位'},{shot_no:4,rule_id:'duration',level:'info',message:'生成时长不足 4 秒'}],chars:2345,shots:[{no:1,shot_size:'中景',angle:'平视',camera:'固定',action:'他抬手挡住门',duration_s:2.2,basis:['scene-fight']},{no:2,shot_size:'近景',angle:'侧面',camera:'固定',action:'木屑落在地上',duration_s:1.8,basis:['grammar-camera-movement']}],review};
const modeWithout={...modeResult,template_id:null,deviations:'',card_ids:[],chars:0,lint:[],review:null,shots:[{...modeResult.shots[0],basis:[]}]};
const trialDone={id:'t1',kind:'kb_trial',status:'done',modes:['with_kb','without_kb'],with_kb:modeResult,without_kb:modeWithout,review:{with_kb:review,without_kb:null}};
"""


def test_requests_paths_bodies_and_helpers():
    assert probe(SETUP + r"""
const lib=load('lib/studio-kb.ts');
assert.equal(lib.kbSceneTypeOptions.length,17);
assert.deepEqual(lib.kbSceneTypeOptions.map(option=>option.id),['dialogue','establishing','confrontation','fight','chase','reveal','monologue','flashback','ensemble','montage','twist','intimacy','phone-call','process-closeup','explainer','scare','investigation']);
assert.equal(lib.kbReviewProviderOptions.map(option=>option.label).join('、'),'Claude、千问 3.8 Max、DeepSeek、关闭');
assert.equal(lib.kbSceneTypeLabel('fight'),'打斗');
assert.equal(lib.kbModeLabel('with_kb'),'带知识库');
assert.deepEqual(lib.kbShotBasis({basis:['a','b']}),['a','b']);
assert.equal(lib.kbRange([1.5,2.3],'秒'),'1.5–2.3 秒');
assert.equal(lib.kbInjectedChars({chars:123}),123);
assert.equal(lib.kbInjectedChars({injected_chars:88}),88);
assert.equal(lib.parseKbJson('{"a":1}',{}).a,1);
const merged=lib.kbTrialMode({id:'t',review:{with_kb:review},modes:{with_kb:{shots:[]}}},'with_kb');
assert.equal(merged.review.summary,review.summary);
assert.equal(lib.kbTrialInFlight({id:'t',status:'running'}),true);
assert.equal(lib.kbTrialInFlight(trialDone),false);
const calls=[];
agents.apiJson=async(url,init={})=>{calls.push({url,method:init.method??'GET',body:init.body});return {};};
await lib.listKbCards('grammar','推轨');
await lib.listKbCards();
await lib.getKbCard('scene-dialogue');
await lib.listKbExemplars({scene_type:'fight',kind:'bad'});
await lib.listKbExemplars({});
await lib.patchKbExemplar('ex-1',{kind:'bad',reason:'正脸'});
await lib.patchKbExemplar('ex-1',{archived:true});
await lib.getKbStats();
const tags={scene_type:'fight',position:'opening',pace:'fast',emotion:'紧张',cast_count:2,realism:'photoreal',setting:'interior',sensitive:['face_closeup']};
const input={scene_text:'夜里，他在渡口等人。',tags,target_seconds:30,video_model:'wan',modes:['with_kb','without_kb']};
await lib.quoteKbTrial('p1',input);
await lib.startKbTrial('p1','q1');
await lib.getKbTrial('p1','t 1');
await lib.getKbReviewProvider('p1');
await lib.setKbReviewProvider('p1','off');
assert.equal(calls[0].url,'/api/studio/kb/cards?type=grammar&q='+encodeURIComponent('推轨'));
assert.equal(calls[1].url,'/api/studio/kb/cards');
assert.equal(calls[2].url,'/api/studio/kb/cards/scene-dialogue');
assert.equal(calls[3].url,'/api/studio/kb/exemplars?scene_type=fight&kind=bad');
assert.equal(calls[4].url,'/api/studio/kb/exemplars');
assert.equal(calls[5].method,'PATCH');assert.equal(calls[5].url,'/api/studio/kb/exemplars/ex-1');assert.deepEqual(JSON.parse(calls[5].body),{kind:'bad',reason:'正脸'});
assert.deepEqual(JSON.parse(calls[6].body),{archived:true});
assert.equal(calls[7].url,'/api/studio/kb/stats');
assert.equal(calls[8].url,'/api/studio/projects/p1/kb/trial/quote');
const body=JSON.parse(calls[8].body);
assert.deepEqual(Object.keys(body),['scene_text','tags','target_seconds','video_model','modes']);
assert.equal(body.scene_text,input.scene_text);assert.equal(body.target_seconds,30);assert.equal(body.video_model,'wan');
assert.deepEqual(body.tags,tags);assert.deepEqual(body.modes,['with_kb','without_kb']);
assert.equal(calls[9].url,'/api/studio/projects/p1/kb/trial/start');assert.deepEqual(JSON.parse(calls[9].body),{quote_id:'q1'});
assert.equal(calls[10].url,'/api/studio/projects/p1/kb/trials/t%201');
assert.equal(calls[11].url,'/api/studio/projects/p1/review-provider');
assert.equal(calls[12].method,'PATCH');assert.equal(calls[12].url,'/api/studio/projects/p1/review-provider');assert.deepEqual(JSON.parse(calls[12].body),{review_provider:'off'});
process.stdout.write('true');
""") is True


def test_links_tabs_entry_points_and_gate_states():
    workbench = (ROOT / "frontend/components/studio/kb/KbWorkbench.tsx").read_text(encoding="utf-8")
    for label in ["语法", "场景模板", "模型能力", "反例", "案例库", "节奏统计", "试拆对比"]:
        assert f'label: "{label}"' in workbench, label
    assert 'role="tablist"' in workbench
    assert "flex-wrap" in workbench
    studio_page = (ROOT / "frontend/app/studio/page.tsx").read_text(encoding="utf-8")
    assert 'studioHref("/studio/kb", embedded)' in studio_page
    assert "useSearchParams" in studio_page
    assert 'href="/studio/kb"' not in studio_page
    assert "导演知识库" in studio_page
    shell = (ROOT / "frontend/components/studio/StudioWorkbench.tsx").read_text(encoding="utf-8")
    assert "ReviewProviderPicker" in shell
    assert 'studioHref("/studio/kb", embedded)' in shell
    assert "导演知识库" in shell
    kb_page = (ROOT / "frontend/app/studio/kb/page.tsx").read_text(encoding="utf-8")
    assert "KbWorkbench" in kb_page
    assert (ROOT / "frontend/components/studio/kb/ReviewProviderPicker.tsx").is_file()

    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();
const Workbench=load('components/studio/kb/KbWorkbench.tsx').AccountKbWorkbench;
const loading=renderToStaticMarkup(realReact.createElement(Workbench,{owner:env.owner,embedded:false}));
assert(loading.includes('正在打开导演知识库…'));
env.mode='hooks';cache.clear();
const WorkbenchHooks=load('components/studio/kb/KbWorkbench.tsx').AccountKbWorkbench;
let calls=[];
agents.apiJson=async(url,init={})=>{calls.push(url);if(url==='/api/studio/access')return access;if(url.includes('/kb/cards?'))return [grammarSummary];if(url.endsWith('/kb/cards/grammar-shot-size'))return grammarCard;if(url.endsWith('/kb/stats'))return {ready:false,episodes:2};throw new Error('unexpected '+url);};
const page=mount(WorkbenchHooks,{owner:env.owner,embedded:false});await flush();
const tabs=all(page.tree,n=>n.type==='button'&&n.props.role==='tab');
assert.equal(tabs.length,7);
assert.deepEqual(tabs.map(text),['语法','场景模板','模型能力','反例','案例库','节奏统计','试拆对比']);
assert.equal(all(page.tree,n=>n.props?.role==='tabpanel')[0].props.id,'kb-panel-grammar');
assert(text(page.tree).includes('导演知识库'));
all(page.tree,n=>n.type==='button'&&n.props.role==='tab'&&text(n)==='节奏统计')[0].props.onClick();await flush();
assert.equal(named(page,'KbStatsPanel').props.owner,env.owner);
page.close();
agents.apiJson=async()=>{throw new ApiError('Not Found',404);};
const unauthorised=mount(WorkbenchHooks,{owner:env.owner,embedded:false});await flush();
assert(text(unauthorised.tree).includes('暂未开放'));unauthorised.close();process.stdout.write('true');
""") is True


def test_workbench_404_and_login_states():
    assert probe(SETUP + r"""
let fail=true;const original=agents.apiJson;
agents.apiJson=async(url,init)=>{if(fail)throw new ApiError('Not Found',404);return original(url,init);};
const Workbench=load('components/studio/kb/KbWorkbench.tsx').AccountKbWorkbench;
const page=mount(Workbench,{owner:env.owner,embedded:false});await flush();
assert(text(page.tree).includes('暂未开放'));
fail=false;agents.apiJson=async(url)=>url==='/api/studio/access'?access:[grammarSummary];
const login=mount(Workbench,{owner:'',embedded:false});await flush();
assert(text(login.tree).includes('请登录后打开导演知识库。'));
login.close();page.close();
process.stdout.write('true');
""") is True


def test_card_browser_loading_empty_error_search_tag_and_detail():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();
const BrowserSSR=load('components/studio/kb/KbCardBrowser.tsx').default;
const initial=renderToStaticMarkup(realReact.createElement(BrowserSSR,{type:'grammar',owner:env.owner}));
assert(initial.includes('正在读取语法卡片…'));
env.mode='hooks';cache.clear();
const BrowserHooks=load('components/studio/kb/KbCardBrowser.tsx').default;
let fail=false;
agents.apiJson=async(url,init={})=>{
 if(fail)throw new ApiError('卡片读取失败',500);
 if(url.includes('/kb/cards?'))return [grammarSummary,cameraSummary];
 if(url.endsWith('/kb/cards/grammar-shot-size'))return grammarCard;
 if(url.endsWith('/kb/cards/grammar-camera-movement'))return cardMap['grammar-camera-movement'];
 throw new Error('unexpected '+url);
};
const page=mount(BrowserHooks,{type:'grammar',owner:env.owner});await flush();
assert(text(page.tree).includes('景别'));
assert(text(page.tree).includes('九级景别与用法'));
assert.equal(named(page,'KbCardDetail').props.card.definition,'景别是人物在画面中的大小。');
assert.deepEqual(named(page,'KbCardDetail').props.card.related,['grammar-camera-angle']);
assert.equal(named(page,'KbCardDetail').props.card.sources[0].name,'作者实测');
const search=all(page.tree,n=>n.type==='input'&&n.props.type==='search')[0];
search.props.onChange({target:{value:'运镜'}});await flush();
let list=all(page.tree,n=>n.props?.['aria-label']==='语法卡片列表')[0];
let cards=all(list,n=>n.type==='button');
assert.equal(cards.length,1);assert(text(cards[0]).includes('运镜总表'));
search.props.onChange({target:{value:''}});await flush();
all(page.tree,n=>n.type==='button'&&text(n)==='camera')[0].props.onClick();await flush();
list=all(page.tree,n=>n.props?.['aria-label']==='语法卡片列表')[0];
cards=all(list,n=>n.type==='button');
assert.equal(cards.length,1);assert(text(cards[0]).includes('运镜总表'));
all(page.tree,n=>n.type==='button'&&text(n)==='camera')[0].props.onClick();await flush();
fail=true;const broken=mount(BrowserHooks,{type:'grammar',owner:env.owner});await flush();
assert(error(broken).includes('卡片读取失败'));
fail=false;named(broken,'ErrorNotice').props.retry();await flush();
assert(text(broken.tree).includes('景别'));
broken.close();
agents.apiJson=async()=>[];
const empty=mount(BrowserHooks,{type:'grammar',owner:env.owner});await flush();
assert(text(empty.tree).includes('还没有语法卡片。'));empty.close();
page.close();process.stdout.write('true');
""") is True


def test_card_detail_renders_each_card_type():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();
const Detail=load('components/studio/kb/KbCardDetail.tsx').default;
const checks=[[grammarCard,['景别','定义','叙事作用','提示词安全写法','不要这样写','子条目','中景','相关卡片','作者实测']],
 [sceneCard,['打斗','识别信号','节拍','覆盖拍法','节奏分档','每分钟 18–24 镜','运镜建议','声音设计','AI 风险与降级','改逆光剪影','示例拆法','相关语法','相关反例']],
 [modelCard,['Seedance 2.5 写实','能力事实','肖像闸','版权拦截','运镜风险','提示词写法','同框人数上限','检查规则','seedance-portrait','写实中景露脸建议改万相']],
 [negativeCard,['错误写法','正确写法','原因','出处','适用场景','适用模型','检查正则','looks at camera']]];
for(const [card,values] of checks){const html=renderToStaticMarkup(realReact.createElement(Detail,{card}));for(const value of values)assert(html.includes(value),value);assert(!html.includes('font-bold'));assert(!html.includes('font-semibold'));}
process.stdout.write('true');
""") is True


def test_stats_not_ready_ready_and_error_retry():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();
const Stats=load('components/studio/kb/KbStatsPanel.tsx').default;
const initial=renderToStaticMarkup(realReact.createElement(Stats,{owner:env.owner}));
assert(initial.includes('正在读取节奏统计…'));
env.mode='hooks';cache.clear();
const StatsHooks=load('components/studio/kb/KbStatsPanel.tsx').default;
let payload={ready:false,episodes:2};
agents.apiJson=async()=>payload;
const page=mount(StatsHooks,{owner:env.owner});await flush();
assert(text(page.tree).includes('累计满 5 集后显示你的节奏统计'));
assert(text(page.tree).includes('当前累计 2 集'));
page.close();
payload={ready:true,episodes:6,shots:312,avg_shot_s:3.9,scene_types:[{scene_type:'fight',episodes:6,shots:312,avg_shot_s:3.9,shot_size_json:'{"中景":120,"近景":80}',camera_json:'{"固定":150}',updated_at:'2026-10-16 00:00:00'}]};
const ready=mount(StatsHooks,{owner:env.owner});await flush();
for(const value of ['累计 6 集','累计 312 镜','平均每镜 3.90 秒','中景 120','固定 150','打斗'])assert(text(ready.tree).includes(value),value);
ready.close();
agents.apiJson=async()=>{throw new ApiError('统计读取失败',500);};
const broken=mount(StatsHooks,{owner:env.owner});await flush();
assert(error(broken).includes('统计读取失败'));
agents.apiJson=async()=>({ready:false,episodes:1});
named(broken,'ErrorNotice').props.retry();await flush();
assert(named(broken,'ErrorNotice')===undefined);
assert(text(broken.tree).includes('累计满 5 集后显示你的节奏统计'));
broken.close();process.stdout.write('true');
""") is True


def test_exemplars_filters_edit_archive_loading_and_empty():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();
const ExemplarsSSR=load('components/studio/kb/KbExemplars.tsx');
const initial=renderToStaticMarkup(realReact.createElement(ExemplarsSSR.default,{owner:env.owner}));
assert(initial.includes('正在读取案例…'));
env.mode='hooks';cache.clear();
const Exemplars=load('components/studio/kb/KbExemplars.tsx');
const calls=[];
agents.apiJson=async(url,init={})=>{
 const method=init.method??'GET';const body=typeof init.body==='string'?JSON.parse(init.body):undefined;
 calls.push({url,method,body});
 if(method==='PATCH')return {...exemplar,...body};
 if(url.includes('/kb/exemplars?'))return [exemplar];
 if(url.endsWith('/kb/exemplars'))return [exemplar,badExemplar];
 throw new Error('unexpected '+method+' '+url);
};
const page=mount(Exemplars.default,{owner:env.owner});await flush();
const rows=all(page.tree,n=>n.type?.name==='KbExemplarRow');
assert.equal(rows.length,2);
assert.equal(rows[0].props.exemplar.reason,'受击方向清楚');
assert.equal(rows[0].props.exemplar.shot.camera,'固定');
await rows[0].props.onSave({kind:'bad',reason:'改判为反例'});
assert(calls.some(call=>call.method==='PATCH'&&call.url==='/api/studio/kb/exemplars/ex-1'&&call.body.kind==='bad'));
await rows[0].props.onArchive();
assert(calls.some(call=>call.method==='PATCH'&&call.body.archived===true));
const selects=all(page.tree,n=>n.type==='select');
selects[0].props.onChange({target:{value:'fight'}});await flush();
assert(calls.some(call=>call.url==='/api/studio/kb/exemplars?scene_type=fight'));
selects[1].props.onChange({target:{value:'good'}});await flush();
assert(calls.some(call=>call.url==='/api/studio/kb/exemplars?scene_type=fight&kind=good'));
const row=mount(load('components/studio/kb/KbExemplars.tsx').KbExemplarRow,{exemplar,busy:false,onSave:async patch=>calls.push({url:'row-save',method:'ROW',body:patch}),onArchive:async()=>{}});await flush();
all(row.tree,n=>n.type==='button'&&text(n)==='反例')[0].props.onClick();await flush();
all(row.tree,n=>n.type==='textarea')[0].props.onChange({target:{value:'正脸看镜头'}});await flush();
all(row.tree,n=>n.type==='button'&&text(n)==='保存')[0].props.onClick();await flush();
assert.deepEqual(calls.find(call=>call.method==='ROW').body,{kind:'bad',reason:'正脸看镜头'});
row.close();
const archived=mount(load('components/studio/kb/KbExemplars.tsx').KbExemplarRow,{exemplar:{...exemplar,archived:1},busy:false,onSave:async()=>{},onArchive:async()=>{}});await flush();
assert(text(archived.tree).includes('已归档'));
assert(all(archived.tree,n=>n.type==='button'&&text(n)==='已归档')[0].props.disabled);
archived.close();
agents.apiJson=async()=>[];
const empty=mount(Exemplars.default,{owner:env.owner});await flush();
assert(text(empty.tree).includes('还没有符合条件的案例。'));empty.close();
page.close();process.stdout.write('true');
""") is True


def test_review_provider_picker_dropdown_same_model_hint_and_patch():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();
const Picker=load('components/studio/kb/ReviewProviderPicker.tsx').default;
const initial=renderToStaticMarkup(realReact.createElement(Picker,{projectId:'p1',owner:env.owner,brainProvider:'qwen'}));
assert(initial.includes('正在读取审核模型…'));
assert(initial.includes('审核会把原文发给所选厂商。'));
env.mode='hooks';cache.clear();
const PickerHooks=load('components/studio/kb/ReviewProviderPicker.tsx').default;
const calls=[];
agents.apiJson=async(url,init={})=>{
 calls.push({url,method:init.method??'GET',body:init.body});
 if((init.method??'GET')==='PATCH'){const body=JSON.parse(init.body);return {review_provider:body.review_provider,brain_provider:'qwen',same_as_director:body.review_provider==='qwen'};}
 return {review_provider:'qwen',brain_provider:'qwen',same_as_director:true};
};
const page=mount(PickerHooks,{projectId:'p1',owner:env.owner,brainProvider:'qwen'});await flush();
assert(text(page.tree).includes('同一模型自审，效果有限'));
assert(text(page.tree).includes('审核会把原文发给所选厂商。'));
const select=all(page.tree,n=>n.type==='select')[0];
assert(select);
assert.equal(all(select,n=>n.type==='option').map(text).join('、'),'Claude、千问 3.8 Max、DeepSeek、关闭');
select.props.onChange({target:{value:'deepseek'}});await flush();
assert.equal(calls.at(-1).method,'PATCH');
assert.equal(calls.at(-1).url,'/api/studio/projects/p1/review-provider');
assert.deepEqual(JSON.parse(calls.at(-1).body),{review_provider:'deepseek'});
assert(!text(page.tree).includes('同一模型自审，效果有限'));
page.close();
const other=mount(PickerHooks,{projectId:'p1',owner:env.owner,brainProvider:'claude'});await flush();
assert(!text(other.tree).includes('同一模型自审，效果有限'));other.close();
let fail=true;
agents.apiJson=async()=>{if(fail)throw new ApiError('审核读取失败',500);return {review_provider:'off',brain_provider:'qwen',same_as_director:false};};
const broken=mount(PickerHooks,{projectId:'p1',owner:env.owner,brainProvider:'qwen'});await flush();
assert(error(broken).includes('审核读取失败'));
fail=false;named(broken,'ErrorNotice').props.retry();await flush();
assert(all(broken.tree,n=>n.type==='select').length===1);
broken.close();process.stdout.write('true');
""") is True


def test_trial_quote_workflow_polling_and_two_column_results():
    assert probe(SETUP + r"""
async function fire(delay){const pair=[...env.timers].find(([,timer])=>timer.delay===delay);assert(pair,'missing '+delay+' timer');env.timers.delete(pair[0]);await pair[1].fn();await flush();}
env.mode='ssr';cache.clear();
const Trial=load('components/studio/kb/KbTrialPanel.tsx');
const loading=renderToStaticMarkup(realReact.createElement(Trial.default,{owner:env.owner}));
assert(loading.includes('正在读取项目…'));
const quoteHtml=renderToStaticMarkup(realReact.createElement(load('components/studio/kb/KbQuoteDialog.tsx').default,{quote,busy:false,onConfirm:async()=>{},onClose:()=>{}}));
for(const value of ['确认试拆报价','确认开始试拆','导演试拆 · 带知识库','¥0.0800','报价剩余有效时间'])assert(quoteHtml.includes(value),value);
const expired=renderToStaticMarkup(realReact.createElement(load('components/studio/kb/KbQuoteDialog.tsx').default,{quote:{...quote,expires_at:'2000-01-01T00:00:00Z'},busy:false,onConfirm:async()=>{},onClose:()=>{}}));
assert(expired.includes('报价已过期'));assert(/<button type="submit"[^>]*disabled/.test(expired));
env.mode='ssr';cache.clear();
const column=renderToStaticMarkup(realReact.createElement(Trial.KbTrialModeColumn,{mode:'with_kb',data:modeResult}));
for(const value of ['带知识库','模板 id：scene-fight','注入字数：2345','景别','机位','动作','时长','依据','中景','他抬手挡住门','2.2 秒','scene-fight','知识库检查','敏感镜头建议固定机位','交叉审核','第 3 镜动作过多','must','单镜动作超过 3 个','拆成两镜','原文第 2 段'])assert(column.includes(value),value);
assert(column.includes('tag tag-rec'));
assert(!column.includes('<b'));assert(!column.includes('font-bold'));assert(!column.includes('font-semibold'));
assert(column.includes('@[560px]:block'));assert(column.includes('@[560px]:hidden'));
const noReview=renderToStaticMarkup(realReact.createElement(Trial.KbTrialModeColumn,{mode:'without_kb',data:{...modeWithout,review:null}}));
assert(noReview.includes('本次未开启交叉审核。'));
const failedReview=renderToStaticMarkup(realReact.createElement(Trial.KbTrialModeColumn,{mode:'with_kb',data:{...modeResult,review:{provider:'qwen',model:'qwen3.8-max',status:'failed',verdict:null,summary:null,issues:[]}}}));
assert(failedReview.includes('审核失败'));
env.mode='hooks';cache.clear();
const TrialHooks=load('components/studio/kb/KbTrialPanel.tsx').default;
let quotes=[],starts=[],reads=0;
agents.apiJson=async(url,init={})=>{
 const method=init.method??'GET';const body=typeof init.body==='string'?JSON.parse(init.body):undefined;
 if(url==='/api/studio/projects'&&method==='GET')return projects;
 if(url.endsWith('/kb/trial/quote')){quotes.push(body);return quote;}
 if(url.endsWith('/kb/trial/start')){starts.push(body);return {id:'t1',trial_id:'t1',status:'queued',modes:['with_kb','without_kb']};}
 if(url.endsWith('/kb/trials/t1')){reads++;return trialDone;}
 throw new Error('unexpected '+method+' '+url);
};
const page=mount(TrialHooks,{owner:env.owner});await flush();
assert(text(page.tree).includes('1 选项目'));
assert(text(page.tree).includes('2 粘贴一场戏'));
assert(text(page.tree).includes('3 填标签'));
assert(text(page.tree).includes('4 报价并开始'));
assert.equal(all(page.tree,n=>n.type==='select')[0].props.value,'p1');
const scene=all(page.tree,n=>n.type==='textarea')[0];
scene.props.onChange({target:{value:'夜里，他在渡口等人。'}});await flush();
all(page.tree,n=>n.type==='button'&&text(n)==='试拆报价')[0].props.onClick();await flush();
assert.equal(quotes.length,1);
assert.equal(quotes[0].scene_text,'夜里，他在渡口等人。');
assert.deepEqual(quotes[0].modes,['with_kb','without_kb']);
assert.equal(quotes[0].target_seconds,30);
assert.equal(quotes[0].video_model,'wan');
assert.equal(quotes[0].tags.scene_type,'dialogue');
assert.equal(quotes[0].tags.position,'body');
assert.equal(quotes[0].tags.cast_count,2);
assert.equal(quotes[0].tags.pace,'mid');
assert.equal(named(page,'KbQuoteDialog')!==undefined,true);
await named(page,'KbQuoteDialog').props.onConfirm();await flush();
assert.equal(starts.length,1);assert.deepEqual(starts[0],{quote_id:'q1'});
assert(text(page.tree).includes('排队中'));
assert([...env.timers.values()].some(timer=>timer.delay===3000));
await fire(3000);
assert.equal(reads,1);
const columns=all(page.tree,n=>n.type?.name==='KbTrialModeColumn');
assert.equal(columns.length,2);
assert.equal(columns[0].props.mode,'with_kb');assert.equal(columns[1].props.mode,'without_kb');
assert.equal(columns[0].props.data.template_id,'scene-fight');
assert.equal(columns[0].props.data.chars,2345);
assert.equal(columns[0].props.data.review.issues[0].severity,'must');
assert.equal(columns[1].props.data.template_id,null);
assert.equal(columns[1].props.data.review,null);
page.close();process.stdout.write('true');
""") is True


def test_mixed_currency_quote_shows_per_line_currency_and_split_totals():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();
const Dialog=load('components/studio/kb/KbQuoteDialog.tsx').default;
const mixed=renderToStaticMarkup(realReact.createElement(Dialog,{quote:mixedQuote,busy:false,onConfirm:async()=>{},onClose:()=>{}}));
assert(mixed.includes('导演试拆 · 带知识库'),mixed);
assert(mixed.includes('$0.4329'),mixed);
assert(mixed.includes('¥0.2743'),mixed);
assert(mixed.includes('$0.4318'),mixed);
assert(mixed.includes('合计 <span class="readout">¥0.5486 + $0.8647</span>'),mixed);
assert(!mixed.includes('$1.4133'),mixed);
assert(!mixed.includes('¥1.4133'),mixed);
const single=renderToStaticMarkup(realReact.createElement(Dialog,{quote,busy:false,onConfirm:async()=>{},onClose:()=>{}}));
assert(single.includes('¥0.0800'),single);
assert(!single.includes(' + $'),single);
process.stdout.write('true');
""") is True


def test_trial_mode_column_warns_when_model_card_missing():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();
const Column=load('components/studio/kb/KbTrialPanel.tsx').KbTrialModeColumn;
const warning='该写实度没有对应的模型卡，未注入模型能力与其检查规则';
const missing=renderToStaticMarkup(realReact.createElement(Column,{mode:'with_kb',data:{...modeResult,model_card_missing:true}}));
assert(missing.includes(warning),missing);
assert(missing.indexOf('模板 id')<missing.indexOf(warning));
assert(missing.indexOf(warning)<missing.indexOf('知识库检查'));
const present=renderToStaticMarkup(realReact.createElement(Column,{mode:'without_kb',data:{...modeWithout,model_card_missing:false}}));
assert(!present.includes(warning));
const absent=renderToStaticMarkup(realReact.createElement(Column,{mode:'with_kb',data:modeResult}));
assert(!absent.includes(warning));
process.stdout.write('true');
""") is True


def test_studio_page_kb_entry_keeps_embed():
    assert probe(SETUP + r"""
env.mode='ssr';env.search='embed=1';cache.clear();
const Page=load('app/studio/page.tsx').default;
const embedded=renderToStaticMarkup(realReact.createElement(Page));
assert(embedded.includes('href="/studio/kb?embed=1"'),embedded);
env.search='';cache.clear();
const plain=renderToStaticMarkup(realReact.createElement(load('app/studio/page.tsx').default));
assert(plain.includes('href="/studio/kb"'),plain);
assert(!plain.includes('href="/studio/kb?embed=1"'));
process.stdout.write('true');
""") is True


def test_trial_validation_does_not_request():
    assert probe(SETUP + r"""
const calls=[];
agents.apiJson=async(url,init={})=>{calls.push(url);if(url==='/api/studio/projects')return projects;throw new Error('unexpected '+url);};
const Trial=load('components/studio/kb/KbTrialPanel.tsx').default;
const page=mount(Trial,{owner:env.owner});await flush();
all(page.tree,n=>n.type==='button'&&text(n)==='试拆报价')[0].props.onClick();await flush();
assert.equal(calls.filter(url=>url.includes('/kb/trial/quote')).length,0);
assert(text(page.tree).includes('请粘贴一场戏。'));
const scene=all(page.tree,n=>n.type==='textarea')[0];
scene.props.onChange({target:{value:'一场戏'}});await flush();
const numberInputs=all(page.tree,n=>n.type==='input'&&n.props.type==='number');
numberInputs.find(input=>input.props.max===120).props.onChange({target:{value:'5'}});await flush();
all(page.tree,n=>n.type==='button'&&text(n)==='试拆报价')[0].props.onClick();await flush();
assert(text(page.tree).includes('目标时长为 10–120 秒。'));
assert.equal(calls.filter(url=>url.includes('/kb/trial/quote')).length,0);
page.close();process.stdout.write('true');
""") is True


def test_no_bold_no_horizontal_overflow_and_narrow_layout_constraints():
    bold = re.compile(r"font-semibold|font-bold|font-weight\s*:\s*(?:[6-9]\d{2}|bold)|fontWeight|<b>|</b>|<strong>|</strong>")
    for relative in NEW_FILES:
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert not bold.search(text), relative
        assert "overflow-x-auto" not in text, relative
        assert "min-w-[" not in text, relative
    trial = (ROOT / "frontend/components/studio/kb/KbTrialPanel.tsx").read_text(encoding="utf-8")
    assert "@[1000px]:grid-cols-2" in trial
    assert "grid-cols-1" in trial
    assert "@[560px]:block" in trial and "@[560px]:hidden" in trial
    assert "flex-wrap" in trial
    browser = (ROOT / "frontend/components/studio/kb/KbCardBrowser.tsx").read_text(encoding="utf-8")
    assert "@[900px]:grid-cols-[minmax(0,320px)_minmax(0,1fr)]" in browser
    assert "grid-cols-1" in browser
    stats = (ROOT / "frontend/components/studio/kb/KbStatsPanel.tsx").read_text(encoding="utf-8")
    assert "累计满 5 集后显示你的节奏统计" in stats
    picker = (ROOT / "frontend/components/studio/kb/ReviewProviderPicker.tsx").read_text(encoding="utf-8")
    for value in ["同一模型自审，效果有限", "审核会把原文发给所选厂商。", "kbReviewProviderOptions"]:
        assert value in picker, value
    lib = (ROOT / "frontend/lib/studio-kb.ts").read_text(encoding="utf-8")
    for value in ["Claude", "千问 3.8 Max", "DeepSeek", "关闭"]:
        assert value in lib, value
