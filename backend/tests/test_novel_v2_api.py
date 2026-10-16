"""Offline structure opt-in, volume gates, and upgrade API contracts."""

import asyncio
from copy import deepcopy
import inspect
import json
import sqlite3
import threading
import time

import pytest

from novel import runner, service
from novel.agent_pool import get_agent
from novel.billing import NovelBilling
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.store_db import NOVEL_TABLES_DDL, get_db
from rate_limit import limiter


USER='v2-api-author'
HEADERS={'X-Dev-User':USER}


def run(operation):
    return asyncio.run(operation)


@pytest.fixture
def workshop(client,monkeypatch):
    monkeypatch.setenv('FIONA_NOVEL','1')
    monkeypatch.setenv('FIONA_NOVEL_USERS',USER+',other')
    monkeypatch.setattr(limiter,'enabled',False)
    fake=FakeLLM()
    monkeypatch.setattr(runner,'router_factory',lambda store,username,novel_id,run_token:
        LLMRouter(store,dry_run=True,fake=fake))
    return client,fake


def payload(*,structure='v2',automation='per_batch',chapters=3,batch_size=5):
    value={'seed_idea':'普通家庭出身的主角加入宗门，靠修炼和机缘一路变强。',
           'agents':{'editor':'dashscope:qwen3.8-max','writer':'deepseek:deepseek-flash',
                     'archivist':'dashscope:qwen3.8-max','reviewer':'dashscope:qwen3.8-max'},
           'automation':automation,'batch_size':batch_size,
           'target':{'min_chapters':chapters,'max_chapters':chapters,'chapter_words':1000},
           'budget_strawberries':100000}
    if structure is not None:
        value['structure']=structure
    return value


def wait(client,novel_id,state):
    last=None
    for _ in range(1000):
        response=client.get('/novels/'+novel_id,headers=HEADERS)
        assert response.status_code==200,response.text
        last=response.json()
        if last['status']==state:
            return last
        if last['status'] in ('failed','paused') and state not in ('failed','paused'):
            pytest.fail(str(last))
        time.sleep(.01)
    pytest.fail('timeout: '+str(last))


async def snapshot(novel_id):
    async with get_db() as db:
        book=await service.row(db,'SELECT * FROM novels WHERE id=?',(novel_id,))
        versions=await service.rows(db,'SELECT * FROM novel_bible_versions WHERE novel_id=? ORDER BY version',(novel_id,))
        chapters=await service.rows(db,'SELECT * FROM novel_chapters WHERE novel_id=? ORDER BY chapter',(novel_id,))
        steps=await service.rows(db,'SELECT * FROM novel_steps WHERE novel_id=? ORDER BY step_key',(novel_id,))
    return book,versions,chapters,steps


async def set_config(novel_id,**updates):
    async with get_db() as db:
        book=await service.row(db,'SELECT config_json FROM novels WHERE id=?',(novel_id,))
        config=json.loads(book['config_json'])
        config.update(updates)
        await db.execute('UPDATE novels SET config_json=? WHERE id=?',(service.encoded(config),novel_id))
        await db.commit()


async def set_status(novel_id,status):
    async with get_db() as db:
        await db.execute('UPDATE novels SET status=? WHERE id=?',(status,novel_id))
        await db.commit()


def create(client,*,volume_gate=False,**kwargs):
    response=client.post('/novels',json=payload(**kwargs),headers=HEADERS)
    assert response.status_code==201,response.text
    novel_id=response.json()['id']
    wait(client,novel_id,'awaiting_setup')
    if volume_gate:
        run(set_config(novel_id,volume_gate=True))
    return novel_id


def approve_setup(client,novel_id,body=None):
    response=client.post(f'/novels/{novel_id}/setup/approve',json=body or {},headers=HEADERS)
    assert response.status_code==200,response.text
    return response


