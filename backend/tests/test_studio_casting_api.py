# -*- coding: utf-8 -*-
"""WO3d 块 A：定妆（G1）与声线的 REST 编排、门禁、报价与归属。

隔离：独立 SQLite（TestClient lifespan 建表）+ JWT 作者门禁 + 全部块 B / 块 C 函数
monkeypatch 成假实现（本文件不依赖 studio/providers/*、audio.py、voices.py、
casting_prompts.py 是否存在）。付费任务只建行、不派发（_schedule 打桩）。
"""
import asyncio
import json
import shutil
import uuid

import pytest
from fastapi import HTTPException

from studio import brain, brain_jobs, breakdown_plan, casting_jobs, pricing, spend, store
from studio import casting as casting_module


def run(coro):
    return asyncio.run(coro)


async def rows(sql, params=()):
    async with store.connection() as db:
        return await store._many(db, sql, params)


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

@pytest.fixture
def casting(client, monkeypatch, tmp_path):
    import database
    from auth import create_token

    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_OWNERS", "owner,other")
    monkeypatch.setenv("FIONA_STUDIO_REQUIRE_JWT", "1")
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path / "studio"))
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    monkeypatch.setenv("FIONA_STUDIO_BRAIN_MONTHLY_USD", "40")

    accounts = {}
    for username in ("owner", "other", "outsider"):
        user = run(database.get_or_create_user(username))
        accounts[username] = {"Authorization": f"Bearer {create_token(username, user['session_version'])}"}

    calls = {"image": 0, "cosy": 0, "edge": 0, "scheduled": []}
    gates = {"g0": True}

    async def fake_image(*args, **kwargs):
        calls["image"] += 1
        raise AssertionError("API 测试不应真正出图")

    async def fake_cosy(*args, **kwargs):
        calls["cosy"] += 1
        raise AssertionError("API 测试不应真正合成")

    async def fake_edge(*args, **kwargs):
        calls["edge"] += 1
        raise AssertionError("API 测试不应真正合成")

    async def fake_episodes(pid, owner):
        project = await store.get_project(pid, owner)
        return {"g0_approved": gates["g0"],
                "breakdown_id": project.get("breakdown_id") if gates["g0"] else None,
                "episodes": [{"no": 1, "title": "第一集"}]}

    async def available(username):
        return [{"id": pid, "label": pid, "available": True, "model": model}
                for pid, model in (("claude", "claude-sonnet-5-5"), ("qwen", "qwen3.8-max"),
                                   ("deepseek", "deepseek-v4-pro"))]

    monkeypatch.setattr(casting_jobs, "_generate_sheet", fake_image)
    monkeypatch.setattr(casting_jobs, "_synthesize_cosy", fake_cosy)
    monkeypatch.setattr(casting_jobs, "_synthesize_edge", fake_edge)
    monkeypatch.setattr(casting_jobs, "_schedule", lambda jid: calls["scheduled"].append(jid))
    monkeypatch.setattr(brain_jobs, "_schedule", lambda jid: calls["scheduled"].append(jid))
    monkeypatch.setattr(breakdown_plan, "get_episodes", fake_episodes)
    monkeypatch.setattr(brain, "provider_options", available)
    # 本文件不跑真实音频处理；CI 机器没有 ffmpeg，预检按「工具在位」模拟（缺工具的分支另有专测）。
    real_which = shutil.which
    monkeypatch.setattr(casting_module.shutil, "which",
                        lambda name, *args, **kwargs: f"/usr/bin/{name}" if name in casting_module.AUDIO_TOOLS
                        else real_which(name, *args, **kwargs))

    return {"client": client, "headers": accounts, "calls": calls, "gates": gates}


def auth(casting, name="owner"):
    return casting["headers"][name]


# ---------------------------------------------------------------------------
# 建数据
# ---------------------------------------------------------------------------

async def new_project(owner="owner", title="定妆项目", aspect="16:9", breakdown=True):
    project = await store.create_project(owner, title, aspect)
    if breakdown:
        bid, stamp = "bd-" + uuid.uuid4().hex, store.utcnow()
        async with store.connection(transaction=True) as db:
            await db.execute("""INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,
                status,settings_json,import_json,created_at,updated_at)
                VALUES(?,?,?,1,'claude','done','{}','{}',?,?)""", (bid, project["id"], owner, stamp, stamp))
            await db.execute("UPDATE studio_projects SET breakdown_id=? WHERE id=? AND owner=?",
                             (bid, project["id"], owner))
    return await store.get_project(project["id"], owner)


async def new_bible(project, owner="owner", *, kind="character", name="阿宁", appearance="短发、旧棉袄",
                    role="主角", description="小镇邮差", needs_author=0, archived=0, merged_into=None):
    item_id = str(uuid.uuid4())
    async with store.connection(transaction=True) as db:
        await db.execute("""INSERT INTO studio_bible(id,project_id,owner,breakdown_id,kind,name,
            aliases_json,role,description,appearance,appearance_source,excerpt,needs_author,episodes_json,
            merged_into,archived,updated_at)
            VALUES(?,?,?,?,?,?,'[]',?,?,?,'author','',?,'[]',?,?,?)""",
                         (item_id, project["id"], owner, project["breakdown_id"], kind, name, role, description,
                          appearance, needs_author, merged_into, archived, store.utcnow()))
    return item_id


async def new_asset(project, owner="owner", *, item_id=None, role="sheet", version_no=1, kind="image",
                    archived=0, prompt="", spec=None, text="", duration_s=None, measured_lufs=None):
    asset_id = uuid.uuid4().hex
    meta = {}
    if prompt:
        meta["prompt"] = prompt
    if spec is not None:
        meta["spec"] = spec
    if text:
        meta["text"] = text
    if measured_lufs is not None:
        meta["measured_lufs"] = measured_lufs
    async with store.connection(transaction=True) as db:
        await db.execute("""INSERT INTO studio_assets(id,project_id,owner,kind,source,rel_path,sha256,
            bytes,meta_json,archived,item_id,version_no,role,duration_s,created_at)
            VALUES(?,?,?,?,'generated',?,?,10,?,?,?,?,?,?,?)""",
                         (asset_id, project["id"], owner, kind, f"{asset_id}.bin", asset_id * 2,
                          store._json(meta), archived, item_id, version_no, role, duration_s, store.utcnow()))
    return asset_id


