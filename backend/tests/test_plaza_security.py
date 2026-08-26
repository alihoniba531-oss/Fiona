# -*- coding: utf-8 -*-
import asyncio
import hashlib


def test_pseudonyms_are_stable_keyed_and_namespace_separated():
    from utils.pseudonym import anonymous_id

    post_id = anonymous_id("alice", "plaza-author")
    assert post_id == anonymous_id("alice", "plaza-author")
    assert post_id != anonymous_id("alice", "community-interest")
    assert post_id != hashlib.md5(b"fiona_plaza_alice").hexdigest()[:12]


def test_plaza_read_routes_are_really_public(client):
    for path in ("/plaza/tags", "/plaza/feed", "/plaza/community-interests"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)


def test_like_missing_post_returns_404_without_orphan(client, dev_headers):
    import aiosqlite
    import database

    response = client.post("/plaza/like/999999", headers=dev_headers)
    assert response.status_code == 404

    async def count_orphans():
        async with aiosqlite.connect(database.DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM post_likes WHERE post_id = ?",
                (999999,),
            ) as cursor:
                row = await cursor.fetchone()
        return row[0]

    assert asyncio.run(count_orphans()) == 0


def test_plaza_pagination_parameters_are_bounded(client):
    assert client.get("/plaza/feed?limit=101").status_code == 422
    assert client.get("/plaza/feed?offset=-1").status_code == 422
    assert client.get("/plaza/feed?sort=unknown").status_code == 422
