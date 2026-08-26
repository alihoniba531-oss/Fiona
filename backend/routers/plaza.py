# -*- coding: utf-8 -*-
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile

from auth_dep import get_current_user, get_optional_user
from utils.media import _save_plaza_upload, delete_uploaded_files
from utils.pseudonym import anonymous_id

router = APIRouter()


# 预定义标签列表（前后端共用）
PLAZA_TAGS = ["日常", "风景", "美食", "创意", "情感", "搞笑", "音乐", "运动", "宠物", "穿搭", "旅行", "随拍"]


@router.get("/plaza/tags")
async def plaza_tags():
    return {"tags": PLAZA_TAGS}


@router.get("/plaza/feed")
async def plaza_feed(
    tag: Annotated[str, Query(max_length=20)] = "",
    sort: Literal["recommended", "latest", "hot"] = "recommended",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    user: str | None = Depends(get_optional_user),
):
    """feed：默认按用户偏好（推荐），可指定 latest / hot。匿名也能用，但无个性化"""
    from database import get_posts, get_recommended_posts, get_time_slot
    current_slot = get_time_slot()
    if sort in {"latest", "hot"}:
        posts = await get_posts(limit=limit, offset=offset, sort=sort, tag=tag)
    elif user:
        posts = await get_recommended_posts(
            user,
            current_slot,
            limit=limit,
            offset=offset,
            tag=tag,
        )
    else:
        posts = await get_posts(limit=limit, offset=offset, sort="latest", tag=tag)
    return {"posts": posts, "time_slot": current_slot}


@router.get("/plaza/time-prefs")
async def plaza_time_prefs(user: str = Depends(get_current_user)):
    """返回当前用户各时段的标签偏好（用于可视化）"""
    from database import get_all_time_tag_prefs, get_time_slot
    prefs = await get_all_time_tag_prefs(user)
    return {"username": user, "time_slot": get_time_slot(), "prefs": prefs}


@router.get("/plaza/community-interests")
async def community_interests(user: str | None = Depends(get_optional_user)):
    """返回其他用户的兴趣标签，用于广场底部滚动展示（匿名）。
    已登录则排除自己；匿名则全量返回。"""
    import aiosqlite
    from database import DB_PATH
    exclude = user or ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT username, tag, score FROM user_tag_prefs WHERE username != ? AND score > 0 ORDER BY score DESC LIMIT 80",
            (exclude,),
        ) as cursor:
            rows = await cursor.fetchall()
    seen: dict[str, int] = {}
    items = []
    for r in rows:
        u = r["username"]
        seen[u] = seen.get(u, 0) + 1
        if seen[u] > 3:
            continue
        anon = anonymous_id(u, "community-interest", length=10)
        items.append({"tag": f"#{r['tag']}", "user": anon})
    return {"items": items}


@router.post("/plaza/post")
async def plaza_post(
    caption: str = Form(default="", max_length=1000),
    tags: str = Form(default="[]", max_length=500),
    file: UploadFile = File(...),
    user: str = Depends(get_current_user),
):
    from database import save_post
    try:
        tag_list = json.loads(tags)
        tag_list = [t for t in tag_list if t in PLAZA_TAGS][:5]
    except Exception:
        tag_list = []
    anon_id = anonymous_id(user, "plaza-author", length=12)
    media_path, media_type = await _save_plaza_upload(file)
    post_id = await save_post(anon_id, media_path, media_type, caption, tag_list, user)
    if post_id is None:
        delete_uploaded_files([media_path])
        raise HTTPException(status_code=409, detail="账号已失效")
    return {"id": post_id, "anon_id": anon_id, "media_path": media_path, "tags": tag_list}


@router.post("/plaza/like/{post_id}")
async def plaza_like(
    post_id: int = Path(gt=0),
    user: str = Depends(get_current_user),
):
    from database import get_post, like_post, update_tag_prefs
    post = await get_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="帖子不存在")
    # 按真实登录用户名去重(不是帖子作者的 anon_id),防同一人重复刷赞
    likes, inserted = await like_post(post_id, user)
    # 只有新点赞才更新偏好；按 id 直查，旧帖也不会被漏掉。
    if inserted and post.get("tags"):
        await update_tag_prefs(user, post["tags"])
    return {"likes": likes}