@pytest.mark.parametrize('structure,expected',[(None,'v1'),('v1','v1'),('v2','v2')])
def test_create_structure_opt_in_and_private_volume_gate(workshop,structure,expected):
    client,_=workshop
    novel_id=create(client,structure=structure)
    book,_,_,_=run(snapshot(novel_id))
    config=json.loads(book['config_json'])
    if expected=='v2':
        assert config['structure']=='v2' and config['volume_gate'] is False
    else:
        assert 'structure' not in config and 'volume_gate' not in config
        legacy=payload(structure=None)
        legacy.update(panel_mode='solo',drama_adaptation=False,
            adaptation={'max_main_characters':6,'max_scenes_per_chapter':3},
            experiment='P1',critique_rounds=1,enable_arc_summaries=True,enable_context_compression=True)
        assert book['config_json']==json.dumps(legacy,ensure_ascii=False,sort_keys=True)
    assert ('genre_contract' in json.loads(book['compass_json']))==(expected=='v2')
    value=payload(); value['volume_gate']=True
    assert client.post('/novels',json=value,headers=HEADERS).status_code==422


def test_missing_structure_stays_v1_without_volume_steps(workshop):
    client,fake=workshop
    novel_id=create(client,structure=None,chapters=1)
    async def remove_key():
        async with get_db() as db:
            book=await service.row(db,'SELECT config_json FROM novels WHERE id=?',(novel_id,))
            config=json.loads(book['config_json']); assert 'structure' not in config
            await db.execute('UPDATE novels SET config_json=? WHERE id=?',(service.encoded(config),novel_id))
            await db.commit()
    run(remove_key())
    approve_setup(client,novel_id)
    result=wait(client,novel_id,'awaiting_end')
    assert result['bible_version']==3
    assert not any('volume' in call['step_key'] for call in fake.calls)
    assert client.get(f'/novels/{novel_id}/volumes',headers=HEADERS).json()==[]


@pytest.mark.parametrize('nested',[False,True])
def test_setup_can_edit_every_contract_field_but_not_unknown_thread(workshop,monkeypatch,nested):
    client,_=workshop
    novel_id=create(client)
    current=wait(client,novel_id,'awaiting_setup')
    contract=deepcopy(current['compass']['genre_contract'])
    contract.update(genre='修仙升级',reader_promise='见证主角靠修炼不断变强',
        core_thread=current['compass']['main_threads'][-1]['id'],
        core_payoffs=['修为突破','越级取胜','宗门排名'],payoff_every_chapters=2,
        progression_ladder=['凡人','练气','筑基'],drift_warnings=['只查案却不修炼'])
    invalid=deepcopy(contract); invalid['core_thread']='T999'
    def body(value):
        return {'compass':{'genre_contract':value}} if nested else {'genre_contract':value}
    bad=client.post(f'/novels/{novel_id}/setup/approve',json=body(invalid),headers=HEADERS)
    assert bad.status_code==422
    assert wait(client,novel_id,'awaiting_setup')['compass']['genre_contract']==current['compass']['genre_contract']
    async def no_background(*args,**kwargs):
        pass
    monkeypatch.setattr(runner,'start_novel',no_background)
    response=approve_setup(client,novel_id,body(contract))
    assert response.json()['compass']['genre_contract']==contract


def test_v1_setup_rejects_contract_edits(workshop):
    client,_=workshop
    novel_id=create(client,structure='v1')
    assert client.post(f'/novels/{novel_id}/setup/approve',json={'genre_contract':{}},headers=HEADERS).status_code==422
    assert client.post(f'/novels/{novel_id}/setup/approve',json={'compass':{'genre_contract':{}}},headers=HEADERS).status_code==422


@pytest.mark.parametrize('automation',['per_batch','per_chapter'])
def test_volume_gate_precedes_chapter_and_pause_resume_does_not_repeat(workshop,automation):
    client,fake=workshop
    novel_id=create(client,volume_gate=True,automation=automation)
    approve_setup(client,novel_id)
    result=wait(client,novel_id,'awaiting_volume')
    assert result['chapters_done']==0 and result['bible_version']==3
    book,versions,chapters,_=run(snapshot(novel_id))
    assert versions[-1]['source']=='volume:1' and chapters==[]
    plans=client.get(f'/novels/{novel_id}/volumes',headers=HEADERS).json()
    assert len(plans)==1 and all(item['status']=='open' for item in plans[0]['milestones'])
    count=len(fake.calls)
    assert client.post(f'/novels/{novel_id}/pause',headers=HEADERS).status_code==200
    wait(client,novel_id,'paused')
    assert client.post(f'/novels/{novel_id}/resume',headers=HEADERS).status_code==200
    restored=wait(client,novel_id,'awaiting_volume')
    assert restored['bible_version']==3 and len(fake.calls)==count
    assert client.post(f'/novels/{novel_id}/volume/approve',json={},headers=HEADERS).status_code==200
    wait(client,novel_id,'awaiting_plan' if automation=='per_chapter' else 'awaiting_end')
    assert sum(call['task']=='volume_plan' for call in fake.calls)==1