def make_project(casting, owner="owner", **kwargs):
    return run(new_project(owner, **kwargs))


def seed_items(casting, project, owner="owner", count=1, **kwargs):
    return [run(new_bible(project, owner, name=f"人物{index}", **kwargs)) for index in range(count)]


def confirm_setup(casting, project, **body):
    payload = {"resolution": "480P", "video_model": "wan", "language": "zh", **body}
    return casting["client"].put(f"/studio/projects/{project['id']}/casting/setup",
                                 json=payload, headers=auth(casting))


def choose_style(casting, project, realism="photoreal"):
    return casting["client"].put(f"/studio/projects/{project['id']}/casting/style",
                                 json={"realism": realism,
                                       "custom": {"name": "水墨", "visual_style": "宣纸质感",
                                                  "palette": "青灰", "camera": "固定机位",
                                                  "lighting": "柔和侧光", "rationale": "含蓄"}},
                                 headers=auth(casting))


def get_state(casting, project, owner="owner"):
    response = casting["client"].get(f"/studio/projects/{project['id']}/casting", headers=auth(casting, owner))
    assert response.status_code == 200, response.text
    return response.json()


def item_by_bible(state, bible_id):
    for item in state["items"]:
        if item["bible_id"] == bible_id:
            return item
    raise AssertionError(f"没有条目对应总表行 {bible_id}")


# ---------------------------------------------------------------------------
# 门禁
# ---------------------------------------------------------------------------

def test_gates_require_g0_setup_and_style_without_paid_calls(casting):
    client = casting["client"]
    project = make_project(casting)
    bible = run(new_bible(project))
    casting["gates"]["g0"] = False

    state = get_state(casting, project)
    assert state["g0_approved"] is False and state["setup"] is None

    endpoints = [
        ("put", f"/studio/projects/{project['id']}/casting/setup",
         {"resolution": "480P", "video_model": "wan", "language": "zh"}),
        ("post", f"/studio/projects/{project['id']}/casting/style/quote", None),
    ]
    for method, url, body in endpoints:
        response = getattr(client, method)(url, json=body, headers=auth(casting))
        assert response.status_code == 409, (url, response.text)
    assert client.get("/studio/casting/voice-catalog", headers=auth(casting)).status_code == 200
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json={"items": [{"item_id": "x", "versions": 1}]}, headers=auth(casting))
    assert response.status_code == 409
    response = client.post(f"/studio/projects/{project['id']}/casting/voices/audition",
                           json={"item_id": bible, "text": "你好", "variants": [cosy()]}, headers=auth(casting))
    assert response.status_code == 409

    # G0 批准但未开工确认：风格报价与出图报价、试听仍 409。
    casting["gates"]["g0"] = True
    assert client.post(f"/studio/projects/{project['id']}/casting/style/quote",
                       headers=auth(casting)).status_code == 409
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json={"items": [{"item_id": "x", "versions": 1}]}, headers=auth(casting))
    assert response.status_code == 409 and "开工" in response.json()["detail"]
    confirm_setup(casting, project)

    # 开工确认但未选风格：出图报价 409。
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json={"items": [{"item_id": "x", "versions": 1}]}, headers=auth(casting))
    assert response.status_code == 409 and "风格" in response.json()["detail"]

    assert casting["calls"] == {"image": 0, "cosy": 0, "edge": 0, "scheduled": []}
    assert run(rows("SELECT id FROM studio_jobs")) == []


def test_setup_validation_persistence_and_overwrite(casting):
    client = casting["client"]
    casting["gates"]["g0"] = False
    project = make_project(casting)
    response = confirm_setup(casting, project)
    assert response.status_code == 409
    casting["gates"]["g0"] = True

    assert confirm_setup(casting, project, resolution="720p").status_code == 422
    assert confirm_setup(casting, project, video_model="sora").status_code == 422
    assert confirm_setup(casting, project, language="ja").status_code == 422
    assert client.put(f"/studio/projects/{project['id']}/casting/setup",
                      json={"resolution": "480P", "video_model": "wan", "language": "zh", "extra": 1},
                      headers=auth(casting)).status_code == 422

    state = confirm_setup(casting, project, resolution="720P", video_model="seedance", language="en").json()
    assert state["setup"] == {"aspect": "16:9", "resolution": "720P", "video_model": "seedance",
                              "language": "en", "sheet_size": "2560x1440",
                              "confirmed_at": state["setup"]["confirmed_at"]}

    state = confirm_setup(casting, project, resolution="1080P").json()
    assert state["setup"]["resolution"] == "1080P" and state["setup"]["language"] == "zh"
    assert state["prices"] == {"seedream_cny": 0.30, "cosyvoice_cny_per_10k_chars": 2.0}


def test_style_quote_confirms_once_persists_and_expires(casting):
    client = casting["client"]
    project = make_project(casting)
    confirm_setup(casting, project)
    quote = client.post(f"/studio/projects/{project['id']}/casting/style/quote", headers=auth(casting)).json()
    assert quote["kind"] == "casting_style" and quote["currency"] in {"CNY", "USD"}
    assert quote["total"] > 0 and quote["items"][0]["name"] == "风格提案"
    assert quote["items"][0]["est"] == quote["total"]
    assert quote["expires_at"]

    started = client.post(f"/studio/projects/{project['id']}/casting/style/start",
                          json={"quote_id": quote["id"]}, headers=auth(casting))
    assert started.status_code == 200
    state = started.json()
    assert state["style"]["proposal_job"] is not None
    assert state["style"]["proposal_job"]["kind"] in {"brain"}
    stored = run(rows("SELECT * FROM studio_jobs WHERE kind='brain' AND task='style_proposals'"))
    assert len(stored) == 1 and stored[0]["status"] == "queued"
    assert stored[0]["group_id"] == run(store.get_project(project["id"], "owner"))["style_group_id"]

    again = client.post(f"/studio/projects/{project['id']}/casting/style/start",
                        json={"quote_id": quote["id"]}, headers=auth(casting))
    assert again.status_code == 409 and "只能确认一次" in again.json()["detail"]

    missing = client.post(f"/studio/projects/{project['id']}/casting/style/start",
                          json={"quote_id": str(uuid.uuid4())}, headers=auth(casting))
    assert missing.status_code == 404

    expired = client.post(f"/studio/projects/{project['id']}/casting/style/quote", headers=auth(casting)).json()
    run(set_expired(expired["id"]))
    response = client.post(f"/studio/projects/{project['id']}/casting/style/start",
                           json={"quote_id": expired["id"]}, headers=auth(casting))
    assert response.status_code == 409 and "过期" in response.json()["detail"]


