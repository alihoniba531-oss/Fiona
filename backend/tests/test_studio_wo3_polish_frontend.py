"""Regression probes for WO2 review items 2–7; all run without a browser or network."""
from pathlib import Path

from test_studio_frontend_components import probe
from test_studio_frontend_navigation import probe as navigation_probe
from test_studio_frontend_shell import probe as shell_probe, SETUP


ROOT = Path(__file__).resolve().parents[2]


def test_quote_live_region_announces_expiry_without_per_second_countdown():
    assert probe(r"""
const page=mount(load('components/studio/QuoteDialog.tsx').default,{quote,onConfirm:async()=>{},onClose:()=>{}});
const live=all(page.tree,node=>node.props?.['aria-live']==='polite');assert.equal(live.length,1);assert.equal(text(live[0]),'');assert(!all(live[0],node=>node.props?.className==='readout').length);
assert(text(page.tree).includes('报价剩余有效时间'));page.close();
const expired=mount(load('components/studio/QuoteDialog.tsx').default,{quote:{...quote,expires_at:'2000-01-01T00:00:00Z'},onConfirm:async()=>{},onClose:()=>{}});
assert.equal(text(all(expired.tree,node=>node.props?.['aria-live']==='polite')[0]),'报价已过期，请重新报价');expired.close();process.stdout.write('true');
""") is True


def test_stage_roving_tabindex_and_arrow_home_end_focus():
    assert shell_probe(SETUP + r"""
const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:true});await flush();
let focused=-1,prevented=0;const elements=Array.from({length:5},(_,index)=>({focus:()=>focused=index}));
const tabs=()=>all(page.tree,node=>node.props?.role==='tab');const key=async(index,value)=>{tabs()[index].props.onKeyDown({key:value,preventDefault:()=>prevented++,currentTarget:{parentElement:{querySelectorAll:()=>elements}}});await flush();};
assert.deepEqual(tabs().map(tab=>tab.props.tabIndex),[-1,-1,-1,0,-1]);await key(3,'ArrowRight');assert.equal(focused,4);assert.equal(tabs()[4].props['aria-selected'],true);
await key(4,'ArrowRight');assert.equal(focused,0);await key(0,'ArrowLeft');assert.equal(focused,4);await key(4,'Home');assert.equal(focused,0);await key(0,'End');assert.equal(focused,4);
assert.equal(tabs().filter(tab=>tab.props.tabIndex===0).length,1);assert.equal(prevented,5);page.close();process.stdout.write('true');
""") is True
    assert "useRovingTabs" not in (ROOT / "frontend/components/novel/NovelWorkbench.tsx").read_text()


def test_release_failure_has_only_one_error_notice_in_modal():
    assert probe(r"""
const card=mount(load('components/studio/ShotCard.tsx').default,{job:job('uncertain'),...callbacks(),onRelease:async()=>{throw Error('额度释放失败');}});
button(card,'确认未扣费，释放额度').props.onClick();await flush();await named(card,'ReleaseDialog').props.onConfirm();await flush();
assert.equal(all(card.tree,node=>node.type?.name==='ErrorNotice').length,0);
const element=named(card,'ReleaseDialog'),dialog=mount(element.type,element.props);assert.equal(all(dialog.tree,node=>node.type?.name==='ErrorNotice').length,1);assert.equal(error(dialog),'额度释放失败');
button(dialog,'取消').props.onClick();await flush();assert.equal(all(card.tree,node=>node.type?.name==='ErrorNotice').length,1);card.close();dialog.close();process.stdout.write('true');
""") is True