def test_volume_approval_validates_edits_and_resets_archive_owned_status(workshop,monkeypatch):
    client,_=workshop
    novel_id=create(client,volume_gate=True)
    approve_setup(client,novel_id); wait(client,novel_id,'awaiting_volume')
    plans=client.get(f'/novels/{novel_id}/volumes',headers=HEADERS).json()
    plan=deepcopy(plans[0]); plan['chapters']=[1,999]
    assert client.post(f'/novels/{novel_id}/volume/approve',json={'volume_plan':plan},headers=HEADERS).status_code==422
    assert client.get(f'/novels/{novel_id}/volumes',headers=HEADERS).json()==plans
    async def no_background(*args,**kwargs):
        pass
    monkeypatch.setattr(runner,'start_novel',no_background)
    plan=deepcopy(plans[0]); plan['goal']='作者修订的阶段目标'
    for milestone in plan['milestones']:
        milestone['status']='done'
    response=client.post(f'/novels/{novel_id}/volume/approve',json={'volume_plan':plan},headers=HEADERS)
    assert response.status_code==200,response.text
    book,versions,chapters,_=run(snapshot(novel_id))
    assert book['status']=='running' and chapters==[]
    assert json.loads(book['config_json'])['_volume_gate']['approved'] is True
    assert versions[-1]['source']=='user_edit' and book['bible_version']==4
    edited=client.get(f'/novels/{novel_id}/volumes',headers=HEADERS).json()[0]
    assert edited['goal']==plan['goal'] and all(item['status']=='open' for item in edited['milestones'])


def test_volume_redo_replans_and_uses_fresh_persistent_counter(workshop):
    client,fake=workshop
    novel_id=create(client,volume_gate=True)
    approve_setup(client,novel_id); wait(client,novel_id,'awaiting_volume')
    for count in (1,2):
        response=client.post(f'/novels/{novel_id}/volume/redo',json={'text':f'第{count}次加强修炼线'},headers=HEADERS)
        assert response.status_code==200,response.text
        result=wait(client,novel_id,'awaiting_volume')
        assert result['bible_version']==3+count
        config=json.loads(run(snapshot(novel_id))[0]['config_json'])
        assert '_volume_redo' not in config and config['_volume_redo_counts']['1']==count
    redos=[call for call in fake.calls if 'redo' in call['step_key'] and '/vol01/' in call['step_key']]
    assert len(redos)>=2 and len({call['step_key'] for call in redos})==len(redos)


def test_full_auto_never_waits_at_volume_even_when_gate_is_enabled(workshop):
    client,_=workshop
    novel_id=create(client,volume_gate=True,automation='full_auto')
    approve_setup(client,novel_id)
    assert wait(client,novel_id,'awaiting_end')['chapters_done']==3


def test_switching_paused_volume_to_full_auto_does_not_restore_manual_gate(workshop):
    client,_=workshop
    novel_id=create(client,volume_gate=True)
    approve_setup(client,novel_id); wait(client,novel_id,'awaiting_volume')
    assert client.post(f'/novels/{novel_id}/pause',headers=HEADERS).status_code==200
    assert client.patch(f'/novels/{novel_id}',json={'automation':'full_auto'},headers=HEADERS).status_code==200
    assert client.post(f'/novels/{novel_id}/resume',headers=HEADERS).status_code==200
    assert wait(client,novel_id,'awaiting_end')['chapters_done']==3


