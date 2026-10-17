# -*- coding: utf-8 -*-
"""WO3d 块 A：定妆出图 / 声线任务的建行、预留、派发、执行与结算。

隔离：独立 SQLite + 全部块 B / 块 C 函数 monkeypatch 成假实现；付费调用只在这里
显式驱动 `casting_jobs.execute`，绝不真正出网。块 B（providers/audio）缺失时相关
分类用例自动跳过，其余用例仍可运行。
"""
import asyncio
from decimal import Decimal
import io
import json
import uuid

import httpx
import pytest

from studio import casting_jobs, pricing, spend, store

try:  # 块 B 尚未实现时也要能收集本文件
    from studio.providers.media_errors import MediaCallError
except Exception:  # pragma: no cover - 仅在缺块 B 时走到
    MediaCallError = None


class SheetResult:
    def __init__(self, *, width=2560, height=1440, model="seedream-5-pro", png=b"\x89PNG-sheet"):
        self.png, self.width, self.height, self.model = png, width, height, model


class RawAudio:
    def __init__(self, *, audio=b"raw-audio", audio_format="wav", chars=0, engine="cosyvoice", voice=""):
        self.audio, self.audio_format, self.chars, self.engine, self.voice = audio, audio_format, chars, engine, voice
        self.words = None


class Processed:
    def __init__(self, *, duration_s=1.25, measured_lufs=-16.2):
        self.wav, self.sample_rate, self.samples = b"processed-wav", 48000, 60000
        self.duration_s, self.measured_lufs, self.true_peak = duration_s, measured_lufs, -1.5


@pytest.fixture
def casting_db(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "casting.db"))
    monkeypatch.setenv("FIONA_STUDIO_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("FIONA_STUDIO", "1")
    monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "300")
    monkeypatch.setenv("FIONA_STUDIO_MAX_QUOTE_CNY", "100")

    async def initialize():
        async with store.connection(transaction=True) as db:
            await db.execute("CREATE TABLE users(username TEXT PRIMARY KEY)")
            await db.execute("INSERT INTO users(username) VALUES('author')")
            for statement in store.STUDIO_TABLES_DDL:
                await db.execute(statement)

    asyncio.run(initialize())
    return tmp_path


@pytest.fixture
def paid(monkeypatch):
    """全部块 B / 块 C 的假实现 + 派发打桩；返回可观察的调用记录。"""
    calls = {"image": [], "cosy": [], "edge": [], "doubao": [], "voice": [], "discarded": [], "saved": []}
    state = {"image_exc": None, "cosy_exc": None, "edge_exc": None, "doubao_exc": None, "save_exc": None,
             "image_result": SheetResult(), "processed": Processed()}

    async def fake_image(prompt, *, size, reference_images):
        calls["image"].append({"prompt": prompt, "size": size, "references": list(reference_images)})
        if state["image_exc"] is not None:
            raise state["image_exc"]
        return state["image_result"]

    async def fake_cosy(text, *, voice, rate, pitch):
        calls["cosy"].append({"text": text, "voice": voice, "rate": rate, "pitch": pitch})
        if state["cosy_exc"] is not None:
            raise state["cosy_exc"]
        return RawAudio(chars=len(text), engine="cosyvoice", voice=voice)

    async def fake_edge(text, *, voice, rate, pitch):
        calls["edge"].append({"text": text, "voice": voice, "rate": rate, "pitch": pitch})
        if state["edge_exc"] is not None:
            raise state["edge_exc"]
        return RawAudio(audio_format="mp3", engine="edge-tts", voice=voice)

    async def fake_doubao(text, *, voice, rate, pitch, direction):
        calls["doubao"].append({"text": text, "voice": voice, "rate": rate, "pitch": pitch,
                                "direction": direction})
        if state["doubao_exc"] is not None:
            raise state["doubao_exc"]
        return RawAudio(audio_format="mp3", engine="doubao", voice=voice, chars=len(text))

    async def fake_process(raw, *, input_format, fx, target_lufs):
        calls["voice"].append({"fx": fx, "target_lufs": target_lufs, "format": input_format})
        return state["processed"]

    async def fake_save_image(project_id, data, metadata):
        calls["saved"].append(("image", project_id, metadata))
        if state["save_exc"] is not None:
            raise state["save_exc"]
        return {"rel_path": f"{project_id}/images/sheet.png", "sha256": uuid.uuid4().hex * 2,
                "bytes": len(data)}

    async def fake_save_audio(project_id, data):
        calls["saved"].append(("audio", project_id, len(data)))
        if state["save_exc"] is not None:
            raise state["save_exc"]
        return {"rel_path": f"{project_id}/audio/audition.wav", "sha256": uuid.uuid4().hex * 2,
                "bytes": len(data)}

    async def fake_inspect(data):
        return {"width": 2560, "height": 1440}

    async def fake_reference_bytes(asset):
        calls.setdefault("references", []).append(asset["id"])
        return b"reference-bytes"

    async def fake_discard(rel_path):
        calls["discarded"].append(rel_path)

    monkeypatch.setattr(casting_jobs, "_generate_sheet", fake_image)
    monkeypatch.setattr(casting_jobs, "_synthesize_cosy", fake_cosy)
    monkeypatch.setattr(casting_jobs, "_synthesize_edge", fake_edge)
    monkeypatch.setattr(casting_jobs, "_synthesize_doubao", fake_doubao)
    monkeypatch.setattr(casting_jobs, "_process_voice", fake_process)
    monkeypatch.setattr(casting_jobs, "_save_image", fake_save_image)
    monkeypatch.setattr(casting_jobs, "_save_audio", fake_save_audio)
    monkeypatch.setattr(casting_jobs, "_inspect_image", fake_inspect)
    monkeypatch.setattr(casting_jobs, "_reference_bytes", fake_reference_bytes)
    monkeypatch.setattr(casting_jobs, "_discard_file", fake_discard)
    monkeypatch.setattr(casting_jobs, "_build_sheet_prompt", lambda **kwargs: "组装后的定妆提示词")
    monkeypatch.setattr(casting_jobs, "_reference_note", lambda kind, derived: f"note:{kind}:{derived}")
    scheduled = []
    real_schedule = casting_jobs._schedule
    monkeypatch.setattr(casting_jobs, "_schedule", lambda jid: scheduled.append(jid))
    calls["references"] = []
    return {"calls": calls, "state": state, "scheduled": scheduled, "real_schedule": real_schedule}


