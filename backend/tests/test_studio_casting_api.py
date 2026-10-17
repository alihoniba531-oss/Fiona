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

    calls = {"image": 0, "cosy": 0, "edge": 0, "doubao": 0, "scheduled": []}
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

    async def fake_doubao(*args, **kwargs):
        calls["doubao"] += 1
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
    monkeypatch.setattr(casting_jobs, "_synthesize_doubao", fake_doubao)
    monkeypatch.setattr(casting_jobs, "doubao_configured", lambda: True)
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

    assert casting["calls"] == {"image": 0, "cosy": 0, "edge": 0, "doubao": 0, "scheduled": []}
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
    assert state["prices"] == {"seedream_cny": 0.30, "cosyvoice_cny_per_10k_chars": 2.0,
                               "doubao_cny_per_10k_chars": 3.0}


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
           "gender": "male", "note": ""},
          {"engine": "doubao", "voice": "zh_female_sophie_uranus_bigtts", "label": "魅力苏菲 2.0",
           "lang": "zh", "gender": "female", "note": "高冷御姐，外冷内柔（官方标注指令遵循）"}]


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
            "fx": None, "role": "dialogue", "direction": None, **overrides}


def edge(**overrides):
    return {"engine": "edge-tts", "voice": "en-US-AndrewNeural", "rate": "+0%", "pitch": "+0Hz",
            "fx": None, "role": "narration", "direction": None, **overrides}


def doubao(**overrides):
    return {"engine": "doubao", "voice": "zh_female_sophie_uranus_bigtts", "rate": 1.0,
            "pitch": 0, "fx": None, "role": "dialogue", "direction": None, **overrides}


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


def test_doubao_audition_validation_and_spec(voice_stubs):
    """豆包方案：rate 0.5–2.0、pitch 为 -12~12 整数、指示只对豆包开放。"""
    casting = voice_stubs
    client = casting["client"]
    project = make_project(casting)
    character = run(new_bible(project, name="阿宁"))
    confirm_setup(casting, project)
    item = item_by_bible(get_state(casting, project), character)
    url = f"/studio/projects/{project['id']}/casting/voices/audition"
    text = "我是阿宁。"
    direction = "压低声音，不安里带着一点倔强"

    def post(variant):
        return client.post(url, json={"item_id": item["id"], "text": text, "variants": [variant]},
                           headers=auth(casting))

    # 非豆包引擎不能带表演指示。
    assert post(cosy(direction=direction)).status_code == 422
    assert post(edge(direction=direction)).status_code == 422
    # 201 字指示在请求层就被 max_length 拦下。
    assert post(doubao(direction="长" * 201)).status_code == 422
    assert post(doubao(pitch=1.5)).status_code == 422
    assert post(doubao(pitch="0")).status_code == 422
    assert post(doubao(pitch=True)).status_code == 422
    assert post(doubao(pitch=13)).status_code == 422
    assert post(doubao(pitch=-13)).status_code == 422
    for bad in (doubao(rate=0.4), doubao(rate=2.1), doubao(rate="fast")):
        assert post(bad).status_code == 422, bad
    assert post(doubao(voice="longxiaocheng_v2")).status_code == 422
    assert post(doubao(fx="robot:Z")).status_code == 422
    assert casting["calls"]["cosy"] == 0 and casting["calls"]["edge"] == 0
    assert casting["calls"]["doubao"] == 0

    # 值是整数的浮点（3.0）按整数接受；指示去首尾空白后写进 spec。
    response = post(doubao(rate=1.2, pitch=3.0, direction=f"  {direction}  "))
    assert response.status_code == 200, response.text
    jobs = [job for job in response.json()["jobs"] if job["kind"] == "tts"]
    assert len(jobs) == 1 and jobs[0]["reserved_amount"] == pytest.approx(0.01)
    stored = run(rows("SELECT params_json,media_provider FROM studio_jobs WHERE kind='tts'"))
    assert len(stored) == 1 and stored[0]["media_provider"] == "doubao"
    spec = json.loads(stored[0]["params_json"])["spec"]
    assert spec == doubao(rate=1.2, pitch=3, direction=direction)
    assert run(spend.today())["committed_cny"] == pytest.approx(0.01)
    assert casting["calls"]["doubao"] == 0