def reviewed_book(client,*,status='awaiting_review'):
    novel_id=create(client,structure='v1',batch_size=1)
    approve_setup(client,novel_id)
    wait(client,novel_id,'awaiting_review')
    if status!='awaiting_review':
        run(set_status(novel_id,status))
    return novel_id


@pytest.mark.parametrize('status',['awaiting_review','paused'])
def test_upgrade_only_updates_compass_config_and_next_chapter_starts_with_volume(workshop,status):
    client,fake=workshop
    novel_id=reviewed_book(client,status=status)
    before=run(snapshot(novel_id)); calls=len(fake.calls)
    response=client.post(f'/novels/{novel_id}/upgrade-structure',headers=HEADERS)
    assert response.status_code==200,response.text
    after=run(snapshot(novel_id)); config=json.loads(after[0]['config_json'])
    assert after[0]['status']==status and after[0]['run_token'] is None
    assert config['structure']=='v2' and config['volume_gate'] is False
    assert config['_volume_upgrade']=={'volume':2,'start_chapter':2,'end_chapter':3}
    assert after[1]==before[1] and after[2]==before[2]
    old_compass=json.loads(before[0]['compass_json']); new_compass=json.loads(after[0]['compass_json'])
    assert {key:value for key,value in new_compass.items() if key!='genre_contract'}==old_compass
    assert len(fake.calls)==calls+1 and fake.calls[-1]['task']=='genre_contract'
    upgrade_payload=FakeLLM.payload(fake.calls[-1])
    assert upgrade_payload['seed_idea']==before[0]['seed_idea']
    assert upgrade_payload['chapter_summaries']==json.loads(before[1][-1]['bible_json'])['dynamic']['chapter_summaries']
    assert client.post(f'/novels/{novel_id}/upgrade-structure',headers=HEADERS).status_code==409
    next_action='resume' if status=='paused' else 'continue'
    assert client.post(f'/novels/{novel_id}/{next_action}',headers=HEADERS).status_code==200
    wait(client,novel_id,'awaiting_review')
    assert fake.calls[calls+1]['task']=='volume_plan'
    assert client.get(f'/novels/{novel_id}/volumes',headers=HEADERS).json()[0]['chapters']==[2,3]


@pytest.mark.parametrize('status',['setup_running','running','awaiting_setup','awaiting_plan','awaiting_volume','awaiting_end','completed','failed'])
def test_upgrade_rejects_other_states_without_model_call(workshop,status):
    client,fake=workshop
    novel_id=create(client,structure='v1')
    run(set_status(novel_id,status))
    before=run(snapshot(novel_id)); calls=len(fake.calls)
    assert client.post(f'/novels/{novel_id}/upgrade-structure',headers=HEADERS).status_code==409
    assert len(fake.calls)==calls and run(snapshot(novel_id))==before


def test_volume_and_upgrade_endpoints_are_owner_scoped(workshop):
    client,_=workshop
    novel_id=create(client)
    for method,path,body in [('GET','volumes',None),('POST','volume/approve',{}),
        ('POST','volume/redo',{'text':'重做'}),('POST','upgrade-structure',None)]:
        response=client.request(method,f'/novels/{novel_id}/{path}',headers={'X-Dev-User':'other'},
                                **({'json':body} if body is not None else {}))
        assert response.status_code==404,response.text


def test_upgrade_reuses_edit_guard_and_failed_model_leaves_book_unchanged(workshop):
    client,fake=workshop
    novel_id=reviewed_book(client)
    before=run(snapshot(novel_id))
    runner._editing.add(novel_id)
    try:
        response=client.post(f'/novels/{novel_id}/upgrade-structure',headers=HEADERS)
        assert response.status_code==409 and '改稿' in response.json()['detail']
    finally:
        runner._editing.discard(novel_id)
    assert run(snapshot(novel_id))==before
    fake.script=lambda request,_index: {} if request['task']=='genre_contract' else None
    response=client.post(f'/novels/{novel_id}/upgrade-structure',headers=HEADERS)
    assert response.status_code==422,response.text
    after=run(snapshot(novel_id))
    assert after[0]['config_json']==before[0]['config_json'] and after[0]['compass_json']==before[0]['compass_json']
    assert after[0]['run_token'] is None and after[0]['reserved_strawberries']==0
    assert after[1:3]==before[1:3]


