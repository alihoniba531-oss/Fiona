"""R1 money conservation under seeded parallel calls, faults and cancellation.

The provider seam is a local FakeLLM. Inputs are constructed here and the only
files used are the test's own temporary SQLite database. No git or scratchpad
probe is loaded by this test.
"""

import asyncio
from collections import Counter
import random
import socket

from fastapi import HTTPException
import pytest

import database
from novel import runner, service
from novel.billing import NovelBilling
from novel.fake_llm import FakeLLM
from novel.llm_router import LLMRouter
from novel.store_db import get_db
from rate_limit import limiter


class ChaosProvider:
    def __init__(self, seed):
        self.random = random.Random(seed)
        self.fake = FakeLLM()
        self.calls = 0
        self.active = 0
        self.peak = 0
        self.faults = Counter()
        self.roles = Counter()
        self.phases = {}

    async def __call__(self, request):
        self.calls += 1
        serial = self.calls
        self.roles[request['role']] += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            # A three-advisor barrier makes overlap deterministic even on a
            # slow SQLite worker, while cancellation still drains every sibling.
            if request['task'] == 'critique_plan':
                phase = self.phases.setdefault(request['chapter'],
                                               {'ready': asyncio.Event(), 'waiting': 0})
                phase['waiting'] += 1
                if phase['waiting'] >= 3:
                    phase['ready'].set()
                try:
                    await phase['ready'].wait()
                finally:
                    phase['waiting'] -= 1
            await asyncio.sleep(self.random.uniform(.002, .008))
            result = self.fake.default_response(request)
            if request['task'] != 'setup':
                if serial % 11 == 0:
                    self.faults['network'] += 1
                    raise ConnectionError('offline synthetic network failure')
                if serial % 13 == 0 and request['output'] == 'json':
                    self.faults['bad_json'] += 1
                    return '{not-json', {'input_tokens': 1000, 'output_tokens': 200}, 'stop'
                if serial % 7 == 0:
                    self.faults['missing_usage'] += 1
                    return result, None, 'stop'
            return result, {'input_tokens': 1000, 'output_tokens': 200,
                            'cached_tokens': 100}, 'stop'
        finally:
            self.active -= 1


async def snapshot(username):
    async with get_db() as db:
        balance = (await (await db.execute(
            'SELECT strawberry_balance FROM users WHERE username=?', (username,)
        )).fetchone())[0]
        books = await (await db.execute(
            'SELECT id,spent_strawberries,reserved_strawberries FROM novels WHERE username=?',
            (username,),
        )).fetchall()
        ledger = (await (await db.execute(
            'SELECT COALESCE(SUM(strawberries_charged),0), '
            "COALESCE(SUM(CASE WHEN billing_status='reserved' THEN strawberries_reserved ELSE 0 END),0) "
            'FROM novel_steps WHERE username=?', (username,),
        )).fetchone())
    return balance, books, ledger