def test_doubao_audition_requires_key_and_ffmpeg(voice_stubs, monkeypatch):
    """块 B：缺 Key / 缺 ffmpeg 都返回 503，预检在任何付费请求之前。"""
    casting = voice_stubs
    client = casting["client"]
    project = make_project(casting)
    character = run(new_bible(project, name="阿宁"))
    confirm_setup(casting, project)
    item = item_by_bible(get_state(casting, project), character)
    url = f"/studio/projects/{project['id']}/casting/voices/audition"

    monkeypatch.setattr(casting_jobs, "doubao_configured", lambda: False)
    response = client.post(url, json={"item_id": item["id"], "text": "我是阿宁。", "variants": [doubao()]},
                           headers=auth(casting))
    assert response.status_code == 503 and "VOLC_SPEECH_API_KEY" in response.json()["detail"]
    assert run(rows("SELECT id FROM studio_jobs WHERE kind='tts'")) == []
    assert casting["calls"]["doubao"] == 0

    # 混合批次里只要有一条豆包，同样在落库前 503。
    response = client.post(url, json={"item_id": item["id"], "text": "我是阿宁。",
                                      "variants": [edge(), doubao()]}, headers=auth(casting))
    assert response.status_code == 503
    assert run(rows("SELECT id FROM studio_jobs WHERE kind='tts'")) == []

    monkeypatch.setattr(casting_jobs, "doubao_configured", lambda: True)
    monkeypatch.setattr(casting_module.shutil, "which", lambda name: None)
    response = client.post(url, json={"item_id": item["id"], "text": "我是阿宁。", "variants": [doubao()]},
                           headers=auth(casting))
    assert response.status_code == 503 and "ffmpeg" in response.json()["detail"]
    assert run(rows("SELECT id FROM studio_jobs WHERE kind='tts'")) == []
    assert run(spend.today())["committed_cny"] == pytest.approx(0)
    assert casting["calls"]["doubao"] == 0


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
    assert body["voice"]["spec"] == {**spec, "baseline": None}
    assert body["voice"]["approved_asset_id"] == audition_asset
    entry = body["voice"]["auditions"][0]
    assert entry == {"asset_id": audition_asset, "created_at": entry["created_at"],
                     "archived": False, "spec": spec, "text": "我是阿宁。", "duration_s": 1.6,
                     "measured_lufs": -16.2}


def test_voice_approve_baseline_defaults_to_direction(voice_stubs):
    """定档时方向写进 spec；baseline 未传时默认取该条试听的指示。"""
    casting = voice_stubs
    client = casting["client"]
    project = make_project(casting)
    character = run(new_bible(project, name="阿宁"))
    confirm_setup(casting, project)
    item = item_by_bible(get_state(casting, project), character)
    direction = "压低声音，不安里带着一点倔强"
    spec = doubao(direction=direction)
    asset = run(new_asset(project, item_id=item["id"], role="audition", kind="audio",
                          version_no=1, spec=spec, text="我是阿宁。", duration_s=1.6,
                          measured_lufs=-16.2))
    url = f"/studio/casting/items/{item['id']}/voice/approve"

    body = client.post(url, json={"asset_id": asset}, headers=auth(casting)).json()
    assert body["voice"]["spec"] == {**spec, "baseline": direction}

    body = client.post(url, json={"asset_id": asset, "baseline": "  克制，像在自言自语  "},
                       headers=auth(casting)).json()
    assert body["voice"]["spec"]["direction"] == direction
    assert body["voice"]["spec"]["baseline"] == "克制，像在自言自语"

    # 空白 baseline 视为未传，仍回落到试听指示。
    body = client.post(url, json={"asset_id": asset, "baseline": "   "}, headers=auth(casting)).json()
    assert body["voice"]["spec"]["baseline"] == direction

    response = client.post(url, json={"asset_id": asset, "baseline": "基" * 201}, headers=auth(casting))
    assert response.status_code == 422


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


# ---------------------------------------------------------------------------
# 造型说明（块 A）
# ---------------------------------------------------------------------------

async def mark_looks_succeeded(project, looks):
    async with store.connection(transaction=True) as db:
        await db.execute("""UPDATE studio_jobs SET status='succeeded',result_json=?,actual_amount='0',
            finished_at=? WHERE kind='brain' AND task='casting_look' AND project_id=?""",
                         (store._json({"looks": looks}), store.utcnow(), project["id"]))