@pytest.mark.parametrize('status',['awaiting_review','paused'])
def test_upgrade_blocks_resume_while_contract_is_in_flight(workshop,status):
    client,fake=workshop
    novel_id=reviewed_book(client,status=status)
    entered=threading.Event(); release=threading.Event()
    async def blocked(request,_index):
        if request['task']=='genre_contract':
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.005)
    fake.script=blocked
    result=[]
    def upgrade():
        result.append(client.post(f'/novels/{novel_id}/upgrade-structure',headers=HEADERS))
    thread=threading.Thread(target=upgrade)
    thread.start()
    try:
        assert entered.wait(5)
        action='resume' if status=='paused' else 'continue'
        response=client.post(f'/novels/{novel_id}/{action}',headers=HEADERS)
        assert response.status_code==409 and '改稿' in response.json()['detail']
        lease=run(snapshot(novel_id))[0]['run_token']
        assert lease and novel_id in service._upgrading
        paused=client.post(f'/novels/{novel_id}/pause',headers=HEADERS)
        assert paused.status_code==409 and paused.json()['detail']=='正在升级结构，请稍后再试'
        current=run(snapshot(novel_id))[0]
        assert current['run_token']==lease and current['status']==status
    finally:
        release.set(); thread.join(10)
    assert not thread.is_alive() and result[0].status_code==200
    assert novel_id not in service._upgrading


@pytest.mark.parametrize('done,end',[(7,10),(8,20),(9,20)])
def test_upgrade_merges_less_than_three_chapters_into_following_boundary(workshop,done,end):
    client,_=workshop
    novel_id=create(client,structure='v1',chapters=25,batch_size=done)
    approve_setup(client,novel_id)
    assert wait(client,novel_id,'awaiting_review')['chapters_done']==done
    before=run(snapshot(novel_id))
    response=client.post(f'/novels/{novel_id}/upgrade-structure',headers=HEADERS)
    assert response.status_code==200,response.text
    config=json.loads(run(snapshot(novel_id))[0]['config_json'])
    assert config['_volume_upgrade']=={'volume':2,'start_chapter':done+1,'end_chapter':end}
    assert run(snapshot(novel_id))[1:3]==before[1:3]


@pytest.mark.parametrize('chapters,extend',[(3,1),(9,4)])
def test_extension_expands_last_volume_preserves_statuses_and_adds_payoffs(workshop,monkeypatch,chapters,extend):
    client,fake=workshop
    novel_id=create(client,chapters=chapters,automation='full_auto')
    approve_setup(client,novel_id); wait(client,novel_id,'awaiting_end')
    async def mark_milestones():
        async with get_db() as db:
            book=await service.row(db,'SELECT * FROM novels WHERE id=?',(novel_id,))
            current=await service._latest_bible(db,book)
            milestones=current['dynamic']['volumes'][-1]['milestones']
            milestones[0]['status']='done'; milestones[1]['status']='missed'
            await db.execute('UPDATE novel_bible_versions SET bible_json=? WHERE novel_id=? AND version=?',
                (service.encoded(current),novel_id,book['bible_version']))
            await db.commit()
    run(mark_milestones())
    before=run(snapshot(novel_id)); old=json.loads(before[1][-1]['bible_json'])
    calls=len(fake.calls)
    async def no_background(*args,**kwargs):
        pass
    monkeypatch.setattr(runner,'start_novel',no_background)
    response=client.post(f'/novels/{novel_id}/end/reject',json={'extend_chapters':extend},headers=HEADERS)
    assert response.status_code==200,response.text
    after=run(snapshot(novel_id)); current=json.loads(after[1][-1]['bible_json'])
    assert len(current['dynamic']['volumes'])==1
    plan=current['dynamic']['volumes'][0]; previous=old['dynamic']['volumes'][0]
    assert plan['chapters']==[1,chapters+extend]
    assert plan['milestones']==previous['milestones']
    assert plan['payoff_plan'][:len(previous['payoff_plan'])]==previous['payoff_plan']
    period=response.json()['compass']['genre_contract']['payoff_every_chapters']
    assert len(plan['payoff_plan'])>len(previous['payoff_plan'])
    assert len(plan['payoff_plan'])>=(chapters+extend+period-1)//period
    assert all(1<=payoff['chapter_hint']<=chapters+extend for payoff in plan['payoff_plan'])
    assert after[1][-1]['source']=='volume_extend:1'
    assert after[0]['bible_version']==before[0]['bible_version']+1
    assert after[1][:-1]==before[1] and after[2]==before[2] and len(fake.calls)==calls
    assert json.loads(after[0]['config_json'])['_volume_gate']['end_chapter']==chapters+extend


