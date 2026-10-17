"""Offline WO3d casting component, SSR, and request-contract probes."""
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
 if(name==='lucide-react')""").replace(
    "const data=url.endsWith('/clips/quote')?quote:{id:'frame-uploaded'};",
    "if(env.resolve)return env.resolve(url,init);const data=url.endsWith('/clips/quote')?quote:{id:'frame-uploaded'};",
).replace("{type:'image/png'}", "{type:env.blobType||'image/png'}")


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
const project={id:'p',title:'渡船',aspect:'16:9',brain_provider:'qwen'};
const catalog={voices:[
 {engine:'cosyvoice',voice:'longxiaocheng_v2',label:'龙小淳',lang:'zh',gender:'male',note:'待核实'},
 {engine:'cosyvoice',voice:'longjielidou_v2',label:'龙杰力豆',lang:'zh',gender:'female',note:'待核实'},
 {engine:'edge-tts',voice:'en-US-AndrewNeural',label:'Andrew',lang:'en',gender:'male',note:'英文'},
 {engine:'edge-tts',voice:'zh-CN-XiaoxiaoNeural',label:'晓晓',lang:'zh',gender:'female',note:'中文备选'}],
 fx:{robot:['A','B','E'],beast:['A','C'],inner:['A']}};
const proposal=name=>({name,visual_style:name+' 视效',palette:'青灰',camera:'固定长镜',lighting:'阴天散射光',rationale:name+' 的理由'});
const version=(asset_id,version_no,extra={})=>({asset_id,version_no,created_at:'2026-10-16T00:00:00Z',archived:false,prompt:'三视图 '+asset_id,...extra});
const castingItem=(id,kind,name,extra={})=>({id,bible_id:'b-'+id,kind,name,role:'main',appearance:kind==='character'?'灰布短衫。':'',description:'',needs_author:false,orphaned:false,status:'pending',locked_features:'',extra_prompt:'',reference_asset_ids:[],approved_asset_id:null,versions:[],voice:null,...extra});
const castingJob=(id,kind,item_id,status,extra={})=>({id,kind,item_id,status,error_code:null,error_message:null,reserved_amount:0.3,actual_amount:null,currency:'CNY',created_at:'2026-10-16T00:00:00Z',...extra});
const baseItems=[
 castingItem('i1','character','阿川',{appearance:'灰布短衫，右眉有疤。',locked_features:'右眉有疤',versions:[version('a1',1),version('a2',2)]}),
 castingItem('i2','character','阿莲',{appearance:'',needs_author:true}),
 castingItem('i3','location','渡口'),
 castingItem('i4','prop','旧船桨')];
const buildState=extra=>({g0_approved:false,setup:null,style:{chosen:null,proposals:[],proposal_job:null},items:baseItems,g1:{approved:false,total:4,done:0,skipped:0},jobs:[],prices:{seedream_cny:0.3,cosyvoice_cny_per_10k_chars:2.0},...extra});
const confirmedSetup={aspect:'16:9',resolution:'720P',video_model:'seedance',language:'en',sheet_size:'2560x1440',confirmed_at:'2026-10-16T10:00:00Z'};
const localStamp=value=>{const date=new Date(value);const pad=number=>String(number).padStart(2,'0');return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;};
const chosenStyle={...proposal('潮汐旧胶片'),realism:'photoreal',source:'proposal',proposal_index:0};
const styleQuote={id:'q-style',kind:'casting_style',items:[{item_id:null,name:'风格提案',versions:1,unit:0.04,est:0.04}],total:0.04,currency:'CNY',expires_at:'2099-01-01T00:00:00Z'};
const state=buildState();
const posts=[];let reads=0;
const ready=()=>{Object.assign(state,{g0_approved:true,setup:confirmedSetup,style:{chosen:chosenStyle,proposals:[proposal('潮汐旧胶片'),proposal('雾港插画')],proposal_job:null},g1:{approved:false,total:4,done:2,skipped:0}});};
const itemOf=id=>state.items.find(item=>item.id===id);
const clone=()=>JSON.parse(JSON.stringify(state));
const sheetQuote=body=>({id:'q-sheets',kind:'casting_sheets',items:body.items.map(line=>{const item=itemOf(line.item_id);return {item_id:line.item_id,name:item?item.name:line.item_id,versions:line.versions,unit:0.3,est:Number((line.versions*0.3).toFixed(4))};}),total:body.items.reduce((sum,line)=>sum+line.versions*0.3,0),currency:'CNY',expires_at:'2099-01-01T00:00:00Z'});
const itemIdOf=url=>url.split('/items/')[1].split('/')[0];
agents.apiJson=async(url,init={})=>{
 const method=init.method??'GET';
 const body=typeof init.body==='string'?JSON.parse(init.body):undefined;
 if(method!=='GET')posts.push({url,method,body});
 if(url.endsWith('/casting')&&method==='GET'){reads++;return clone();}
 if(url.endsWith('/casting/voice-catalog'))return JSON.parse(JSON.stringify(catalog));
 if(url.endsWith('/casting/setup')){state.setup={...confirmedSetup,...body};return clone();}
 if(url.endsWith('/casting/style/quote'))return JSON.parse(JSON.stringify(styleQuote));
 if(url.endsWith('/casting/style/start')){state.style.proposal_job=castingJob('jstyle','brain',null,'running');return clone();}
 if(url.endsWith('/casting/style')){state.style.chosen=body.custom?{...body.custom,realism:body.realism,source:'custom',proposal_index:null}:{...state.style.proposals[body.proposal_index],realism:body.realism,source:'proposal',proposal_index:body.proposal_index};return clone();}
 if(url.endsWith('/casting/sheets/quote'))return sheetQuote(body);
 if(url.endsWith('/casting/sheets/start')){state.jobs=[...state.jobs,castingJob('jimg','image','i1','running')];return clone();}
 if(url.endsWith('/casting/voices/audition')){const target=itemOf(body.item_id);target.voice={spec:null,approved_asset_id:null,auditions:body.variants.map((variant,index)=>({asset_id:'aud-'+index,spec:{...variant},text:body.text,duration_s:2.5,measured_lufs:-16.1,created_at:'2026-10-16T00:00:00Z',archived:false}))};return clone();}
 if(/\/casting\/items\/[^/]+\/voice\/approve$/.test(url)){const target=itemOf(itemIdOf(url));target.voice={...target.voice,approved_asset_id:body.asset_id,spec:target.voice.auditions.find(audio=>audio.asset_id===body.asset_id).spec};return JSON.parse(JSON.stringify(target));}
 if(/\/casting\/items\/[^/]+\/approve$/.test(url)){const target=itemOf(itemIdOf(url));target.approved_asset_id=body.asset_id;target.status='approved';return JSON.parse(JSON.stringify(target));}
 if(/\/casting\/items\/[^/]+\/skip$/.test(url)){const target=itemOf(itemIdOf(url));target.status='skipped';return JSON.parse(JSON.stringify(target));}
 if(/\/casting\/items\/[^/]+\/reopen$/.test(url)){const target=itemOf(itemIdOf(url));target.status='pending';return JSON.parse(JSON.stringify(target));}
 if(/\/casting\/items\/[^/]+$/.test(url)&&method==='PATCH'){const target=itemOf(url.split('/items/')[1]);Object.assign(target,body);return JSON.parse(JSON.stringify(target));}
 if(/\/casting\/assets\/[^/]+\/archive$/.test(url))return {ok:true};
 if(url.endsWith('/release'))return {id:'released'};
 if(/\/bible\/[^/]+$/.test(url)&&method==='PATCH')return {id:url.split('/bible/')[1],...body};
 if(url.endsWith('/assets')&&method==='POST')return {id:'3f9c1d2e-4b5a-4c6d-8e7f-0123456789ab',role:'reference'};
 throw new Error('unmapped request '+method+' '+url);
};
const props={project,owner:env.owner,busy:false,onBusyChange:()=>{},onChanged:async()=>{}};
const loadIn=(mode,relative)=>{env.mode=mode;cache.clear();return load(relative);};
const passthrough=async action=>{await action(new AbortController().signal);};
const calls=()=>posts;
const lastCall=()=>posts[posts.length-1];
const pulses=()=>[...env.timers.values()].filter(timer=>timer.delay===5000);
const fire=async delay=>{const pair=[...env.timers].find(([,timer])=>timer.delay===delay);assert(pair,'missing '+delay+'ms timer');env.timers.delete(pair[0]);await pair[1].fn();await flush();};
const cardsOf=page=>all(page.tree,node=>node.type?.name==='CastingItemCard');
"""


