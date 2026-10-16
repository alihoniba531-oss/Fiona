"""Offline HTTP workflow checks using the existing isolated client fixture."""
import asyncio
import json
import time

import pytest

from novel import runner
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from rate_limit import limiter

USER='novel_author'
HEADERS={'X-Dev-User':USER}


def payload(chapters=3,mode='critique',automation='per_batch',batch=5):
    agents={'editor':'dashscope:qwen3.8-max','writer':'deepseek:deepseek-flash','archivist':'dashscope:qwen3.8-max','reviewer':'dashscope:qwen3.8-max'}
    if mode=='critique': agents['twist_designer']='ark:doubao-seed-2-1-pro-260915'
    return {'seed_idea':'一本关于失落档案的悬疑小说','agents':agents,'panel_mode':mode,'automation':automation,'batch_size':batch,'target':{'min_chapters':chapters,'max_chapters':chapters,'chapter_words':1000},'budget_strawberries':100000}


@pytest.fixture
def workshop(client,monkeypatch):
    monkeypatch.setenv('FIONA_NOVEL','1'); monkeypatch.setenv('FIONA_NOVEL_USERS',USER+',other')
    monkeypatch.setattr(limiter,'enabled',False)
    fake=FakeLLM()
    monkeypatch.setattr(runner,'router_factory',lambda store,username,novel_id,run_token: LLMRouter(store,dry_run=True,fake=fake))
    return client,fake


def wait(client,book,state,headers=HEADERS):
    for _ in range(600):
        response=client.get('/novels/'+book,headers=headers)
        assert response.status_code==200,response.text
        data=response.json()
        if data['status']==state: return data
        if data['status'] in ('failed','paused') and state not in ('failed','paused'):
            pytest.fail(str(data))
        time.sleep(.01)
    pytest.fail('timeout: '+str(data))


def create(client,**kwargs):
    response=client.post('/novels',json=payload(**kwargs),headers=HEADERS)
    assert response.status_code==201,response.text
    book=response.json()['id']; data=wait(client,book,'awaiting_setup')
    assert data['bible_version']==1 and data['chapters_done']==0
    return book


def approve(client,book):
    response=client.post(f'/novels/{book}/setup/approve',json={},headers=HEADERS)
    assert response.status_code==200,response.text


@pytest.mark.parametrize('mode',['critique','solo'])
def test_complete_batch_and_end(workshop,mode):
    client,fake=workshop; book=create(client,chapters=7,mode=mode)
    approve(client,book)
    data=wait(client,book,'awaiting_review')
    assert data['chapters_done']==5 and data['bible_version']==7
    meeting=client.get(f'/novels/{book}/chapters/1',headers=HEADERS).json()['meeting']
    if mode=='critique':
        assert meeting['plan'] and meeting['critiques'] and meeting['objections']
        assert any(item['id'].startswith('A') for item in meeting['objections'])
        assert meeting['decision']['objection_responses']
    assert client.post(f'/novels/{book}/continue',headers=HEADERS).status_code==200
    data=wait(client,book,'awaiting_end'); assert data['chapters_done']==7 and data['bible_version']==9
    assert client.post(f'/novels/{book}/end/confirm',headers=HEADERS).status_code==200
    assert wait(client,book,'completed')['completed_at']
    export=client.get(f'/novels/{book}/export',headers=HEADERS)
    assert export.status_code==200 and 'attachment' in export.headers['content-disposition'] and '# 第7章' in export.text
    assert client.get('/novels',headers=HEADERS).json()[0]['id']==book


def test_three_chapter_fake_e2e_and_per_chapter_gates(workshop):
    client,fake=workshop; book=create(client,automation='per_chapter')
    approve(client,book)
    data=wait(client,book,'awaiting_plan'); assert data['chapters_done']==0 and data['bible_version']==2
    assert client.post(f'/novels/{book}/plan/approve',json={'beat_sheet':{}},headers=HEADERS).status_code==422
    before=len(fake.calls)
    assert client.post(f'/novels/{book}/plan/redo',json={'text':'请加强因果'},headers=HEADERS).status_code==200
    wait(client,book,'awaiting_plan')
    assert len(fake.calls)==before+1
    chapter=client.get(f'/novels/{book}/chapters/1',headers=HEADERS).json()
    beat=chapter['meeting']['decision']['beat_sheet']; beat['title']='作者修改的标题'
    assert client.post(f'/novels/{book}/plan/approve',json={'beat_sheet':beat},headers=HEADERS).status_code==200
    wait(client,book,'awaiting_plan')
    assert client.post(f'/novels/{book}/plan/approve',json={},headers=HEADERS).status_code==200
    wait(client,book,'awaiting_plan')
    assert client.post(f'/novels/{book}/plan/approve',json={},headers=HEADERS).status_code==200
    data=wait(client,book,'awaiting_end'); assert data['chapters_done']==3 and data['bible_version']==5
    assert client.get(f'/novels/{book}/chapters/1',headers=HEADERS).json()['title']=='作者修改的标题'


