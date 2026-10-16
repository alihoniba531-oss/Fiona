"""工作室 HTTP 流程与隐藏准入；TestClient 不使用真实端口或网络。"""
import asyncio
import io

import aiosqlite
from PIL import Image
import pytest


def image_bytes(mode="RGB", size=(320, 240), image_format="PNG", **save_options):
    buffer = io.BytesIO()
    Image.new(mode, size).save(buffer, format=image_format, **save_options)
    return buffer.getvalue()


def jwt_headers(user):
    from auth import create_token
    from database import get_or_create_user
    account = asyncio.run(get_or_create_user(user))
    return {"Authorization": f"Bearer {create_token(user, account['session_version'])}"}


@pytest.fixture
def studio_client(client, monkeypatch, tmp_path):
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", " owner, other ")
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "1")
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    return client, jwt_headers("owner")


def create_project(client, headers):
    response = client.post("/studio/projects", headers=headers,
                           json={"title": "第一镜", "aspect": "16:9"})
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, headers, project, data=None):
    return client.post(f"/studio/projects/{project['id']}/assets", headers=headers,
                       files={"file": ("frame.png", image_bytes() if data is None else data, "image/png")})


def create_quote(client, headers, project, asset, **params):
    return client.post(f"/studio/projects/{project['id']}/clips/quote", headers=headers,
                       json={"first_frame_asset_id": asset["id"], "prompt": "女孩抬头望向窗外。", **params})


def update_row(sql, params):
    async def run():
        import database
        async with aiosqlite.connect(database.DB_PATH) as db:
            await db.execute(sql, params)
            await db.commit()
    asyncio.run(run())


ALL_ENDPOINTS = [
    ("GET", "/studio/access"),
    ("POST", "/studio/projects"),
    ("GET", "/studio/projects"),
    ("POST", "/studio/projects/foreign/assets"),
    ("POST", "/studio/projects/foreign/clips/quote"),
    ("POST", "/studio/quotes/foreign/confirm"),
    ("GET", "/studio/projects/foreign/jobs"),
    ("GET", "/studio/jobs/foreign"),
    ("POST", "/studio/jobs/foreign/cancel"),
    ("POST", "/studio/jobs/foreign/recheck"),
    ("POST", "/studio/jobs/foreign/link-task"),
    ("POST", "/studio/jobs/foreign/release"),
    ("GET", "/studio/assets/foreign/file"),
]


@pytest.mark.parametrize("method,path", ALL_ENDPOINTS)
@pytest.mark.parametrize("denial", ["anonymous", "not_owner", "disabled", "dev", "empty_owners"])
def test_every_endpoint_hidden(studio_client, monkeypatch, method, path, denial):
    client, headers = studio_client
    if denial == "anonymous":
        headers = {}
    elif denial == "not_owner":
        headers = jwt_headers("outsider")
    elif denial == "disabled":
        monkeypatch.setenv("FIONA_STUDIO", "0")
    elif denial == "dev":
        headers = {"X-Dev-User": "owner"}
    elif denial == "empty_owners":
        monkeypatch.setenv("FIONA_STUDIO_OWNERS", " , ")
    # 非作者即使发送损坏 JSON，也只得到隐藏的 404。
    response = client.request(method, path, headers={**headers, "Content-Type": "application/json"},
                              content=b"{")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert response.headers["cache-control"] == "private, no-store"


def test_calltime_gate_and_bearer_cookie_dev(studio_client, monkeypatch):
    client, headers = studio_client
    response = client.get("/studio/access", headers=headers)
    assert response.status_code == 200
    assert response.json()["caps"] == {"daily_cny": 300.0, "max_quote_cny": 100.0,
                                       "inflight": {"wan": 3, "seedance": 3}}
    assert response.json()["today"] == {"committed_cny": 0, "remaining_cny": 300}
    assert response.headers["cache-control"] == "private, no-store"
    client.cookies.set("fiona_token", headers["Authorization"][7:])
    assert client.get("/studio/access").status_code == 200
    client.cookies.clear()
    assert client.get("/studio/access", headers={"X-Dev-User": "owner"}).status_code == 404
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "0")
    assert client.get("/studio/access", headers={"X-Dev-User": "owner"}).status_code == 200
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", "owner-suffix")
    assert client.get("/studio/access", headers=headers).status_code == 404
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", "owner")
    monkeypatch.setenv("FIONA_STUDIO", "false")
    assert client.get("/studio/access", headers=headers).status_code == 200