def test_casting_gate_hides_sections_and_shows_ssr_loading():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();const loading=renderToStaticMarkup(realReact.createElement(load('components/studio/CastingStage.tsx').default,props));assert(loading.includes('正在读取定妆设置'));
const page=mount(loadIn('hooks','components/studio/CastingStage.tsx').default,props);await flush();const body=text(page.tree);assert(body.includes('请先在①拆解批准分集方案。'));for(const value of ['开工确认','风格','定妆','声线'])assert(!body.includes(value),value);assert(!named(page,'SetupCard'));assert(!named(page,'StyleCard'));assert(!named(page,'CastingItems'));assert(!named(page,'VoicePanel'));page.close();process.stdout.write('true');
""") is True


def test_casting_read_error_then_retry():
    assert probe(SETUP + r"""
const original=agents.apiJson;let failing=true;agents.apiJson=async(url,init={})=>{if(failing&&url.endsWith('/projects/p/casting')&&(init.method??'GET')==='GET')throw new ApiError('定妆数据读取失败',500);return original(url,init);};
const page=mount(loadIn('hooks','components/studio/CastingStage.tsx').default,props);await flush();const notice=named(page,'ErrorNotice');assert(notice);assert(notice.props.message.includes('定妆数据读取失败'));failing=false;notice.props.retry();await flush();assert(!error(page).includes('定妆数据读取失败'));assert(text(page.tree).includes('请先在①拆解批准分集方案。'));page.close();process.stdout.write('true');
""") is True


def test_casting_stage_empty_then_unstyled_then_ready_wiring():
    assert probe(SETUP + r"""
ready();state.style.chosen=null;state.style.proposals=[];
const emptySetup=mount(loadIn('hooks','components/studio/CastingStage.tsx').default,{...props});await flush();assert(text(emptySetup.tree).includes('选定风格之后，才能报价出定妆图。'));assert(named(emptySetup,'SetupCard'));assert(named(emptySetup,'StyleCard'));assert(!named(emptySetup,'CastingItems'));assert.equal(named(emptySetup,'VoicePanel').props.catalog.voices.length,4);emptySetup.close();
Object.assign(state,{g0_approved:true,setup:null,style:{chosen:null,proposals:[],proposal_job:null}});
const blank=mount(loadIn('hooks','components/studio/CastingStage.tsx').default,{...props});await flush();assert(text(blank.tree).includes('开工确认之后，才能生成风格提案、出定妆图和试听声线。'));assert(named(blank,'SetupCard'));assert(!named(blank,'StyleCard'));assert(!named(blank,'CastingItems'));assert(!named(blank,'VoicePanel'));blank.close();
ready();const r0=reads;const page=mount(loadIn('hooks','components/studio/CastingStage.tsx').default,{...props});await flush();assert.equal(reads,r0+1);assert(named(page,'CastingItems'));assert(!text(page.tree).includes('选定风格之后'));assert.equal(named(page,'SetupCard').props.aspect,'16:9');assert.equal(named(page,'SetupCard').props.setup.video_model,'seedance');assert.equal(named(page,'CastingItems').props.g1.done,2);assert.equal(named(page,'CastingItems').props.items.length,4);assert.equal(named(page,'VoicePanel').props.items.length,2);assert.equal(named(page,'VoicePanel').props.language,'en');assert.equal(named(page,'VoicePanel').props.catalogError,'');assert(!named(page,'CastingQuoteDialog'));page.close();process.stdout.write('true');
""") is True


def test_setup_card_defaults_confirm_and_reedit():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();const ssr=renderToStaticMarkup(realReact.createElement(load('components/studio/SetupCard.tsx').default,{aspect:'16:9',setup:null,busy:false,onSave:async()=>{}}));for(const value of ['开工确认','画幅（沿用项目设置，只读）','万相 ¥0.3 / ¥0.6 / ¥1.2 每秒','（三视图横幅）','确认开工设置','中文声线用 CosyVoice（付费），英文声线用 edge-tts（免费）。'])assert(ssr.includes(value),value);assert(ssr.includes('aria-pressed="true"'));
let saved=null;const page=mount(loadIn('hooks','components/studio/SetupCard.tsx').default,{aspect:'16:9',setup:null,busy:false,onSave:async input=>{saved=input;}});assert(button(page,'480P').props['aria-pressed']);button(page,'720P').props.onClick();await flush();assert(!button(page,'480P').props['aria-pressed']);button(page,'Seedance').props.onClick();await flush();button(page,'英文').props.onClick();await flush();button(page,'确认开工设置').props.onClick();await flush();assert.deepEqual(saved,{resolution:'720P',video_model:'seedance',language:'en'});page.close();
const summary=mount(loadIn('hooks','components/studio/SetupCard.tsx').default,{aspect:'9:16',setup:confirmedSetup,busy:false,onSave:async()=>{}});const body=text(summary.tree);for(const value of ['画幅 9:16','分辨率 720P','默认模型 Seedance','语言 英文','定妆图 2560×1440'])assert(body.includes(value),value);
assert(body.includes(`开工已确认：${localStamp(confirmedSetup.confirmed_at)}`),body);assert(!body.includes(confirmedSetup.confirmed_at));assert(!body.includes('确认开工设置'));button(summary,'修改').props.onClick();await flush();assert(button(summary,'确认开工设置'));assert(button(summary,'取消'));button(summary,'取消').props.onClick();await flush();assert(text(summary.tree).includes('开工已确认'));summary.close();process.stdout.write('true');
""") is True