async def set_bible(bible_id, **fields):
    assignments = ",".join(f"{key}=?" for key in fields)
    async with store.connection(transaction=True) as db:
        await db.execute(f"UPDATE studio_bible SET {assignments} WHERE id=?", (*fields.values(), bible_id))


def looks_quote(casting, project, item_ids):
    return casting["client"].post(f"/studio/projects/{project['id']}/casting/looks/quote",
                                  json={"item_ids": item_ids}, headers=auth(casting))


def looks_start(casting, project, quote_id):
    return casting["client"].post(f"/studio/projects/{project['id']}/casting/looks/start",
                                  json={"quote_id": quote_id}, headers=auth(casting))


def test_looks_quote_gates_author_exclusion_and_batching(casting):
    client = casting["client"]
    project = make_project(casting)
    bibles = [run(new_bible(project, name=f"人物{index}")) for index in range(12)]
    prop = run(new_bible(project, kind="prop", name="旧邮包", appearance="", description="帆布邮包"))
    state = get_state(casting, project)
    ids = [item_by_bible(state, bible)["id"] for bible in bibles]
    ids.append(item_by_bible(state, prop)["id"])

    casting["gates"]["g0"] = False
    assert looks_quote(casting, project, ids).status_code == 409
    casting["gates"]["g0"] = True
    assert looks_quote(casting, project, ids[:1]).status_code == 409
    confirm_setup(casting, project)
    response = looks_quote(casting, project, ids[:1])
    assert response.status_code == 409 and "风格" in response.json()["detail"]
    choose_style(casting, project)

    assert looks_quote(casting, project, []).status_code == 422
    assert looks_quote(casting, project, ids * 3).status_code == 422
    assert looks_quote(casting, project, [str(uuid.uuid4())]).status_code == 404

    location = run(new_bible(project, kind="location", name="车站", appearance="", description="旧站台"))
    location_id = item_by_bible(get_state(casting, project), location)["id"]
    response = looks_quote(casting, project, [ids[0], location_id])
    assert response.status_code == 409 and "场景" in response.json()["detail"]

    orphan_bible = run(new_bible(project, name="孤儿"))
    orphan_id = item_by_bible(get_state(casting, project), orphan_bible)["id"]
    run(set_bible(orphan_bible, archived=1))
    response = looks_quote(casting, project, [orphan_id])
    assert response.status_code == 409 and "总表" in response.json()["detail"]

    author = client.patch(f"/studio/casting/items/{ids[0]}", json={"look": {"hair": "作者手写"}},
                          headers=auth(casting))
    assert author.status_code == 200 and author.json()["look_source"] == "author"
    response = looks_quote(casting, project, [ids[0]])
    assert response.status_code == 409 and response.json()["detail"] == "这些条目的造型说明已由作者修改"

    quote = looks_quote(casting, project, ids)
    assert quote.status_code == 200, quote.text
    body = quote.json()
    assert body["kind"] == "casting_looks" and body["currency"] == "USD"
    assert [line["versions"] for line in body["items"]] == [1, 1, 1]
    assert [line["name"] for line in body["items"]] == [
        "造型说明 第 1 批（4 个条目）", "造型说明 第 2 批（4 个条目）", "造型说明 第 3 批（4 个条目）"]
    assert [line["item_count"] for line in body["items"]] == [4, 4, 4]
    assert body["total"] == pytest.approx(sum(line["unit"] for line in body["items"]))


