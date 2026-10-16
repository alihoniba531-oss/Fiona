"""Private, opt-in novel workshop HTTP API."""
import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from auth_dep import get_current_user
from novel import service
from rate_limit import limiter


async def workshop_user(user: str = Depends(get_current_user)):
    if os.getenv('FIONA_NOVEL','0') != '1':
        raise HTTPException(404,'Not Found')
    allowed={name.strip() for name in os.getenv('FIONA_NOVEL_USERS','').split(',') if name.strip()}
    if user not in allowed:
        raise HTTPException(403,'小说工坊暂未对该账号开放')
    return user


router=APIRouter(prefix='/novels',tags=['novels'])


@router.get('/catalog')
async def catalog(user: str = Depends(workshop_user)):
    return await service.catalog(user)


@router.post('/estimate')
@limiter.limit('20/minute')
async def estimate(request: Request, body: service.CreateNovel, user: str = Depends(workshop_user)):
    return await service.estimate(user,body)


@router.post('',status_code=201)
@limiter.limit('20/minute')
async def create(request: Request,body: service.CreateNovel,user: str = Depends(workshop_user)):
    return await service.create(user,body)


@router.get('')
async def list_books(user: str = Depends(workshop_user)):
    return await service.list_books(user)


@router.get('/{novel_id}')
async def detail(novel_id: str,user: str = Depends(workshop_user)):
    return await service.detail(user,novel_id)


@router.get('/{novel_id}/bible')
async def bible(novel_id: str,user: str = Depends(workshop_user)):
    return await service.bible(user,novel_id)


@router.get('/{novel_id}/notes')
async def notes(novel_id: str,user: str = Depends(workshop_user)):
    return await service.notes(user,novel_id)


@router.get('/{novel_id}/chapters/{number}')
async def chapter(novel_id: str,number: int = Path(ge=1,le=300),user: str = Depends(workshop_user)):
    return await service.chapter(user,novel_id,number)


@router.post('/{novel_id}/setup/approve')
@limiter.limit('20/minute')
async def approve_setup(request: Request,novel_id: str,body: service.SetupApproval = service.SetupApproval(),user: str = Depends(workshop_user)):
    return await service.approve_setup(user,novel_id,body)


@router.post('/{novel_id}/plan/approve')
@limiter.limit('20/minute')
async def approve_plan(request: Request,novel_id: str,body: service.PlanApproval = service.PlanApproval(),user: str = Depends(workshop_user)):
    return await service.approve_plan(user,novel_id,body)


@router.post('/{novel_id}/plan/redo')
@limiter.limit('20/minute')
async def redo_plan(request: Request,novel_id: str,body: service.Note,user: str = Depends(workshop_user)):
    return await service.redo_plan(user,novel_id,body)


@router.post('/{novel_id}/continue')
@limiter.limit('20/minute')
async def continue_book(request: Request,novel_id: str,user: str = Depends(workshop_user)):
    return await service.transition(user,novel_id,'continue')


@router.post('/{novel_id}/pause')
@limiter.limit('20/minute')
async def pause(request: Request,novel_id: str,user: str = Depends(workshop_user)):
    return await service.transition(user,novel_id,'pause')


@router.post('/{novel_id}/resume')
@limiter.limit('20/minute')
async def resume(request: Request,novel_id: str,user: str = Depends(workshop_user)):
    return await service.transition(user,novel_id,'resume')


@router.patch('/{novel_id}')
@limiter.limit('20/minute')
async def patch(request: Request,novel_id: str,body: service.PatchNovel,user: str = Depends(workshop_user)):
    return await service.patch(user,novel_id,body)


@router.post('/{novel_id}/notes')
@limiter.limit('20/minute')
async def note(request: Request,novel_id: str,body: service.Note,user: str = Depends(workshop_user)):
    return await service.note(user,novel_id,body)


@router.patch('/{novel_id}/characters/{character_id}')
@limiter.limit('20/minute')
async def update_character(request: Request,novel_id: str,character_id: str,body: service.CharacterEdit,user: str = Depends(workshop_user)):
    return await service.update_character(user,novel_id,character_id,body)


@router.put('/{novel_id}/chapters/{number}')
@limiter.limit('20/minute')
async def edit_chapter(request: Request,novel_id: str,body: service.Manuscript,number: int = Path(ge=1,le=300),user: str = Depends(workshop_user)):
    return await service.edit_chapter(user,novel_id,number,body)


@router.post('/{novel_id}/end/confirm')
@limiter.limit('20/minute')
async def confirm_end(request: Request,novel_id: str,user: str = Depends(workshop_user)):
    return await service.transition(user,novel_id,'confirm')


@router.post('/{novel_id}/end/reject')
@limiter.limit('20/minute')
async def reject_end(request: Request,novel_id: str,body: service.RejectEnd,user: str = Depends(workshop_user)):
    return await service.reject_end(user,novel_id,body)


@router.get('/{novel_id}/export')
async def export(novel_id: str,user: str = Depends(workshop_user)):
    return Response(await service.export(user,novel_id),media_type='text/markdown',headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote('小说-'+novel_id+'.md')})


@router.delete('/{novel_id}')
@limiter.limit('20/minute')
async def delete(request: Request,novel_id: str,user: str = Depends(workshop_user)):
    return await service.delete(user,novel_id)