def test_casting_stage_style_quote_start_and_polling():
    assert probe(SETUP + r"""
ready();const page=mount(loadIn('hooks','components/studio/CastingStage.tsx').default,{...props});await flush();const r0=reads;assert.equal(r0,1);
await named(page,'StyleCard').props.onQuote();await flush();assert.equal(reads,r0+1);const quotedCalls=calls().filter(call=>call.url.endsWith('/casting/style/quote'));assert.equal(quotedCalls.length,1);assert.deepEqual(quotedCalls[0].body,{});
let modal=named(page,'CastingQuoteDialog');assert(modal);assert.equal(modal.props.quote.id,'q-style');assert.equal(modal.props.quote.kind,'casting_style');assert.equal(modal.props.model,'千问');
await modal.props.onConfirm();await flush();const started=calls().filter(call=>call.url.endsWith('/casting/style/start'));assert.equal(started.length,1);assert.deepEqual(started[0].body,{quote_id:'q-style'});assert(!named(page,'CastingQuoteDialog'));
assert.equal(named(page,'StyleCard').props.state.style.proposal_job.status,'running');assert.equal(pulses().length,1);assert.equal(reads,r0+2);
state.style.proposal_job=null;state.style.proposals=[proposal('潮汐旧胶片'),proposal('雾港插画'),proposal('渔村水彩')];const r1=reads;await fire(5000);assert.equal(reads,r1+1);assert.equal(pulses().length,0);assert(!named(page,'StyleCard').props.state.style.proposal_job);assert.equal(named(page,'StyleCard').props.state.style.proposals.length,3);page.close();process.stdout.write('true');
""") is True


def test_style_card_selection_realism_and_payloads():
    assert probe(SETUP + r"""
let quoted=0,released=[];const saved=[];
const block=state=>mount(loadIn('hooks','components/studio/StyleCard.tsx').default,{state:{...state,style:state.style},busy:false,onQuote:async()=>{quoted++;},onSave:async update=>{saved.push(update);},onRelease:async id=>{released.push(id);}});
const page=block({...state,style:{chosen:chosenStyle,proposals:[proposal('潮汐旧胶片'),proposal('雾港插画')],proposal_job:null}});await flush();const body=text(page.tree);for(const value of ['当前方案','潮汐旧胶片','雾港插画','写实','动漫','3D','保存风格','选这个'])assert(body.includes(value),value);
all(page.tree,node=>node.type==='button'&&text(node)==='选这个')[0].props.onClick();await flush();all(page.tree,node=>node.type==='input'&&node.props.type==='radio')[1].props.onChange();await flush();button(page,'保存风格').props.onClick();await flush();assert.deepEqual(saved[0],{proposal_index:0,realism:'anime'});
all(page.tree,node=>node.type==='button'&&text(node)==='选这个')[1].props.onClick();await flush();field(page,'style-lighting').props.onChange({target:{value:'阴天散射光'}});await flush();all(page.tree,node=>node.type==='input'&&node.props.type==='radio')[1].props.onChange();await flush();button(page,'保存风格').props.onClick();await flush();assert.equal(saved[1].realism,'anime');assert.deepEqual(saved[1].custom,{name:'雾港插画',visual_style:'雾港插画 视效',palette:'青灰',camera:'固定长镜',lighting:'阴天散射光',rationale:'雾港插画 的理由'});page.close();
const gated=block({...state,style:{chosen:chosenStyle,proposals:[],proposal_job:null}});await flush();assert.equal(field(gated,'style-name').props.value,'潮汐旧胶片');assert(!text(gated.tree).includes('名称与视觉风格不能为空'));assert.equal(button(gated,'保存风格').props.disabled,false);
field(gated,'style-name').props.onChange({target:{value:'   '}});await flush();assert.equal(button(gated,'保存风格').props.disabled,true);assert(text(gated.tree).includes('名称与视觉风格不能为空，填好之后才能保存风格。'));const beforeEmpty=saved.length;button(gated,'保存风格').props.onClick();await flush();assert.equal(saved.length,beforeEmpty);
field(gated,'style-name').props.onChange({target:{value:'潮汐旧胶片'}});await flush();assert.equal(button(gated,'保存风格').props.disabled,false);field(gated,'style-visual_style').props.onChange({target:{value:'  '}});await flush();assert.equal(button(gated,'保存风格').props.disabled,true);field(gated,'style-visual_style').props.onChange({target:{value:'潮汐旧胶片 视效'}});await flush();assert.equal(button(gated,'保存风格').props.disabled,false);gated.close();
const running=block({...state,style:{chosen:null,proposals:[],proposal_job:castingJob('jstyle','brain',null,'running')}});await flush();assert(text(running.tree).includes('正在生成风格提案'));assert(button(running,'生成风格提案').props.disabled);running.close();
const failed=block({...state,style:{chosen:null,proposals:[],proposal_job:castingJob('jstyle','brain',null,'uncertain',{error_message:'风格提案结果不确定'})}});await flush();assert(error(failed).includes('风格提案结果不确定'));assert(text(failed.tree).includes('可能已扣费，请先到供应商控制台核对再释放。'));button(failed,'释放预留').props.onClick();await flush();assert.deepEqual(released,['jstyle']);failed.close();
const blank=block({...state,style:{chosen:null,proposals:[],proposal_job:null}});await flush();assert(text(blank.tree).includes('还没有风格提案'));button(blank,'生成风格提案').props.onClick();await flush();assert.equal(quoted,1);blank.close();process.stdout.write('true');
""") is True