def test_gate_whitelist_inputs_catalog_and_health(workshop,monkeypatch):
    client,_=workshop
    monkeypatch.setenv('FIONA_NOVEL','0'); assert client.get('/novels',headers=HEADERS).status_code==404
    monkeypatch.setenv('FIONA_NOVEL','true'); assert client.get('/novels',headers=HEADERS).status_code==404
    monkeypatch.setenv('FIONA_NOVEL','1'); monkeypatch.setenv('FIONA_NOVEL_USERS',''); assert client.get('/novels',headers=HEADERS).status_code==403
    monkeypatch.setenv('FIONA_NOVEL_USERS','other'); assert client.get('/novels',headers=HEADERS).status_code==403
    monkeypatch.setenv('FIONA_NOVEL_USERS',USER)
    cat=client.get('/novels/catalog',headers=HEADERS).json()
    assert len(cat['models'])==3 and 'system_prompt' not in json.dumps(cat)
    assert '自带 Claude' in cat['notice']
    for change in ({'agents':{'writer':'deepseek:deepseek-flash'}},{'agents':{'editor':'anthropic:claude-sonnet-5-5','writer':'deepseek:deepseek-flash','archivist':'dashscope:qwen3.8-max'}},{'budget_strawberries':1},{'panel_mode':'merge'},{'seed_idea':'x'*2001},{'batch_size':11}):
        value=payload(); value.update(change)
        assert client.post('/novels',json=value,headers=HEADERS).status_code==422
    estimate=client.post('/novels/estimate',json=payload(),headers=HEADERS)
    assert estimate.status_code==200 and estimate.json()['per_chapter']['min']>0
    assert client.get('/health').status_code==200


def test_notes_pause_resume_rearchive_early_edit_and_delete(workshop):
    client,fake=workshop; book=create(client,chapters=4,automation='per_chapter')
    for i in range(5): assert client.post(f'/novels/{book}/notes',json={'text':f'留言{i}'},headers=HEADERS).status_code==200
    assert client.post(f'/novels/{book}/notes',json={'text':'第六条'},headers=HEADERS).status_code==409
    approve(client,book); wait(client,book,'awaiting_plan')
    assert client.post(f'/novels/{book}/plan/approve',json={},headers=HEADERS).status_code==200
    data=wait(client,book,'awaiting_plan'); assert data['pending_notes']==0
    assert client.post(f'/novels/{book}/pause',headers=HEADERS).status_code==200
    assert wait(client,book,'paused')['pause_reason']=='user'
    assert client.post(f'/novels/{book}/resume',headers=HEADERS).status_code==200
    wait(client,book,'awaiting_plan')
    assert client.patch(f'/novels/{book}',json={'automation':'per_batch','batch_size':1},headers=HEADERS).status_code==200
    assert client.post(f'/novels/{book}/plan/approve',json={},headers=HEADERS).status_code==200
    data=wait(client,book,'awaiting_review'); assert data['chapters_done']==2
    version=data['bible_version']; calls=len(fake.calls)
    result=client.put(f'/novels/{book}/chapters/2',json={'body':'# 第2章 改稿\n\n作者修改正文。'},headers=HEADERS)
    assert result.status_code==200 and result.json()['rearchiving']
    data=wait(client,book,'awaiting_review'); assert data['bible_version']==version+1 and len(fake.calls)==calls+1
    calls=len(fake.calls)
    result=client.put(f'/novels/{book}/chapters/1',json={'body':'作者重写第一章'},headers=HEADERS)
    assert result.status_code==200 and not result.json()['rearchiving']
    assert client.get(f'/novels/{book}/chapters/2',headers=HEADERS).json()['status']=='stale'
    assert len(fake.calls)==calls
    from novel.writing import compact_length
    data=client.get('/novels/'+book,headers=HEADERS).json()
    assert data['words_done']==compact_length('作者重写第一章')+compact_length('# 第2章 改稿\n\n作者修改正文。')
    assert sum(ch['words'] for ch in data['chapters'])==data['words_done']
    assert client.delete(f'/novels/{book}',headers=HEADERS).status_code==200
    assert client.get(f'/novels/{book}',headers=HEADERS).status_code==404
    from novel.store_db import get_db
    async def check():
        async with get_db() as db:
            for table in ('novels','novel_steps','novel_notes','novel_chapters','novel_bible_versions'):
                cursor=await db.execute(f'SELECT COUNT(*) FROM {table} WHERE '+('id' if table=='novels' else 'novel_id')+'=?',(book,))
                assert (await cursor.fetchone())[0]==0
    asyncio.run(check())