def test_build_upload_quote_confirm_and_cancel(studio_client):
    client, headers = studio_client
    project = create_project(client, headers)
    assert client.get("/studio/projects", headers=headers).json()[0]["id"] == project["id"]
    asset_response = upload(client, headers, project)
    assert asset_response.status_code == 201
    asset = asset_response.json()
    assert "rel_path" not in asset
    assert (asset["width"], asset["height"]) == (320, 240)
    assert upload(client, headers, project).json()["id"] == asset["id"]
    quote_response = create_quote(client, headers, project, asset)
    assert quote_response.status_code == 200, quote_response.text
    quote = quote_response.json()
    assert quote["total_min_cny"] == pytest.approx(1.05)
    assert quote["total_max_cny"] == pytest.approx(1.5)
    assert "today" in quote
    response = client.post(f"/studio/quotes/{quote['id']}/confirm", headers=headers)
    assert response.status_code == 200, response.text
    job = response.json()[0]
    assert "result_url" not in job
    assert "run_token" not in job
    assert job["status"] == "queued"
    assert job["reserved_cny"] == 1.5
    assert "base64" not in job["params_json"]
    assert client.post(f"/studio/quotes/{quote['id']}/confirm", headers=headers).status_code == 409
    assert client.get(f"/studio/jobs/{job['id']}", headers=headers).json()["id"] == job["id"]
    assert client.get(f"/studio/projects/{project['id']}/jobs", headers=headers).json()[0]["id"] == job["id"]
    response = client.post(f"/studio/jobs/{job['id']}/cancel", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert client.post(f"/studio/jobs/{job['id']}/cancel", headers=headers).status_code == 409
    assert client.get("/studio/access", headers=headers).json()["today"]["committed_cny"] == 0


def test_user_amount_messages_have_two_decimals_without_rounding_numeric_api(studio_client, monkeypatch):
    client, headers = studio_client
    project = create_project(client, headers)
    asset = upload(client, headers, project).json()
    capped = create_quote(client, headers, project, asset, provider="seedance", resolution="1080p", duration=30)
    assert capped.status_code == 422
    assert capped.json()["detail"] == "本次报价超过单次上限 ¥100.00"
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "2.734")
    quote = create_quote(client, headers, project, asset).json()
    assert client.post(f"/studio/quotes/{quote['id']}/confirm", headers=headers).status_code == 200
    second_quote = create_quote(client, headers, project, asset).json()
    assert second_quote["today"]["remaining_cny"] == 1.234
    denied = client.post(f"/studio/quotes/{second_quote['id']}/confirm", headers=headers)
    assert denied.status_code == 409
    assert denied.json()["detail"] == "今日额度不足，剩余额度 ¥1.23"


def test_file_range_no_store_and_missing_file(studio_client):
    client, headers = studio_client
    project = create_project(client, headers)
    data = image_bytes()
    asset = upload(client, headers, project, data).json()
    url = f"/studio/assets/{asset['id']}/file"
    response = client.get(url, headers={**headers, "Range": "bytes=0-15"})
    assert response.status_code == 206
    assert response.content == data[:16]
    assert response.headers["content-range"] == f"bytes 0-15/{len(data)}"
    assert response.headers["cache-control"] == "private, no-store"
    response = client.get(url, headers=headers)
    assert response.content == data
    from studio import storage, store
    storage.resolve_asset_path(asyncio.run(store.get_asset(asset["id"], "owner"))).unlink()
    assert client.get(url, headers=headers).status_code == 404