def test_casting_items_tabs_progress_batch_and_quote():
    assert probe(SETUP + r"""
ready();let quoted=null;const refId='3f9c1d2e-4b5a-4c6d-8e7f-0123456789ab';const batchItems=[{...baseItems[0],approved_asset_id:'a2',status:'approved'},baseItems[1],baseItems[2],baseItems[3]];
const page=mount(loadIn('hooks','components/studio/CastingItems.tsx').default,{projectId:'p',items:batchItems,jobs:[],g1:{approved:false,total:4,done:2,skipped:1},busy:false,mutate:passthrough,onQuoteSheets:async requests=>{quoted=requests;}});await flush();
const tabs=all(page.tree,node=>node.props?.role==='tab');assert.equal(tabs.length,3);assert.deepEqual(tabs.map(node=>text(node)),['人物 2','场景 1','道具 1']);
const bar=all(page.tree,node=>node.props?.role==='progressbar')[0];assert(bar);assert.equal(bar.props['aria-label'],'G1 定妆进度');assert.equal(bar.props['aria-valuenow'],2);assert.equal(bar.props['aria-valuemax'],4);assert(text(page.tree).includes('（跳过 1）'));assert(!text(page.tree).includes('G1 定妆通过'));
tabs[1].props.onClick();await flush();assert.deepEqual(cardsOf(page).map(card=>card.props.item.name),['渡口']);tabs[2].props.onClick();await flush();assert.deepEqual(cardsOf(page).map(card=>card.props.item.name),['旧船桨']);tabs[0].props.onClick();await flush();assert.deepEqual(cardsOf(page).map(card=>card.props.item.name),['阿川','阿莲']);
cardsOf(page)[0].props.onSelect(true);await flush();assert(text(page.tree).includes('已勾选 1 个条目（合计 1 张）'));
assert(!field(page,'casting-derive').props.disabled);assert(!text(page.tree).includes('还没有已选定版本'));assert(text(page.tree).includes('补充提示词（只对本批生效，追加在条目自己的补充提示词之后）'));
field(page,'casting-versions').props.onChange({target:{value:'2'}});await flush();assert(text(page.tree).includes('（合计 2 张）'));
field(page,'casting-derive').props.onChange({target:{checked:true}});await flush();field(page,'casting-extra').props.onChange({target:{value:'偏冷色调'}});await flush();
field(page,'casting-reference').props.onChange({target:{files:[new File(['x'],'ref.png',{type:'image/png'})]}});await flush();assert(text(page.tree).includes('参考图 1'));
const chips=all(page.tree,node=>typeof node.props?.title==='string'&&node.props.title.includes(refId));assert.equal(chips.length,1);assert.equal(chips[0].props.title,refId);assert(chips[0].props.className.includes('min-w-0')&&chips[0].props.className.includes('max-w-full'));
assert(!text(page.tree).includes(refId));assert(text(chips[0]).includes('参考图 1'));assert(text(chips[0]).includes(refId.slice(0,8)));assert.equal(button(page,'移除').props['aria-label'],'移除参考图 1');
button(page,'报价出图').props.onClick();await flush();assert.deepEqual(quoted,[{item_id:'i1',versions:2,extra_prompt:'偏冷色调',reference_asset_ids:[refId],derive_from_approved:true}]);
button(page,'取消选择').props.onClick();await flush();assert(!text(page.tree).includes('已勾选'));page.close();
const done=mount(loadIn('hooks','components/studio/CastingItems.tsx').default,{projectId:'p',items:baseItems,jobs:[],g1:{approved:true,total:4,done:4,skipped:0},busy:false,mutate:passthrough,onQuoteSheets:async()=>{}});await flush();assert(text(done.tree).includes('G1 定妆通过'));done.close();process.stdout.write('true');
""") is True


def test_casting_items_derive_gate_and_orphan_exclusion():
    assert probe(SETUP + r"""
ready();let quoted=null;
const approved={...baseItems[1],appearance:'黑布衣裙。',needs_author:false,approved_asset_id:'x1',versions:[version('x1',1)]};
const page=mount(loadIn('hooks','components/studio/CastingItems.tsx').default,{projectId:'p',items:[baseItems[0],approved,{...baseItems[2],kind:'character',name:'幽灵',orphaned:true}],jobs:[],g1:{approved:false,total:2,done:1,skipped:0},busy:false,mutate:passthrough,onQuoteSheets:async requests=>{quoted=requests;}});await flush();
const bar=all(page.tree,node=>node.props?.role==='progressbar')[0];assert.equal(bar.props['aria-valuemax'],2);assert.equal(bar.props['aria-valuenow'],1);assert(text(page.tree).includes('已确认 1 / 共 2（跳过 0）'));assert(!text(page.tree).includes('（跳过 1）'));
assert.deepEqual(cardsOf(page).map(card=>card.props.item.name),['阿川','阿莲','幽灵']);
cardsOf(page)[0].props.onSelect(true);await flush();assert.equal(field(page,'casting-derive').props.disabled,true);assert(text(page.tree).includes('要先给这些条目「选定」一个版本才能派生'));
button(page,'报价出图').props.onClick();await flush();assert.deepEqual(quoted,[{item_id:'i1',versions:1}]);
cardsOf(page)[1].props.onSelect(true);await flush();assert.equal(field(page,'casting-derive').props.disabled,true);
cardsOf(page)[0].props.onSelect(false);await flush();assert.equal(field(page,'casting-derive').props.disabled,false);assert(!text(page.tree).includes('要先给这些条目'));
field(page,'casting-derive').props.onChange({target:{checked:true}});await flush();
quoted=null;button(page,'报价出图').props.onClick();await flush();assert.deepEqual(quoted,[{item_id:'i2',versions:1,derive_from_approved:true}]);
cardsOf(page)[2].props.onSelect(true);await flush();assert(text(page.tree).includes('已勾选 1 个条目（合计 1 张）'));
quoted=null;button(page,'报价出图').props.onClick();await flush();assert.deepEqual(quoted,[{item_id:'i2',versions:1,derive_from_approved:true}]);
page.close();process.stdout.write('true');
""") is True


def test_casting_items_needs_author_gate_blocks_quote():
    assert probe(SETUP + r"""
ready();let quoted=null;
const page=mount(loadIn('hooks','components/studio/CastingItems.tsx').default,{projectId:'p',items:baseItems,jobs:[],g1:{approved:false,total:4,done:0,skipped:0},busy:false,mutate:passthrough,onQuoteSheets:async requests=>{quoted=requests;}});await flush();
assert.equal(all(page.tree,node=>node.type==='button'&&text(node)==='报价出图').length,0);
cardsOf(page)[1].props.onSelect(true);await flush();assert(text(page.tree).includes('以下人物需要先补写外形：阿莲。'));assert(button(page,'报价出图').props.disabled);assert.equal(quoted,null);
cardsOf(page)[0].props.onSelect(true);await flush();assert(text(page.tree).includes('以下人物需要先补写外形：阿莲。'));assert(button(page,'报价出图').props.disabled);
cardsOf(page)[1].props.onSelect(false);await flush();assert(!text(page.tree).includes('以下人物需要先补写外形'));assert(!button(page,'报价出图').props.disabled);button(page,'报价出图').props.onClick();await flush();assert.deepEqual(quoted,[{item_id:'i1',versions:1}]);page.close();process.stdout.write('true');
""") is True