async def set_expired(quote_id):
    async with store.connection(transaction=True) as db:
        await db.execute("UPDATE studio_quotes SET expires_at=? WHERE id=?",
                         ("2000-01-01T00:00:00+00:00", quote_id))


def test_style_proposals_stay_bound_to_current_project_and_put_style(casting):
    client = casting["client"]
    project = make_project(casting)
    other_project = make_project(casting, title="别的项目")
    confirm_setup(casting, project)
    quote = client.post(f"/studio/projects/{project['id']}/casting/style/quote", headers=auth(casting)).json()
    client.post(f"/studio/projects/{project['id']}/casting/style/start",
                json={"quote_id": quote["id"]}, headers=auth(casting))

    proposals = [
        {"name": "暖雨", "visual_style": "写实电影感", "palette": "暖棕", "camera": "手持",
         "lighting": "黄昏逆光", "rationale": "贴合旧信"},
        {"name": "冷雾", "visual_style": "冷调动画", "palette": "蓝灰", "camera": "固定",
         "lighting": "阴天漫射", "rationale": "突出距离"},
    ]
    run(mark_succeeded(project, proposals))

    state = get_state(casting, project)
    assert [entry["name"] for entry in state["style"]["proposals"]] == ["暖雨", "冷雾"]
    assert get_state(casting, other_project)["style"]["proposals"] == []

    response = client.put(f"/studio/projects/{project['id']}/casting/style",
                          json={"proposal_index": 1, "realism": "anime"}, headers=auth(casting))
    assert response.status_code == 200
    chosen = response.json()["style"]["chosen"]
    assert chosen == {**proposals[1], "realism": "anime", "source": "proposal", "proposal_index": 1}

    assert client.put(f"/studio/projects/{project['id']}/casting/style",
                      json={"proposal_index": 9, "realism": "anime"}, headers=auth(casting)).status_code == 422
    assert client.put(f"/studio/projects/{project['id']}/casting/style",
                      json={"proposal_index": 0, "realism": "sketch"}, headers=auth(casting)).status_code == 422
    assert client.put(f"/studio/projects/{project['id']}/casting/style",
                      json={"proposal_index": 0, "custom": {"name": "x"}}, headers=auth(casting)).status_code == 422

    chosen_custom = {"realism": "3d", "custom": {"name": "立体", "visual_style": "体块",
                                                 "palette": "低饱和", "camera": "轨道",
                                                 "lighting": "棚拍", "rationale": "统一"}}
    response = client.put(f"/studio/projects/{project['id']}/casting/style",
                          json=chosen_custom, headers=auth(casting))
    assert response.json()["style"]["chosen"]["source"] == "custom"
    assert response.json()["style"]["chosen"]["proposal_index"] is None


def test_custom_style_requires_name_and_visual_style(casting):
    """可优化 f：自定义风格的名称与视觉风格必须非空，否则 422，且不落库。"""
    client = casting["client"]
    project = make_project(casting)
    confirm_setup(casting, project)
    url = f"/studio/projects/{project['id']}/casting/style"
    base = {"palette": "青灰", "camera": "固定", "lighting": "侧光", "rationale": "含蓄"}
    for custom in ({"name": "  ", "visual_style": "宣纸", **base},
                   {"name": "水墨", "visual_style": "", **base},
                   {**base}):
        response = client.put(url, json={"realism": "photoreal", "custom": custom}, headers=auth(casting))
        assert response.status_code == 422, custom
    assert get_state(casting, project)["style"]["chosen"] is None
    # 直连业务函数也必须拦（不能只靠 Pydantic 的字段上限）。
    for custom in ({"name": "", "visual_style": "宣纸"}, {"name": "水墨", "visual_style": " "}):
        with pytest.raises(HTTPException) as error:
            run(casting_module.put_style(project["id"], "owner", realism="photoreal", custom=custom))
        assert error.value.status_code == 422


async def mark_succeeded(project, proposals):
    payload = store._json({"proposals": proposals})
    async with store.connection(transaction=True) as db:
        await db.execute("""UPDATE studio_jobs SET status='succeeded',result_json=?,actual_amount='0',
            finished_at=? WHERE kind='brain' AND task='style_proposals' AND project_id=?""",
                         (payload, store.utcnow(), project["id"]))


# ---------------------------------------------------------------------------
# 出图报价与派发
# ---------------------------------------------------------------------------

def sheets_ready(casting, *, count=1, **bible):
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    bibles = seed_items(casting, project, count=count, **bible)
    return project, bibles


def test_sheets_quote_prices_limits_and_needs_author(casting):
    client = casting["client"]
    project, bibles = sheets_ready(casting, count=2)
    first = item_id(casting, project, bibles[0])
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json={"items": [{"item_id": first, "versions": 2}]}, headers=auth(casting))
    assert response.status_code == 200, response.text
    quote = response.json()
    assert quote["kind"] == "casting_sheets" and quote["total"] == 0.6
    assert quote["items"] == [{"item_id": first, "name": "人物0",
                               "versions": 2, "unit": 0.3, "est": 0.6}]
    assert run(rows("SELECT id FROM studio_jobs")) == []

    assert client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                       json={"items": [{"item_id": first, "versions": 5}]},
                       headers=auth(casting)).status_code == 422
    assert client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                       json={"items": [{"item_id": first, "versions": 1, "extra": 1}]},
                       headers=auth(casting)).status_code == 422
    assert client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                       json={"items": []}, headers=auth(casting)).status_code == 422

    # 待作者补外形的角色不能出图。
    author = run(new_bible(project, name="待补", needs_author=1, appearance=""))
    author_item = item_id(casting, project, author)
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json={"items": [{"item_id": author_item, "versions": 1}]}, headers=auth(casting))
    assert response.status_code == 409 and "外形" in response.json()["detail"]

    # 合计超过 60 张。
    many = seed_items(casting, project, count=16)
    state = get_state(casting, project)
    entries = [{"item_id": item_by_bible(state, bible)["id"], "versions": 4} for bible in many]
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json={"items": entries}, headers=auth(casting))
    assert response.status_code == 422 and "60" in response.json()["detail"]

    # 参考图必须属于本项目且是图片。
    foreign = make_project(casting, title="别的项目")
    foreign_asset = run(new_asset(foreign))
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json={"items": [{"item_id": first, "versions": 1,
                                            "reference_asset_ids": [foreign_asset]}]}, headers=auth(casting))
    assert response.status_code == 404
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json={"items": [{"item_id": first, "versions": 1,
                                            "reference_asset_ids": [str(uuid.uuid4())]}]}, headers=auth(casting))
    assert response.status_code == 404
    assert casting["calls"]["image"] == 0
    assert run(rows("SELECT id FROM studio_jobs")) == []


