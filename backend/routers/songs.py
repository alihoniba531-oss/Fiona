# -*- coding: utf-8 -*-
"""写歌项目快照、生成与音频 HTTP API（仅白名单用户，全部私有缓存头）。"""
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from auth_dep import get_current_user
from rate_limit import limiter
from song import config, jobs, media, store


router = APIRouter(prefix="/songs", tags=["songs"])

PRIVATE_HEADERS = {"Cache-Control": "private, no-store"}


async def song_user(
    response: Response, user: str = Depends(get_current_user)
) -> str:
    """开关关闭或用户名不在白名单时一律 404，并带上私有缓存头。"""
    if not config.song_enabled_for(user):
        raise HTTPException(404, "Not Found", headers=PRIVATE_HEADERS)
    response.headers.update(PRIVATE_HEADERS)
    return user


class GenerateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lyrics_revision: StrictInt = Field(ge=0)
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9_-]{8,64}$")


def _public_version(version: dict) -> dict:
    return {
        key: version.get(key)
        for key in (
            "id",
            "lyrics_revision",
            "status",
            "progress",
            "failure_message",
            "duration_s",
            "created_at",
        )
    }


def _sections_with_types(project: dict, lyrics: dict) -> list[dict]:
    """段落类型以结构蓝图为准；旧数据缺 type 时也能补齐。"""
    blueprint_types: dict[str, str] = {}
    structure = project.get("structure")
    if isinstance(structure, list):
        for item in structure:
            if not isinstance(item, dict):
                continue
            section_id = item.get("id")
            section_type = item.get("type")
            if isinstance(section_id, str) and isinstance(section_type, str):
                blueprint_types[section_id] = section_type

    result: list[dict] = []
    sections = lyrics.get("sections")
    if not isinstance(sections, list):
        return result
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = section.get("id")
        section_type = section.get("type")
        if isinstance(section_id, str) and section_id in blueprint_types:
            section_type = blueprint_types[section_id]
        lines = section.get("lines")
        result.append(
            {
                "id": section_id,
                "type": section_type if isinstance(section_type, str) else None,
                "lines": list(lines) if isinstance(lines, list) else [],
            }
        )
    return result


def _blocked_reason(
    *,
    has_lyrics: bool,
    lyrics_ok: bool,
    configured: bool,
    inflight: int,
    today: int,
) -> str | None:
    if not has_lyrics:
        return "还没有歌词"
    if not lyrics_ok:
        return "歌词有未解决的问题"
    if not configured:
        return "写歌服务未配置"
    if inflight >= config.song_max_inflight():
        return "同时在途的歌曲太多"
    if today >= config.song_daily_limit():
        return "今天生成歌曲的次数已用完"
    return None


@router.get("/projects/{project_id}")
async def project_snapshot(
    project_id: str, response: Response, user: str = Depends(song_user)
):
    project = await store.get_project(project_id, owner_username=user)
    if project is None:
        raise HTTPException(404, "Not Found", headers=PRIVATE_HEADERS)

    lyrics = await store.get_lyrics(project_id)
    raw_versions = await store.list_versions(project_id, limit=10)
    versions = [_public_version(version) for version in raw_versions]

    lyrics_ok = bool(
        lyrics and isinstance(lyrics.get("check"), dict)
        and lyrics["check"].get("ok") is True
    )
    configured = config.song_configured()
    inflight, today = await jobs.usage_counts(user)
    reason = _blocked_reason(
        has_lyrics=lyrics is not None,
        lyrics_ok=lyrics_ok,
        configured=configured,
        inflight=inflight,
        today=today,
    )

    public_lyrics = None
    if lyrics is not None:
        check = lyrics.get("check")
        public_lyrics = {
            "revision": lyrics.get("revision"),
            "sections": _sections_with_types(project, lyrics),
            "check": check if isinstance(check, dict) else {},
            "changed_section_ids": lyrics.get("changed_section_ids") or [],
        }

    return {
        "id": project["id"],
        "title": project.get("title") or "",
        "brief": project.get("brief") or {},
        "structure": project.get("structure") or [],
        "lyrics_revision": project.get("lyrics_revision") or 0,
        "lyrics": public_lyrics,
        "versions": versions,
        "price_strawberries": config.song_price_strawberries(),
        "can_generate": reason is None,
        "generate_blocked_reason": reason,
        "configured": configured,
    }


@router.post("/projects/{project_id}/generate", status_code=202)
@limiter.limit("10/minute")
async def generate_song(
    request: Request,
    project_id: str,
    body: GenerateBody,
    response: Response,
    user: str = Depends(song_user),
):
    try:
        return await jobs.create_generation(
            user, project_id, body.lyrics_revision, body.idempotency_key
        )
    except jobs.SongError as exc:
        raise HTTPException(
            exc.status_code, exc.detail, headers=PRIVATE_HEADERS
        ) from None


@router.get("/versions/{version_id}/audio")
async def version_audio(
    version_id: str,
    download: str | None = Query(default=None),
    user: str = Depends(song_user),
):
    version = await jobs.get_version(version_id, owner_username=user)
    if version is None or version.get("status") != "succeeded":
        raise HTTPException(404, "Not Found", headers=PRIVATE_HEADERS)

    path = media.safe_audio_path(version.get("audio_rel_path"))
    try:
        available = path is not None and path.is_file()
    except OSError:
        available = False
    if not available:
        raise HTTPException(404, "Not Found", headers=PRIVATE_HEADERS)

    headers = dict(PRIVATE_HEADERS)
    if download == "1":
        title = version.get("project_title")
        filename = title.strip() if isinstance(title, str) else ""
        if not filename:
            filename = "song"
        headers["Content-Disposition"] = (
            "attachment; filename*=UTF-8''" + quote(filename, safe="") + ".mp3"
        )
    return FileResponse(path, media_type="audio/mpeg", headers=headers)