def test_item_card_appearance_locked_actions_and_preview():
    assert probe(SETUP + r"""
const item=castingItem('i1','character','阿川',{appearance:'灰布短衫，右眉有疤。',locked_features:'右眉有疤',versions:[version('a1',1),version('a2',2)]});
const patches=[],approved=[],archived=[],appearances=[];let skips=0,reopens=0;
const card=(extra={})=>mount(loadIn('hooks','components/studio/CastingItemCard.tsx').default,{item,jobs:[],selected:false,busy:false,onSelect:()=>{},onPatch:async patch=>{patches.push(patch);},onApprove:async id=>{approved.push(id);},onSkip:async()=>{skips++;},onReopen:async()=>{reopens++;},onArchive:async id=>{archived.push(id);},onRelease:async()=>{},onSaveAppearance:async value=>{appearances.push(value);},...extra});
const page=card();await flush();const body=text(page.tree);for(const value of ['阿川','待定妆','灰布短衫，右眉有疤。','第 1 版','第 2 版','锁定特征（出图提示词会带上，之后不得改动）','补充提示词（之后每次出图都会带上）','标为不需要'])assert(body.includes(value),value);assert(!body.includes('只对下一次出图生效'));assert(!body.includes('重新打开'));assert(!body.includes('确认此条'));
const scaleImages=all(page.tree,node=>node.type?.name==='StudioAssetImage');assert.equal(scaleImages.length,2);for(const scale of scaleImages){const outer=mount(scale.type,scale.props);const frame=mount(outer.tree.type,outer.tree.props);await flush();const img=all(frame.tree,node=>node.type==='img')[0];assert(img,'missing version image');assert.equal(img.props.loading,'lazy');assert.equal(img.props.decoding,'async');frame.close();outer.close();}
const archives=all(page.tree,node=>node.type==='button'&&text(node)==='归档');assert.equal(archives.length,2);assert.equal(archives[0].props.disabled,false);assert.equal(archives[0].props.title,undefined);
all(page.tree,node=>node.type==='button'&&text(node)==='选定')[0].props.onClick();await flush();all(page.tree,node=>node.type==='button'&&text(node)==='归档')[1].props.onClick();await flush();assert.deepEqual(approved,['a1']);assert.deepEqual(archived,['a2']);
button(page,'标为不需要').props.onClick();await flush();assert.equal(skips,1);
field(page,'locked-i1').props.onChange({target:{value:'右眉有疤、左手缺指'}});await flush();button(page,'保存锁定特征').props.onClick();await flush();assert.deepEqual(patches[0],{locked_features:'右眉有疤、左手缺指'});
field(page,'extra-i1').props.onChange({target:{value:'补一条旧围巾'}});await flush();button(page,'保存补充提示词').props.onClick();await flush();assert.deepEqual(patches[1],{extra_prompt:'补一条旧围巾'});
all(page.tree,node=>node.type==='button'&&node.props['aria-label']==='查看阿川第 1 版大图')[0].props.onClick();await flush();const dialog=named(page,'BreakdownDialog');assert(dialog);assert.equal(dialog.props.title,'阿川 · 第 1 版');dialog.props.onClose();await flush();assert(!named(page,'BreakdownDialog'));page.close();
const orphan=card({item:{...item,orphaned:true}});await flush();assert(text(orphan.tree).includes('已不在当前总表'));assert(!text(orphan.tree).includes('总表已移除'));assert.equal(all(orphan.tree,node=>node.type==='input'&&node.props.type==='checkbox')[0].props.disabled,true);assert(button(orphan,'选定').props.disabled);assert(button(orphan,'标为不需要').props.disabled);assert(button(orphan,'归档').props.disabled);orphan.close();
const chosen=card({item:{...item,status:'approved',approved_asset_id:'a1'}});await flush();const picked=all(chosen.tree,node=>node.type==='button'&&text(node)==='归档');assert.equal(picked[0].props.disabled,true);assert.equal(picked[0].props.title,'先换选定');assert.equal(picked[1].props.disabled,false);assert.equal(picked[1].props.title,undefined);assert.equal(button(chosen,'选定').props.disabled,true);chosen.close();
const skipped=card({item:{...item,status:'skipped'}});await flush();assert(!all(skipped.tree,node=>node.type==='button'&&text(node)==='标为不需要').length);button(skipped,'重新打开').props.onClick();await flush();assert.equal(reopens,1);skipped.close();
const need=card({item:castingItem('i2','character','阿莲',{appearance:'',needs_author:true})});await flush();assert(text(need.tree).includes('原文没有外形描述，先补外形才能出图。'));assert(text(need.tree).includes('待作者补充'));button(need,'先补外形').props.onClick();await flush();field(need,'appearance-i2').props.onChange({target:{value:'黑布衣裙，长发。'}});await flush();all(need.tree,node=>node.type==='form')[0].props.onSubmit({preventDefault(){}});await flush();assert.deepEqual(appearances,['黑布衣裙，长发。']);need.close();process.stdout.write('true');
""") is True


def test_item_card_inflight_placeholder_and_uncertain_release():
    assert probe(SETUP + r"""
const item=castingItem('i1','character','阿川',{appearance:'灰布短衫。',versions:[version('a1',1)]});const released=[];
const card=jobs=>mount(loadIn('hooks','components/studio/CastingItemCard.tsx').default,{item,jobs,selected:false,busy:false,onSelect:()=>{},onPatch:async()=>{},onApprove:async()=>{},onSkip:async()=>{},onReopen:async()=>{},onArchive:async()=>{},onRelease:async id=>{released.push(id);},onSaveAppearance:async()=>{}});
const running=card([castingJob('jimg','image','i1','running')]);await flush();assert(text(running.tree).includes('正在出图…'));assert(text(running.tree).includes('进行中'));assert(!text(running.tree).includes('可能已扣费'));running.close();
const rejected=card([castingJob('jimg','image','i1','rejected',{error_message:'参考图尺寸不符'})]);await flush();assert(text(rejected.tree).includes('被拒绝（未扣费）'));assert(text(rejected.tree).includes('参考图尺寸不符'));assert(!text(rejected.tree).includes('可能已扣费'));rejected.close();
const uncertain=card([castingJob('jimg','image','i1','uncertain',{error_message:'可能已扣费，请勿直接重试，去控制台核对'})]);await flush();const body=text(uncertain.tree);assert(body.includes('结果不确定'));assert.equal(body.split('可能已扣费').length-1,1);assert(body.includes('可能已扣费，请勿直接重试，去控制台核对'));assert(!body.includes('可能已扣费，请勿直接重试。'));button(uncertain,'释放').props.onClick();await flush();assert.deepEqual(released,['jimg']);uncertain.close();
const detail=card([castingJob('jimg','image','i1','uncertain',{error_message:'上游超时'})]);await flush();assert.equal(text(detail.tree).split('可能已扣费').length-1,1);assert(text(detail.tree).includes('可能已扣费，请勿直接重试，去控制台核对'));assert(text(detail.tree).includes('上游超时'));detail.close();process.stdout.write('true');
""") is True