def item_id(casting, project, bible_id):
    return item_by_bible(get_state(casting, project), bible_id)["id"]


def test_sheets_quote_respects_single_and_daily_caps(casting, monkeypatch):
    client = casting["client"]
    project, bibles = sheets_ready(casting)
    body = {"items": [{"item_id": item_id(casting, project, bibles[0]), "versions": 4}]}

    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "1")
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json=body, headers=auth(casting))
    assert response.status_code == 409 and "单次报价上限" in response.json()["detail"]

    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "1")
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json=body, headers=auth(casting))
    assert response.status_code == 409 and "额度不足" in response.json()["detail"]

    assert casting["calls"]["image"] == 0
    assert run(rows("SELECT id FROM studio_jobs")) == []
    assert run(spend.today())["committed_cny"] == 0


def test_sheets_start_creates_one_job_per_sheet_and_confirms_once(casting):
    client = casting["client"]
    project, bibles = sheets_ready(casting)
    item = item_id(casting, project, bibles[0])
    approved = run(new_asset(project, item_id=item, version_no=1))
    approve(casting, item, approved)
    quote = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                        json={"items": [{"item_id": item, "versions": 2,
                                        "derive_from_approved": True, "extra_prompt": "加一条围巾"}]},
                        headers=auth(casting)).json()
    assert quote["total"] == 0.6

    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/start",
                           json={"quote_id": quote["id"]}, headers=auth(casting))
    assert response.status_code == 200
    state = response.json()
    jobs = [job for job in state["jobs"] if job["kind"] == "image"]
    assert len(jobs) == 2 and all(job["status"] == "queued" for job in jobs)
    assert all(job["reserved_amount"] == 0.3 and job["item_id"] == item for job in jobs)
    assert len(casting["calls"]["scheduled"]) == 2
    assert casting["calls"]["image"] == 0

    stored = run(rows("SELECT * FROM studio_jobs WHERE kind='image'"))
    assert len(stored) == 2 and {row["media_provider"] for row in stored} == {"seedream"}
    assert all(row["status"] == "queued" for row in stored)
    params = json.loads(stored[0]["params_json"])
    # 统一口径：报价只存显式参考图，已选定版本由执行期按 derive_from_approved 合并。
    assert params["reference_asset_ids"] == [] and params["derive_from_approved"] is True
    assert params["extra_prompt"] == "加一条围巾"
    assert run(spend.today())["committed_cny"] == pytest.approx(0.6)

    again = client.post(f"/studio/projects/{project['id']}/casting/sheets/start",
                        json={"quote_id": quote["id"]}, headers=auth(casting))
    assert again.status_code == 409 and "只能确认一次" in again.json()["detail"]


def approve(casting, item_id, asset_id):
    return casting["client"].post(f"/studio/casting/items/{item_id}/approve", json={"asset_id": asset_id},
                                  headers=auth(casting))


def quote_sheets(casting, project, entries, owner="owner"):
    return casting["client"].post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                                  json={"items": entries}, headers=auth(casting, owner))


def start_sheets(casting, project, quote_id, owner="owner"):
    return casting["client"].post(f"/studio/projects/{project['id']}/casting/sheets/start",
                                  json={"quote_id": quote_id}, headers=auth(casting, owner))


def stored_quote_line(quote_id, index=0):
    row = run(rows("SELECT items_json FROM studio_quotes WHERE id=?", (quote_id,)))[0]
    return json.loads(row["items_json"])["items"][index]


def image_job_params():
    return [json.loads(row["params_json"]) for row in
            run(rows("SELECT * FROM studio_jobs WHERE kind='image' ORDER BY created_at,id"))]


def test_sheets_merge_item_defaults_with_batch_input(casting):
    """条目卡保存的补充提示词 / 参考图是常驻默认；批量栏的补充追加、参考图合并去重。"""
    client = casting["client"]
    project, bibles = sheets_ready(casting, count=2)
    item = item_id(casting, project, bibles[0])
    saved_ref = run(new_asset(project))
    batch_ref = run(new_asset(project))
    assert client.patch(f"/studio/casting/items/{item}",
                        json={"extra_prompt": "常驻要求", "reference_asset_ids": [saved_ref]},
                        headers=auth(casting)).status_code == 200

    # 不填批量栏：常驻默认也要带上。
    quote = quote_sheets(casting, project, [{"item_id": item, "versions": 1}]).json()
    line = stored_quote_line(quote["id"])
    assert line["extra_prompt"] == "常驻要求" and line["reference_asset_ids"] == [saved_ref]
    assert line["derive_from_approved"] is False

    # 批量栏：补充追加在常驻之后；参考图与常驻合并、重复只留一次。
    quote = quote_sheets(casting, project,
                         [{"item_id": item, "versions": 1, "extra_prompt": "本批加围巾",
                           "reference_asset_ids": [batch_ref, saved_ref]}]).json()
    line = stored_quote_line(quote["id"])
    assert line["extra_prompt"] == "常驻要求 本批加围巾"
    assert line["reference_asset_ids"] == [saved_ref, batch_ref]

    assert start_sheets(casting, project, quote["id"]).status_code == 200
    params = image_job_params()
    assert [entry["extra_prompt"] for entry in params] == ["常驻要求 本批加围巾"]
    assert [entry["reference_asset_ids"] for entry in params] == [[saved_ref, batch_ref]]
    assert casting["calls"]["image"] == 0