def test_looks_start_writes_back_and_protects_author_and_orphans(casting):
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    bibles = [run(new_bible(project, name=name)) for name in ("阿宁", "老周", "小满", "作者条目")]
    state = get_state(casting, project)
    ids = [item_by_bible(state, bible)["id"] for bible in bibles]
    assert [item_by_bible(state, bible)["look"] for bible in bibles] == [None] * 4
    assert [item_by_bible(state, bible)["look_source"] for bible in bibles] == [None] * 4
    assert casting["client"].patch(f"/studio/casting/items/{ids[3]}", json={"look": {"hair": "作者发型"}},
                                   headers=auth(casting)).status_code == 200

    quote = looks_quote(casting, project, ids).json()
    assert len(quote["items"]) == 1
    response = looks_start(casting, project, quote["id"])
    assert response.status_code == 200, response.text
    started = response.json()
    job = next(entry for entry in started["jobs"] if entry["task"] == "casting_look")
    assert job["kind"] == "brain" and job["status"] == "queued"
    assert job["id"] in casting["calls"]["scheduled"]
    stored = run(rows("SELECT * FROM studio_jobs WHERE task='casting_look'"))
    assert len(stored) == 1 and stored[0]["status"] == "queued"
    assert "looks" not in (stored[0].get("result") or {})
    assert looks_start(casting, project, quote["id"]).status_code == 409

    # 任务进行期间作者改了阿宁、老周被移出总表；结果里还夹了不属于本次请求的 id。
    assert casting["client"].patch(f"/studio/casting/items/{ids[0]}", json={"look": {"hair": "期间改成"}},
                                   headers=auth(casting)).status_code == 200
    run(set_bible(bibles[1], merged_into="other-bible"))
    look_a = {"hair": "导演发型", "makeup": "导演妆容", "top": "灰蓝工装", "bottom": "束脚裤",
              "footwear": "帆布鞋", "accessories": "邮差包", "materials": "棉布磨损", "palette": "灰蓝"}
    look_b = {"hair": "导演发型B", "makeup": "妆容B", "top": "上装B", "bottom": "下装B",
              "footwear": "鞋B", "accessories": "配饰B", "materials": "材质B", "palette": "主色B"}
    unknown = {"hair": "不该写回", "makeup": "x", "top": "x", "bottom": "x",
               "footwear": "x", "accessories": "x", "materials": "x", "palette": "x"}
    run(mark_looks_succeeded(project, [
        {"item_id": ids[0], "kind": "character", "look": look_a},
        {"item_id": ids[1], "kind": "character", "look": look_b},
        {"item_id": ids[2], "kind": "character", "look": look_b},
        {"item_id": str(uuid.uuid4()), "kind": "character", "look": unknown},
    ]))

    state = get_state(casting, project)
    assert item_by_bible(state, bibles[0])["look"] == {"hair": "期间改成"}
    assert item_by_bible(state, bibles[0])["look_source"] == "author"
    assert item_by_bible(state, bibles[1])["look"] is None
    assert item_by_bible(state, bibles[2])["look"] == look_b
    assert item_by_bible(state, bibles[2])["look_source"] == "director"
    assert item_by_bible(state, bibles[3])["look"] == {"hair": "作者发型"}
    succeeded = next(entry for entry in state["jobs"] if entry["task"] == "casting_look")
    assert succeeded["status"] == "succeeded"

    # 导演任务再次被读到时不覆盖后来的作者修改。
    assert casting["client"].patch(f"/studio/casting/items/{ids[2]}", json={"look": {"hair": "作者再改"}},
                                   headers=auth(casting)).status_code == 200
    state = get_state(casting, project)
    assert item_by_bible(state, bibles[2])["look"]["hair"] == "作者再改"
    assert item_by_bible(state, bibles[2])["look_source"] == "author"


def test_looks_start_revalidates_locked_features_from_quote_payload(casting):
    client = casting["client"]
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    bibles = [run(new_bible(project, name=name)) for name in ("阿宁", "老周")]
    state = get_state(casting, project)
    ids = [item_by_bible(state, bible)["id"] for bible in bibles]
    for item_id in ids:
        assert client.patch(f"/studio/casting/items/{item_id}",
                            json={"locked_features": "右眉有疤"}, headers=auth(casting)).status_code == 200

    unchanged = looks_quote(casting, project, [ids[0]]).json()
    response = looks_start(casting, project, unchanged["id"])
    assert response.status_code == 200, response.text
    assert len(run(rows("SELECT id FROM studio_jobs WHERE task='casting_look'"))) == 1

    changed = looks_quote(casting, project, [ids[1]]).json()
    assert client.patch(f"/studio/casting/items/{ids[1]}",
                        json={"locked_features": "左眉有疤"}, headers=auth(casting)).status_code == 200
    response = looks_start(casting, project, changed["id"])
    assert response.status_code == 409 and "锁定特征已修改" in response.json()["detail"]
    assert run(rows("SELECT status FROM studio_quotes WHERE id=?", (changed["id"],)))[0]["status"] == "open"


