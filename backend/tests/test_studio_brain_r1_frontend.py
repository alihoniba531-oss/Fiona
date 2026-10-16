"""Offline SSR and state-transition probes for the brain trial wait message."""
from test_studio_frontend_components import probe


SETUP = r"""
const brainJob=status=>({id:'brain-job',provider:'claude',task:'read_through',model:'claude-sonnet-5-5',status,
 output:null,warnings:['保留原有警告'],usage:null,cost:{currency:'USD',amount:.01},latency_s:null,
 parent_job_id:null,error_code:null,error_message:null});
const waitMessage='长任务可能需要数分钟';
"""


def test_brain_wait_message_ssr_only_for_queued_and_running_preserves_status():
    assert probe(SETUP + r"""
env.mode='ssr';const component=load('components/studio/BrainTrial.tsx'),lib=load('lib/studio.ts');
for(const status of ['queued','running','succeeded','uncertain','rejected','failed','invalid_output','released']){
 const html=renderToStaticMarkup(realReact.createElement(component.BrainResultCard,{attempts:[brainJob(status)],busy:false,onRelease:()=>{}}));
 assert.equal(html.includes(waitMessage),status==='queued'||status==='running',status);
 assert(html.includes(lib.brainStatusLabel(status)),`${status} retains its original status`);
 assert(html.includes('警告：保留原有警告'));assert(html.includes('claude-sonnet-5-5'));
}
assert.equal(env.calls.length,0);process.stdout.write('true');
""") is True


def test_brain_wait_message_updates_with_job_state_without_network():
    assert probe(SETUP + r"""
const component=load('components/studio/BrainTrial.tsx'),lib=load('lib/studio.ts');
const props={attempts:[brainJob('queued')],busy:false,onRelease:()=>{}};
const card=mount(component.BrainResultCard,props);
assert(text(card.tree).includes(waitMessage));assert(text(card.tree).includes('排队中'));
props.attempts=[brainJob('running')];card.render();await flush();
assert(text(card.tree).includes(waitMessage));assert(text(card.tree).includes('试读中'));
for(const status of ['succeeded','uncertain','rejected','failed','invalid_output','released']){
 props.attempts=[brainJob(status)];card.render();await flush();
 assert(!text(card.tree).includes(waitMessage),status);assert(text(card.tree).includes(lib.brainStatusLabel(status)));
}
assert.equal(env.calls.length,0);card.close();process.stdout.write('true');
""") is True