def test_sheets_quote_stores_only_explicit_references_and_caps_merged(casting):
    """派生：报价只存显式参考图 + 标志；合并（含已选定）超过 4 张 422；无选定 409。"""
    client = casting["client"]
    project, bibles = sheets_ready(casting, count=2)
    item = item_id(casting, project, bibles[0])
    approved = run(new_asset(project, item_id=item, version_no=1))
    approve(casting, item, approved)
    extra = [run(new_asset(project, version_no=index + 1)) for index in range(3)]

    # 显式 3 张 + 派生（合并后 4 张，含已选定）→ 报价合法，但只存显式 3 张。
    response = quote_sheets(casting, project,
                            [{"item_id": item, "versions": 1, "derive_from_approved": True,
                              "reference_asset_ids": extra}])
    assert response.status_code == 200, response.text
    line = stored_quote_line(response.json()["id"])
    assert line["reference_asset_ids"] == extra and line["derive_from_approved"] is True

    # 显式 4 张 + 派生 = 合并后 5 张 → 报价阶段就拒。
    fourth = run(new_asset(project, version_no=4))
    response = quote_sheets(casting, project,
                            [{"item_id": item, "versions": 1, "derive_from_approved": True,
                              "reference_asset_ids": [*extra, fourth]}])
    assert response.status_code == 422 and "4" in response.json()["detail"]

    # 没有已选定版本却勾派生 → 409。
    pending = item_id(casting, project, bibles[1])
    response = quote_sheets(casting, project, [{"item_id": pending, "versions": 1,
                                                "derive_from_approved": True}])
    assert response.status_code == 409 and "已选定" in response.json()["detail"]
    assert casting["calls"]["image"] == 0
    assert run(rows("SELECT id FROM studio_jobs WHERE kind='image'")) == []


def test_start_sheets_revalidates_and_keeps_quote_open(casting, monkeypatch):
    """可优化 a/b：确认报价、预留、建任务同一个写事务；复核失败或撞日上限时报价保持 open。"""
    client = casting["client"]
    project, bibles = sheets_ready(casting, count=2)
    first = item_id(casting, project, bibles[0])
    second = item_id(casting, project, bibles[1])
    reference = run(new_asset(project, item_id=first, version_no=1))

    archived_quote = quote_sheets(casting, project,
                                  [{"item_id": first, "versions": 1, "reference_asset_ids": [reference]}]).json()
    assert client.post(f"/studio/casting/assets/{reference}/archive",
                       headers=auth(casting)).json() == {"ok": True}
    response = start_sheets(casting, project, archived_quote["id"])
    assert response.status_code == 404
    assert run(rows("SELECT status FROM studio_quotes WHERE id=?",
                    (archived_quote["id"],)))[0]["status"] == "open"
    assert run(rows("SELECT id FROM studio_jobs WHERE kind='image'")) == []

    capped_quote = quote_sheets(casting, project, [{"item_id": second, "versions": 1}]).json()
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "0.1")
    response = start_sheets(casting, project, capped_quote["id"])
    assert response.status_code == 409 and "额度" in response.json()["detail"]
    assert run(rows("SELECT status FROM studio_quotes WHERE id=?",
                    (capped_quote["id"],)))[0]["status"] == "open"
    assert run(rows("SELECT id FROM studio_jobs WHERE kind='image'")) == []

    # 额度恢复后同一张报价仍可确认（没有被烧掉）。
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    response = start_sheets(casting, project, capped_quote["id"])
    assert response.status_code == 200
    assert len(run(rows("SELECT id FROM studio_jobs WHERE kind='image'"))) == 1

    # 事务内建任务 / 预留失败（例如并发撞日上限）时，报价也必须是 open：
    # 老实现先把 confirmed 单独提交，再另开事务建任务，报价会被烧掉。
    ok_quote = quote_sheets(casting, project, [{"item_id": second, "versions": 1}]).json()

    def quota_failure(*args, **kwargs):
        raise HTTPException(409, "今日额度不足，剩余额度 ¥0.00")

    original = casting_jobs.prepare_jobs
    monkeypatch.setattr(casting_jobs, "prepare_jobs", quota_failure)
    try:
        response = start_sheets(casting, project, ok_quote["id"])
        assert response.status_code == 409 and "额度" in response.json()["detail"]
    finally:
        monkeypatch.setattr(casting_jobs, "prepare_jobs", original)
    assert run(rows("SELECT status FROM studio_quotes WHERE id=?",
                    (ok_quote["id"],)))[0]["status"] == "open"
    assert len(run(rows("SELECT id FROM studio_jobs WHERE kind='image'"))) == 1

    # 失败没有烧掉报价：同一张报价仍能确认。
    response = start_sheets(casting, project, ok_quote["id"])
    assert response.status_code == 200
    assert len(run(rows("SELECT id FROM studio_jobs WHERE kind='image'"))) == 2


# ---------------------------------------------------------------------------
# 条目同步与操作
# ---------------------------------------------------------------------------

def test_items_sync_orphan_and_patch(casting):
    client = casting["client"]
    project = make_project(casting)
    first = run(new_bible(project, name="阿宁"))
    second = run(new_bible(project, kind="location", name="旧邮局"))

    state = get_state(casting, project)
    assert [item["name"] for item in state["items"]] == ["阿宁", "旧邮局"]
    assert all(item["orphaned"] is False for item in state["items"])

    # 总表新增：读取时补建。
    third = run(new_bible(project, kind="prop", name="旧邮包"))
    state = get_state(casting, project)
    assert len(state["items"]) == 3
    assert item_by_bible(state, third)["status"] == "pending"

    # 归档 / 合并：标 orphaned，不删除。
    run(mark_bible(second, archived=1))
    run(mark_bible(first, merged_into=third))
    state = get_state(casting, project)
    assert item_by_bible(state, second)["orphaned"] is True
    assert item_by_bible(state, first)["orphaned"] is True
    assert len(state["items"]) == 3

    item = item_by_bible(state, third)
    response = client.patch(f"/studio/casting/items/{item['id']}",
                            json={"locked_features": "左眉有疤", "extra_prompt": "补光"},
                            headers=auth(casting))
    assert response.status_code == 200 and response.json()["locked_features"] == "左眉有疤"
    assert client.patch(f"/studio/casting/items/{item['id']}", json={"extra_prompt": "x" * 501},
                        headers=auth(casting)).status_code == 422
    assert client.patch(f"/studio/casting/items/{item['id']}", json={"unknown": 1},
                        headers=auth(casting)).status_code == 422

    foreign = make_project(casting, title="别的项目")
    foreign_asset = run(new_asset(foreign))
    assert client.patch(f"/studio/casting/items/{item['id']}",
                        json={"reference_asset_ids": [foreign_asset]}, headers=auth(casting)).status_code == 404

    own_asset = run(new_asset(project))
    response = client.patch(f"/studio/casting/items/{item['id']}",
                            json={"reference_asset_ids": [own_asset]}, headers=auth(casting))
    assert response.status_code == 200 and response.json()["reference_asset_ids"] == [own_asset]

    assert client.post(f"/studio/casting/items/{item['id']}/skip", headers=auth(casting)).json()["status"] == "skipped"
    assert client.post(f"/studio/casting/items/{item['id']}/reopen", headers=auth(casting)).json()["status"] == "pending"
    assert client.patch(f"/studio/casting/items/{uuid.uuid4()}", json={"extra_prompt": "x"},
                        headers=auth(casting)).status_code == 404