def test_casting_stage_polling_ticks_pauses_and_stops():
    assert probe(SETUP + r"""
ready();state.jobs=[castingJob('jimg','image','i1','running')];
const page=mount(loadIn('hooks','components/studio/CastingStage.tsx').default,{...props});await flush();const r0=reads;assert.equal(pulses().length,1);assert.equal(named(page,'CastingItems').props.jobs[0].status,'running');
document.hidden=true;for(const fn of env.listeners.get('visibilitychange'))fn();assert.equal(pulses().length,0);
document.hidden=false;for(const fn of env.listeners.get('visibilitychange'))fn();await flush();assert.equal(pulses().length,1);assert(reads>=r0);
state.jobs=[castingJob('jimg','image','i1','uncertain',{error_message:'上游超时'})];const r1=reads;await fire(5000);assert.equal(reads,r1+1);assert.equal(pulses().length,0);assert.equal(named(page,'CastingItems').props.jobs[0].status,'uncertain');
await fire(5000).catch(error=>{});assert.equal(pulses().length,0);page.close();process.stdout.write('true');
""") is True


def test_casting_quote_dialog_ssr_lines_total_and_expiry():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();const sheetsQuote={id:'q-sheets',kind:'casting_sheets',items:[{item_id:'i1',name:'阿川',versions:2,unit:0.3,est:0.6},{item_id:'i3',name:'渡口',versions:1,unit:0.3,est:0.3}],total:0.9,currency:'CNY',expires_at:'2099-01-01T00:00:00Z'};
const render=quote=>renderToStaticMarkup(realReact.createElement(load('components/studio/CastingQuoteDialog.tsx').default,{quote,model:'Seedream 5.0 · 2560×1440',busy:false,onConfirm:async()=>{},onClose:()=>{}}));
const html=render(sheetsQuote);for(const value of ['定妆出图','阿川','渡口','2 版','1 版','¥0.3000','¥0.6000','¥0.9000','报价剩余有效时间','确认出图','一律 2560×1440 三视图横幅、纯白背景。'])assert(html.includes(value),value);assert(!html.includes('报价已过期'));assert(!/<button type="submit"[^>]*disabled/.test(html));
const expired=render({...sheetsQuote,expires_at:'2000-01-01T00:00:00Z'});assert(expired.includes('报价已过期，请取消后重新报价'));assert(/<button type="submit"[^>]*disabled/.test(expired));
const styleHtml=render(styleQuote);assert(styleHtml.includes('风格提案'));assert(styleHtml.includes('确认生成'));assert(styleHtml.includes('¥0.0400'));assert(!styleHtml.includes('三视图横幅'));process.stdout.write('true');
""") is True


def test_studio_asset_audio_renders_controls_and_rejects_non_audio():
    assert probe(SETUP + r"""
env.blobType='audio/wav';const outer=mount(loadIn('hooks','components/studio/StudioAssetAudio.tsx').default,{assetId:'aud-1',label:'第 1 条试听'});const page=mount(outer.tree.type,outer.tree.props);await flush();const audio=all(page.tree,node=>node.type==='audio')[0];assert(audio);assert.equal(audio.props.controls,true);assert.equal(audio.props.preload,'metadata');assert(audio.props.src.startsWith('blob:'));assert.equal(audio.props['aria-label'],'第 1 条试听');assert(text(page.tree).includes('第 1 条试听'));const url=audio.props.src;page.close();assert(env.revoked.includes(url));process.stdout.write('true');
""") is True


def test_studio_asset_audio_error_state_and_missing_object_url():
    assert probe(SETUP + r"""
env.blobType='text/plain';const outer=mount(loadIn('hooks','components/studio/StudioAssetAudio.tsx').default,{assetId:'aud-2'});const page=mount(outer.tree.type,outer.tree.props);await flush();assert(error(page).includes('试听音频格式无法播放，请重试。'));assert.equal(all(page.tree,node=>node.type==='audio').length,0);assert.equal(env.created.length,0);page.close();assert.deepEqual(env.revoked,[]);process.stdout.write('true');
""") is True


def test_voice_panel_card_defaults_validation_generate_and_approve():
    assert probe(SETUP + r"""