def test_looks_start_rejects_second_open_quote_and_keeps_it_open(casting):
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    bibles = [run(new_bible(project, name=name)) for name in ("阿宁", "老周")]
    state = get_state(casting, project)
    ids = [item_by_bible(state, bible)["id"] for bible in bibles]

    first = looks_quote(casting, project, ids).json()
    second = looks_quote(casting, project, ids).json()
    assert first["id"] != second["id"]
    assert looks_start(casting, project, first["id"]).status_code == 200

    response = looks_start(casting, project, second["id"])
    assert response.status_code == 409
    assert response.json()["detail"] == "这些条目正在补全造型，请等完成后再报价"
    stored = run(rows("SELECT * FROM studio_jobs WHERE task='casting_look'"))
    assert len(stored) == 1 and float(stored[0]["reserved_amount"]) > 0
    statuses = {row["id"]: row["status"] for row in run(rows("SELECT id,status FROM studio_quotes"))}
    assert statuses[first["id"]] == "confirmed" and statuses[second["id"]] == "open"


def test_patch_look_validates_fields_and_merges(casting):
    client = casting["client"]
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    character = run(new_bible(project, name="阿宁"))
    prop = run(new_bible(project, kind="prop", name="旧邮包", appearance="", description="帆布邮包"))
    location = run(new_bible(project, kind="location", name="车站", appearance="", description="旧站台"))
    state = get_state(casting, project)
    item_id = item_by_bible(state, character)["id"]
    prop_id = item_by_bible(state, prop)["id"]
    location_id = item_by_bible(state, location)["id"]

    response = client.patch(f"/studio/casting/items/{item_id}", json={"look": {"hair": "短发"}},
                            headers=auth(casting))
    assert response.status_code == 200
    assert response.json()["look"] == {"hair": "短发"} and response.json()["look_source"] == "author"
    response = client.patch(f"/studio/casting/items/{item_id}",
                            json={"look": {"makeup": "裸妆", "top": "棉布外套"}}, headers=auth(casting))
    assert response.json()["look"] == {"hair": "短发", "makeup": "裸妆", "top": "棉布外套"}
    assert response.json()["look_source"] == "author"

    assert client.patch(f"/studio/casting/items/{item_id}", json={"look": {"unknown": "x"}},
                        headers=auth(casting)).status_code == 422
    assert client.patch(f"/studio/casting/items/{item_id}", json={"look": {"hair": "长" * 201}},
                        headers=auth(casting)).status_code == 422
    assert client.patch(f"/studio/casting/items/{item_id}", json={"look": {"hair": 3}},
                        headers=auth(casting)).status_code == 422
    assert client.patch(f"/studio/casting/items/{location_id}", json={"look": {"form": "站牌"}},
                        headers=auth(casting)).status_code == 422
    response = client.patch(f"/studio/casting/items/{prop_id}",
                            json={"look": {"form": "方形帆布包", "material": "蜡布"}}, headers=auth(casting))
    assert response.status_code == 200 and response.json()["look_source"] == "author"
    assert response.json()["look"] == {"form": "方形帆布包", "material": "蜡布"}
    assert client.patch(f"/studio/casting/items/{prop_id}", json={"look": {"hair": "短发"}},
                        headers=auth(casting)).status_code == 422
    assert client.patch(f"/studio/casting/items/{item_id}", json={"look": "not-a-dict"},
                        headers=auth(casting)).status_code == 422



# ---------------------------------------------------------------------------
# 返修 R1（块 A）
# ---------------------------------------------------------------------------

def insert_look_job(project, item_ids, looks, *, created_at, finished_at=None,
                    status="succeeded", owner="owner"):
    """直接落一条已完成 / 指定状态的造型任务，便于构造时序与损坏结果。"""
    params = {"item_ids": list(item_ids),
              "inputs": {"items": [{"item_id": item_id} for item_id in item_ids]}}

    async def write():
        async with store.connection(transaction=True) as db:
            qid = await casting_jobs._synthetic_quote(db, project["id"], owner, f"look-{uuid.uuid4()}")
            job_id = str(uuid.uuid4())
            await db.execute("""INSERT INTO studio_jobs(id,project_id,owner,kind,provider,model,
                params_json,fingerprint,quote_id,quote_item_id,status,est_min_cny,est_max_cny,
                created_at,updated_at,confirmed_day,task,result_json,currency,brain_provider,finished_at)
                VALUES(?,?,?,'brain','wan','claude-sonnet-5-5',?,?,?,?,?,'0','0',?,?,?,'casting_look',?,'USD','claude',?)""",
                             (job_id, project["id"], owner, store._json(params), job_id, qid, job_id, status,
                              created_at, created_at, spend.shanghai_day(created_at),
                              store._json({"looks": looks}), finished_at or created_at))
            return job_id

    return run(write())