@pytest.mark.parametrize('write_next_chapter',[False,True])
def test_interrupted_upgrade_reuses_identical_input_but_refreshes_changed_content(workshop,monkeypatch,write_next_chapter):
    from fastapi import HTTPException
    client,fake=workshop
    novel_id=reviewed_book(client)
    original=service.owned
    calls=0
    async def interrupted(db,username,novel_id,states=()):
        nonlocal calls
        book=await original(db,username,novel_id,states)
        if states==('awaiting_review','paused'):
            calls+=1
            if calls==3:
                raise HTTPException(409,'模拟主编完成后发布中断')
        return book
    monkeypatch.setattr(service,'owned',interrupted)
    assert client.post(f'/novels/{novel_id}/upgrade-structure',headers=HEADERS).status_code==409
    assert len([call for call in fake.calls if call['task']=='genre_contract'])==1
    assert 'structure' not in json.loads(run(snapshot(novel_id))[0]['config_json'])
    monkeypatch.setattr(service,'owned',original)
    if write_next_chapter:
        assert client.post(f'/novels/{novel_id}/continue',headers=HEADERS).status_code==200
        assert wait(client,novel_id,'awaiting_review')['chapters_done']==2
    response=client.post(f'/novels/{novel_id}/upgrade-structure',headers=HEADERS)
    assert response.status_code==200,response.text
    contracts=[call for call in fake.calls if call['task']=='genre_contract']
    assert len(contracts)==(2 if write_next_chapter else 1)
    if write_next_chapter:
        assert contracts[0]['step_key']!=contracts[1]['step_key']


@pytest.mark.parametrize('failure',[False,True])
def test_upgrade_offline_paid_route_settles_and_refunds_atomically(workshop,monkeypatch,failure):
    client,fake=workshop
    novel_id=reviewed_book(client)
    monkeypatch.setenv('DEV_MODE','0')
    calls=[]
    def factory(store,username,novel_id,token):
        router=LLMRouter(store,billing=NovelBilling(username,novel_id,token))
        router.retry_delay=0
        async def provider(request):
            calls.append(request)
            if failure:
                raise RuntimeError('offline provider failure')
            return fake.default_response(request),{'input_tokens':100,'output_tokens':100,'cached_tokens':0}
        monkeypatch.setattr(router,'_single_real_call',provider)
        return router
    monkeypatch.setattr(runner,'router_factory',factory)
    async def scenario():
        async with get_db() as db:
            await db.execute('UPDATE users SET strawberry_balance=10000 WHERE username=?',(USER,))
            await db.commit()
        if failure:
            from fastapi import HTTPException
            with pytest.raises(HTTPException):
                await service.upgrade_structure(USER,novel_id)
        else:
            await service.upgrade_structure(USER,novel_id)
        book,_,_,steps=await snapshot(novel_id)
        async with get_db() as db:
            user=await service.row(db,'SELECT strawberry_balance FROM users WHERE username=?',(USER,))
        assert calls and book['reserved_strawberries']==0 and book['run_token'] is None
        assert book['spent_strawberries']==sum(step['strawberries_charged'] for step in steps)
        assert user['strawberry_balance']==10000-book['spent_strawberries']
        config=json.loads(book['config_json'])
        if failure:
            assert 'structure' not in config and 'volume_gate' not in config
        else:
            assert config['structure']=='v2' and config['volume_gate'] is False
        assert book['spent_strawberries']==(0 if failure else 1)
    run(scenario())