@pytest.mark.parametrize("rel_path", ["../private.txt", "/etc/passwd", "symlink/private.txt"])
def test_tampered_asset_path_hidden(studio_client, tmp_path, rel_path):
    client, headers = studio_client
    project = create_project(client, headers)
    asset = upload(client, headers, project).json()
    from studio.storage import storage_root
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("private")
    (storage_root() / "symlink").symlink_to(outside, target_is_directory=True)
    update_row("UPDATE studio_assets SET rel_path=? WHERE id=?", (rel_path, asset["id"]))
    response = client.get(f"/studio/assets/{asset['id']}/file", headers=headers)
    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"


def test_all_resource_types_isolate_owners(studio_client):
    client, headers = studio_client
    project = create_project(client, headers)
    asset = upload(client, headers, project).json()
    quote = create_quote(client, headers, project, asset).json()
    other = jwt_headers("other")
    assert client.get("/studio/projects", headers=other).json() == []
    assert upload(client, other, project).status_code == 404
    assert create_quote(client, other, project, asset).status_code == 404
    own_project = create_project(client, other)
    assert create_quote(client, other, own_project, asset).status_code == 404
    assert client.post(f"/studio/quotes/{quote['id']}/confirm", headers=other).status_code == 404
    assert client.get(f"/studio/projects/{project['id']}/jobs", headers=other).status_code == 404
    assert client.get(f"/studio/assets/{asset['id']}/file", headers=other).status_code == 404
    job = client.post(f"/studio/quotes/{quote['id']}/confirm", headers=headers).json()[0]
    for suffix, body in [("", None), ("/cancel", None), ("/recheck", None),
                         ("/link-task", {"task_id": "provider-task"}),
                         ("/release", {"not_charged": True})]:
        response = client.request("GET" if not suffix else "POST", f"/studio/jobs/{job['id']}{suffix}",
                                  headers=other, json=body)
        assert response.status_code == 404


@pytest.mark.parametrize("mode,size,save_options", [
    ("RGBA", (320, 240), {}),
    ("P", (320, 240), {"transparency": 0}),
    ("RGB", (239, 320), {}),
    ("RGB", (8001, 240), {}),
])
def test_wan_rejects_alpha_or_dimensions_at_quote(studio_client, mode, size, save_options):
    client, headers = studio_client
    project = create_project(client, headers)
    response = upload(client, headers, project, image_bytes(mode, size, **save_options))
    assert response.status_code == 201
    assert create_quote(client, headers, project, response.json()).status_code == 422


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_upload_allowed_formats(studio_client, image_format):
    client, headers = studio_client
    project = create_project(client, headers)
    assert upload(client, headers, project, image_bytes(image_format=image_format)).status_code == 201


@pytest.mark.parametrize("bad_data", [b"not-an-image", image_bytes(image_format="GIF"),
                                      image_bytes()[:35]], ids=["text", "gif", "truncated"])
def test_upload_rejects_invalid_formats(studio_client, bad_data):
    client, headers = studio_client
    project = create_project(client, headers)
    assert upload(client, headers, project, bad_data).status_code == 422


def test_upload_size_limit(studio_client):
    client, headers = studio_client
    project = create_project(client, headers)
    response = upload(client, headers, project, b"x" * (20 * 1024 * 1024 + 1))
    assert response.status_code == 422
    assert "20MB" in response.json()["detail"]


@pytest.mark.parametrize("params", [{"prompt": ""}, {"prompt": " "}, {"prompt": "字" * 2001},
                                   {"duration": True}, {"duration": 1.5}, {"duration": 31},
                                   {"provider": "seedance", "duration": 3},
                                   {"resolution": "240P"}, {"model": "unknown"}])
def test_quote_invalid_parameters(studio_client, params):
    client, headers = studio_client
    project = create_project(client, headers)
    asset = upload(client, headers, project).json()
    assert create_quote(client, headers, project, asset, **params).status_code == 422


def test_quote_limit_and_dev_daily_cap(studio_client, monkeypatch):
    client, headers = studio_client
    project = create_project(client, headers)
    asset = upload(client, headers, project).json()
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "1")
    response = create_quote(client, headers, project, asset)
    assert response.status_code == 422
    assert "1" in response.json()["detail"]
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "1")
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "0")
    dev = {"X-Dev-User": "owner"}
    quote = create_quote(client, dev, project, asset).json()
    response = client.post(f"/studio/quotes/{quote['id']}/confirm", headers=dev)
    assert response.status_code == 409
    assert "剩余" in response.json()["detail"]


