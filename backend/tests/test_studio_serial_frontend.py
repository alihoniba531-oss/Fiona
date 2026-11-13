"""连载续拆：前端请求契约、组件接线、SSR 文案与新增元素字重。"""
from html.parser import HTMLParser

from test_studio_breakdown_frontend import SETUP as BREAKDOWN_SETUP, STAGE_SETUP as BREAKDOWN_STAGE_SETUP
from test_studio_sources_frontend import (
    DRIVER as SOURCE_DRIVER,
    NOVEL_DRIVER,
    SETUP as SOURCE_SETUP,
    probe,
)


VOID_ELEMENTS = {"area", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
BOLD_CLASSES = {"font-medium", "font-semibold", "font-bold"}


class SerialWeightParser(HTMLParser):
    """Track the open tag stack and audit every data-serial element's ancestry."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.count = 0
        self.errors = []

    def _open(self, tag, attrs, push):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        self_bold = tag in {"b", "strong"} or any(name in BOLD_CLASSES for name in classes)
        if "data-serial" in attrs:
            self.count += 1
            if tag in {"b", "strong"}:
                self.errors.append(f"data-serial element is <{tag}>")
            if any(name in BOLD_CLASSES for name in classes):
                self.errors.append(f"data-serial <{tag}> has bold class: {attrs.get('class')}")
            for ancestor_tag, ancestor_bold in self.stack:
                if ancestor_tag in {"b", "strong"}:
                    self.errors.append(f"data-serial <{tag}> has <{ancestor_tag}> ancestor")
                if ancestor_bold:
                    self.errors.append(f"data-serial <{tag}> has bold ancestor <{ancestor_tag}>")
        if push and tag not in VOID_ELEMENTS:
            self.stack.append((tag, self_bold))

    def handle_starttag(self, tag, attrs):
        self._open(tag, attrs, True)

    def handle_startendtag(self, tag, attrs):
        self._open(tag, attrs, False)

    def handle_endtag(self, tag):
        if tag in VOID_ELEMENTS:
            return
        while self.stack:
            open_tag, _ = self.stack.pop()
            if open_tag == tag:
                break


def assert_regular_weight(label, html):
    parser = SerialWeightParser()
    parser.feed(html)
    parser.close()
    assert parser.count > 0, f"{label}: no data-serial elements were rendered"
    assert not parser.errors, f"{label}: " + "; ".join(parser.errors)
    return parser.count


def test_quote_and_start_continuation_requests():
    assert probe(r"""
const lib=load('lib/studio-breakdown.ts');
const calls=[];agents.apiJson=async(url,init={})=>{calls.push({url,method:init.method,body:init.body});return {};};
await lib.quoteStudioContinuation('p');
await lib.startStudioContinuation('p','q');
assert.equal(calls.length,2);
assert.equal(calls[0].url,'/api/studio/projects/p/breakdown/continue/quote');
assert.equal(calls[0].method,'POST');
assert.deepEqual(JSON.parse(calls[0].body),{});
assert.equal(calls[1].url,'/api/studio/projects/p/breakdown/continue/start');
assert.equal(calls[1].method,'POST');
assert.deepEqual(JSON.parse(calls[1].body),{quote_id:'q'});
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def _stage_continue_setup(view_js, quote_js="({...costQuote,id:'cq1',continue_from:6,continue_to:8,total_chunks:2})", start_js="serialView"):
    return BREAKDOWN_STAGE_SETUP + f"""
const serialView={view_js};
const serialQuote={quote_js};
agents.apiJson=async(url,init={{}})=>{{
  const method=init.method??'GET';
  if(method==='POST'){{
    posts.push({{url,body:JSON.parse(init.body??'{{}}')}});
    if(url.endsWith('/breakdown/continue/quote'))return serialQuote;
    if(url.endsWith('/breakdown/continue/start'))return {start_js};
    return costQuote;
  }}
  if(url.endsWith('/breakdown')){{breakdownReads++;return JSON.parse(JSON.stringify(serialView));}}
  if(url.endsWith('/bible'))return [entry];
  if(url.endsWith('/episodes'))return {{...plan,appended_from:null,continuing:serialView.continuing}};
  throw Error('Unexpected route '+url);
}};
"""


SERIAL_VIEW = "{...breakdown,status:'done',outdated:1,continuable:true,covered_through:5,continue_from:6,continue_to:8,changed_covered:[3,4],stale_chapters:[2],continuations:[{round:1,from:4,to:5,snapshot_no:2}],continuing:false,chunks:[{...chunk,status:'succeeded'}]}"
SERIAL_QUOTE = "{...costQuote,id:'cq1',continue_from:6,continue_to:8,total_chunks:2}"


def test_stage_continue_quote_is_wired_and_confirmed():
    assert probe(_stage_continue_setup(SERIAL_VIEW, SERIAL_QUOTE, "({...serialView,status:'running',continuing:true})") + r"""
const page=mount(load('components/studio/BreakdownStage.tsx').default,props);await flush();
assert.equal(breakdownReads,1);
await named(page,'BreakdownPanel').props.onContinue();await flush();
let modal=named(page,'BreakdownQuoteDialog');assert(modal);
assert.deepEqual(modal.props.continueRange,{from:6,to:8});
assert.equal(modal.props.targetMin,undefined);
assert.equal(modal.props.affectsApproved,undefined);
assert.equal(modal.props.replacesPartial,undefined);
assert.equal(posts.length,1);
assert.equal(posts[0].url,'/api/studio/projects/p/breakdown/continue/quote');
assert.deepEqual(posts[0].body,{});
await modal.props.onConfirm();await flush();
assert.equal(posts.length,2);
assert(posts[1].url.endsWith('/breakdown/continue/start'),posts[1].url);
assert.deepEqual(posts[1].body,{quote_id:'cq1'});
assert(text(page.tree).includes('续拆已开始。'));
page.close();process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_stage_continue_quote_409_shows_backend_message_and_refreshes():
    assert probe(_stage_continue_setup(SERIAL_VIEW, SERIAL_QUOTE) + r"""
const original=agents.apiJson;
agents.apiJson=async(url,init={})=>{
  if((init.method??'GET')==='POST'&&url.endsWith('/breakdown/continue/quote')){
    posts.push({url,body:JSON.parse(init.body??'{}')});
    throw new ApiError('续拆报价已失效，请重新报价',409);
  }
  return original(url,init);
};
const page=mount(load('components/studio/BreakdownStage.tsx').default,props);await flush();
const before=breakdownReads;
await named(page,'BreakdownPanel').props.onContinue();await flush();
assert.equal(posts.length,1);
assert(breakdownReads>before);
assert(error(page).includes('续拆报价已失效，请重新报价'),error(page));
page.close();process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_stage_continue_account_switch_does_not_request_and_plan_gets_continuing():
    assert probe(_stage_continue_setup(SERIAL_VIEW) + r"""
const page=mount(load('components/studio/BreakdownStage.tsx').default,props);await flush();
assert.equal(named(page,'EpisodePlan').props.continuing,false);
page.close();
serialView.continuing=true;serialView.status='running';serialView.chunks=[{...chunk,status:'running'}];
const active=mount(load('components/studio/BreakdownStage.tsx').default,props);await flush();
assert.equal(named(active,'EpisodePlan').props.continuing,true);
env.owner='other';
await named(active,'BreakdownPanel').props.onContinue();await flush();
assert.equal(posts.length,0);
active.close();process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_panel_continuable_block_wording_and_outdated_replacement():
    assert probe(BREAKDOWN_SETUP + r"""
env.mode='ssr';const Panel=load('components/studio/BreakdownPanel.tsx').default;
const view={...breakdown,status:'done',outdated:1,continuable:true,covered_through:5,continue_from:6,continue_to:8,changed_covered:[],stale_chapters:[],continuations:[],continuing:false,chunks:[{...chunk,status:'succeeded'}]};
const render=value=>renderToStaticMarkup(realReact.createElement(Panel,{project,breakdown:value,providers,busy:false,onQuote:async()=>{},onContinue:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}}));
const html=render(view);
for(const value of ['已拆到第 5 章；作品已同步到第 8 章，可以续拆第 6–8 章。','续拆只为新增章节付费，已拆的部分、你改过的分集和已定的妆都保留；续拆完成后分集方案要重新批准一次。','>续拆第 6–8 章</button>','>重新拆解</button>'])assert(html.includes(value),value);
const primary=(html.match(/<button[^>]*>续拆第 6–8 章<\/button>/)||[])[0];assert(primary,html);
assert(primary.includes('data-serial=""'),primary);
assert(primary.includes('class="btn btn-primary min-h-10"'),primary);
assert(!html.includes('拆解基于快照'),'outdated block must be replaced');
const single=render({...view,continue_from:6,continue_to:6});
assert(single.includes('可以续拆第 6 章。'));assert(single.includes('>续拆第 6 章</button>'));assert(!single.includes('续拆第 6–6 章'));
env.mode='hooks';cache.clear();
const HookPanel=load('components/studio/BreakdownPanel.tsx').default;
const panel=mount(HookPanel,{project,breakdown:view,providers,busy:false,onQuote:async()=>{},onContinue:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}});
all(panel.tree,node=>node.type==='input')[0].props.onChange({target:{value:'500'}});await flush();
assert.equal(button(panel,'续拆第 6–8 章').props.disabled,false);
assert.equal(button(panel,'重新拆解').props.disabled,true);
panel.close();
const blockedProviders=providers.map(item=>item.id==='qwen'?{...item,available:false}:item);
const blocked=mount(HookPanel,{project,breakdown:view,providers:blockedProviders,busy:false,onQuote:async()=>{},onContinue:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}});
assert.equal(button(blocked,'续拆第 6–8 章').props.disabled,true);
blocked.close();
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_panel_changed_covered_line_only_when_nonempty_even_when_not_continuable():
    assert probe(BREAKDOWN_SETUP + r"""
env.mode='ssr';const Panel=load('components/studio/BreakdownPanel.tsx').default;
const render=value=>renderToStaticMarkup(realReact.createElement(Panel,{project,breakdown:value,providers,busy:false,onQuote:async()=>{},onContinue:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}}));
const changed={...breakdown,status:'done',continuable:false,outdated:0,changed_covered:[3,4,7],stale_chapters:[],continuations:[],continuing:false,chunks:[{...chunk,status:'succeeded'}]};
const line='第 3–4、7 章在拆解之后改过，续拆不会重拆它们；需要时可以整本重新拆解（会生成新的总表，已定的妆要重新定）。';
const count=(html,text)=>html.split(text).length-1;
assert.equal(count(render(changed),line),1,'non-continuable changed line must appear exactly once');
assert(render({...changed,changed_covered:[]}).includes('在拆解之后改过')===false);
const continuable=render({...changed,continuable:true,outdated:1,continue_from:6,continue_to:8,covered_through:5});
assert.equal(count(continuable,line),1,'continuable changed line must appear exactly once');
assert.equal(count(continuable,'在拆解之后改过'),1,'continuable changed sentence must appear exactly once');
assert(continuable.includes(line),'changed line belongs inside the continuation block');
assert(continuable.indexOf(line)>continuable.indexOf('续拆只为新增章节付费'));
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_panel_whole_book_quote_button_tier_follows_continuable():
    assert probe(BREAKDOWN_SETUP + r"""
env.mode='ssr';const Panel=load('components/studio/BreakdownPanel.tsx').default;
const render=value=>renderToStaticMarkup(realReact.createElement(Panel,{project,breakdown:value,providers,busy:false,onQuote:async()=>{},onContinue:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}}));
const classOf=(html,label)=>{const button=(html.match(new RegExp('<button[^>]*>'+label+'</button>'))||[])[0];assert(button,label+' not rendered: '+html);return (button.match(/class="([^"]*)"/)||[])[1];};
const view={...breakdown,status:'done',outdated:1,continuable:true,covered_through:5,continue_from:6,continue_to:8,changed_covered:[],stale_chapters:[],continuations:[],continuing:false,chunks:[{...chunk,status:'succeeded'}]};
assert.equal(classOf(render(view),'重新报价拆解'),'btn btn-quiet min-h-10');
assert.equal(classOf(render({...view,continuable:false,outdated:0,continue_from:null,continue_to:null}),'重新报价拆解'),'btn btn-primary min-h-10');
assert.equal(classOf(render(null),'报价'),'btn btn-primary min-h-10');
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_panel_stale_done_and_continuing_lines_have_their_own_conditions():
    assert probe(BREAKDOWN_SETUP + r"""
env.mode='ssr';const Panel=load('components/studio/BreakdownPanel.tsx').default;
const base={...breakdown,outdated:0,continuable:false,changed_covered:[],chunks:[{...chunk,status:'succeeded'}]};
const render=value=>renderToStaticMarkup(realReact.createElement(Panel,{project,breakdown:value,providers,busy:false,onQuote:async()=>{},onContinue:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}}));
const done=render({...base,status:'done',covered_through:8,stale_chapters:[2,5],continuations:[{round:1,from:6,to:8,snapshot_no:2}],continuing:false});
assert(done.includes('第 2、5 章拆解时在书斋里标为待复核，拆解按快照里的原文进行。'));
assert(done.includes('已续拆 1 次，拆到第 8 章。'));
assert(!done.includes('正在续拆'));
const active=render({...base,status:'running',covered_through:5,stale_chapters:[],continuations:[{round:1,from:4,to:5,snapshot_no:2}],continuing:true});
assert(active.includes('正在续拆第 4–5 章。'));
assert(!active.includes('已续拆 1 次'));
const one=render({...base,status:'running',continuations:[{round:1,from:4,to:4,snapshot_no:2}],continuing:true});
assert(one.includes('正在续拆第 4 章。'));
const empty=render({...base,status:'done',covered_through:5,stale_chapters:[],continuations:[],continuing:false});
for(const value of ['拆解时在书斋里标为待复核','已续拆 ','正在续拆'])assert(!empty.includes(value),value);
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_panel_continuing_hides_cancel_and_partial_note_is_conditional():
    assert probe(BREAKDOWN_SETUP + r"""
env.mode='ssr';const Panel=load('components/studio/BreakdownPanel.tsx').default;
const base={...breakdown,outdated:0,continuable:false,changed_covered:[],stale_chapters:[],continuations:[],chunks:[{...chunk,status:'succeeded'}]};
const render=value=>renderToStaticMarkup(realReact.createElement(Panel,{project,breakdown:value,providers,busy:false,onQuote:async()=>{},onContinue:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}}));
const cancelHidden='>取消拆解</button>',continuingNote='续拆进行中不能取消，失败的批次可以单批重跑。';
const partialNote='续拆有批次未完成：完成前不能同步新章，也不能修改或批准分集方案。单批重跑读的是本轮的快照，在书斋里改原文对重跑无效；重跑仍失败时，只能整本重新拆解（会生成新的总表，已定的妆要重新定）。';
for(const status of ['running','partial']){
 const html=render({...base,status,continuing:true,chunks:[{...chunk,status:status==='partial'?'failed':'running'}]});
 assert(!html.includes(cancelHidden),status+' must hide cancel');
 assert(html.includes(continuingNote),status+' must explain cancellation is unavailable');
 assert.equal(html.includes(partialNote),status==='partial',status+' partial note');
}
const running=render({...base,status:'running',continuing:false,chunks:[{...chunk,status:'running'}]});
assert(running.includes(cancelHidden));
assert(!running.includes(continuingNote));
const done=render({...base,status:'done',continuing:true,chunks:[{...chunk,status:'succeeded'}]});
assert(!done.includes(partialNote));
const partialOnly=render({...base,status:'partial',continuing:false,chunks:[{...chunk,status:'failed'}]});
assert(!partialOnly.includes(partialNote));
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_quote_dialog_continue_mode_suppresses_whole_book_prompts():
    assert probe(BREAKDOWN_SETUP + r"""
env.mode='ssr';const Dialog=load('components/studio/BreakdownQuoteDialog.tsx').default;
const props={quote:{...costQuote,continue_from:6,continue_to:8},continueRange:{from:6,to:8},targetMin:120,targetMax:180,affectsApproved:true,replacesPartial:true,busy:false,onConfirm:async()=>{},onClose:()=>{}};
const html=renderToStaticMarkup(realReact.createElement(Dialog,props));
for(const value of ['续拆报价','确认续拆','只拆第 6–8 章。','新增的集会追加到分集方案末尾，方案会退回待批准。','确认后不能取消；有批次失败时可以单批重跑。','导演模型：千问','共 <span class="readout">4</span> 批','预估费用','报价剩余有效时间'])assert(html.includes(value),value);
for(const value of ['每集目标时长将保存为 120–180 秒','当前已批准方案的目标时长将发生变化','上一次拆解未执行的批次将取消并释放预留','确认拆解报价','确认开始'])assert(!html.includes(value),value);
const single=renderToStaticMarkup(realReact.createElement(Dialog,{...props,continueRange:{from:6,to:6}}));
assert(single.includes('只拆第 6 章。'));assert(!single.includes('第 6–6 章'));
assert(single.includes('续拆报价'));assert(single.includes('确认续拆'));
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_quote_dialog_without_continue_range_keeps_the_whole_book_output():
    assert probe(BREAKDOWN_SETUP + r"""
env.mode='ssr';const Dialog=load('components/studio/BreakdownQuoteDialog.tsx').default;
const html=renderToStaticMarkup(realReact.createElement(Dialog,{quote:costQuote,targetMin:120,targetMax:180,affectsApproved:true,replacesPartial:true,busy:false,onConfirm:async()=>{},onClose:()=>{}}));
for(const value of ['确认拆解报价','确认开始','每集目标时长将保存为 120–180 秒（确认开始时保存）。','当前已批准方案的目标时长将发生变化。旧方案与 G0 状态保留至新方案发布；新方案发布后会退回待批准，需要重新批准。','上一次拆解未执行的批次将取消并释放预留。','共 <span class="readout">4</span> 批'])assert(html.includes(value),value);
for(const value of ['续拆报价','确认续拆','只拆第','新增的集会追加到分集方案末尾','确认后不能取消'])assert(!html.includes(value),value);
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_episode_plan_added_tags_only_on_new_episodes_in_both_views():
    assert probe(BREAKDOWN_SETUP + r"""
env.mode='ssr';const Plan=load('components/studio/EpisodePlan.tsx').default;
const episodes=[...plan.episodes,...[3,4,5].map(no=>({...plan.episodes[1],id:'ep'+no,no,title:'第'+no+'集',unit_from:no,unit_to:no,notes:'',warnings:[],target_min:null,target_max:null}))];
const render=value=>renderToStaticMarkup(realReact.createElement(Plan,{plan:value,busy:false,onOperate:async()=>{},onApprove:async()=>{},onExport:async()=>{}}));
const html=render({...plan,episodes,appended_from:3,continuing:false});
assert(html.includes('第 3–5 集是这次续拆新增的，看过后重新批准分集方案。'));
const table=html.slice(html.indexOf('data-testid="episode-table"'),html.indexOf('data-testid="episode-cards"'));
const cards=html.slice(html.indexOf('data-testid="episode-cards"'));
const count=(region,tag)=>(region.match(new RegExp(tag.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'g'))||[]).length;
const tableTag='<span class="tag ml-2" data-serial="">新增</span>';
const cardTag='<span class="tag" data-serial="">新增</span>';
assert.equal(count(table,tableTag),3,'table added tags must be tag ml-2');
assert.equal(count(table,cardTag),0,'table added tags must not be bare tag');
assert.equal(count(cards,cardTag),3,'card added tags must be tag');
assert.equal(count(cards,tableTag),0,'card added tags must not carry ml-2');
for(const [label,region] of [['table',table],['cards',cards]]){
  const chunks=region.split(label==='table'?'<tr':'<article').slice(1);
  for(const chunk of chunks){
    if(!chunk.includes('新增'))continue;
    const no=label==='table'?(chunk.match(/<td class="readout p-3">(\d+)<\/td>/)||[])[1]:(chunk.match(/第 (\d+) 集 ·/)||[])[1];
    assert(no!=null,label+' row has no number');
    assert(Number(no)>=3,label+' tagged a non-new episode '+no);
  }
}
const single=render({...plan,episodes,appended_from:5,continuing:false});
assert(single.includes('第 5 集是这次续拆新增的，看过后重新批准分集方案。'));
assert(!single.includes('第 5–5 集'));
assert.equal(count(single,tableTag),1,'single new episode keeps one table tag');
assert.equal(count(single,cardTag),1,'single new episode keeps one card tag');
const none=render({...plan,episodes,appended_from:null,continuing:false});
assert(!none.includes('这次续拆新增的'));
assert(!none.includes(tableTag));
assert(!none.includes(cardTag));
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_episode_plan_continuing_and_partial_sentences():
    assert probe(BREAKDOWN_SETUP + r"""
env.mode='ssr';const Plan=load('components/studio/EpisodePlan.tsx').default;
const continuingSentence='续拆进行中，完成后新增的集会追加到方案末尾，已有的集保持不变；完成前暂不能修改或批准分集方案。';
const oldSentence='拆解尚未全部完成，补跑完成后分集方案会按新结果重新生成。';
const render=(value,extra={})=>renderToStaticMarkup(realReact.createElement(Plan,{plan:value,busy:false,...extra,onOperate:async()=>{},onApprove:async()=>{},onExport:async()=>{}}));
const active=render({...plan,appended_from:null},{continuing:true});
assert(active.includes(continuingSentence));
assert(!active.includes('按新结果重新生成'));
const partialHtml=render({...plan,appended_from:null},{partial:true});
assert(partialHtml.includes(oldSentence));
assert(!partialHtml.includes(continuingSentence));
const activePartial=render({...plan,appended_from:null},{partial:true,continuing:true});
assert(activePartial.includes(continuingSentence));
assert(!activePartial.includes('按新结果重新生成'));
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_source_panel_drift_snapshot_stale_and_serial_hints():
    assert probe(SOURCE_SETUP + r"""
const Panel=load('components/studio/SourcePanel.tsx').default;
async function show(state){
  agents.apiJson=async()=>state;
  const panel=mount(Panel,{owner:env.owner,projectId:'project',onChanged:async()=>{}});await flush();
  const value=text(panel.tree);const serials=all(panel.tree,n=>n.props&&Object.prototype.hasOwnProperty.call(n.props,'data-serial')).length;panel.close();
  return {text:value,serials};
}
const snapshot={no:2,created_at:'2026-10-16T00:00:00Z',chapters:6,chars:9000,flagged:[],stale:[2,4]};
const changed=await show({kind:'novel',title:'春山',snapshot:{...snapshot,stale:[]},drift:{state:'changed',changed:[3],bible_changed:true,eligible:true,stale:[2,4],book_status:'running'}});
assert(changed.text.includes('原作有改动：第 3 章内容变化，故事圣经已更新，第 2、4 章待复核'),changed.text);
assert(!changed.text.includes('快照中第 2、4 章待复核。'));
const unchanged=await show({kind:'novel',title:'春山',snapshot,drift:{state:'unchanged',eligible:true,book_status:'running'}});
assert(unchanged.text.includes('快照中第 2、4 章待复核。'));
assert(unchanged.text.includes('作品还在写，同步只收已写好的章节。'));
assert(unchanged.serials>0);
const unavailable=await show({kind:'novel',title:'春山',snapshot,drift:{state:'unavailable'}});
assert(unavailable.text.includes('快照中第 2、4 章待复核。'));
assert(!unavailable.text.includes('作品还在写'));
const empty=await show({kind:'novel',title:'春山',snapshot:{...snapshot,stale:[]},drift:{state:'unchanged',eligible:true,book_status:'completed'}});
assert(!empty.text.includes('待复核。'));
assert(!empty.text.includes('作品还在写'));
const paste=await show({kind:'paste',title:'粘贴',snapshot:{...snapshot,stale:[]},drift:{state:'not_applicable'}});
assert(!paste.text.includes('作品还在写'));
const completed=await show({kind:'novel',title:'春山',snapshot:{...snapshot,stale:[]},drift:{state:'unchanged',book_status:'completed'}});
assert(!completed.text.includes('作品还在写'));
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_source_choices_serial_hints_and_snapshot_chapter_hint():
    assert probe(SOURCE_SETUP + r"""
env.mode='ssr';const mod=load('components/studio/SourceChoices.tsx');
const serial={...candidate,status:'running',chapters_done:5,stale:[3,5],eligible:true};
const hints=renderToStaticMarkup(realReact.createElement(mod.SerialSourceHints,{book:serial}));
assert(hints.includes('第 3、5 章待复核，会照常收进快照。'));
assert(hints.includes('连载中，只收已写好的 5 章。'));
const completedHints=renderToStaticMarkup(realReact.createElement(mod.SerialSourceHints,{book:{...serial,status:'completed'}}));
assert(completedHints.includes('待复核，会照常收进快照。'));
assert(!completedHints.includes('连载中'));
const serialOnly=renderToStaticMarkup(realReact.createElement(mod.SerialSourceHints,{book:{...serial,stale:[]}}));
assert(serialOnly.includes('连载中，只收已写好的 5 章。'));
assert(!serialOnly.includes('待复核'));
const noHints=renderToStaticMarkup(realReact.createElement(mod.SerialSourceHints,{book:{...serial,status:'completed',stale:[]}}));
assert.equal(noHints,'');
const ineligible=renderToStaticMarkup(realReact.createElement(mod.SerialSourceHints,{book:{...serial,stale:[],eligible:false}}));
assert.equal(ineligible,'');
const projects=[{id:'old',title:'旧项目',snapshot_no:1,created_at:'2026-10-16T00:00:00Z',snapshot_chapters:2}];
const behind=renderToStaticMarkup(realReact.createElement(mod.ExistingSourceProjects,{projects,embedded:true,chaptersDone:5}));
assert(behind.includes('快照到第 2 章，到来源面板同步后可以续拆'));
const current=renderToStaticMarkup(realReact.createElement(mod.ExistingSourceProjects,{projects,embedded:true,chaptersDone:2}));
assert(!current.includes('快照到第'));
const unknown=renderToStaticMarkup(realReact.createElement(mod.ExistingSourceProjects,{projects,embedded:true}));
assert(!unknown.includes('快照到第'));
const nullChapters=renderToStaticMarkup(realReact.createElement(mod.ExistingSourceProjects,{projects:[{...projects[0],snapshot_chapters:null}],embedded:true,chaptersDone:5}));
assert(!nullChapters.includes('快照到第'));
const fractionalChapters=renderToStaticMarkup(realReact.createElement(mod.ExistingSourceProjects,{projects:[{...projects[0],snapshot_chapters:2.5}],embedded:true,chaptersDone:5}));
assert(!fractionalChapters.includes('快照到第'));
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_novel_film_dialog_serial_candidate_shows_both_hint_lines():
    assert probe(SOURCE_SETUP + r"""
const Film=load('components/novel/NovelFilmDialog.tsx').default;
function deepText(node){
  if(Array.isArray(node))return node.map(deepText).join('');
  if(node==null||node===false||node===true)return '';
  if(typeof node!=='object')return String(node);
  if(typeof node.type==='function')return deepText(node.type(node.props));
  if(typeof node.type!=='string')return '';
  return deepText(node.props?.children);
}
const serial={...candidate,status:'running',chapters_done:6,stale:[3,5],eligible:true,
  projects:[{id:'old',title:'已有项目',snapshot_no:1,created_at:'2026-10-16T00:00:00Z',snapshot_chapters:2}]};
agents.apiJson=async url=>url.endsWith('/novels')?{enabled:true,books:[serial]}:[];
const dialog=mount(Film,{owner:env.owner,bookId:'book-1',bookTitle:'春山',embedded:true,onClose:()=>{}});await flush();
const body=deepText(dialog.tree);
assert(body.includes('第 3、5 章待复核，会照常收进快照。'),body);
assert(body.includes('连载中，只收已写好的 6 章。'),body);
assert(body.includes('快照到第 2 章，到来源面板同步后可以续拆'),body);
assert.equal(named(dialog,'ExistingSourceProjects').props.chaptersDone,6);
dialog.close();process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_create_project_dialog_new_empty_state():
    assert probe(SOURCE_SETUP + r"""
agents.apiJson=async url=>url.endsWith('/novels')?{enabled:true,books:[]}:[];
const dialog=mount(load('components/studio/CreateProjectDialog.tsx').CreateProjectDialog,{owner:env.owner,busy:false,onCreate:async()=>{},onClose:()=>{}});await flush();
button(dialog,'小说工坊').props.onClick();await flush();
assert(text(dialog.tree).includes('没有找到符合书名的作品。只有有故事圣经、至少写好一章、且不在修改中的作品可以导入；连载中的书只收已写好的章节。'));
dialog.close();process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_novel_workbench_serial_book_requests_studio_and_shows_film_button():
    assert probe(r"""
env.book.status='running';
env.book.chapters_done=3;
env.book.chapters=env.book.chapters.slice(0,3).map(chapter=>({...chapter,status:'completed'}));
const page=await screen('components/novel/NovelWorkbench.tsx',{id:env.book.id,embedded:true});
assert.equal(env.calls.filter(call=>call==='GET /api/studio/access').length,1,JSON.stringify(env.calls));
assert(all(page.tree,node=>node.type==='button'&&node.props.children==='做成片').length===1);
assert.equal(named(page,'GateBanner').props.onMakeFilm,undefined);
page.close();process.stdout.write('true');
""", NOVEL_DRIVER) is True


def test_novel_workbench_without_a_chapter_does_not_request_studio():
    assert probe(r"""
env.book.status='awaiting_review';
env.book.chapters_done=0;
env.book.chapters=[];
const page=await screen('components/novel/NovelWorkbench.tsx',{id:env.book.id});
assert(!env.calls.some(call=>call.includes('/studio/')),JSON.stringify(env.calls));
assert(!all(page.tree,node=>node.type==='button'&&node.props.children==='做成片').length);
assert.equal(named(page,'GateBanner').props.onMakeFilm,undefined);
page.close();process.stdout.write('true');
""", NOVEL_DRIVER) is True


def test_novel_workbench_completed_gate_banner_behavior_is_unchanged():
    assert probe(r"""
const page=await screen('components/novel/NovelWorkbench.tsx',{id:env.book.id,embedded:true});
assert.equal(env.book.status,'completed');
assert.equal(env.calls.filter(call=>call==='GET /api/studio/access').length,1);
assert.equal(typeof named(page,'GateBanner').props.onMakeFilm,'function');
await named(page,'GateBanner').props.onMakeFilm();await flush();
assert.equal(named(page,'NovelFilmDialog').props.embedded,true);
page.close();process.stdout.write('true');
""", NOVEL_DRIVER) is True


def test_format_chapter_ranges_empty_single_consecutive_and_mixed():
    assert probe(r"""
const lib=load('lib/studio-breakdown.ts');
assert.equal(lib.formatChapterRanges([]),'');
assert.equal(lib.formatChapterRanges([3]),'第 3 章');
assert.equal(lib.formatChapterRanges([5,3,4]),'第 3–5 章');
assert.equal(lib.formatChapterRanges([10,6,5,1,3,2,2]),'第 1–3、5–6、10 章');
process.stdout.write('true');
""", SOURCE_DRIVER) is True


def test_new_serial_elements_have_regular_weight_and_no_bold_ancestors():
    probe_result = probe(BREAKDOWN_SETUP + r"""
function esc(value){return String(value).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
const voids=['area','br','col','embed','hr','img','input','link','meta','source','track','wbr'];
function expand(node){
  if(Array.isArray(node))return node.map(expand).filter(item=>item!=null);
  if(node==null||node===false||node===true)return null;
  if(typeof node==='string'||typeof node==='number')return node;
  const type=node.type,props=node.props??{};
  if(typeof type==='function')return expand(type(props));
  if(typeof type!=='string')return null;
  return {type,props:{...props,children:expand(props.children)}};
}
function attrsText(props){
  const pairs=[];
  for(const [key,value] of Object.entries(props??{})){
    if(['children','ref','key','style'].includes(key))continue;
    if(key==='className'){pairs.push(['class',String(value)]);continue;}
    if(typeof value==='string'||typeof value==='number'){pairs.push([key,String(value)]);continue;}
    if(value===true)pairs.push([key,'']);
  }
  return pairs.map(([key,value])=>` ${key}="${esc(value)}"`).join('');
}
function toHtml(node){
  const expanded=expand(node);
  if(expanded==null)return '';
  if(Array.isArray(expanded))return expanded.map(toHtml).join('');
  if(typeof expanded!=='object')return esc(expanded);
  const {type,props={}}=expanded;
  const children=toHtml(props.children);
  return voids.includes(type)?`<${type}${attrsText(props)}/>`:`<${type}${attrsText(props)}>${children}</${type}>`;
}
env.mode='ssr';cache.clear();
const Panel=load('components/studio/BreakdownPanel.tsx').default;
const Dialog=load('components/studio/BreakdownQuoteDialog.tsx').default;
const Plan=load('components/studio/EpisodePlan.tsx').default;
const Choices=load('components/studio/SourceChoices.tsx');
const view={...breakdown,status:'done',outdated:1,continuable:true,covered_through:5,continue_from:6,continue_to:8,changed_covered:[3,4],stale_chapters:[2],continuations:[{round:1,from:4,to:5,snapshot_no:2}],continuing:false,chunks:[{...chunk,status:'succeeded'}]};
const renderPanel=value=>renderToStaticMarkup(realReact.createElement(Panel,{project,breakdown:value,providers,busy:false,onQuote:async()=>{},onContinue:async()=>{},onRetry:async()=>{},onRelease:async()=>{},onCancel:async()=>{}}));
const panelHtml=renderPanel(view);
const continuingHtml=renderPanel({...breakdown,status:'partial',outdated:0,continuable:false,covered_through:5,continue_from:null,continue_to:null,changed_covered:[],stale_chapters:[],continuations:[{round:1,from:6,to:8,snapshot_no:2}],continuing:true,chunks:[{...chunk,status:'failed'}]});
const dialogHtml=renderToStaticMarkup(realReact.createElement(Dialog,{quote:{...costQuote,continue_from:6,continue_to:8},continueRange:{from:6,to:8},targetMin:120,targetMax:180,affectsApproved:true,replacesPartial:true,busy:false,onConfirm:async()=>{},onClose:()=>{}}));
const episodes=[...plan.episodes,...[3,4,5].map(no=>({...plan.episodes[1],id:'ep'+no,no,title:'第'+no+'集',unit_from:no,unit_to:no,notes:'',warnings:[],target_min:null,target_max:null}))];
const planHtml=renderToStaticMarkup(realReact.createElement(Plan,{plan:{...plan,episodes,appended_from:3,continuing:true},partial:true,busy:false,onOperate:async()=>{},onApprove:async()=>{},onExport:async()=>{}}));
const candidate={id:'book-1',title:'春山',status:'running',chapters_done:6,words_done:15000,completed_at:null,updated_at:'2026-10-16T00:00:00Z',drama_adaptation:false,eligible:true,reason:null,flagged:[],stale:[3,5],projects:[{id:'old',title:'已有项目',snapshot_no:1,created_at:'2026-10-16T00:00:00Z',snapshot_chapters:2}]};
const choicesHtml=renderToStaticMarkup(realReact.createElement(Choices.NovelSourceChoice,{book:candidate,embedded:true,onSelect:()=>{}}));
env.mode='hooks';cache.clear();
const sourceState={kind:'novel',title:'春山',snapshot:{no:2,created_at:'2026-10-16T00:00:00Z',chapters:6,chars:9000,flagged:[],stale:[2,4]},drift:{state:'unchanged',eligible:true,book_status:'running'}};
agents.apiJson=async()=>sourceState;
const source=mount(load('components/studio/SourcePanel.tsx').default,{owner:env.owner,projectId:'project',onChanged:async()=>{}});await flush();
const sourceHtml=toHtml(source.tree);source.close();
agents.apiJson=async url=>url.endsWith('/novels')?{enabled:true,books:[candidate]}:[];
const film=mount(load('components/novel/NovelFilmDialog.tsx').default,{owner:env.owner,bookId:'book-1',bookTitle:'春山',embedded:true,onClose:()=>{}});await flush();
const filmHtml=toHtml(film.tree);film.close();
process.stdout.write(JSON.stringify({panel:[panelHtml,continuingHtml],dialog:dialogHtml,plan:planHtml,choices:choicesHtml,source:sourceHtml,film:filmHtml}));
""", SOURCE_DRIVER)
    for label, html in probe_result.items():
        for index, value in enumerate(html if isinstance(html, list) else [html]):
            assert_regular_weight(f"{label}[{index}]" if isinstance(html, list) else label, value)
