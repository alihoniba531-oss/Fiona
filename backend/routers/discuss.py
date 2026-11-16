"""Private, opt-in discussion-group HTTP API."""
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from auth_dep import get_current_user
from discuss import cards, service
from rate_limit import limiter


async def discuss_user(user: str = Depends(get_current_user)):
    if os.getenv('FIONA_DISCUSS', '0') != '1':
        raise HTTPException(404, 'Not Found')
    allowed = {name.strip() for name in os.getenv('FIONA_DISCUSS_USERS', '').split(',')
               if name.strip()}
    if user not in allowed:
        raise HTTPException(403, '讨论群暂未对该账号开放')
    return user


router = APIRouter(prefix='/discuss', tags=['discuss'])


@router.get('/access')
async def access(user: str = Depends(discuss_user)):
    return await service.access()


@router.get('/catalog')
async def catalog(user: str = Depends(discuss_user)):
    return await service.catalog(user)


@router.get('/task-cards/{card_id}')
async def task_card(card_id: str, user: str = Depends(discuss_user)):
    return await cards.task_card_view(user, card_id)


@router.get('/note-cards/{card_id}')
async def note_card(card_id: str, user: str = Depends(discuss_user)):
    return await cards.note_card_view(user, card_id)


@router.post('/note-cards/{card_id}/send')
@limiter.limit('20/minute')
async def send_note_card(request: Request, card_id: str,
                         user: str = Depends(discuss_user)):
    return await cards.send_note_card(user, card_id)


@router.post('/groups', status_code=201)
@limiter.limit('10/minute')
async def create_group(request: Request, body: service.CreateGroup,
                       user: str = Depends(discuss_user)):
    return await service.create_group(user, body)


@router.get('/groups')
async def list_groups(user: str = Depends(discuss_user)):
    return await service.list_groups(user)


@router.get('/groups/{group_id}')
async def detail(group_id: str, after: int = 0, user: str = Depends(discuss_user)):
    return await service.detail(user, group_id, after)


@router.patch('/groups/{group_id}/plan')
@limiter.limit('20/minute')
async def update_plan(request: Request, group_id: str, body: service.UpdatePlan,
                      user: str = Depends(discuss_user)):
    return await service.update_plan(user, group_id, body)


@router.post('/groups/{group_id}/start')
@limiter.limit('20/minute')
async def start(request: Request, group_id: str, body: service.StartGroup,
                user: str = Depends(discuss_user)):
    return await service.start(user, group_id, body)


@router.post('/groups/{group_id}/notes')
@limiter.limit('20/minute')
async def add_note(request: Request, group_id: str, body: service.NoteIn,
                   user: str = Depends(discuss_user)):
    return await service.add_note(user, group_id, body)


@router.post('/groups/{group_id}/pause')
@limiter.limit('20/minute')
async def pause(request: Request, group_id: str, user: str = Depends(discuss_user)):
    return await service.pause(user, group_id)


@router.post('/groups/{group_id}/resume')
@limiter.limit('20/minute')
async def resume(request: Request, group_id: str,
                 body: service.ResumeGroup = service.ResumeGroup(),
                 user: str = Depends(discuss_user)):
    return await service.resume(user, group_id, body)


@router.post('/groups/{group_id}/continue')
@limiter.limit('20/minute')
async def continue_group(request: Request, group_id: str,
                         body: service.ContinueGroup = service.ContinueGroup(),
                         user: str = Depends(discuss_user)):
    return await service.continue_group(user, group_id, body)


@router.post('/groups/{group_id}/accept')
@limiter.limit('20/minute')
async def accept(request: Request, group_id: str, user: str = Depends(discuss_user)):
    return await service.accept(user, group_id)


@router.post('/groups/{group_id}/close')
@limiter.limit('20/minute')
async def close(request: Request, group_id: str, user: str = Depends(discuss_user)):
    return await service.close(user, group_id)


@router.delete('/groups/{group_id}')
@limiter.limit('20/minute')
async def delete(request: Request, group_id: str, user: str = Depends(discuss_user)):
    return await service.delete(user, group_id)


@router.get('/groups/{group_id}/sources')
async def sources(group_id: str, user: str = Depends(discuss_user)):
    return await service.sources(user, group_id)


@router.get('/groups/{group_id}/output')
async def output(group_id: str, version: int | None = None,
                 user: str = Depends(discuss_user)):
    return await service.output(user, group_id, version)


@router.get('/groups/{group_id}/export')
async def export(group_id: str, user: str = Depends(discuss_user)):
    text, filename = await service.export(user, group_id)
    return Response(
        text,
        media_type='text/markdown; charset=utf-8',
        headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(filename)},
    )