def test_studio_tags_wrap_and_can_grow_without_global_token_changes():
    assert probe(r"""
const html=render('components/studio/ShotCard.tsx',{job:job('uncertain'),...callbacks()});
for(const rule of ['[&amp;_.tag]:h-auto','[&amp;_.tag]:min-h-[22px]','[&amp;_.tag]:whitespace-normal','[&amp;_.tag]:leading-relaxed'])assert(html.includes(rule),rule);
assert(html.includes('可能已扣费，请勿直接重试，去控制台核对'));process.stdout.write('true');
""") is True
    shell = (ROOT / "frontend/components/studio/StudioShell.tsx").read_text()
    assert "[&_.tag]:h-auto" in shell and "[&_.tag]:whitespace-normal" in shell


def test_video_polling_refreshes_budget_jobs_but_not_project_detail():
    assert shell_probe(SETUP + r"""
const page=mount(load('components/studio/StudioWorkbench.tsx').AccountStudioWorkbench,{id:'project',owner:env.owner,embedded:true});await flush();
const count=path=>env.calls.filter(call=>call==='GET /api/studio/'+path).length;
assert.equal(count('projects/project'),1);assert.equal(count('projects/project/jobs'),1);assert.equal(count('access'),1);
await timer(5000);await timer(5000);assert.equal(count('projects/project'),1);assert.equal(count('projects/project/jobs'),3);assert.equal(count('access'),3);
await named(page,'ClipComposer').props.onChanged();await flush();assert.equal(count('projects/project'),2);page.close();process.stdout.write('true');
""") is True


def test_sidebar_uses_shared_access_outcome_without_requesting_again():
    assert navigation_probe(r"""
const Sidebar=load('components/Sidebar.tsx').default;
const forbidden=mount(Sidebar,{onChatClick:()=>{},studioAccessAllowed:false});await flush();assert.equal(links(forbidden).length,0);assert.equal(env.calls.filter(call=>call.url==='/api/studio/access').length,0);forbidden.close();
const allowed=mount(Sidebar,{onChatClick:()=>{},studioAccessAllowed:true});await flush();assert.equal(links(allowed).length,1);assert.equal(env.calls.filter(call=>call.url==='/api/studio/access').length,0);allowed.close();process.stdout.write('true');
""") is True


def test_home_notices_effect_waits_for_successful_access():
    assert shell_probe(r"""
const source=fs.readFileSync(path.join(frontend,'app/page.tsx'),'utf8');
const at=source.indexOf('const poller = createStudioNoticePoller({');const start=source.lastIndexOf('useEffect(() => {',at);const end=source.indexOf('}, [hydrated, username, refreshList, studioAllowed]);',at)+'}, [hydrated, username, refreshList, studioAllowed]);'.length;
assert(start>=0&&end>start);const effect=source.slice(start,end);
let starts=0,requests=0;
const compiled=ts.transpileModule(`function HomeNoticeProbe({hydrated,username,studioAllowed,refreshList}){${effect}}`,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
const factory=new Function('useEffect','createStudioNoticePoller','readStoredUsername','apiFetch','API','setStudioInbox','localWatchNotificationsEnabled',compiled+';return HomeNoticeProbe;');
document.visibilityState='visible';window.setInterval=()=>1;window.clearInterval=()=>{};
const Component=factory(React.useEffect,options=>{starts++;return {tick:async()=>{if(options.isVisible())await options.fetchPage(0,new AbortController().signal);},pause:()=>{},dispose:()=>{}};},()=>env.owner,async()=>{requests++;return {status:200,ok:true,json:async()=>[]};},'/api',()=>{},()=>false);
const denied=mount(Component,{hydrated:true,username:env.owner,studioAllowed:false,refreshList:()=>{}});await flush();assert.equal(starts,0);assert.equal(requests,0);denied.close();
const allowed=mount(Component,{hydrated:true,username:env.owner,studioAllowed:true,refreshList:()=>{}});await flush();assert.equal(starts,1);assert.equal(requests,1);allowed.close();process.stdout.write('true');
""") is True
    source = (ROOT / "frontend/app/page.tsx").read_text()
    assert source.count("checkStudioAccess(request.signal)") == 1
    assert "studioAccessAllowed={studioAllowed}" in source