def stored_spec(item_id):
    row = run(rows("SELECT spec_json FROM studio_items WHERE id=?", (item_id,)))[0]
    return json.loads(row["spec_json"])


LOOK_FULL = {"hair": "齐耳短发", "makeup": "裸妆", "top": "灰蓝工装", "bottom": "束脚裤",
             "footwear": "帆布鞋", "accessories": "邮差包", "materials": "棉布磨损", "palette": "灰蓝"}


def make_item(casting, project, **kwargs):
    bible = run(new_bible(project, **kwargs))
    return bible, item_by_bible(get_state(casting, project), bible)["id"]


def test_looks_quote_currency_follows_provider(casting):
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    _, item_id = make_item(casting, project)

    claude = looks_quote(casting, project, [item_id])
    assert claude.status_code == 200, claude.text
    assert claude.json()["currency"] == "USD"

    async def set_qwen():
        async with store.connection(transaction=True) as db:
            await db.execute("UPDATE studio_projects SET brain_provider='qwen' WHERE id=? AND owner=?",
                             (project["id"], "owner"))

    run(set_qwen())
    qwen = looks_quote(casting, project, [item_id])
    assert qwen.status_code == 200, qwen.text
    assert qwen.json()["currency"] == "CNY"


def test_look_results_use_created_at_watermark(casting, monkeypatch):
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    _, item_id = make_item(casting, project)
    old_look = {**LOOK_FULL, "hair": "旧发型"}
    new_look = {**LOOK_FULL, "hair": "新发型"}
    # 旧请求创建得早、完成得晚；按完成时间回放会翻回旧值。
    insert_look_job(project, [item_id], [{"item_id": item_id, "kind": "character", "look": old_look}],
                    created_at="2026-01-01T00:00:00+00:00", finished_at="2026-01-03T00:00:00+00:00")
    insert_look_job(project, [item_id], [{"item_id": item_id, "kind": "character", "look": new_look}],
                    created_at="2026-01-02T00:00:00+00:00", finished_at="2026-01-02T12:00:00+00:00")

    state = get_state(casting, project)
    item = next(item for item in state["items"] if item["id"] == item_id)
    assert item["look"] == new_look and item["look_source"] == "director"
    spec = stored_spec(item_id)
    assert spec["look_job_created_at"] == "2026-01-02T00:00:00+00:00"
    assert "look_job_ids" not in spec

    calls = []
    real = casting_module._clean_look
    monkeypatch.setattr(casting_module, "_clean_look",
                        lambda kind, value: calls.append(value) or real(kind, value))
    get_state(casting, project)
    assert calls == []


def test_look_results_apply_before_quote_and_start(casting):
    client = casting["client"]
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    _, item_id = make_item(casting, project)
    first = {**LOOK_FULL, "hair": "第一次导演"}
    insert_look_job(project, [item_id], [{"item_id": item_id, "kind": "character", "look": first}],
                    created_at="2026-01-01T00:00:00+00:00")
    response = client.post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                           json={"items": [{"item_id": item_id, "versions": 1}]}, headers=auth(casting))
    assert response.status_code == 200, response.text
    assert stored_spec(item_id)["look"] == first

    quote = response.json()
    second = {**LOOK_FULL, "hair": "第二次导演"}
    insert_look_job(project, [item_id], [{"item_id": item_id, "kind": "character", "look": second}],
                    created_at="2026-01-02T00:00:00+00:00")
    started = client.post(f"/studio/projects/{project['id']}/casting/sheets/start",
                          json={"quote_id": quote["id"]}, headers=auth(casting))
    assert started.status_code == 200, started.text
    assert stored_spec(item_id)["look"] == second


def test_patch_look_merges_on_top_of_pending_director_result(casting):
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    _, item_id = make_item(casting, project)
    insert_look_job(project, [item_id],
                    [{"item_id": item_id, "kind": "character",
                      "look": {"hair": "导演发型", "makeup": "导演妆容"}}],
                    created_at="2026-01-01T00:00:00+00:00")
    response = casting["client"].patch(f"/studio/casting/items/{item_id}",
                                      json={"look": {"hair": "作者发型"}}, headers=auth(casting))
    assert response.status_code == 200, response.text
    assert response.json()["look"] == {"hair": "作者发型", "makeup": "导演妆容"}
    assert response.json()["look_source"] == "author"