const prices={seedream_cny:0.3,cosyvoice_cny_per_10k_chars:2.0};const castItem=castingItem('i1','character','阿川',{appearance:'灰布短衫。'});
const mutate=async action=>{await action(new AbortController().signal);};
const show=(items,language='zh')=>{const panel=mount(loadIn('hooks','components/studio/VoicePanel.tsx').default,{projectId:'p',items,language,prices,catalog,busy:false,mutate,onChanged:async()=>{}});const card=named(panel,'VoiceCard');return {panel,card:card?mount(card.type,card.props):null};};
const first=show([castItem]);await flush();assert(first.card);assert.equal(field(first.card,'voice-text-i1').props.value,'灰布短衫。');assert.equal(field(first.card,'voice-engine-i1-0').props.value,'cosyvoice');assert.equal(field(first.card,'voice-name-i1-0').props.value,'longxiaocheng_v2');assert.equal(field(first.card,'voice-rate-i1-0').props.value,'1');assert.equal(field(first.card,'voice-pitch-i1-0').props.value,'1');assert.equal(field(first.card,'voice-fx-i1-0').props.value,'');assert.equal(field(first.card,'voice-role-i1-0').props.value,'dialogue');assert(text(first.card.tree).includes('约 ¥0.01'));
button(first.card,'再加一个方案').props.onClick();await flush();assert(field(first.card,'voice-engine-i1-1'));assert.equal(all(first.card.tree,node=>node.type==='button'&&text(node)==='移除').length,2);
field(first.card,'voice-text-i1').props.onChange({target:{value:''}});await flush();button(first.card,'生成试听').props.onClick();await flush();assert(text(first.card.tree).includes('试听台词需要 1–120 字。'));assert(!calls().length);
field(first.card,'voice-text-i1').props.onChange({target:{value:'灰布短衫。'}});await flush();all(first.card.tree,node=>node.type==='button'&&text(node)==='移除')[0].props.onClick();await flush();button(first.card,'生成试听').props.onClick();await flush();const call=lastCall();assert(call.url.endsWith('/casting/voices/audition'));assert.equal(call.body.item_id,'i1');assert.equal(call.body.text,'灰布短衫。');assert.deepEqual(call.body.variants,[{engine:'cosyvoice',voice:'longxiaocheng_v2',rate:1,pitch:1,fx:null,role:'dialogue'}]);first.panel.close();first.card.close();
assert.equal(itemOf('i1').voice.auditions.length,1);const listing=show([itemOf('i1')]);await flush();const audio=named(listing.card,'StudioAssetAudio');assert(audio);assert.equal(audio.props.assetId,'aud-0');assert.equal(audio.props.label,'第 1 条试听');assert(text(listing.card.tree).includes('实测响度'));assert(text(listing.card.tree).includes('CosyVoice'));const audTime=all(listing.card.tree,node=>node.type==='time')[0];assert(audTime);assert.equal(audTime.props.dateTime,'2026-10-16T00:00:00Z');assert.equal(text(audTime),'创建于 '+localStamp('2026-10-16T00:00:00Z'));assert(!text(listing.card.tree).includes('2026-10-16T00:00:00Z'));const auditionArchive=all(listing.card.tree,node=>node.type==='button'&&text(node)==='归档');assert.equal(auditionArchive.length,1);assert.equal(auditionArchive[0].props.disabled,false);assert.equal(auditionArchive[0].props.title,undefined);auditionArchive[0].props.onClick();await flush();assert(lastCall().url.endsWith('/casting/assets/aud-0/archive'));assert.deepEqual(lastCall().body,{});button(listing.card,'选定这条').props.onClick();await flush();assert(lastCall().url.endsWith('/casting/items/i1/voice/approve'));assert.deepEqual(lastCall().body,{asset_id:'aud-0'});listing.panel.close();listing.card.close();
assert.equal(itemOf('i1').voice.approved_asset_id,'aud-0');const approved=show([itemOf('i1')]);await flush();assert(text(approved.card.tree).includes('已定档'));assert(text(approved.card.tree).includes('无特效'));const approvedArchive=all(approved.card.tree,node=>node.type==='button'&&text(node)==='归档');assert.equal(approvedArchive.length,1);assert.equal(approvedArchive[0].props.disabled,true);assert.equal(approvedArchive[0].props.title,'先换选定');assert.equal(button(approved.card,'选定这条').props.disabled,true);approved.panel.close();approved.card.close();
const orphanVoice=show([{...castItem,orphaned:true}]);await flush();assert(text(orphanVoice.card.tree).includes('已不在当前总表'));assert.equal(button(orphanVoice.card,'生成试听').props.disabled,true);assert.equal(field(orphanVoice.card,'voice-text-i1').props.disabled,true);assert.equal(field(orphanVoice.card,'voice-engine-i1-0').props.disabled,true);orphanVoice.panel.close();orphanVoice.card.close();
const english=show([castItem],'en');await flush();assert(text(english.card.tree).includes('免费'));assert.equal(field(english.card,'voice-engine-i1-0').props.value,'edge-tts');assert.equal(field(english.card,'voice-rate-i1-0').props.value,'+0%');assert.equal(field(english.card,'voice-name-i1-0').props.value,'en-US-AndrewNeural');english.panel.close();english.card.close();
const broken=mount(loadIn('hooks','components/studio/VoicePanel.tsx').default,{projectId:'p',items:[castItem],language:'zh',prices,catalog,catalogError:'音色目录加载失败',busy:false,mutate,onChanged:async()=>{}});await flush();assert(error(broken).includes('音色目录加载失败'));assert(!named(broken,'VoiceCard'));broken.close();
const loading=mount(loadIn('hooks','components/studio/VoicePanel.tsx').default,{projectId:'p',items:[castItem],language:'zh',prices,catalog:null,busy:false,mutate,onChanged:async()=>{}});await flush();assert(text(loading.tree).includes('正在读取音色…'));loading.close();
const none=mount(loadIn('hooks','components/studio/VoicePanel.tsx').default,{projectId:'p',items:[castingItem('i3','location','渡口')],language:'zh',prices,catalog,busy:false,mutate,onChanged:async()=>{}});await flush();assert(text(none.tree).includes('暂无可配置声线的人物。'));none.close();process.stdout.write('true');
""") is True


def test_voice_panel_ssr_defaults_cost_and_approved_summary():
    assert probe(SETUP + r"""
env.mode='ssr';cache.clear();const prices={seedream_cny:0.3,cosyvoice_cny_per_10k_chars:2.0};const castItem=castingItem('i1','character','阿川',{appearance:'灰布短衫。'});
const renderPanel=(extra={})=>renderToStaticMarkup(realReact.createElement(load('components/studio/VoicePanel.tsx').default,{projectId:'p',items:[castItem,castingItem('i2','character','阿莲',{appearance:'',needs_author:true})],language:'zh',prices,catalog,busy:false,mutate:async()=>{},onChanged:async()=>{},...extra}));
const html=renderPanel();for(const value of ['声线','中文用 CosyVoice（付费），英文用 edge-tts（免费）。','试听台词','voice-text-i1','voice-engine-i1-0','voice-name-i1-0','voice-fx-i1-0','voice-role-i1-0','音色','声线特效','角色类型','无特效','机器人 A','生成试听','约 ¥0.01','我是阿莲。'])assert(html.includes(value),value);
assert(!html.includes('已定档'));assert(!html.includes('还没有试听'));
assert(renderPanel({language:'en'}).includes('免费'));assert(renderPanel({language:'en'}).includes('edge-tts'));
assert(renderPanel({catalogError:'音色目录加载失败'}).includes('音色目录加载失败'));
assert(renderPanel({catalog:null}).includes('正在读取音色…'));
const withVoice={...castItem,voice:{spec:{engine:'cosyvoice',voice:'longxiaocheng_v2',rate:1,pitch:1,fx:'robot:B',role:'dialogue'},approved_asset_id:'aud-9',auditions:[{asset_id:'aud-9',spec:{engine:'cosyvoice',voice:'longxiaocheng_v2',rate:1,pitch:1,fx:'robot:B',role:'dialogue'},text:'我是阿川。',duration_s:2.4,measured_lufs:-16.2,created_at:'2026-10-16T00:00:00Z',archived:false}]}};
const approved=renderPanel({items:[withVoice]});for(const value of ['已定档','机器人 B','实测响度','LUFS','选定这条'])assert(approved.includes(value),value);
assert(approved.includes('dateTime="2026-10-16T00:00:00Z"'));assert(approved.includes('创建于 '+localStamp('2026-10-16T00:00:00Z')));assert.equal(approved.split('2026-10-16T00:00:00Z').length-1,1);assert(approved.includes('>归档</button>'));
const unsafe=renderPanel({items:[{...castItem,voice:{spec:null,approved_asset_id:null,auditions:[]}}]});assert(unsafe.includes('还没有试听，先生成一条方案。'));assert(!unsafe.includes('已定档'));assert(!unsafe.includes('实测响度'));process.stdout.write('true');
""") is True


def test_casting_request_wrappers_use_contract_paths():
    assert probe(SETUP + r"""