def test_end_reject_and_all_cross_user_endpoints(workshop):
    client,fake=workshop; book=create(client,chapters=1,mode='solo'); approve(client,book); wait(client,book,'awaiting_end')
    assert client.post(f'/novels/{book}/end/reject',json={},headers=HEADERS).status_code==422
    calls=len(fake.calls)
    other={'X-Dev-User':'other'}
    operations=[('GET','',None),('GET','/chapters/1',None),('GET','/export',None),('POST','/setup/approve',{}),('POST','/plan/approve',{}),('POST','/plan/redo',{'text':'重定稿'}),('POST','/continue',None),('POST','/pause',None),('POST','/resume',None),('PATCH','',{'budget_strawberries':200000}),('POST','/notes',{'text':'留言'}),('PUT','/chapters/1',{'body':'改稿'}),('POST','/end/confirm',None),('POST','/end/reject',{'extend_chapters':1}),('DELETE','',None)]
    for method,path,body in operations:
        response=client.request(method,'/novels/'+book+path,headers=other,**({'json':body} if body is not None else {}))
        assert response.status_code==404,(method,path,response.text)
    assert len(fake.calls)==calls
    assert client.post(f'/novels/{book}/end/reject',json={'extend_chapters':2,'text':'让故事继续'},headers=HEADERS).status_code==200
    data=wait(client,book,'awaiting_end'); assert data['chapters_done']==3
    assert client.post(f'/novels/{book}/continue',headers=HEADERS).status_code==409


def test_daily_cap_and_unresolved_review(workshop,monkeypatch):
    client,fake=workshop
    monkeypatch.setattr('novel.runner.check_daily_cap',lambda *args: object())
    book=create(client,chapters=3); approve(client,book)
    data=wait(client,book,'paused')
    assert data['pause_reason']=='daily_cap' and data['chapters_done']==1


@pytest.mark.parametrize('locked',[{'characters':[None]},{'characters':[1]},{'characters':1},{'world_rules':None},{'style_guide':[]}])
def test_malformed_setup_edits_are_422(workshop,locked):
    client,_=workshop; book=create(client)
    response=client.post(f'/novels/{book}/setup/approve',json={'locked':locked},headers=HEADERS)
    assert response.status_code==422,response.text
    assert wait(client,book,'awaiting_setup')['bible_version']==1


def test_setup_edit_fields_are_restricted_and_validated(workshop):
    from copy import deepcopy
    client,fake=workshop; book=create(client)
    # Pause may race the final setup commit: the persisted bible exists, but
    # the user has never approved it. Resume must keep the mandatory gate.
    from novel.store_db import get_db
    async def pause_after_setup_commit():
        async with get_db() as db:
            await db.execute("UPDATE novels SET status='paused',pause_reason='user' WHERE id=?",(book,))
            await db.commit()
    asyncio.run(pause_after_setup_commit())
    calls=len(fake.calls)
    assert client.post(f'/novels/{book}/resume',headers=HEADERS).status_code==200
    original=wait(client,book,'awaiting_setup')
    assert original['bible_version']==1 and len(fake.calls)==calls
    characters=deepcopy(original['bible']['locked']['characters']); characters[0]['name']='改名'
    assert client.post(f'/novels/{book}/setup/approve',json={'locked':{'characters':characters}},headers=HEADERS).status_code==422
    characters[0]['name']=original['bible']['locked']['characters'][0]['name']
    characters[0]['motivation']='找到档案的来源'
    response=client.post(f'/novels/{book}/setup/approve',json={'compass':{'title':'作者的书名'},'locked':{'characters':characters}},headers=HEADERS)
    assert response.status_code==200,response.text
    data=wait(client,book,'awaiting_end'); assert data['title']=='作者的书名'
    assert data['bible']['locked']['characters'][0]['motivation']=='找到档案的来源'