async def mark_bible(bible_id, *, archived=None, merged_into=None):
    async with store.connection(transaction=True) as db:
        if archived is not None:
            await db.execute("UPDATE studio_bible SET archived=? WHERE id=?", (archived, bible_id))
        if merged_into is not None:
            await db.execute("UPDATE studio_bible SET merged_into=? WHERE id=?", (merged_into, bible_id))


async def switch_breakdown(project):
    """重新拆解：项目指向新的 breakdown_id，旧总表条目随即成为孤儿。"""
    bid, stamp = "bd-" + uuid.uuid4().hex, store.utcnow()
    async with store.connection(transaction=True) as db:
        await db.execute("""INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,
            status,settings_json,import_json,created_at,updated_at)
            VALUES(?,?,?,1,'claude','done','{}','{}',?,?)""",
                         (bid, project["id"], project["owner"], stamp, stamp))
        await db.execute("UPDATE studio_projects SET breakdown_id=? WHERE id=? AND owner=?",
                         (bid, project["id"], project["owner"]))
    return bid


def test_rebreakdown_orphans_old_items_and_blocks_paid_paths(casting):
    """重新拆解后旧总表条目变孤儿：不计入 G1，不能报价 / 出图 / 试听。"""
    client = casting["client"]
    project, bibles = sheets_ready(casting)
    old_item = item_id(casting, project, bibles[0])

    run(switch_breakdown(project))
    project = run(store.get_project(project["id"], "owner"))
    fresh_bible = run(new_bible(project, name="新条目"))

    state = get_state(casting, project)
    assert item_by_bible(state, bibles[0])["orphaned"] is True
    assert item_by_bible(state, fresh_bible)["orphaned"] is False
    assert state["g1"]["total"] == 1

    response = quote_sheets(casting, project, [{"item_id": old_item, "versions": 1}])
    assert response.status_code == 409 and "总表" in response.json()["detail"]
    response = client.post(f"/studio/projects/{project['id']}/casting/voices/audition",
                           json={"item_id": old_item, "text": "我是阿宁。", "variants": [cosy()]},
                           headers=auth(casting))
    assert response.status_code == 409 and "总表" in response.json()["detail"]

    # 报价后重新拆解 → 执行前复核 409，报价保持 open，一张图都不出。
    fresh_item = item_by_bible(state, fresh_bible)["id"]
    quote = quote_sheets(casting, project, [{"item_id": fresh_item, "versions": 2}]).json()
    run(switch_breakdown(project))
    response = start_sheets(casting, project, quote["id"])
    assert response.status_code == 409 and "总表" in response.json()["detail"]
    assert run(rows("SELECT status FROM studio_quotes WHERE id=?", (quote["id"],)))[0]["status"] == "open"
    assert run(rows("SELECT id FROM studio_jobs WHERE kind='image'")) == []
    assert casting["calls"]["image"] == 0


def test_skip_and_reopen_clear_approved_version(casting):
    """skip / reopen 都清空 approved_asset_id，作者才有地方取消选定。"""
    client = casting["client"]
    project = make_project(casting)
    bible = run(new_bible(project))
    item = item_by_bible(get_state(casting, project), bible)
    first = run(new_asset(project, item_id=item["id"], version_no=1))
    assert approve(casting, item["id"], first).json()["approved_asset_id"] == first

    skipped = client.post(f"/studio/casting/items/{item['id']}/skip", headers=auth(casting)).json()
    assert skipped["status"] == "skipped" and skipped["approved_asset_id"] is None
    # 选定被清掉后，之前选中的版本可以归档了。
    assert client.post(f"/studio/casting/assets/{first}/archive",
                       headers=auth(casting)).json() == {"ok": True}

    second = run(new_asset(project, item_id=item["id"], version_no=2))
    assert approve(casting, item["id"], second).json()["approved_asset_id"] == second
    reopened = client.post(f"/studio/casting/items/{item['id']}/reopen", headers=auth(casting)).json()
    assert reopened["status"] == "pending" and reopened["approved_asset_id"] is None


def test_patch_locked_features_caps_at_600(casting):
    """可优化 m：locked_features 上限 600 字，超出 422。"""
    client = casting["client"]
    project = make_project(casting)
    bible = run(new_bible(project))
    item = item_by_bible(get_state(casting, project), bible)

    assert client.patch(f"/studio/casting/items/{item['id']}", json={"locked_features": "字" * 600},
                        headers=auth(casting)).status_code == 200
    assert client.patch(f"/studio/casting/items/{item['id']}", json={"locked_features": "字" * 601},
                        headers=auth(casting)).status_code == 422
    # 直连业务函数也必须拦（不能只靠 Pydantic 的字段上限）。
    with pytest.raises(HTTPException) as error:
        run(casting_module.patch_item(item["id"], "owner", {"locked_features": "字" * 601}))
    assert error.value.status_code == 422