# ---------------------------------------------------------------------------
# 建数据
# ---------------------------------------------------------------------------

async def new_project(title="定妆项目", style=None):
    project = await store.create_project("author", title, "16:9")
    breakdown_id, stamp = "bd-" + uuid.uuid4().hex, store.utcnow()
    async with store.connection(transaction=True) as db:
        await db.execute("""INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,
            status,settings_json,import_json,created_at,updated_at)
            VALUES(?,?,'author',1,'claude','done','{}','{}',?,?)""",
                         (breakdown_id, project["id"], stamp, stamp))
        await db.execute("UPDATE studio_projects SET breakdown_id=?, style_json=? WHERE id=?",
                         (breakdown_id, store._json(style) if style is not None else None, project["id"]))
    return await store.get_project(project["id"], "author")


STYLE = {"name": "水墨", "visual_style": "写实电影感", "palette": "青灰", "camera": "固定机位",
         "lighting": "柔和侧光", "rationale": "含蓄", "realism": "photoreal", "source": "custom",
         "proposal_index": None}


async def new_item(project, *, kind="character", name="阿宁", appearance="短发、旧棉袄",
                   description="小镇邮差", role="主角", needs_author=0, locked_features="",
                   extra_prompt="", reference_asset_ids=(), approved_asset_id=None,
                   look=None, look_source=None):
    bible_id, item_id, stamp = uuid.uuid4().hex, uuid.uuid4().hex, store.utcnow()
    spec = {"locked_features": locked_features, "extra_prompt": extra_prompt,
            "reference_asset_ids": list(reference_asset_ids), "voice": None}
    if look is not None:
        spec["look"] = look
    if look_source is not None:
        spec["look_source"] = look_source
    async with store.connection(transaction=True) as db:
        await db.execute("""INSERT INTO studio_bible(id,project_id,owner,breakdown_id,kind,name,
            aliases_json,role,description,appearance,appearance_source,excerpt,needs_author,episodes_json,
            archived,updated_at) VALUES(?,?,?,?,?,?,'[]',?,?,?,'author','',?,'[]',0,?)""",
                         (bible_id, project["id"], "author", project["breakdown_id"], kind, name, role, description,
                          appearance, needs_author, stamp))
        await db.execute("""INSERT INTO studio_items(id,project_id,owner,bible_id,kind,name,status,
            spec_json,approved_asset_id,created_at,updated_at) VALUES(?,?,?,?,?,?,'pending',?,?,?,?)""",
                         (item_id, project["id"], "author", bible_id, kind, name, store._json(spec),
                          approved_asset_id, stamp, stamp))
    return item_id, bible_id


async def new_image_asset(project, *, item_id=None, version_no=1, archived=0, rel_path=None):
    asset_id = uuid.uuid4().hex
    async with store.connection(transaction=True) as db:
        await db.execute("""INSERT INTO studio_assets(id,project_id,owner,kind,source,rel_path,sha256,
            bytes,meta_json,archived,item_id,version_no,role,width,height,created_at)
            VALUES(?,?,'author','image','generated',?,?,10,'{}',?,?,?,'sheet',2560,1440,?)""",
                         (asset_id, project["id"], rel_path or f"{asset_id}.png", asset_id * 2, archived,
                          item_id, version_no, store.utcnow()))
    return asset_id