const lib=load('lib/studio-casting.ts');const seen=[];agents.apiJson=async(url,init={})=>{seen.push({url,method:init.method??'GET',body:init.body?JSON.parse(init.body):undefined});return {};};
await lib.getStudioCasting('p');await lib.putStudioCastingSetup('p',{resolution:'480P',video_model:'wan',language:'zh'});await lib.quoteStudioCastingStyle('p');await lib.startStudioCastingStyle('p','q');await lib.putStudioCastingStyle('p',{proposal_index:1,realism:'anime'});await lib.patchCastingItem('i1',{locked_features:'疤'});await lib.approveCastingItem('i1','a1');await lib.skipCastingItem('i1');await lib.reopenCastingItem('i1');await lib.archiveCastingAsset('a1');await lib.quoteCastingSheets('p',[{item_id:'i1',versions:2}]);await lib.startCastingSheets('p','q2');await lib.auditionCastingVoices('p',{item_id:'i1',text:'我是阿川。',variants:[]});await lib.approveCastingVoice('i1','aud-1');await lib.getCastingVoiceCatalog();
assert.deepEqual(seen.map(call=>call.method+':'+call.url.replace('/api/studio','')),['GET:/projects/p/casting','PUT:/projects/p/casting/setup','POST:/projects/p/casting/style/quote','POST:/projects/p/casting/style/start','PUT:/projects/p/casting/style','PATCH:/casting/items/i1','POST:/casting/items/i1/approve','POST:/casting/items/i1/skip','POST:/casting/items/i1/reopen','POST:/casting/assets/a1/archive','POST:/projects/p/casting/sheets/quote','POST:/projects/p/casting/sheets/start','POST:/projects/p/casting/voices/audition','POST:/casting/items/i1/voice/approve','GET:/casting/voice-catalog']);
assert.deepEqual(seen[1].body,{resolution:'480P',video_model:'wan',language:'zh'});assert.deepEqual(seen[2].body,{});assert.deepEqual(seen[3].body,{quote_id:'q'});assert.deepEqual(seen[4].body,{proposal_index:1,realism:'anime'});assert.deepEqual(seen[5].body,{locked_features:'疤'});assert.deepEqual(seen[6].body,{asset_id:'a1'});assert.deepEqual(seen[7].body,{});assert.deepEqual(seen[8].body,{});assert.deepEqual(seen[9].body,{});assert.deepEqual(seen[10].body,{items:[{item_id:'i1',versions:2}]});assert.deepEqual(seen[11].body,{quote_id:'q2'});assert.deepEqual(seen[12].body,{item_id:'i1',text:'我是阿川。',variants:[]});assert.deepEqual(seen[13].body,{asset_id:'aud-1'});process.stdout.write('true');
""") is True


def test_casting_lib_labels_costs_and_guards():
    assert probe(SETUP + r"""
const lib=load('lib/studio-casting.ts');
assert.equal(lib.castingSheetSize,'2560x1440');assert.equal(lib.castingResolutionPriceNote,'万相 ¥0.3 / ¥0.6 / ¥1.2 每秒');assert.deepEqual(lib.castingResolutionOptions,['480P','720P','1080P']);
assert.equal(lib.castingVideoModelLabel('wan'),'万相');assert.equal(lib.castingLanguageLabel('en'),'英文');assert.equal(lib.castingItemKindLabel('location'),'场景');assert.equal(lib.castingItemStatusLabel('skipped'),'不需要定妆');assert.equal(lib.castingRealismLabel('anime'),'动漫');assert.equal(lib.castingQuoteKindLabel('casting_sheets'),'定妆出图');assert.equal(lib.castingJobStatusLabel('uncertain'),'结果不确定');assert.equal(lib.castingVoiceRoleLabel('narration'),'旁白');assert.equal(lib.castingFxLabel('robot:B'),'机器人 B');assert.equal(lib.castingFxLabel(null),'无特效');
assert.equal(lib.formatCastingMoney(0.6,'CNY'),'¥0.6000');assert.equal(lib.formatCastingMoney(0.6,'USD'),'$0.6000');
assert.match(lib.formatCastingTime('2026-10-16T10:00:00Z'),/^\d{4}-\d\d-\d\d \d\d:\d\d$/);
assert.equal(lib.formatCastingTime('2026-10-16T10:00:00Z'),localStamp('2026-10-16T10:00:00Z'));
assert.equal(lib.formatCastingTime('2026-10-16T10:00:00.032045+00:00'),localStamp('2026-10-16T10:00:00Z'));
assert.equal(lib.formatCastingTime('2026-10-16 10:00:00'),localStamp('2026-10-16T10:00:00Z'));
assert.equal(lib.formatCastingTime('不是时间'),'不是时间');
assert(!lib.formatCastingTime('2026-10-16T10:00:00Z').includes('T'));
assert.equal(lib.castingAuditionCostLabel('中文四字','zh',{cosyvoice_cny_per_10k_chars:2}),'约 ¥0.01');assert.equal(lib.castingAuditionCostLabel('text','en',{cosyvoice_cny_per_10k_chars:2}),'免费');
assert.equal(lib.castingDefaultAuditionText(castingItem('x','character','阿川',{appearance:''})),'我是阿川。');assert.equal(lib.castingDefaultAuditionText(castingItem('y','character','阿川',{appearance:'灰布短衫，右眉有疤。长发。'})),'灰布短衫，右眉有疤。');
assert.equal(lib.castingItemVersions(castingItem('z','character','阿川',{versions:[version('a',1),version('b',2,{archived:true})]})).length,1);
assert.equal(lib.castingJobInflight(castingJob('j','image','i1','running')),true);assert.equal(lib.castingJobInflight(castingJob('j','image','i1','uncertain')),false);assert.equal(lib.castingJobInflight(null),false);
assert.equal(lib.castingItemInflight([castingJob('j','image','i1','running')],'i1').length,1);assert.equal(lib.castingItemInflight([castingJob('j','image','i2','running')],'i1').length,0);assert.equal(lib.castingItemFinished([castingJob('j','image','i1','rejected')],'i1').length,1);
assert.equal(lib.castingInflight(buildState()),false);assert.equal(lib.castingInflight(buildState({jobs:[castingJob('j','image','i1','running')]})),true);assert.equal(lib.castingInflight(buildState({style:{chosen:null,proposals:[],proposal_job:castingJob('j','brain',null,'queued')}})),true);
assert.equal(lib.castingNeedsAppearance(baseItems,['i2']),true);assert.equal(lib.castingNeedsAppearance(baseItems,['i1']),false);assert.equal(lib.castingNeedsAppearance(baseItems,['i3']),false);process.stdout.write('true');
""") is True
