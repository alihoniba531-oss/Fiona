"""Authenticated workshop operations; model work is delegated to the runner."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agent_pool import AGENTS
from .billing import estimate_cost, get_prices
from .schemas import ValidationError, compact, validate_decision, validate_setup
from .store_db import get_db
from .writing import compact_length

PLATFORM_MODELS = ('dashscope:qwen3.8-max', 'deepseek:deepseek-flash', 'ark:doubao-seed-2-1-pro-260915')
JSON_MODELS = (PLATFORM_MODELS[0], PLATFORM_MODELS[2], 'byok:self')
WRITER_MODELS = (PLATFORM_MODELS[1], PLATFORM_MODELS[0], 'byok:self')
ROLE_DESCRIPTIONS = {'editor':'生成立项与章节定稿，回应顾问和作者意见。','writer':'依照细纲撰写和修订正文。','archivist':'维护故事圣经与伏笔账本。','reviewer':'核对正文与设定，给出有证据的修订意见。','plot_architect':'检查主线因果与情节结构。','character_advocate':'检查人物动机与成长。','reader_rep':'检查阅读吸引力。','twist_designer':'提出反转和替代走向。','pacing_advisor':'检查章节节奏。','adaptation_advisor':'检查短剧改编可行性。'}
ADVISORS = ('plot_architect', 'character_advocate', 'reader_rep', 'twist_designer', 'pacing_advisor', 'adaptation_advisor')


def fail(message, code=409):
    raise HTTPException(code, message)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Target(Input):
    min_chapters: int = Field(default=50, ge=1, le=200)
    max_chapters: int = Field(default=70, ge=1, le=200)
    chapter_words: int = Field(default=2000, ge=1000, le=4000)

    @model_validator(mode='after')
    def ordered(self):
        if self.min_chapters > self.max_chapters:
            raise ValueError('最少章数不得超过最多章数')
        return self


class Adaptation(Input):
    max_main_characters: int = Field(default=6, ge=1, le=12)
    max_scenes_per_chapter: int = Field(default=3, ge=1, le=10)


class CreateNovel(Input):
    seed_idea: str = Field(min_length=1, max_length=2000)
    agents: dict[str, str] = Field(min_length=3, max_length=9)
    panel_mode: Literal['critique', 'solo'] = 'critique'
    automation: Literal['per_batch', 'per_chapter', 'full_auto'] = 'per_batch'
    batch_size: int = Field(default=5, ge=1, le=10)
    target: Target = Field(default_factory=Target)
    adaptation: Adaptation = Field(default_factory=Adaptation)
    drama_adaptation: bool = False
    budget_strawberries: int = Field(ge=1, le=10_000_000)


class PatchNovel(Input):
    budget_strawberries: int | None = Field(default=None, ge=1, le=10_000_000)
    automation: Literal['per_batch', 'per_chapter', 'full_auto'] | None = None
    batch_size: int | None = Field(default=None, ge=1, le=10)
    agents: dict[str, str] | None = Field(default=None, min_length=3, max_length=9)


class Note(Input):
    text: str = Field(min_length=1, max_length=500)


class Manuscript(Input):
    body: str = Field(min_length=1, max_length=30000)


class CharacterEdit(Input):
    appearance: str | None = None
    personality: str | None = Field(default=None, min_length=1)
    motivation: str | None = Field(default=None, min_length=1)

    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError('至少修改外形、性格或动机中的一项')
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError('人物修改字段必须为字符串')
        return self


class PlanApproval(Input):
    beat_sheet: dict | None = None

    @model_validator(mode='after')
    def bounded(self):
        if len(encoded(self.beat_sheet)) > 30000:
            raise ValueError('细纲过长')
        return self


class SetupApproval(Input):
    compass: dict | None = None
    locked: dict | None = None

    @model_validator(mode='after')
    def bounded(self):
        if len(encoded(self.model_dump())) > 60000:
            raise ValueError('立项修改过长')
        return self


class RejectEnd(Input):
    extend_chapters: int = Field(ge=1, le=10)
    text: str | None = Field(default=None, max_length=500)


async def row(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        result = await cursor.fetchone()
    return dict(result) if result else None


async def rows(db, sql, args=()):
    async with db.execute(sql, args) as cursor:
        return [dict(item) for item in await cursor.fetchall()]


async def owned(db, username, novel_id, states=()):
    book = await row(db, 'SELECT * FROM novels WHERE id=? AND username=?', (novel_id, username))
    if not book:
        fail('小说不存在', 404)
    if states and book['status'] not in states:
        fail('当前状态不能执行此操作')
    return book


async def check_active(db, username, novel_id=None):
    other = await row(db, "SELECT id FROM novels WHERE username=? AND status IN ('running','setup_running') AND id<>?", (username, novel_id or ''))
    if other:
        fail('每个用户同时只能运行一本小说')


async def validate_selection(username, data):
    agents = data.agents
    if not {'editor', 'writer', 'archivist'} <= agents.keys():
        fail('必须选择主编、写手和档案员', 422)
    if set(agents) - {'editor', 'writer', 'archivist', 'reviewer', *ADVISORS}:
        fail('存在不支持的智能体', 422)
    if len(set(agents) & set(ADVISORS)) > 5:
        fail('推演顾问最多选择五位', 422)
    for role, model in agents.items():
        allowed = JSON_MODELS if role in ('editor','archivist','reviewer') else WRITER_MODELS if role == 'writer' else (*PLATFORM_MODELS, 'byok:self')
        if model not in allowed:
            fail(f'{role} 的模型不在允许清单', 422)
    if 'byok:self' in agents.values():
        from .byok_bridge import ByokBridge
        try:
            await ByokBridge(username).describe()
        except ValueError as error:
            fail(str(error), 422)


async def estimate(username, data):
    await validate_selection(username, data)
    async with get_db() as db:
        history = await rows(db, "SELECT role,model,input_tokens,output_tokens,attempts FROM novel_steps WHERE username=? AND status='ok' AND billing_status='settled' ORDER BY updated_at DESC LIMIT 20", (username,))
    return estimate_cost(data.agents, data.panel_mode, data.target.model_dump(), history)


def summary(book):
    result = {key: book[key] for key in ('id','title','status','pause_reason','bible_version','chapters_done','words_done','budget_strawberries','spent_strawberries','reserved_strawberries','created_at','updated_at','completed_at')}
    result['max_chapters'] = int(json.loads(book['config_json']).get('target', {}).get('max_chapters', Target().max_chapters))
    return result


async def catalog(username):
    from .byok_bridge import ByokBridge
    try:
        byok = await ByokBridge(username).describe()
    except ValueError:
        byok = None
    return {'agents': [{'id': key, 'name': card['name'], 'category': card['category'], 'required': key in ('editor','writer','archivist'), 'description': ROLE_DESCRIPTIONS[key]} for key,card in AGENTS.items() if key in ('editor','writer','archivist','reviewer',*ADVISORS)], 'models': [{'id': name, 'price': get_prices()[name]} for name in PLATFORM_MODELS], 'byok': byok, 'allowed_models': {role:list(JSON_MODELS if role!='writer' else WRITER_MODELS) for role in ('editor','writer','archivist','reviewer')}, 'notice': '主编可选千问或豆包。想用 Claude：先在「设置 → 聊天模型」配好并启用自带 Claude，这里会多出「我的模型」，不扣草莓'}


async def create(username, data):
    cost = await estimate(username, data)
    if data.budget_strawberries < cost['per_chapter']['min']:
        fail('预算低于估算下限的一章份额', 422)
    config = data.model_dump()
    config.update(experiment='P1', critique_rounds=1, enable_arc_summaries=True, enable_context_compression=True)
    if not set(config['agents']) & set(ADVISORS):
        config['panel_mode'] = 'solo'
    novel_id = str(uuid4())
    async with get_db() as db:
        await db.execute('BEGIN IMMEDIATE')
        await check_active(db, username)
        if not await row(db,'SELECT username FROM users WHERE username=?',(username,)):
            fail('账号不存在',404)
        await db.execute("INSERT INTO novels(id,username,seed_idea,status,config_json,budget_strawberries) VALUES(?,?,?,'setup_running',?,?)", (novel_id,username,data.seed_idea,encoded(config),data.budget_strawberries))
        await db.commit()
    from .runner import start_novel
    await start_novel(novel_id, username)
    return await detail(username, novel_id)


async def list_books(username):
    async with get_db() as db:
        return [summary(book) for book in await rows(db,'SELECT * FROM novels WHERE username=? ORDER BY created_at DESC,id',(username,))]


async def find_books(username, query):
    query = query.strip().casefold()
    if not query:
        return []
    return [book for book in await list_books(username) if query in (book['title'] or '').casefold()]


async def detail(username, novel_id):
    async with get_db() as db:
        book = await owned(db,username,novel_id)
        version = await row(db,'SELECT bible_json FROM novel_bible_versions WHERE novel_id=? AND version=?',(novel_id,book['bible_version']))
        chapters = await rows(db,'SELECT chapter,title,status,flags_json,body,edited_by_user FROM novel_chapters WHERE novel_id=? ORDER BY chapter',(novel_id,))
        count = await row(db,"SELECT COUNT(*) AS n FROM novel_notes WHERE novel_id=? AND status='pending'",(novel_id,))
    result=summary(book)
    result.update(config=json.loads(book['config_json']), compass=json.loads(book['compass_json']) if book['compass_json'] else None, bible=json.loads(version['bible_json']) if version else None, chapters=[{**{key:value for key,value in ch.items() if key not in ('flags_json','body','edited_by_user')},'words':compact_length(ch['body'] or ''),'flags':json.loads(ch['flags_json'] or '[]'),'edited_by_user':bool(ch['edited_by_user'])} for ch in chapters], pending_gate=book['status'] if book['status'].startswith('awaiting_') else None,pending_notes=count['n'])
    if result['bible']:
        from .context import trim_bible
        result['bible']=trim_bible(result['bible'],chapter=book['chapters_done']+1)
    result['last_error']=result['config'].pop('_last_error',None)
    return result


async def bible(username, novel_id):
    """Return the canonical latest bible, without the model context window."""
    async with get_db() as db:
        book = await owned(db,username,novel_id)
        version = await row(db,'SELECT bible_json FROM novel_bible_versions WHERE novel_id=? AND username=? AND version=?',(novel_id,username,book['bible_version']))
    if not version:
        return None
    result = json.loads(version['bible_json'])
    result['compass'] = json.loads(book['compass_json']) if book['compass_json'] else None
    return result


async def notes(username, novel_id):
    """List every author note and its editor response in stable time order."""
    async with get_db() as db:
        await owned(db,username,novel_id)
        result = await rows(db,'SELECT id,text,status,delivered_chapter,created_at,response_json FROM novel_notes WHERE novel_id=? AND username=? ORDER BY created_at,id',(novel_id,username))
    for item in result:
        raw_response = item.pop('response_json')
        response = json.loads(raw_response) if item['status'] == 'delivered' and raw_response else {}
        item['adopted'] = response.get('adopted')
        item['response'] = response.get('response')
    return result


async def chapter(username, novel_id, number):
    async with get_db() as db:
        await owned(db,username,novel_id)
        result=await row(db,'SELECT * FROM novel_chapters WHERE novel_id=? AND chapter=?',(novel_id,number))
    if not result:
        fail('章节不存在',404)
    return _chapter_result(result)


def _chapter_result(result):
    for field in ('flags','meeting','review','archive'):
        result[field]=json.loads(result.pop(field+'_json') or ('[]' if field in ('flags','review') else '{}'))
    result['review_summary']={'retained':sum(len(review.get('issues',[])) for review in result['review']), 'discarded':sum(len(review.get('dropped_issues',[])) for review in result['review'])}
    result.pop('username',None)
    return result


async def chapters_range(username, novel_id, start, end):
    async with get_db() as db:
        await owned(db,username,novel_id)
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= 300 or end-start+1 > 50:
            fail('章节范围须在 1 至 300 章之间，且一次最多读取 50 章',422)
        chapters = await rows(db,'SELECT * FROM novel_chapters WHERE novel_id=? AND chapter BETWEEN ? AND ? ORDER BY chapter',(novel_id,start,end))
    return [_chapter_result(item) for item in chapters]


async def _latest_bible(db,book):
    value=await row(db,'SELECT bible_json FROM novel_bible_versions WHERE novel_id=? AND version=?',(book['id'],book['bible_version']))
    return json.loads(value['bible_json'])


async def _activate(db,book,username):
    _check_not_editing(book['id'])
    await check_active(db,username,book['id'])
    _check_not_editing(book['id'])
    current=await row(db,'SELECT config_json FROM novels WHERE id=?',(book['id'],))
    config=json.loads(current['config_json']); config.pop('_last_error',None)
    await db.execute("UPDATE novels SET status='running',pause_reason=NULL,config_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(encoded(config),book['id']))


def _check_not_editing(novel_id):
    from .runner import is_editing
    if is_editing(novel_id):
        fail('章节正在改稿，请稍后再继续')


async def update_character(username, novel_id, character_id, data):
    async with get_db() as db:
        await db.execute('BEGIN IMMEDIATE')
        book = await owned(db,username,novel_id)
        if book['status'] == 'awaiting_setup':
            fail('立项阶段请在立项卡里修改')
        if book['status'] == 'failed':
            fail('这本书已出错，不能修改人物')
        if book['status'] not in ('awaiting_review','awaiting_plan','awaiting_end','paused','completed'):
            fail('书正在运行，请先暂停再改人物')
        _check_not_editing(novel_id)
        changes = data.model_dump(exclude_unset=True)
        version = await row(db,'SELECT bible_json FROM novel_bible_versions WHERE novel_id=? AND version=?',(novel_id,book['bible_version']))
        if not version:
            fail('人物不存在',404)
        current = json.loads(version['bible_json'])
        character = next((item for item in current['locked']['characters'] if item['id'] == character_id),None)
        if character is None:
            fail('人物不存在',404)
        if 'appearance' in changes and len(compact(changes['appearance'])) < 20:
            fail('外形至少写 20 个字',422)
        character.update(changes)
        current['version'] = book['bible_version']+1
        await db.execute('INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,?,?,?)',(novel_id,username,current['version'],encoded(current),'user_edit'))
        await db.execute('UPDATE novels SET bible_version=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(current['version'],novel_id))
        await db.commit()
    current['compass'] = json.loads(book['compass_json']) if book['compass_json'] else None
    return current


async def approve_setup(username, novel_id, data):
    async with get_db() as db:
        await db.execute('BEGIN IMMEDIATE')
        book=await owned(db,username,novel_id,('awaiting_setup',))
        config=json.loads(book['config_json']); compass=json.loads(book['compass_json']); bible=await _latest_bible(db,book)
        compass_fields={'title','logline','theme','candidate_endings','main_threads'}
        locked_fields={'characters','world_rules','style_guide'}
        if set(data.compass or {})-compass_fields or set(data.locked or {})-locked_fields:
            fail('立项修改包含不可修改的字段',422)
        compass.update(deepcopy(data.compass or {})); bible['locked'].update(deepcopy(data.locked or {}))
        old=await _latest_bible(db,book)
        try:
            setup={key:compass[key] for key in ('title','logline','theme','core_conflict','protagonist','candidate_endings','main_threads')}
            setup.update(characters=[dict(char,initial_state=bible['dynamic']['character_states'].get(char.get('id'),{})) for char in bible['locked']['characters']],world_rules=bible['locked']['world_rules'],style_guide=bible['locked']['style_guide'],initial_foreshadowing=bible['dynamic']['foreshadowing'])
            validate_setup(setup,config)
        except (ValidationError,KeyError,TypeError,AttributeError):
            fail('立项修改不符合设定格式',422)
        mutable_character_fields={'appearance','personality','motivation'}
        if len(bible['locked']['characters']) != len(old['locked']['characters']):
            fail('立项只能修改既有人物的外形、性格和动机',422)
        for original,updated in zip(old['locked']['characters'],bible['locked']['characters']):
            if {k:v for k,v in original.items() if k not in mutable_character_fields} != {k:v for k,v in updated.items() if k not in mutable_character_fields}:
                fail('立项只能修改既有人物的外形、性格和动机',422)
        # Character identities and thread identities are owned by the engine.
        if [c.get('id') for c in bible['locked']['characters']] != [c['id'] for c in old['locked']['characters']] or [t.get('id') for t in compass['main_threads']] != [t['id'] for t in json.loads(book['compass_json'])['main_threads']]:
            fail('不可修改人物或主线编号',422)
        bible['version']=book['bible_version']+1
        await db.execute('INSERT INTO novel_bible_versions(novel_id,username,version,bible_json,source) VALUES(?,?,?,?,?)',(novel_id,username,bible['version'],encoded(bible),'user_edit'))
        await db.execute('UPDATE novels SET title=?,compass_json=?,bible_version=? WHERE id=?',(compass['title'],encoded(compass),bible['version'],novel_id))
        await _activate(db,book,username); await db.commit()
    from .runner import start_novel
    await start_novel(novel_id,username)
    return await detail(username,novel_id)


async def approve_plan(username,novel_id,data):
    async with get_db() as db:
        await db.execute('BEGIN IMMEDIATE')
        book=await owned(db,username,novel_id,('awaiting_plan',))
        current=await row(db,"SELECT * FROM novel_chapters WHERE novel_id=? AND status='awaiting_plan_approval' ORDER BY chapter DESC LIMIT 1",(novel_id,))
        if not current or not current['meeting_json']:
            fail('当前没有可批准的待批细纲，请刷新后重试')
        meeting=json.loads(current['meeting_json']); decision=deepcopy(meeting['decision'])
        if data.beat_sheet is not None:
            decision['beat_sheet']=data.beat_sheet
        try:
            decision=validate_decision(decision,compass=json.loads(book['compass_json']),bible=await _latest_bible(db,book),chapter=current['chapter'],mode=meeting['brief']['mode'],proposal_ids=[p['id'] for p in meeting.get('proposals',[])],objection_ids=[o['id'] for o in meeting.get('objections',[])],note_ids=[n['id'] for n in meeting['brief']['user_notes']],solo=not meeting.get('proposals'))
        except ValidationError:
            fail('细纲不符合裁决要求',422)
        meeting['decision']=decision
        await db.execute("UPDATE novel_chapters SET status='writing',meeting_json=?,updated_at=CURRENT_TIMESTAMP WHERE novel_id=? AND chapter=?",(encoded(meeting),novel_id,current['chapter']))
        await _activate(db,book,username); await db.commit()
    from .runner import start_novel
    await start_novel(novel_id,username)
    return await detail(username,novel_id)


async def redo_plan(username,novel_id,data):
    async with get_db() as db:
        await db.execute('BEGIN IMMEDIATE')
        book=await owned(db,username,novel_id,('awaiting_plan',))
        current=await row(db,"SELECT * FROM novel_chapters WHERE novel_id=? AND status='awaiting_plan_approval' ORDER BY chapter DESC LIMIT 1",(novel_id,))
        if not current or not current['meeting_json']:
            fail('当前没有可重做的待批细纲，请刷新后重试')
        meeting=json.loads(current['meeting_json']); meeting['_redo_note']=data.text; meeting['_redo_count']=meeting.get('_redo_count',0)+1
        await db.execute("UPDATE novel_chapters SET status='planning',meeting_json=? WHERE novel_id=? AND chapter=?",(encoded(meeting),novel_id,current['chapter']))
        await _activate(db,book,username); await db.commit()
    from .runner import start_novel
    await start_novel(novel_id,username)
    return await detail(username,novel_id)


async def patch(username,novel_id,data):
    async with get_db() as db:
        await db.execute('BEGIN IMMEDIATE')
        book=await owned(db,username,novel_id)
        if data.agents is not None:
            if book['status']!='paused' and not book['status'].startswith('awaiting_'):
                fail('只能在暂停或等待确认时修改角色模型')
            _check_not_editing(novel_id)
            await validate_selection(username,data)
        if data.budget_strawberries is not None and data.budget_strawberries < book['spent_strawberries']:
            fail('预算不得低于已花费',422)
        config=json.loads(book['config_json']); config.update(data.model_dump(exclude_none=True))
        if data.agents is not None and not set(data.agents)&set(ADVISORS):
            config['panel_mode']='solo'
        await db.execute('UPDATE novels SET budget_strawberries=?,config_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(data.budget_strawberries if data.budget_strawberries is not None else book['budget_strawberries'],encoded(config),novel_id)); await db.commit()
    return await detail(username,novel_id)


async def note(username,novel_id,data):
    async with get_db() as db:
        await db.execute('BEGIN IMMEDIATE'); await owned(db,username,novel_id)
        count=await row(db,"SELECT COUNT(*) AS n FROM novel_notes WHERE novel_id=? AND status='pending'",(novel_id,))
        if count['n']>=5:
            fail('待处理留言最多五条')
        await db.execute("INSERT INTO novel_notes(novel_id,username,text,status) VALUES(?,?,?,'pending')",(novel_id,username,data.text)); await db.commit()
    return {'status':'pending'}


async def transition(username,novel_id,action):
    from .runner import start_novel,cancel_novel
    if action=='pause':
        async with get_db() as db:
            await owned(db,username,novel_id,('setup_running','running','awaiting_plan','awaiting_review'))
        await cancel_novel(novel_id,username)
        async with get_db() as db:
            await db.execute("UPDATE novels SET status='paused',pause_reason='user',run_token=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=? AND username=?",(novel_id,username)); await db.commit()
    else:
        states={'continue':('awaiting_review',),'resume':('paused',),'confirm':('awaiting_end',)}[action]
        async with get_db() as db:
            await db.execute('BEGIN IMMEDIATE'); book=await owned(db,username,novel_id,states)
            _check_not_editing(novel_id)
            if action in ('resume','continue'):
                await check_active(db,username,novel_id)
            if action=='confirm':
                await db.execute("UPDATE novels SET status='completed',completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",(novel_id,))
            else:
                if action=='resume':
                    config=json.loads(book['config_json'])
                    if (book['spent_strawberries']*5>=book['budget_strawberries']*4 or
                            book['pause_reason']=='budget_80' and book['budget_strawberries']<=config.get('_budget_at_pause',book['budget_strawberries'])):
                        fail('请先调高预算再继续')
                    import os, database
                    if os.getenv('DEV_MODE','0')!='1' and any(model!='byok:self' for model in config['agents'].values()):
                        balance=await row(db,'SELECT strawberry_balance FROM users WHERE username=?',(username,))
                        if not balance or balance['strawberry_balance']<1:
                            fail('草莓余额不足，请先补充')
                if book['compass_json'] and book['bible_version']==1:
                    # A pause racing setup completion must retain the fixed gate.
                    await db.execute("UPDATE novels SET status='awaiting_setup',pause_reason=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(novel_id,))
                else:
                    await _activate(db,book,username)
                    if not book['compass_json']:
                        await db.execute("UPDATE novels SET status='setup_running' WHERE id=?",(novel_id,))
            await db.commit()
        if action!='confirm':
            await start_novel(novel_id,username)
    return await detail(username,novel_id)


async def reject_end(username,novel_id,data):
    async with get_db() as db:
        await db.execute('BEGIN IMMEDIATE'); book=await owned(db,username,novel_id,('awaiting_end',))
        config=json.loads(book['config_json']); compass=json.loads(book['compass_json'])
        config['target']['max_chapters']+=data.extend_chapters
        config['target']['min_chapters']=max(config['target']['min_chapters'],book['chapters_done']+1)
        if config['target']['max_chapters']>300:
            fail('延长后的篇幅超过上限',422)
        compass['target']=deepcopy(config['target'])
        await db.execute('UPDATE novels SET config_json=?,compass_json=? WHERE id=?',(encoded(config),encoded(compass),novel_id))
        if data.text:
            count=await row(db,"SELECT COUNT(*) AS n FROM novel_notes WHERE novel_id=? AND status='pending'",(novel_id,))
            if count['n']>=5: fail('待处理留言最多五条')
            await db.execute("INSERT INTO novel_notes(novel_id,username,text,status) VALUES(?,?,?,'pending')",(novel_id,username,data.text))
        await _activate(db,book,username); await db.commit()
    from .runner import start_novel
    await start_novel(novel_id,username)
    return await detail(username,novel_id)


async def edit_chapter(username,novel_id,number,data):
    from .runner import cancel_novel,editing_novel,start_novel
    async with get_db() as db:
        book=await owned(db,username,novel_id)
        current=await row(db,'SELECT * FROM novel_chapters WHERE novel_id=? AND chapter=?',(novel_id,number))
        if not current or number>book['chapters_done']: fail('章节不存在',404)
    async with editing_novel(novel_id):
        await cancel_novel(novel_id,username)
        async with get_db() as db:
            await db.execute('BEGIN IMMEDIATE'); book=await owned(db,username,novel_id)
            current=await row(db,'SELECT * FROM novel_chapters WHERE novel_id=? AND chapter=?',(novel_id,number))
            if not current or number>book['chapters_done']: fail('章节不存在',404)
            latest=number==book['chapters_done']
            await db.execute('UPDATE novel_chapters SET body=?,edited_by_user=1,updated_at=CURRENT_TIMESTAMP WHERE novel_id=? AND chapter=?',(data.body,novel_id,number))
            bodies=await rows(db,"SELECT body FROM novel_chapters WHERE novel_id=? AND chapter<=?",(novel_id,book['chapters_done']))
            total_words=sum(compact_length(item['body'] or '') for item in bodies)
            await db.execute('UPDATE novels SET words_done=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(total_words,novel_id))
            if latest:
                config=json.loads(book['config_json']); config['_rearchive']=number
                config.setdefault('_after_rearchive',book['status']); config.setdefault('_after_rearchive_reason',book['pause_reason'])
                await check_active(db,username,novel_id)
                await db.execute("UPDATE novels SET config_json=?,status='running',pause_reason=NULL WHERE id=?",(encoded(config),novel_id))
            else:
                await db.execute("UPDATE novel_chapters SET status='stale' WHERE novel_id=? AND chapter>? AND status NOT IN ('planning','awaiting_plan_approval') AND body IS NOT NULL",(novel_id,number))
            restart=latest or book['status'] in ('running','setup_running')
            await db.commit()
    if restart: await start_novel(novel_id,username)
    return {'rearchiving':latest,'message':'最新章节正在重新归档，完成前不会开始下一章' if latest else '后续章节已标记为 stale；不会自动重写，也不会重算圣经'}


async def delete(username,novel_id):
    async with get_db() as db: await owned(db,username,novel_id)
    from .runner import cancel_novel
    await cancel_novel(novel_id,username)
    async with get_db() as db:
        await db.execute('BEGIN IMMEDIATE'); await owned(db,username,novel_id)
        for table in ('novel_notes','novel_steps','novel_chapters','novel_bible_versions'):
            await db.execute(f'DELETE FROM {table} WHERE novel_id=?',(novel_id,))
        await db.execute('DELETE FROM novels WHERE id=? AND username=?',(novel_id,username)); await db.commit()
    return {'deleted':True}


async def export(username,novel_id):
    async with get_db() as db:
        book=await owned(db,username,novel_id)
        chapters=await rows(db,"SELECT chapter,status,body FROM novel_chapters WHERE novel_id=? AND body IS NOT NULL ORDER BY chapter",(novel_id,))
    pending = [item['chapter'] for item in chapters if item['status'] == 'stale']
    heading = '# '+(book['title'] or '未命名小说')
    if pending:
        heading += '\n本书有 '+str(len(pending))+' 章待复核：第 '+'、'.join(str(number) for number in pending)+' 章。'
    bodies = []
    for item in chapters:
        body = item['body']
        if item['status'] == 'stale':
            first, separator, rest = body.partition('\n')
            marker = '【待复核】前面章节改过稿，本章尚未按新内容复核。'
            body = first+'\n'+marker+(separator+rest if separator else '') if first.startswith('# ') else marker+'\n'+body
        bodies.append(body)
    return heading+'\n\n'+'\n\n'.join(bodies)