def test_patch_look_rejects_empty_object_and_clears_blank_result(casting):
    client = casting["client"]
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    _, item_id = make_item(casting, project)

    assert client.patch(f"/studio/casting/items/{item_id}", json={"look": {}},
                        headers=auth(casting)).status_code == 422
    response = client.patch(f"/studio/casting/items/{item_id}", json={"look": {"hair": ""}},
                            headers=auth(casting))
    assert response.status_code == 200, response.text
    assert response.json()["look"] is None and response.json()["look_source"] is None
    # 清空后可重新交给导演补全。
    assert looks_quote(casting, project, [item_id]).status_code == 200


def test_looks_quote_skips_inflight_items_and_jobs_expose_item_ids(casting):
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    bibles = [run(new_bible(project, name=name)) for name in ("阿宁", "老周")]
    state = get_state(casting, project)
    ids = [item_by_bible(state, bible)["id"] for bible in bibles]

    quote = looks_quote(casting, project, [ids[0]])
    started = looks_start(casting, project, quote.json()["id"])
    assert started.status_code == 200, started.text
    job = next(entry for entry in started.json()["jobs"] if entry["task"] == "casting_look")
    assert job["item_ids"] == [ids[0]]
    stored = run(rows("SELECT params_json FROM studio_jobs WHERE task='casting_look'"))[0]
    assert json.loads(stored["params_json"])["item_ids"] == [ids[0]]

    response = looks_quote(casting, project, [ids[0]])
    assert response.status_code == 409 and "正在补全" in response.json()["detail"]
    response = looks_quote(casting, project, [ids[0], ids[1]])
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "造型说明 第 1 批（1 个条目）"


def test_looks_start_revalidates_quote(casting):
    client = casting["client"]
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    bibles = [run(new_bible(project, name=name)) for name in ("锁定", "手改", "孤儿")]
    state = get_state(casting, project)
    ids = [item_by_bible(state, bible)["id"] for bible in bibles]

    quote = looks_quote(casting, project, [ids[0]]).json()
    assert client.patch(f"/studio/casting/items/{ids[0]}", json={"locked_features": "新特征"},
                        headers=auth(casting)).status_code == 200
    response = looks_start(casting, project, quote["id"])
    assert response.status_code == 409 and "重新报价" in response.json()["detail"]

    quote = looks_quote(casting, project, [ids[1]]).json()
    assert client.patch(f"/studio/casting/items/{ids[1]}", json={"look": {"hair": "作者改"}},
                        headers=auth(casting)).status_code == 200
    response = looks_start(casting, project, quote["id"])
    assert response.status_code == 409 and "重新报价" in response.json()["detail"]

    quote = looks_quote(casting, project, [ids[2]]).json()
    run(set_bible(bibles[2], archived=1))
    response = looks_start(casting, project, quote["id"])
    assert response.status_code == 409 and "重新报价" in response.json()["detail"]


def test_corrupt_look_result_is_skipped_with_warning(casting, monkeypatch, caplog):
    project = make_project(casting)
    confirm_setup(casting, project)
    choose_style(casting, project)
    bibles = [run(new_bible(project, name=name)) for name in ("坏结果", "好结果")]
    state = get_state(casting, project)
    ids = [item_by_bible(state, bible)["id"] for bible in bibles]
    insert_look_job(project, ids, [
        {"item_id": ids[0], "kind": "character", "look": {"hair": "坏"}},
        {"item_id": ids[1], "kind": "character", "look": {"hair": "好"}},
    ], created_at="2026-01-01T00:00:00+00:00")

    real = casting_module._clean_look

    def clean(kind, value):
        if value.get("hair") == "坏":
            raise RuntimeError("损坏的结果")
        return real(kind, value)

    monkeypatch.setattr(casting_module, "_clean_look", clean)
    with caplog.at_level("WARNING"):
        state = get_state(casting, project)
    assert item_by_bible(state, bibles[0])["look"] is None
    assert item_by_bible(state, bibles[1])["look"] == {"hair": "好"}
    assert any("造型说明" in record.message for record in caplog.records)