@pytest.mark.parametrize('provider,model',[('custom','qwen3.8-max'),('moonshot','kimi'),('zhipu','glm'),('dashscope','unknown-model')])
def test_unsupported_byok_create_is_rejected(workshop,monkeypatch,provider,model):
    client,_=workshop
    async def public(username): return {'provider':provider,'model':model,'enabled':True,'status':'ok'}
    monkeypatch.setattr('byok.store.get_public_config',public)
    value=payload(); value['agents']['editor']='byok:self'
    response=client.post('/novels',json=value,headers=HEADERS)
    assert response.status_code==422,response.text
    assert any('\u4e00'<=letter<='\u9fff' for letter in response.json()['detail'])


def test_byok_key_and_story_are_absent_from_db_logs_and_responses(workshop,monkeypatch,capsys,caplog):
    import openai
    from novel.billing import NovelBilling
    from novel.byok_bridge import ByokBridge
    from novel.store_db import get_db
    client,fake=workshop
    sentinel='NOVEL-BYOK-KEY-SENTINEL-DO-NOT-PERSIST'
    async def public(username): return {'provider':'dashscope','model':'qwen3.8-max','enabled':True,'status':'ok'}
    async def internal(username): return {**await public(username),'api_key':sentinel}
    monkeypatch.setattr('byok.store.get_public_config',public); monkeypatch.setattr('byok.store.get_internal_config',internal)
    class OfflineClient:
        def __init__(self,**kwargs): assert kwargs['api_key']==sentinel
        async def close(self): pass
    monkeypatch.setattr(openai,'AsyncOpenAI',OfflineClient)
    def factory(store,username,novel_id,run_token):
        router=LLMRouter(store,fake=fake,billing=NovelBilling(username,novel_id,run_token),byok_bridge=ByokBridge(username))
        async def provider_call(client,provider,name,request):
            return fake.default_response(request),{'input_tokens':123,'output_tokens':50,'cached_tokens':12},'stop'
        router._provider_call=provider_call
        return router
    monkeypatch.setattr(runner,'router_factory',factory)
    value=payload(chapters=1,mode='solo'); value['seed_idea']='PRIVATE-SEED-SENTINEL'
    value['agents']={role:'byok:self' for role in value['agents']}
    response=client.post('/novels',json=value,headers=HEADERS); assert response.status_code==201,response.text
    book=response.json()['id']; wait(client,book,'awaiting_setup'); approve(client,book); result=wait(client,book,'awaiting_end')
    chapter=client.get(f'/novels/{book}/chapters/1',headers=HEADERS)
    assert sentinel not in json.dumps(result)+chapter.text+client.get('/novels/catalog',headers=HEADERS).text
    async def check():
        async with get_db() as db:
            for table in ('novels','novel_steps','novel_notes','novel_chapters','novel_bible_versions'):
                cursor=await db.execute(f'SELECT * FROM {table}')
                assert sentinel not in json.dumps([dict(row) for row in await cursor.fetchall()])
    asyncio.run(check())
    streams=capsys.readouterr()
    captured=streams.out+streams.err+caplog.text
    assert sentinel not in captured and value['seed_idea'] not in captured
    assert chapter.json()['body'] not in captured


@pytest.mark.parametrize('config,message',[
    (None,'请先启用可用的自带模型'),
    ({'provider':'moonshot','model':'kimi','enabled':True},'小说工坊仅支持自带 Anthropic、千问或 DeepSeek'),
    ({'provider':'dashscope','model':'unknown-model','enabled':True},'该模型暂不支持用于小说工坊'),
])
def test_byok_create_preserves_the_specific_unavailability_reason(workshop,monkeypatch,config,message):
    client,_=workshop
    async def public(username): return config
    monkeypatch.setattr('byok.store.get_public_config',public)
    value=payload(); value['agents']['editor']='byok:self'
    response=client.post('/novels',json=value,headers=HEADERS)
    assert response.status_code==422 and response.json()['detail']==message
    assert client.get('/novels/catalog',headers=HEADERS).status_code==200