def test_approve_archive_rules_and_g1(casting):
    client = casting["client"]
    project = make_project(casting)
    one = run(new_bible(project, name="阿宁"))
    two = run(new_bible(project, kind="location", name="旧邮局"))
    state = get_state(casting, project)
    first, second = item_by_bible(state, one), item_by_bible(state, two)

    version_a = run(new_asset(project, item_id=first["id"], version_no=1, prompt="第一版"))
    version_b = run(new_asset(project, item_id=first["id"], version_no=2, prompt="第二版"))
    foreign = run(new_asset(project, item_id=second["id"], version_no=1))

    # 不能选别的条目的版本，也不能选已归档版本。
    assert client.post(f"/studio/casting/items/{first['id']}/approve", json={"asset_id": foreign},
                       headers=auth(casting)).status_code == 404
    assert client.post(f"/studio/casting/items/{first['id']}/approve", json={"asset_id": str(uuid.uuid4())},
                       headers=auth(casting)).status_code == 404

    approved = approve(casting, first["id"], version_a).json()
    assert approved["status"] == "approved" and approved["approved_asset_id"] == version_a
    assert [entry["asset_id"] for entry in approved["versions"]] == [version_a, version_b]
    assert approved["versions"][0]["prompt"] == "第一版"

    # 已选定的版本不能归档，先换选定即可归档旧版。
    response = client.post(f"/studio/casting/assets/{version_a}/archive", headers=auth(casting))
    assert response.status_code == 409
    approve(casting, first["id"], version_b)
    assert client.post(f"/studio/casting/assets/{version_a}/archive",
                       headers=auth(casting)).json() == {"ok": True}
    assert [entry["asset_id"] for entry in get_state(casting, project)["items"][0]["versions"]] == [version_b]

    state = get_state(casting, project)
    assert state["g1"] == {"approved": False, "total": 2, "done": 1, "skipped": 0}
    assert client.post(f"/studio/casting/items/{second['id']}/skip", headers=auth(casting)).status_code == 200
    state = get_state(casting, project)
    assert state["g1"] == {"approved": True, "total": 2, "done": 2, "skipped": 1}

    # 全部跳过时不算通过。
    assert client.post(f"/studio/casting/items/{first['id']}/reopen", headers=auth(casting)).status_code == 200
    assert client.post(f"/studio/casting/items/{first['id']}/skip", headers=auth(casting)).status_code == 200
    assert get_state(casting, project)["g1"]["approved"] is False


# ---------------------------------------------------------------------------
# 声线
# ---------------------------------------------------------------------------

VOICES = [{"engine": "cosyvoice", "voice": "longxiaocheng_v2", "label": "龙小诚", "lang": "zh",
           "gender": "male", "note": ""},
          {"engine": "edge-tts", "voice": "en-US-AndrewNeural", "label": "Andrew", "lang": "en",
           "gender": "male", "note": ""}]


@pytest.fixture
def voice_stubs(casting, monkeypatch):
    monkeypatch.setattr(casting_jobs, "lookup_voice",
                        lambda engine, voice: next((v for v in VOICES
                                                    if v["engine"] == engine and v["voice"] == voice), None))
    monkeypatch.setattr(casting_jobs, "valid_fx", lambda fx: fx is None or fx in {"robot:B", "inner:A"})
    monkeypatch.setattr(casting_jobs, "fx_levels", lambda: {"robot": ["A", "B"], "inner": ["A"]})
    monkeypatch.setattr(casting_jobs, "voice_catalog", lambda: VOICES)
    return casting


def cosy(**overrides):
    return {"engine": "cosyvoice", "voice": "longxiaocheng_v2", "rate": 1.0, "pitch": 1.0,
            "fx": None, "role": "dialogue", **overrides}


def edge(**overrides):
    return {"engine": "edge-tts", "voice": "en-US-AndrewNeural", "rate": "+0%", "pitch": "+0Hz",
            "fx": None, "role": "narration", **overrides}


def test_voice_catalog_and_audition(voice_stubs, monkeypatch):
    casting = voice_stubs
    client = casting["client"]
    catalog = client.get("/studio/casting/voice-catalog", headers=auth(casting)).json()
    assert catalog["voices"] == VOICES and catalog["fx"] == {"robot": ["A", "B"], "inner": ["A"]}

    project = make_project(casting)
    character = run(new_bible(project, name="阿宁"))
    location = run(new_bible(project, kind="location", name="旧邮局"))
    text = "我是阿宁，旧信要还回去。"
    url = f"/studio/projects/{project['id']}/casting/voices/audition"

    # 未开工确认。
    response = client.post(url, json={"item_id": character, "text": text, "variants": [cosy()]},
                           headers=auth(casting))
    assert response.status_code == 409
    confirm_setup(casting, project)
    item = item_by_bible(get_state(casting, project), character)
    location_item = item_by_bible(get_state(casting, project), location)

    assert client.post(url, json={"item_id": location_item["id"], "text": text, "variants": [cosy()]},
                       headers=auth(casting)).status_code == 409
    assert client.post(url, json={"item_id": item["id"], "text": "  ", "variants": [cosy()]},
                       headers=auth(casting)).status_code == 422
    assert client.post(url, json={"item_id": item["id"], "text": "x" * 121, "variants": [cosy()]},
                       headers=auth(casting)).status_code == 422
    assert client.post(url, json={"item_id": item["id"], "text": text, "variants": [cosy()] * 4},
                       headers=auth(casting)).status_code == 422
    for bad in (cosy(engine="edge-tts"), cosy(voice="nope"), cosy(fx="robot:Z"),
                cosy(rate=0.1), cosy(rate="fast"), cosy(role="monologue")):
        assert client.post(url, json={"item_id": item["id"], "text": text, "variants": [bad]},
                           headers=auth(casting)).status_code == 422, bad
    for bad in (edge(rate="5%"), edge(pitch="+0"), edge(engine="cosyvoice"), edge(rate="-80%")):
        assert client.post(url, json={"item_id": item["id"], "text": text, "variants": [bad]},
                           headers=auth(casting)).status_code == 422, bad
    assert casting["calls"]["cosy"] == 0 and casting["calls"]["edge"] == 0

    response = client.post(url, json={"item_id": item["id"], "text": text,
                                      "variants": [cosy(), edge(), cosy(fx="robot:B", rate=1.2)]},
                           headers=auth(casting))
    assert response.status_code == 200
    jobs = [job for job in response.json()["jobs"] if job["kind"] == "tts"]
    assert len(jobs) == 3 and all(job["status"] == "queued" for job in jobs)
    stored = run(rows("SELECT * FROM studio_jobs WHERE kind='tts' ORDER BY media_provider"))
    amounts = {row["media_provider"]: row["reserved_amount"] for row in stored}
    assert float(amounts["cosyvoice"]) == pytest.approx(0.01)
    assert float(amounts["edge-tts"]) == 0
    specs = [json.loads(row["params_json"])["spec"] for row in stored]
    assert cosy() in specs and edge() in specs
    assert run(spend.today())["committed_cny"] == pytest.approx(0.02)
    assert casting["calls"]["cosy"] == 0 and casting["calls"]["edge"] == 0