def image_entry(item_id, *, reserved="0.30", extra_prompt="", references=(), derive=False):
    return {"item_id": item_id, "reserved_amount": Decimal(reserved),
            "params": {"item_id": item_id, "extra_prompt": extra_prompt,
                       "reference_asset_ids": list(references), "derive_from_approved": derive}}


def tts_entry(item_id, *, engine="cosyvoice", reserved="0.01", text="我是阿宁。", spec=None):
    return {"item_id": item_id, "media_provider": engine, "reserved_amount": Decimal(reserved),
            "params": {"item_id": item_id, "text": text,
                       "spec": spec or {"engine": engine, "voice": "longxiaocheng_v2", "rate": 1.0,
                                        "pitch": 1.0, "fx": None, "role": "dialogue"}}}


async def create_image_jobs(project, item_id, *, count=1, params=None):
    entries = []
    for _ in range(count):
        entry = image_entry(item_id)
        if params:
            entry["params"].update(params)
        entries.append(entry)
    return await casting_jobs.create_jobs(project, "author", kind="image", media_provider="seedream",
                                          quote_id=None, entries=entries)


async def job_row(job_id):
    async with store.connection() as db:
        return await store._one(db, "SELECT * FROM studio_jobs WHERE id=?", (job_id,))


async def asset_rows(item_id=None):
    async with store.connection() as db:
        if item_id is None:
            return await store._many(db, "SELECT * FROM studio_assets ORDER BY created_at")
        return await store._many(db, "SELECT * FROM studio_assets WHERE item_id=? ORDER BY version_no", (item_id,))


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 出图
# ---------------------------------------------------------------------------

def test_image_success_lands_versioned_asset_and_settles(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        jobs = await create_image_jobs(project, item_id)
        assert len(jobs) == 1 and paid["scheduled"] == [jobs[0]["id"]]
        row = await job_row(jobs[0]["id"])
        assert (row["kind"], row["provider"], row["media_provider"], row["status"]) == \
            ("image", "wan", "seedream", "queued")
        assert float(row["reserved_amount"]) == pytest.approx(0.30)
        assert (await spend.today())["committed_cny"] == pytest.approx(0.30)

        assert await casting_jobs.execute(jobs[0]["id"]) is True
        row = await job_row(jobs[0]["id"])
        assert row["status"] == "succeeded" and row["reserved_amount"] == "0"
        assert float(row["actual_amount"]) == pytest.approx(0.30)
        assert paid["calls"]["image"] == [{"prompt": "组装后的定妆提示词", "size": "2560x1440",
                                           "references": []}]
        assets = await asset_rows(item_id)
        assert len(assets) == 1
        asset = assets[0]
        assert (asset["kind"], asset["role"], asset["source"], asset["version_no"]) == \
            ("image", "sheet", "generated", 1)
        assert asset["width"] == 2560 and asset["height"] == 1440 and asset["archived"] == 0
        meta = json.loads(asset["meta_json"])
        assert meta["prompt"] == "组装后的定妆提示词" and meta["size"] == "2560x1440"
        assert meta["reference_asset_ids"] == [] and meta["provider"] == "seedream"
        assert (await spend.today())["committed_cny"] == pytest.approx(0.30)

    run(scenario())


def test_image_prompt_receives_look(casting_db, paid, monkeypatch):
    seen = {}

    def capture(**kwargs):
        seen.update(kwargs)
        return "带造型说明的定妆提示词"

    monkeypatch.setattr(casting_jobs, "_build_sheet_prompt", capture)
    look = {"hair": "齐耳短发", "makeup": "裸妆", "top": "灰蓝工装",
            "bottom": "束脚裤", "footwear": "帆布鞋", "accessories": "邮差包",
            "materials": "棉布磨损", "palette": "灰蓝"}

    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project, look=look, look_source="director")
        jobs = await create_image_jobs(project, item_id)
        assert await casting_jobs.execute(jobs[0]["id"]) is True
        assert seen["look"] == look
        assert seen["kind"] == "character" and seen["name"] == "阿宁"

    run(scenario())