@pytest.mark.parametrize('action',['approve','redo'])
def test_early_edit_keeps_pending_plan_usable_and_missing_plan_is_409(workshop,action):
    from novel.store_db import get_db
    client,_=workshop
    book=create(client,chapters=4,automation='per_chapter',mode='solo')
    approve(client,book); wait(client,book,'awaiting_plan')
    for _ in range(2):
        assert client.post(f'/novels/{book}/plan/approve',json={},headers=HEADERS).status_code==200
        wait(client,book,'awaiting_plan')
    response=client.put(f'/novels/{book}/chapters/1',json={'body':'作者修改第一章。'},headers=HEADERS)
    assert response.status_code==200 and not response.json()['rearchiving']
    assert client.get(f'/novels/{book}/chapters/2',headers=HEADERS).json()['status']=='stale'
    assert client.get(f'/novels/{book}/chapters/3',headers=HEADERS).json()['status']=='awaiting_plan_approval'
    body={} if action=='approve' else {'text':'重做待批细纲'}
    response=client.post(f'/novels/{book}/plan/{action}',json=body,headers=HEADERS)
    assert response.status_code==200,response.text
    wait(client,book,'awaiting_plan')
    async def remove_pending_state():
        async with get_db() as db:
            await db.execute("UPDATE novel_chapters SET status='planning' WHERE novel_id=? AND status='awaiting_plan_approval'",(book,))
            await db.commit()
    asyncio.run(remove_pending_state())
    response=client.post(f'/novels/{book}/plan/{action}',json=body,headers=HEADERS)
    assert response.status_code==409 and '待批细纲' in response.json()['detail']


def test_patch_agents_requires_pause_or_gate_and_validates_selection(workshop,monkeypatch):
    import threading
    client,fake=workshop
    book=create(client,chapters=2,mode='solo')
    agents=payload(mode='solo')['agents']
    async def public(username): return {'provider':'dashscope','model':'unknown-model','enabled':True}
    monkeypatch.setattr('byok.store.get_public_config',public)
    bad=dict(agents,writer='byok:self')
    result=client.patch(f'/novels/{book}',json={'agents':bad},headers=HEADERS)
    assert result.status_code==422 and result.json()['detail']=='该模型暂不支持用于小说工坊'
    assert client.patch(f'/novels/{book}',json={'agents':{'writer':agents['writer'],'editor':agents['editor'],'plot_architect':agents['editor']}},headers=HEADERS).status_code==422
    assert client.patch(f'/novels/{book}',json={'agents':agents},headers=HEADERS).status_code==200
    entered=threading.Event(); release=threading.Event()
    async def blocked(call,index):
        if call['task']=='write':
            entered.set()
            while not release.is_set(): await asyncio.sleep(.005)
    fake.script=blocked
    approve(client,book)
    assert entered.wait(5)
    response=client.patch(f'/novels/{book}',json={'agents':agents},headers=HEADERS)
    assert response.status_code==409 and '暂停' in response.json()['detail']
    assert client.post(f'/novels/{book}/pause',headers=HEADERS).status_code==200
    assert client.patch(f'/novels/{book}',json={'agents':agents},headers=HEADERS).status_code==200
    release.set()


def test_same_user_running_book_blocks_another_create_and_resume(workshop):
    import threading
    client,fake=workshop
    paused=create(client,mode='solo')
    # Setup approval leaves a runnable manuscript; pause while its writer waits.
    entered=threading.Event(); release=threading.Event()
    async def blocked(call,index):
        if call['task']=='write':
            entered.set()
            while not release.is_set(): await asyncio.sleep(.005)
    fake.script=blocked
    approve(client,paused); assert entered.wait(5)
    assert client.post(f'/novels/{paused}/pause',headers=HEADERS).status_code==200
    entered.clear()
    response=client.post('/novels',json=payload(mode='solo'),headers=HEADERS)
    assert response.status_code==201,response.text
    running=response.json()['id']; wait(client,running,'awaiting_setup')
    approve(client,running); assert entered.wait(5)
    for method,path,kwargs in [
        ('POST','/novels',{'json':payload(mode='solo')}),
        ('POST',f'/novels/{paused}/resume',{}),
    ]:
        response=client.request(method,path,headers=HEADERS,**kwargs)
        assert response.status_code==409 and '同时只能运行一本' in response.json()['detail']
    assert client.post(f'/novels/{running}/pause',headers=HEADERS).status_code==200
    release.set()