@pytest.mark.parametrize('seed', [7, 11, 23])
def test_chaos_conservation_twenty_rounds(seed, monkeypatch, tmp_path):
    """Each seed checks every one of 20 stops, not merely the final balance."""
    def forbidden(*args, **kwargs):
        raise AssertionError('network access forbidden in the conservation test')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setenv('DEV_MODE', '0')
    monkeypatch.setenv('STRAWBERRY_DAILY_REFILL', '0')
    monkeypatch.delenv('FIONA_NOVEL_PRICE_JSON', raising=False)
    monkeypatch.setattr(limiter, 'enabled', False)
    monkeypatch.setattr(database, 'DB_PATH', str(tmp_path / 'conservation.db'))

    async def scenario():
        await database.init_db()
        username = 'chaos-author'
        initial_balance = 1_000_000
        await database.get_or_create_user(username)
        async with get_db() as db:
            await db.execute('UPDATE users SET strawberry_balance=? WHERE username=?',
                             (initial_balance, username))
            await db.commit()
        provider = ChaosProvider(seed)
        controls = random.Random(seed + 1000)
        def factory(store, user, novel_id, token):
            router = LLMRouter(store, billing=NovelBilling(user, novel_id, token))
            router._single_real_call = provider
            router.retry_delay = 0
            return router
        monkeypatch.setattr(runner, 'router_factory', factory)
        data = service.CreateNovel(
            seed_idea='离线测试：档案员追查一段旧录像', panel_mode='critique',
            automation='full_auto', batch_size=5, budget_strawberries=1_000_000,
            target={'min_chapters': 60, 'max_chapters': 60, 'chapter_words': 1000},
            agents={'editor': 'dashscope:qwen3.8-max',
                    'writer': 'deepseek:deepseek-flash',
                    'archivist': 'ark:doubao-seed-2-1-pro-260915',
                    'reviewer': 'dashscope:qwen3.8-max',
                    'plot_architect': 'dashscope:qwen3.8-max',
                    'character_advocate': 'deepseek:deepseek-flash',
                    'twist_designer': 'ark:doubao-seed-2-1-pro-260915'},
        )
        book = await service.create(username, data)
        novel_id = book['id']
        try:
            task = runner.TASKS.get(novel_id)
            if task is not None:
                await asyncio.wait_for(asyncio.shield(task), 10)
            book = await service.detail(username, novel_id)
            assert book['status'] == 'awaiting_setup'
            stop_modes = Counter()
            for iteration in range(20):
                before = provider.calls
                target = before + controls.randint(4, 9)
                if book['status'] == 'awaiting_setup':
                    await service.approve_setup(username, novel_id, service.SetupApproval())
                elif book['status'] == 'paused':
                    await service.transition(username, novel_id, 'resume')
                else:
                    assert book['status'] == 'running', (seed, iteration, book['status'])
                    await runner.start_novel(novel_id, username)
                for _ in range(5000):
                    task = runner.TASKS.get(novel_id)
                    if provider.calls >= target or task is None or task.done():
                        break
                    await asyncio.sleep(.001)
                else:
                    pytest.fail(f'seed={seed} iteration={iteration}: worker did not progress')
                await asyncio.sleep(controls.uniform(0, .004))
                mode = controls.choice(('pause', 'cancel', 'task_cancel'))
                stop_modes[mode] += 1
                if mode == 'pause':
                    try:
                        await service.transition(username, novel_id, 'pause')
                    except HTTPException as error:
                        # A model fault can publish its paused state first.
                        assert error.status_code == 409
                elif mode == 'task_cancel':
                    task = runner.TASKS.get(novel_id)
                    if task is not None:
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                # Also drains a pause which raced a fault and checks refund idempotence.
                await runner.cancel_novel(novel_id, username)
                balance, books, ledger = await snapshot(username)
                spent = sum(row['spent_strawberries'] for row in books)
                assert all(row['reserved_strawberries'] == 0 for row in books), (seed, iteration)
                assert ledger[1] == 0, (seed, iteration)
                assert initial_balance - balance == spent == ledger[0], (
                    seed, iteration, initial_balance - balance, spent, ledger[0])
                assert provider.active == 0
                book = await service.detail(username, novel_id)
                assert book['status'] in ('running', 'paused'), (seed, iteration, book['status'])
            assert set(stop_modes) == {'pause', 'cancel', 'task_cancel'}
            assert {'network', 'bad_json', 'missing_usage'} <= provider.faults.keys()
            assert provider.peak >= 3
            assert all(provider.roles[role] > 0 for role in
                       ('plot_architect', 'character_advocate', 'twist_designer'))
            print(f'CONSERVATION seed={seed} rounds=20 PASS '
                  f'balance_delta={initial_balance - balance} spent={spent} '
                  f'charged={ledger[0]} reserved=0 '
                  f'peak_parallel={provider.peak} faults={dict(provider.faults)}')
        finally:
            await runner.cancel_novel(novel_id, username)
    asyncio.run(scenario())