def test_cosyvoice_audition_requires_ffmpeg_tools(voice_stubs, monkeypatch):
    """可优化 c：含 CosyVoice 变体时先查 ffmpeg / ffprobe，缺就 503 且不发任何付费请求。"""
    casting = voice_stubs
    client = casting["client"]
    project = make_project(casting)
    character = run(new_bible(project, name="阿宁"))
    confirm_setup(casting, project)
    item = item_by_bible(get_state(casting, project), character)
    url = f"/studio/projects/{project['id']}/casting/voices/audition"

    monkeypatch.setattr(casting_module.shutil, "which", lambda name: None)
    response = client.post(url, json={"item_id": item["id"], "text": "我是阿宁。", "variants": [cosy()]},
                           headers=auth(casting))
    assert response.status_code == 503 and "ffmpeg" in response.json()["detail"]
    assert run(rows("SELECT id FROM studio_jobs WHERE kind='tts'")) == []
    assert run(spend.today())["committed_cny"] == pytest.approx(0)

    # 混合批次里只要有一条 CosyVoice，也不能有半条任务落库。
    response = client.post(url, json={"item_id": item["id"], "text": "我是阿宁。",
                                      "variants": [edge(), cosy()]}, headers=auth(casting))
    assert response.status_code == 503
    assert run(rows("SELECT id FROM studio_jobs WHERE kind='tts'")) == []

    # edge-tts 不需要 ffmpeg，缺工具也能建任务。
    response = client.post(url, json={"item_id": item["id"], "text": "我是阿宁。", "variants": [edge()]},
                           headers=auth(casting))
    assert response.status_code == 200
    assert len([job for job in response.json()["jobs"] if job["kind"] == "tts"]) == 1
    assert casting["calls"]["cosy"] == 0 and casting["calls"]["edge"] == 0


def test_voice_approve_writes_spec(voice_stubs):
    casting = voice_stubs
    client = casting["client"]
    project = make_project(casting)
    character = run(new_bible(project, name="阿宁"))
    confirm_setup(casting, project)
    item = item_by_bible(get_state(casting, project), character)
    spec = {**cosy(), "role": "narration"}
    audition_asset = run(new_asset(project, item_id=item["id"], role="audition", kind="audio",
                                   version_no=1, spec=spec, text="我是阿宁。", duration_s=1.6,
                                   measured_lufs=-16.2))
    image_asset = run(new_asset(project, item_id=item["id"], role="sheet", version_no=1))
    url = f"/studio/casting/items/{item['id']}/voice/approve"

    assert client.post(url, json={"asset_id": image_asset}, headers=auth(casting)).status_code == 404
    response = client.post(url, json={"asset_id": audition_asset}, headers=auth(casting))
    assert response.status_code == 200
    body = response.json()
    assert body["voice"]["spec"] == spec and body["voice"]["approved_asset_id"] == audition_asset
    entry = body["voice"]["auditions"][0]
    assert entry == {"asset_id": audition_asset, "created_at": entry["created_at"],
                     "archived": False, "spec": spec, "text": "我是阿宁。", "duration_s": 1.6,
                     "measured_lufs": -16.2}


# ---------------------------------------------------------------------------
# 归属与删号
# ---------------------------------------------------------------------------

def test_ownership_404_and_account_deletion(casting):
    client = casting["client"]
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    bible = run(new_bible(project))
    item = item_by_bible(get_state(casting, project), bible)
    asset = run(new_asset(project, item_id=item["id"]))
    quote = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                        json={"items": [{"item_id": item["id"], "versions": 1}]}, headers=auth(casting)).json()
    assert quote["total"] == 0.3

    for name in ("other", "outsider"):
        headers = auth(casting, name)
        checks = [
            client.get(f"/studio/projects/{project['id']}/casting", headers=headers),
            client.put(f"/studio/projects/{project['id']}/casting/setup",
                       json={"resolution": "480P", "video_model": "wan", "language": "zh"}, headers=headers),
            client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                        json={"items": [{"item_id": item["id"], "versions": 1}]}, headers=headers),
            client.post(f"/studio/projects/{project['id']}/casting/sheets/start",
                        json={"quote_id": quote["id"]}, headers=headers),
            client.post(f"/studio/projects/{project['id']}/casting/voices/audition",
                        json={"item_id": item["id"], "text": "你好", "variants": [cosy()]}, headers=headers),
            client.patch(f"/studio/casting/items/{item['id']}", json={"extra_prompt": "x"}, headers=headers),
            client.post(f"/studio/casting/items/{item['id']}/approve", json={"asset_id": asset}, headers=headers),
            client.post(f"/studio/casting/assets/{asset}/archive", headers=headers),
        ]
        for response in checks:
            assert response.status_code == 404, (name, response.text)
            assert response.headers["cache-control"] == "private, no-store"
    response = client.get(f"/studio/projects/{project['id']}/casting")
    assert response.status_code == 404

    import database
    other_project = make_project(casting, owner="other", title="别人的项目")
    summary = run(database.delete_account_data("owner"))
    assert summary["deleted"] is True
    assert run(rows("SELECT id FROM studio_projects WHERE owner='owner'")) == []
    assert run(rows("SELECT id FROM studio_items WHERE owner='owner'")) == []
    assert run(rows("SELECT id FROM studio_assets WHERE owner='owner'")) == []
    assert run(rows("SELECT id FROM studio_quotes WHERE owner='owner'")) == []
    assert [row["id"] for row in run(rows("SELECT id FROM studio_projects WHERE owner='other'"))] == [other_project["id"]]
    assert run(rows("SELECT id FROM studio_items WHERE owner='other'")) == []