def test_image_versions_increment_for_same_item(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        jobs = await create_image_jobs(project, item_id, count=2)
        for job in jobs:
            await casting_jobs.execute(job["id"])
        assets = await asset_rows(item_id)
        assert [asset["version_no"] for asset in assets] == [1, 2]
        assert len({asset["id"] for asset in assets}) == 2

    run(scenario())


@pytest.mark.skipif(MediaCallError is None, reason="块 B 尚未实现")
@pytest.mark.parametrize("status,expected_commit", [("rejected", 0.0), ("uncertain", 0.30), ("failed", 0.0)])
def test_image_failure_classification_and_reservation(casting_db, paid, status, expected_commit):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        paid["state"]["image_exc"] = MediaCallError(status, f"code_{status}", f"上游 {status}")
        job = (await create_image_jobs(project, item_id))[0]
        assert await casting_jobs.execute(job["id"]) is True
        row = await job_row(job["id"])
        assert row["status"] == status and row["error_code"] == f"code_{status}"
        # uncertain 保留预留（等待人工释放）；rejected / failed 立即释放
        assert float(row["reserved_amount"]) == pytest.approx(0.30 if status == "uncertain" else 0.0)
        assert (row["actual_amount"] is None) if status == "uncertain" else \
            (float(row["actual_amount"]) == 0.0)
        assert await asset_rows(item_id) == []
        assert (await spend.today())["committed_cny"] == pytest.approx(expected_commit)
        if status == "uncertain":
            assert row["needs_recheck"] == 1
            assert await store.release_job(job["id"], "author", True) is not None
            assert (await job_row(job["id"]))["status"] == "released"
            assert (await job_row(job["id"]))["reserved_amount"] == "0"
            assert (await spend.today())["committed_cny"] == 0

    run(scenario())


def test_uncertain_keeps_reservation_until_manual_release(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        paid["state"]["image_exc"] = httpx.ReadTimeout("boom")
        job = (await create_image_jobs(project, item_id))[0]
        await casting_jobs.execute(job["id"])
        row = await job_row(job["id"])
        assert row["status"] == "uncertain" and row["needs_recheck"] == 1
        assert float(row["reserved_amount"]) == pytest.approx(0.30)
        assert (await spend.today())["committed_cny"] == pytest.approx(0.30)
        # 释放前不能自动重发。
        assert await casting_jobs.execute(job["id"]) is False
        assert len(paid["calls"]["image"]) == 1

    run(scenario())


def test_preflight_failures_release_without_paid_call(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        entry = image_entry(item_id, references=[f"r{index}" for index in range(5)])
        job = (await casting_jobs.create_jobs(project, "author", kind="image",
                                              media_provider="seedream", quote_id=None, entries=[entry]))[0]
        await casting_jobs.execute(job["id"])
        row = await job_row(job["id"])
        assert row["status"] == "rejected" and row["error_code"] == "too_many_references"
        assert paid["calls"]["image"] == [] and paid["calls"]["references"] == []

        missing = image_entry("does-not-exist")
        job = (await casting_jobs.create_jobs(project, "author", kind="image",
                                              media_provider="seedream", quote_id=None, entries=[missing]))[0]
        await casting_jobs.execute(job["id"])
        row = await job_row(job["id"])
        assert row["status"] == "rejected" and row["error_code"] == "item_unavailable"
        assert paid["calls"]["image"] == []

    run(scenario())


def test_reference_plan_uses_approved_version_and_caps(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        approved = await new_image_asset(project, version_no=3)
        item_id, _ = await new_item(project, approved_asset_id=approved)
        extra = [await new_image_asset(project, version_no=1) for _ in range(4)]
        entry = image_entry(item_id, references=extra, derive=True)
        job = (await casting_jobs.create_jobs(project, "author", kind="image", media_provider="seedream",
                                              quote_id=None, entries=[entry]))[0]
        await casting_jobs.execute(job["id"])
        # derive_from_approved 与显式参考图合计超过 4 张 → 拒绝。
        assert (await job_row(job["id"]))["status"] == "rejected"

        entry = image_entry(item_id, references=extra[:3], derive=True)
        job = (await casting_jobs.create_jobs(project, "author", kind="image", media_provider="seedream",
                                              quote_id=None, entries=[entry]))[0]
        await casting_jobs.execute(job["id"])
        assert (await job_row(job["id"]))["status"] == "succeeded"
        assert paid["calls"]["references"] == [approved, *extra[:3]]
        assert paid["calls"]["image"][-1]["references"] == [b"reference-bytes"] * 4

    run(scenario())


def test_reference_plan_dedupes_approved_listed_as_explicit_reference(casting_db, paid, monkeypatch):
    """报价里已经含 approved 时，执行期合并去重，derived 标记只留在第一张。"""
    async def scenario():
        project = await new_project(style=STYLE)
        approved = await new_image_asset(project, version_no=2)
        other = await new_image_asset(project, version_no=1)
        third = await new_image_asset(project, version_no=1)
        item_id, _ = await new_item(project, approved_asset_id=approved)
        notes = []
        monkeypatch.setattr(casting_jobs, "_reference_note",
                            lambda kind, derived: notes.append(derived) or f"note:{kind}:{derived}")
        entry = image_entry(item_id, references=[approved, other, third], derive=True)
        job = (await casting_jobs.create_jobs(project, "author", kind="image", media_provider="seedream",
                                              quote_id=None, entries=[entry]))[0]
        assert await casting_jobs.execute(job["id"]) is True
        assert (await job_row(job["id"]))["status"] == "succeeded"
        # 合并顺序：approved（derived）第一，重复的 approved 只保留一次。
        assert paid["calls"]["references"] == [approved, other, third]
        assert paid["calls"]["image"][-1]["references"] == [b"reference-bytes"] * 3
        assert notes == [True, False, False]
        asset = (await asset_rows(item_id))[0]
        assert json.loads(asset["meta_json"])["reference_asset_ids"] == [approved, other, third]

    run(scenario())


def test_derive_without_approved_version_is_rejected_without_paid_call(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)  # 没有 approved_asset_id
        entry = image_entry(item_id, derive=True)
        job = (await casting_jobs.create_jobs(project, "author", kind="image", media_provider="seedream",
                                              quote_id=None, entries=[entry]))[0]
        assert await casting_jobs.execute(job["id"]) is True
        row = await job_row(job["id"])
        assert row["status"] == "rejected" and row["error_code"] == "missing_approved"
        assert paid["calls"]["image"] == [] and paid["calls"]["references"] == []
        assert float(row["actual_amount"]) == 0.0 and row["reserved_amount"] == "0"
        assert (await spend.today())["committed_cny"] == 0

    run(scenario())


@pytest.mark.parametrize("kind", ["archived", "missing"])
def test_reference_unavailable_is_rejected_before_paid_call(casting_db, paid, kind):
    """已归档 / 不存在的参考图是预检失败，绝不能落到 uncertain。"""
    async def scenario():
        project = await new_project(style=STYLE)
        asset_id = await new_image_asset(project, archived=1) if kind == "archived" else uuid.uuid4().hex
        item_id, _ = await new_item(project)
        entry = image_entry(item_id, references=[asset_id])
        job = (await casting_jobs.create_jobs(project, "author", kind="image", media_provider="seedream",
                                              quote_id=None, entries=[entry]))[0]
        assert await casting_jobs.execute(job["id"]) is True
        row = await job_row(job["id"])
        assert row["status"] == "rejected" and row["error_code"] == "reference_unavailable"
        assert paid["calls"]["image"] == [] and paid["calls"]["references"] == []
        assert float(row["actual_amount"]) == 0.0 and row["reserved_amount"] == "0"
        assert row["needs_recheck"] == 0
        assert (await spend.today())["committed_cny"] == 0

    run(scenario())


def test_execute_settles_when_job_read_fails_after_running(casting_db, paid, monkeypatch):
    """置为 running 之后的任何 DB 读取异常都要把任务结算掉，不能停在 running。"""
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        job = (await create_image_jobs(project, item_id))[0]
        real_get_job, seen = store.get_job, []

        async def flaky_get_job(job_id, owner=None):
            seen.append(job_id)
            if len(seen) == 2:  # 第二次即 running 之后那次读取
                raise RuntimeError("db read failed")
            return await real_get_job(job_id, owner)

        monkeypatch.setattr(store, "get_job", flaky_get_job)
        assert await casting_jobs.execute(job["id"]) is True
        assert len(seen) == 2
        row = await job_row(job["id"])
        assert row["status"] != "running"
        assert row["status"] == "uncertain" and row["error_code"] == "media_error"
        assert row["needs_recheck"] == 1
        assert float(row["reserved_amount"]) == pytest.approx(0.30)
        assert paid["calls"]["image"] == []

    run(scenario())


def test_reference_bytes_sync_always_outputs_png(tmp_path):
    from PIL import Image

    source = tmp_path / "reference.jpg"
    Image.new("RGB", (64, 48), (12, 34, 56)).save(source, "JPEG")
    data = casting_jobs._reference_bytes_sync(str(source))
    assert data.startswith(b"\x89PNG\r\n\x1a\n")

    large = tmp_path / "large.png"
    Image.new("RGB", (2000, 1000), (1, 2, 3)).save(large, "PNG")
    scaled = casting_jobs._reference_bytes_sync(str(large))
    assert scaled.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(io.BytesIO(scaled)) as image:
        assert max(image.size) == 1536 and image.mode == "RGB"


def test_commit_failure_keeps_file_still_referenced_by_another_asset(casting_db, paid, monkeypatch):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        rel_path = f"{project['id']}/images/sheet.png"  # paid 里 fake_save_image 的固定输出
        await new_image_asset(project, rel_path=rel_path)

        async def boom(db, owner, project_id, fields):
            raise RuntimeError("asset insert failed")

        monkeypatch.setattr(store, "_create_asset", boom)
        job = (await create_image_jobs(project, item_id))[0]
        await casting_jobs.execute(job["id"])
        assert (await job_row(job["id"]))["status"] == "uncertain"
        # 同一文件仍被别的资产引用 → 不能删。
        assert paid["calls"]["discarded"] == []
        assert [row["rel_path"] for row in await asset_rows()] == [rel_path]

    run(scenario())


def test_execute_never_posts_twice_and_dispatch_is_idempotent(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(casting_jobs, "_schedule", paid["real_schedule"])
        try:
            job = (await create_image_jobs(project, item_id))[0]
            await casting_jobs.dispatch_queued()
            await casting_jobs.dispatch_queued()
            for _ in range(50):
                if paid["calls"]["image"]:
                    break
                await asyncio.sleep(0.01)
            assert len(paid["calls"]["image"]) == 1
            assert (await job_row(job["id"]))["status"] == "succeeded"
            # 已终态的任务再次驱动不会重复付费。
            assert await casting_jobs.execute(job["id"]) is False
            assert len(paid["calls"]["image"]) == 1
        finally:
            monkeypatch.undo()

    run(scenario())


def test_commit_rolls_back_asset_when_creation_fails(casting_db, paid, monkeypatch):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)

        async def boom(db, owner, project_id, fields):
            raise RuntimeError("asset insert failed")

        monkeypatch.setattr(store, "_create_asset", boom)
        job = (await create_image_jobs(project, item_id))[0]
        await casting_jobs.execute(job["id"])
        row = await job_row(job["id"])
        assert row["status"] == "uncertain"
        assert await asset_rows() == []
        assert paid["calls"]["discarded"] == [f"{project['id']}/images/sheet.png"]

    run(scenario())


def test_create_jobs_budget_and_entry_overrides(casting_db, paid, monkeypatch):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        jobs = await casting_jobs.create_jobs(
            project, "author", kind="tts", media_provider=None, quote_id=None,
            entries=[tts_entry(item_id, engine="cosyvoice"),
                     tts_entry(item_id, engine="edge-tts", reserved="0")])
        providers = {row["id"]: row["media_provider"] for row in
                     [await job_row(job["id"]) for job in jobs]}
        assert set(providers.values()) == {"cosyvoice", "edge-tts"}
        for job in jobs:
            assert job["status"] == "queued"

        # 报价上限：写行事务里直接 409，不留任务。
        monkeypatch.setenv("FIONA_STUDIO_DAILY_CNY", "0.5")
        with pytest.raises(Exception) as error:
            await casting_jobs.create_jobs(project, "author", kind="image", media_provider="seedream",
                                           quote_id=None, entries=[image_entry(item_id, reserved="1.00")])
        assert getattr(error.value, "status_code", None) == 409
        async with store.connection() as db:
            count = await store._one(db, "SELECT COUNT(*) AS value FROM studio_jobs")
        assert count["value"] == 2

    run(scenario())


def test_prepare_jobs_uses_caller_transaction_and_schedules_only_on_demand(casting_db, paid):
    """prepare_jobs 不自己开事务、不派发；回滚 = 一行不留，提交 + schedule_jobs 才派发。"""
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        async with store.connection(transaction=True) as db:
            rolled = await casting_jobs.prepare_jobs(db, project, "author", kind="image",
                                                     media_provider="seedream", quote_id=None,
                                                     entries=[image_entry(item_id)])
            assert len(rolled) == 1 and paid["scheduled"] == []
            await db.rollback()
        async with store.connection() as db:
            assert (await store._one(db, "SELECT COUNT(*) AS value FROM studio_jobs"))["value"] == 0
        assert (await spend.today())["committed_cny"] == 0

        async with store.connection(transaction=True) as db:
            jobs = await casting_jobs.prepare_jobs(db, project, "author", kind="image",
                                                   media_provider="seedream", quote_id=None,
                                                   entries=[image_entry(item_id)])
        assert paid["scheduled"] == []
        assert (await job_row(jobs[0]["id"]))["status"] == "queued"
        casting_jobs.schedule_jobs(jobs)
        assert paid["scheduled"] == [jobs[0]["id"]]
        assert await casting_jobs.execute(jobs[0]["id"]) is True
        assert (await job_row(jobs[0]["id"]))["status"] == "succeeded"

    run(scenario())


def test_create_jobs_keeps_signature_and_skips_empty_entries(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        jobs = await create_image_jobs(project, item_id)
        # create_jobs 仍是「建任务 + 派发」的入口：提交后按 job id 派发。
        assert paid["scheduled"] == [jobs[0]["id"]]
        assert (await job_row(jobs[0]["id"]))["status"] == "queued"

        paid["scheduled"].clear()
        assert await casting_jobs.create_jobs(project, "author", kind="image", media_provider="seedream",
                                              quote_id=None, entries=[]) == []
        assert paid["scheduled"] == []
        # 未知类型即使 entries 为空也照旧直接报错（不开事务）。
        with pytest.raises(ValueError):
            await casting_jobs.create_jobs(project, "author", kind="nope", media_provider="seedream",
                                           quote_id=None, entries=[])

    run(scenario())


def test_tts_jobs_reserve_by_chars_and_settle(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        jobs = await casting_jobs.create_jobs(
            project, "author", kind="tts", media_provider=None, quote_id=None,
            entries=[tts_entry(item_id, engine="cosyvoice", reserved="0.01",
                               spec={"engine": "cosyvoice", "voice": "longxiaocheng_v2", "rate": 1.2,
                                     "pitch": 0.8, "fx": "robot:B", "role": "narration"}),
                     tts_entry(item_id, engine="edge-tts", reserved="0",
                               spec={"engine": "edge-tts", "voice": "en-US-AndrewNeural",
                                     "rate": "+5%", "pitch": "-3Hz", "fx": None, "role": "dialogue"})])
        cosy, edge = jobs
        assert await casting_jobs.execute(cosy["id"]) is True
        assert await casting_jobs.execute(edge["id"]) is True

        assert paid["calls"]["cosy"][0] == {"text": "我是阿宁。", "voice": "longxiaocheng_v2",
                                            "rate": 1.2, "pitch": 0.8}
        assert paid["calls"]["edge"][0] == {"text": "我是阿宁。", "voice": "en-US-AndrewNeural",
                                            "rate": "+5%", "pitch": "-3Hz"}
        assert paid["calls"]["voice"][0] == {"fx": "robot:B", "target_lufs": -18.0, "format": "wav"}
        assert paid["calls"]["voice"][1] == {"fx": None, "target_lufs": -16.0, "format": "mp3"}

        cosy_row = await job_row(cosy["id"])
        assert cosy_row["status"] == "succeeded" and float(cosy_row["actual_amount"]) == pytest.approx(0.01)
        edge_row = await job_row(edge["id"])
        assert edge_row["status"] == "succeeded" and float(edge_row["actual_amount"]) == 0.0
        assert edge_row["reserved_amount"] == "0"

        assets = await asset_rows(item_id)
        assert {asset["role"] for asset in assets} == {"audition"}
        assert {asset["kind"] for asset in assets} == {"audio"}
        meta = json.loads(assets[0]["meta_json"])
        assert meta["text"] == "我是阿宁。" and meta["duration_s"] == 1.25 and meta["measured_lufs"] == -16.2
        assert meta["spec"]["engine"] == "cosyvoice"
        assert (await spend.today())["committed_cny"] == pytest.approx(0.01)

    run(scenario())


def test_tts_preflight_rejects_missing_spec_and_unknown_engine(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        broken = tts_entry(item_id, engine="cosyvoice")
        broken["params"].pop("spec")
        unknown = tts_entry(item_id, engine="cosyvoice")
        unknown["params"]["spec"]["engine"] = "polly"
        jobs = await casting_jobs.create_jobs(project, "author", kind="tts", media_provider=None,
                                              quote_id=None, entries=[broken, unknown])
        for job in jobs:
            await casting_jobs.execute(job["id"])
            row = await job_row(job["id"])
            assert row["status"] == "rejected" and float(row["actual_amount"]) == 0.0
        assert paid["calls"]["cosy"] == [] and paid["calls"]["edge"] == []

    run(scenario())


def test_doubao_tts_job_passes_direction_and_processes_mp3(casting_db, paid):
    """豆包任务：延迟导入的封装收到 int pitch 与指示，mp3 走 ffmpeg 处理后再入库。"""
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        spec = {"engine": "doubao", "voice": "zh_female_sophie_uranus_bigtts", "rate": 1.2,
                "pitch": -3, "fx": "inner:A", "role": "dialogue",
                "direction": "压低声音，不安里带着一点倔强"}
        jobs = await casting_jobs.create_jobs(
            project, "author", kind="tts", media_provider=None, quote_id=None,
            entries=[tts_entry(item_id, engine="doubao", reserved="0.01", spec=spec)])
        assert await casting_jobs.execute(jobs[0]["id"]) is True

        assert paid["calls"]["doubao"] == [{"text": "我是阿宁。", "voice": spec["voice"],
                                            "rate": 1.2, "pitch": -3,
                                            "direction": spec["direction"]}]
        assert paid["calls"]["voice"] == [{"fx": "inner:A", "target_lufs": -16.0, "format": "mp3"}]
        row = await job_row(jobs[0]["id"])
        assert row["status"] == "succeeded" and float(row["actual_amount"]) == pytest.approx(0.01)
        meta = json.loads((await asset_rows(item_id))[0]["meta_json"])
        assert meta["spec"] == spec
        assert (await spend.today())["committed_cny"] == pytest.approx(0.01)

    run(scenario())


def test_doubao_preflight_error_releases_reservation(casting_db, paid):
    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        spec = {"engine": "doubao", "voice": "zh_female_sophie_uranus_bigtts", "rate": 1.0,
                "pitch": 0, "fx": None, "role": "dialogue", "direction": ""}
        jobs = await casting_jobs.create_jobs(
            project, "author", kind="tts", media_provider=None, quote_id=None,
            entries=[tts_entry(item_id, engine="doubao", reserved="0.01", spec=spec)])
        paid["state"]["doubao_exc"] = MediaCallError("rejected", "doubao_45002001", "上游拒绝")
        assert await casting_jobs.execute(jobs[0]["id"]) is True
        row = await job_row(jobs[0]["id"])
        assert row["status"] == "rejected" and row["error_code"] == "doubao_45002001"
        assert float(row["actual_amount"]) == 0 and float(row["reserved_amount"]) == 0
        assert len(paid["calls"]["doubao"]) == 1

    run(scenario())


@pytest.mark.parametrize("mutate", [
    lambda spec: spec.update(direction="字" * 201),
    lambda spec: spec.update(pitch=13),
    lambda spec: spec.update(rate="abc"),
])
def test_doubao_pre_send_error_is_rejected_without_post(casting_db, monkeypatch, mutate):
    """POST 之前抛出的参数 / 构造错误必须记 rejected 并释放预留。"""
    from studio.providers import tts_doubao

    posts = []

    def handler(request):
        posts.append(request)
        return httpx.Response(200, content=b"")

    monkeypatch.setenv(tts_doubao.API_KEY_ENV, "test-doubao-key-not-real")
    monkeypatch.setattr(tts_doubao, "_default_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr(casting_jobs, "_schedule", lambda job_id: None)

    async def scenario():
        project = await new_project(style=STYLE)
        item_id, _ = await new_item(project)
        spec = {"engine": "doubao", "voice": "zh_female_sophie_uranus_bigtts", "rate": 1.0,
                "pitch": 0, "fx": None, "role": "dialogue", "direction": ""}
        mutate(spec)
        jobs = await casting_jobs.create_jobs(
            project, "author", kind="tts", media_provider=None, quote_id=None,
            entries=[tts_entry(item_id, engine="doubao", reserved="0.01", spec=spec)])
        assert await casting_jobs.execute(jobs[0]["id"]) is True

        row = await job_row(jobs[0]["id"])
        assert posts == []
        assert row["status"] == "rejected"
        assert row["error_code"] == "invalid_parameters"
        assert float(row["actual_amount"]) == 0
        assert float(row["reserved_amount"]) == 0

    run(scenario())


def test_inflight_limit_defaults_and_env_validation(monkeypatch):
    monkeypatch.delenv(casting_jobs.INFLIGHT_IMAGE_ENV, raising=False)
    monkeypatch.delenv(casting_jobs.INFLIGHT_TTS_ENV, raising=False)
    assert casting_jobs.inflight_limit("seedream") == 3
    assert casting_jobs.inflight_limit("cosyvoice") == 2
    assert casting_jobs.inflight_limit("edge-tts") == 2

    monkeypatch.setenv(casting_jobs.INFLIGHT_IMAGE_ENV, "5")
    monkeypatch.setenv(casting_jobs.INFLIGHT_TTS_ENV, "1")
    assert casting_jobs.inflight_limit("seedream") == 5
    assert casting_jobs.inflight_limit("cosyvoice") == 1

    casting_jobs._LIMIT_WARNED.discard(casting_jobs.INFLIGHT_IMAGE_ENV)
    for invalid in ("0", "11", "abc", "3.5"):
        monkeypatch.setenv(casting_jobs.INFLIGHT_IMAGE_ENV, invalid)
        assert casting_jobs.inflight_limit("seedream") == 3


def test_price_helpers_default_and_env(monkeypatch):
    monkeypatch.delenv(pricing.PRICE_SEEDREAM_ENV, raising=False)
    monkeypatch.delenv(pricing.PRICE_COSYVOICE_ENV, raising=False)
    monkeypatch.delenv(pricing.PRICE_DOUBAO_ENV, raising=False)
    assert pricing.seedream_price() == Decimal("0.30")
    assert pricing.doubao_price_per_10k_chars() == Decimal("3.0")
    assert pricing.estimate_sheets(3) == {"currency": "CNY", "amount": pytest.approx(0.90)}
    assert pricing.estimate_speech(5000, "cosyvoice")["amount"] == pytest.approx(1.0)
    assert pricing.estimate_speech(10, "cosyvoice")["amount"] == pytest.approx(0.01)
    assert pricing.estimate_speech(5000, "doubao")["amount"] == pytest.approx(1.5)
    assert pricing.estimate_speech(10, "doubao")["amount"] == pytest.approx(0.01)
    assert pricing.estimate_speech(10, "edge-tts") == {"currency": "CNY", "amount": 0.0}
    assert casting_jobs.price_for("doubao", chars=10) == Decimal("0.01000000")

    monkeypatch.setenv(pricing.PRICE_SEEDREAM_ENV, "0.42")
    assert pricing.seedream_price() == Decimal("0.42")
    pricing._PRICE_WARNED.discard(pricing.PRICE_SEEDREAM_ENV)
    monkeypatch.setenv(pricing.PRICE_SEEDREAM_ENV, "abc")
    assert pricing.seedream_price() == Decimal("0.30")
    monkeypatch.setenv(pricing.PRICE_COSYVOICE_ENV, "-1")
    assert pricing.cosyvoice_price_per_10k_chars() == Decimal("2.0")
    monkeypatch.setenv(pricing.PRICE_DOUBAO_ENV, "4.2")
    assert pricing.doubao_price_per_10k_chars() == Decimal("4.2")
    monkeypatch.setenv(pricing.PRICE_DOUBAO_ENV, "abc")
    assert pricing.doubao_price_per_10k_chars() == Decimal("3.0")