def test_uncertain_recheck_link_and_release(studio_client):
    client, headers = studio_client
    project = create_project(client, headers)
    asset = upload(client, headers, project).json()

    def uncertain_job():
        quote = create_quote(client, headers, project, asset).json()
        job = client.post(f"/studio/quotes/{quote['id']}/confirm", headers=headers).json()[0]
        update_row("UPDATE studio_jobs SET status='uncertain' WHERE id=?", (job["id"],))
        return job

    job = uncertain_job()
    url = f"/studio/jobs/{job['id']}"
    assert client.post(url + "/recheck", headers=headers).status_code == 409
    response = client.post(url + "/link-task", headers=headers, json={"task_id": "real-task-id"})
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["task_id"] == "real-task-id"
    assert client.post(url + "/recheck", headers=headers).status_code == 200
    assert client.post(url + "/release", headers=headers, json={"not_charged": True}).status_code == 409
    job = uncertain_job()
    url = f"/studio/jobs/{job['id']}"
    for not_charged in (False, 1, "true"):
        assert client.post(url + "/release", headers=headers,
                           json={"not_charged": not_charged}).status_code == 422
    response = client.post(url + "/release", headers=headers,
                           json={"not_charged": True, "note": "控制台核对未扣费"})
    assert response.status_code == 200
    assert response.json()["status"] == "released"
    assert response.json()["reserved_cny"] == 0
    assert client.get("/studio/access", headers=headers).json()["today"]["committed_cny"] == 1.5


@pytest.mark.parametrize("action,status,body,task_id", [
    ("detail", "submitted", None, "upstream-task"),
    ("list", "submitted", None, "upstream-task"),
    ("cancel", "queued", None, None),
    ("recheck", "submitted", None, "upstream-task"),
    ("link-task", "uncertain", {"task_id": "upstream-task"}, None),
    ("release", "uncertain", {"not_charged": True}, None),
])
def test_job_responses_do_not_expose_result_url_or_token(studio_client, action, status, body, task_id):
    client, headers = studio_client
    project = create_project(client, headers)
    asset = upload(client, headers, project).json()
    quote = create_quote(client, headers, project, asset).json()
    job = client.post(f"/studio/quotes/{quote['id']}/confirm", headers=headers).json()[0]
    update_row("UPDATE studio_jobs SET status=?,task_id=?,result_url=?,run_token=? WHERE id=?",
               (status, task_id, "https://private.example/video?signature=secret", "private-token", job["id"]))
    if action == "list":
        response = client.get(f"/studio/projects/{project['id']}/jobs", headers=headers)
        public = response.json()[0]
    elif action == "detail":
        response = client.get(f"/studio/jobs/{job['id']}", headers=headers)
        public = response.json()
    else:
        response = client.post(f"/studio/jobs/{job['id']}/{action}", headers=headers, json=body)
        public = response.json()
    assert response.status_code == 200
    assert "result_url" not in public
    assert "run_token" not in public
    assert "signature=secret" not in response.text


def test_upload_cannot_recreate_project_after_account_cleanup(studio_client, monkeypatch):
    client, headers = studio_client
    project = create_project(client, headers)
    from studio import storage, store
    from database import delete_account_data, mark_upload_cleanup_done
    from utils.media import delete_uploaded_files
    project_dir = storage.storage_root(create=True) / project["id"]
    project_dir.mkdir()
    (project_dir / "old.png").write_bytes(b"old")
    original = store.save_uploaded_asset

    async def after_account_deletion(owner, project_id, data, metadata):
        result = await delete_account_data(owner)
        deleted, failures = delete_uploaded_files(result["upload_paths"])
        assert not failures
        await mark_upload_cleanup_done(deleted)
        assert not project_dir.exists()
        return await original(owner, project_id, data, metadata)

    monkeypatch.setattr(store, "save_uploaded_asset", after_account_deletion)
    response = upload(client, headers, project)
    assert response.status_code == 404
    assert not project_dir.exists()
