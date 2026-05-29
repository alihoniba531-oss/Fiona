# -*- coding: utf-8 -*-
import json

from fastapi import APIRouter, Depends, File, Form, UploadFile

from auth_dep import get_current_user, get_optional_user
from utils.media import _save_plaza_upload

router = APIRouter()


# 预定义标签列表（前后端共用）
PLAZA_TAGS = ["日常", "风景", "美食", "创意", "情感", "搞笑", "音乐", "运动", "宠物", "穿搭", "旅行", "随拍"]


@router.get("/plaza/tags")
async def plaza_tags():
    return {"tags": PLAZA_TAGS}


@router.get("/plaza/feed")
async def plaza_feed(
    tag: str = "",
    sort: str = "recommended",  # recommended | latest | hot
    limit: int = 30,
    offset: int = 0,
    user: str | None = Depends(get_optional_user),
):
    """feed：默认按用户偏好（推荐），可指定 latest / hot。匿名也能用，但无个性化"""
    from database import get_posts, get_tag_prefs, get_time_tag_prefs, get_time_slot
    posts = await get_posts(limit=200, offset=0)

    # 标签过滤
    if tag:
        posts = [p for p in posts if tag in p.get("tags", [])]

    if sort == "latest":
        posts.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    elif sort == "hot":
        posts.sort(key=lambda p: (p.get("likes", 0), p.get("created_at") or ""), reverse=True)
    else:  # recommended
        if user:
            global_prefs = await get_tag_prefs(user)
            time_prefs   = await get_time_tag_prefs(user)
            if global_prefs or time_prefs:
                def score(p):
                    tags = p.get("tags", [])
                    g = sum(global_prefs.get(t, 0) for t in tags)
                    s = sum(time_prefs.get(t, 0) * 1.5 for t in tags)
                    return g + s
                posts.sort(key=score, reverse=True)

    current_slot = get_time_slot()
    return {"posts": posts[offset: offset + limit], "time_slot": current_slot}


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
    import hashlib, aiosqlite
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
        anon = hashlib.md5(("fiona_plaza_" + u).encode()).hexdigest()[:6]
        items.append({"tag": f"#{r['tag']}", "user": anon})
    return {"items": items}


@router.post("/plaza/post")
async def plaza_post(
    caption: str = Form(default=""),
    tags: str = Form(default="[]"),
    file: UploadFile = File(...),
    user: str = Depends(get_current_user),
):
    import hashlib
    from database import save_post
    try:
        tag_list = json.loads(tags)
        tag_list = [t for t in tag_list if t in PLAZA_TAGS][:5]
    except Exception:
        tag_list = []
    anon_id = hashlib.md5(("fiona_plaza_" + user).encode()).hexdigest()[:8]
    media_path, media_type = await _save_plaza_upload(file)
    post_id = await save_post(anon_id, media_path, media_type, caption, tag_list)
    return {"id": post_id, "anon_id": anon_id, "media_path": media_path, "tags": tag_list}


@router.post("/plaza/like/{post_id}")
async def plaza_like(post_id: int, user: str = Depends(get_current_user)):
    from database import like_post, get_posts, update_tag_prefs
    likes = await like_post(post_id)
    # 更新用户标签喜好
    all_posts = await get_posts(limit=200)
    post = next((p for p in all_posts if p["id"] == post_id), None)
    if post and post.get("tags"):
        await update_tag_prefs(user, post["tags"])
    return {"likes": likes}