def test_cancelled_upgrade_refunds_lease_and_preserves_existing_content(workshop,monkeypatch):
    client,_=workshop
    novel_id=reviewed_book(client)
    before=run(snapshot(novel_id))
    monkeypatch.setenv('DEV_MODE','0')
    async def scenario():
        entered=asyncio.Event()
        async with get_db() as db:
            await db.execute('UPDATE users SET strawberry_balance=10000 WHERE username=?',(USER,))
            await db.commit()
        def factory(store,username,novel_id,token):
            router=LLMRouter(store,billing=NovelBilling(username,novel_id,token))
            async def provider(request):
                entered.set()
                await asyncio.Event().wait()
            monkeypatch.setattr(router,'_single_real_call',provider)
            return router
        monkeypatch.setattr(runner,'router_factory',factory)
        task=asyncio.create_task(service.upgrade_structure(USER,novel_id))
        await asyncio.wait_for(entered.wait(),5)
        assert (await snapshot(novel_id))[0]['reserved_strawberries']>0
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        after=await snapshot(novel_id)
        assert after[0]['config_json']==before[0]['config_json']
        assert after[0]['compass_json']==before[0]['compass_json']
        assert after[0]['run_token'] is None and after[0]['reserved_strawberries']==0
        assert after[0]['spent_strawberries']==0 and after[1:3]==before[1:3]
        assert not runner.is_editing(novel_id)
        assert novel_id not in service._upgrading
        async with get_db() as db:
            user=await service.row(db,'SELECT strawberry_balance FROM users WHERE username=?',(USER,))
        assert user['strawberry_balance']==10000
    run(scenario())


def test_v2_execution_and_advisor_cards_require_visible_confirmed_payoffs():
    writer=get_agent('writer',task='write',structure='v2',experiment='P1')['system_prompt']
    assert all(text in writer for text in ('context.genre_payoff','context.milestones_advanced','beat_index','可见的兑现场面'))
    reviewer=get_agent('reviewer',task='review',structure='v2',experiment='P1')['system_prompt']
    assert all(text in reviewer for text in ('payload.genre_payoff','整条节拍缺失','beat_sheet','blocking=true','previous_issue_index','截断的改动全集'))
    archive=get_agent('archivist',task='archive',structure='v2',experiment='P1')['system_prompt']
    assert all(text in archive for text in ('genre_payoff 非 null','payoff_delivered: true|false','如实填 false'))
    for task in ('decision','plan','finalize'):
        editor=get_agent('editor',task=task,structure='v2',experiment='P1')['system_prompt']
        assert '章末钩子不得引入新的未解谜团' in editor
    for role in service.ADVISORS:
        card=get_agent(role,task='critique_plan',structure='v2',experiment='P1')['system_prompt']
        assert all(text in card for text in ('genre_payoff 与 milestones_advanced','爽点保护规则','不能建议删除'))
        v1=get_agent(role,task='critique_plan',structure='v1',experiment='P1')['system_prompt']
        assert 'genre_payoff 与 milestones_advanced' not in v1
    for role,task in [('writer','write'),('reviewer','review'),('archivist','archive')]:
        v1=get_agent(role,task=task,structure='v1',experiment='P1')['system_prompt']
        assert 'payoff_delivered' not in v1 and '可见的兑现场面' not in v1
    p0=get_agent('reviewer',task='review',experiment='A')['system_prompt']
    assert 'previous_issue_index' not in p0


def test_protected_service_signatures_and_chapter_columns_are_unchanged():
    expected={'list_books':['username'],'detail':['username','novel_id'],
              'bible':['username','novel_id'],'chapter':['username','novel_id','number'],
              'owned':['db','username','novel_id','states']}
    for name,parameters in expected.items():
        assert list(inspect.signature(getattr(service,name)).parameters)==parameters
    ddl=next(item for item in NOVEL_TABLES_DDL if 'CREATE TABLE IF NOT EXISTS novel_chapters' in item)
    with sqlite3.connect(':memory:') as db:
        db.execute(ddl)
        columns=[item[1] for item in db.execute('PRAGMA table_info(novel_chapters)')]
    assert columns==['novel_id','username','chapter','status','title','body','flags_json',
                     'meeting_json','review_json','archive_json','ending_status',
                     'edited_by_user','created_at','updated_at']
