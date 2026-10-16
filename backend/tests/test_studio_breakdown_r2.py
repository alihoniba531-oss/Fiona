"""WO3c R2：重新拆解替代旧拆解时的状态与 superseded_by。"""
from fastapi import HTTPException
import pytest

from studio import breakdown, breakdown_plan, store
from test_studio_breakdown_pipeline import OWNER, drain, fake, pipeline, run


def test_restart_keeps_completed_old_breakdown_done_and_published(pipeline, monkeypatch):
    fake(monkeypatch)
    async def scenario():
        first_quote = await breakdown.quote(pipeline['id'], OWNER)
        first = await breakdown.start(pipeline['id'], OWNER, first_quote['id'])
        first = await drain(pipeline['id'])
        assert first['status'] == 'done'
        published = await breakdown_plan.get_episodes(pipeline['id'], OWNER)
        assert published['plan_revision'] == 1 and published['episodes']
        async with store.connection() as db:
            units_before = await breakdown._many(db, 'SELECT * FROM studio_units WHERE breakdown_id=?', (first['id'],))
            bible_before = await breakdown._many(db, 'SELECT * FROM studio_bible WHERE breakdown_id=?', (first['id'],))
        second_quote = await breakdown.quote(pipeline['id'], OWNER)
        second = await breakdown.start(pipeline['id'], OWNER, second_quote['id'])
        assert second['id'] != first['id']
        async with store.connection() as db:
            old = await breakdown._breakdown(db, first['id'], OWNER)
        assert old['status'] == 'done' and old['superseded_by'] == second['id']
        # 已被替代的旧拆解：不重新物化、不重跑、不重新发布方案。
        await breakdown.refresh(first['id'], OWNER)
        with pytest.raises(HTTPException) as retired:
            await breakdown.retry_quote(first['id'], first['chunks'][0]['id'], OWNER, 'deepseek')
        assert retired.value.status_code == 409 and '拆解已取消' in retired.value.detail
        # 新方案发布前，项目 GET 只读；分集表仍显示旧方案。
        await breakdown.get_current(pipeline['id'], OWNER)
        plan = await breakdown_plan.get_episodes(pipeline['id'], OWNER)
        assert plan['breakdown_id'] == first['id'] and plan['active_breakdown_id'] == second['id']
        assert plan['rebreakdown_pending'] is True
        assert plan['plan_revision'] == published['plan_revision']
        assert [episode['title'] for episode in plan['episodes']] == [episode['title'] for episode in published['episodes']]
        async with store.connection() as db:
            assert await breakdown._many(db, 'SELECT * FROM studio_units WHERE breakdown_id=?', (first['id'],)) == units_before
            assert await breakdown._many(db, 'SELECT * FROM studio_bible WHERE breakdown_id=?', (first['id'],)) == bible_before
            again = await breakdown._breakdown(db, first['id'], OWNER)
        assert again['status'] == 'done' and again['superseded_by'] == second['id']
    run(scenario())
