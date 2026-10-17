# -*- coding: utf-8 -*-
"""WO3d 集成任务 I：块 A↔B↔C↔D 的端到端集成测试。

这里跑的是**真实**的块 A / 块 B / 块 C 代码，只在最底层把传输换掉：

* 块 A：REST 编排、条目同步、报价、任务建行 / 预留 / 派发 / 结算、门禁与归属；
* 块 B：Seedream / CosyVoice / edge-tts 适配器 + 真实 ffmpeg 音频处理；
* 块 C：定妆提示词与风格输入组装（真函数，不做替换）；
* 块 D：`frontend/lib/studio-casting.ts` 引用的键名与后端目录对齐（读源码断言）。

注入点（绝不替换 `generate_sheet` / `synthesize_*` / `process_voice` 本身）：

* Seedream：给 `image_seedream` 的 `httpx` 加一层代理，构造 `AsyncClient` 时补上
  `httpx.MockTransport`；由此统计 POST 次数；
* CosyVoice：替换模块级 `tts_cosy._default_synthesizer_factory`，产出真实正弦 WAV；
* edge-tts：向 `sys.modules` 注入假 `edge_tts`（本机与 CI 都可能没装）；
* 导演模型：照块 A 的做法打桩 `brain.provider_options` 与 `_schedule`，再直接写 result_json。

没有 ffmpeg / ffprobe 时整个模块 skip；付费调用一律离线（`conftest` 还有 socket 守卫）。
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import types
import uuid
import wave

import httpx
from PIL import Image
import pytest

from studio import audio, brain, brain_jobs, breakdown_plan, casting_jobs, pricing, recovery
from studio import casting as casting_module
from studio import spend, storage, store, voices
from studio.providers import image_seedream, tts_cosy, tts_doubao


if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
    pytest.skip("需要 ffmpeg 与 ffprobe 才能跑集成测试", allow_module_level=True)


BACKEND_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = BACKEND_ROOT.parent / "frontend"
FRONTEND_TS = FRONTEND_ROOT / "lib" / "studio-casting.ts"

SHEET_SIZE = "2560x1440"
SHEET_PRICE = 0.30
TEXT_ZH = "我是阿宁，旧信要还回去。"
TEXT_EN = "The old letters must go back."

# §8.3 逐字段列出的键集合；多一个少一个都算形状不符。
STATE_KEYS = {"g0_approved", "setup", "style", "items", "g1", "jobs", "prices"}
SETUP_KEYS = {"aspect", "resolution", "video_model", "language", "sheet_size", "confirmed_at"}
STYLE_KEYS = {"chosen", "proposals", "proposal_job"}
PROPOSAL_KEYS = {"name", "visual_style", "palette", "camera", "lighting", "rationale"}
CHOICE_KEYS = PROPOSAL_KEYS | {"realism", "source", "proposal_index"}
ITEM_KEYS = {"id", "bible_id", "kind", "name", "role", "appearance", "description", "needs_author",
             "orphaned", "status", "locked_features", "extra_prompt", "reference_asset_ids",
             "look", "look_source", "approved_asset_id", "versions", "voice"}
VERSION_KEYS = {"asset_id", "version_no", "created_at", "archived", "prompt"}
VOICE_KEYS = {"spec", "approved_asset_id", "auditions"}
AUDITION_SPEC_KEYS = {"engine", "voice", "rate", "pitch", "fx", "role", "direction"}
VOICE_SPEC_KEYS = AUDITION_SPEC_KEYS | {"baseline"}
AUDITION_KEYS = {"asset_id", "spec", "text", "duration_s", "measured_lufs", "created_at", "archived"}
JOB_KEYS = {"id", "kind", "task", "item_id", "status", "error_code", "error_message",
            "reserved_amount", "actual_amount", "currency", "created_at"}
G1_KEYS = {"approved", "total", "done", "skipped"}
PRICE_KEYS = {"seedream_cny", "cosyvoice_cny_per_10k_chars", "doubao_cny_per_10k_chars"}
QUOTE_KEYS = {"id", "kind", "items", "total", "currency", "expires_at"}
QUOTE_LINE_KEYS = {"item_id", "name", "versions", "unit", "est"}
VOICE_OPTION_KEYS = {"engine", "voice", "label", "lang", "gender", "note"}

PROPOSALS = [
    {"name": "水墨留白", "visual_style": "写实电影感", "palette": "青灰", "camera": "固定机位",
     "lighting": "柔和侧光", "rationale": "含蓄克制"},
    {"name": "暖调纪实", "visual_style": "手绘动画", "palette": "暖橙", "camera": "手持跟拍",
     "lighting": "逆光", "rationale": "亲切自然"},
]
CUSTOM_STYLE = {"name": "水墨", "visual_style": "宣纸质感", "palette": "青灰", "camera": "固定机位",
                "lighting": "柔和侧光", "rationale": "含蓄"}

COSY_VARIANT = {"engine": "cosyvoice", "voice": "longxiaocheng_v2", "rate": 1.0, "pitch": 1.0,
                "fx": "robot:B", "role": "dialogue", "direction": None}
NARRATION_VARIANT = {"engine": "cosyvoice", "voice": "longjielidou_v2", "rate": 1.2, "pitch": 0.9,
                     "fx": "inner:A", "role": "narration", "direction": None}
EDGE_VARIANT = {"engine": "edge-tts", "voice": "en-US-AndrewNeural", "rate": "+0%", "pitch": "+0Hz",
                "fx": None, "role": "narration", "direction": None}
DOUBAO_DIRECTION = "压低声音，不安里带着一点倔强，像在问自己"
DOUBAO_VARIANT = {"engine": "doubao", "voice": "zh_female_sophie_uranus_bigtts", "rate": 1.2,
                  "pitch": -3, "fx": None, "role": "dialogue", "direction": DOUBAO_DIRECTION}


def run(coro):
    return asyncio.run(coro)


async def rows(sql, params=()):
    async with store.connection() as db:
        return await store._many(db, sql, params)


async def one(sql, params=()):
    async with store.connection() as db:
        return await store._one(db, sql, params)


# ---------------------------------------------------------------------------
# 最底层的假传输注入
# ---------------------------------------------------------------------------

class _AsyncClientInjector:
    """`image_seedream` 里 `httpx` 的代理：构造客户端时补上注入的 transport。

    这不是替换 `generate_sheet`：`_run_image` → `casting_jobs._generate_sheet`
    → `image_seedream.generate_sheet` 全部走真实代码，只有 socket 层被换掉。
    """

    def __init__(self, module, transport):
        self._module = module
        self._transport = transport

    def __getattr__(self, name):
        return getattr(self._module, name)

    @property
    def AsyncClient(self):
        real = self._module.AsyncClient
        transport = self._transport

        def build(*args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = transport
            return real(*args, **kwargs)

        return build


def install_seedream(monkeypatch, handler) -> list:
    """注入 MockTransport；返回收到的请求列表（用于断言 POST 次数）。"""
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    monkeypatch.setattr(image_seedream, "httpx",
                        _AsyncClientInjector(image_seedream.httpx, httpx.MockTransport(record)))
    return requests


def image_body(request: httpx.Request) -> dict:
    return json.loads(request.content.decode("utf-8"))


class _CosySynthesizer:
    """假 SpeechSynthesizer：把整段 WAV 分两次回调，契约与真 SDK 一致。"""

    def __init__(self, payload: bytes):
        self._payload = payload
        self.callback = None
        self.closed = False
        self.texts: list[str] = []
        self.timeouts: list[int] = []

    def call(self, text, timeout_millis=None):
        self.texts.append(text)
        self.timeouts.append(timeout_millis)
        middle = max(1, len(self._payload) // 2)
        self.callback.on_data(self._payload[:middle])
        self.callback.on_data(self._payload[middle:])
        self.callback.on_complete()

    def close(self):
        self.closed = True


class CosyFactory:
    """假工厂：记录构造参数，产出真实 WAV 字节。"""

    def __init__(self, payload: bytes):
        self.payload = payload
        self.calls: list[dict] = []
        self.synthesizers: list[_CosySynthesizer] = []

    def __call__(self, **params):
        self.calls.append(params)
        synthesizer = _CosySynthesizer(self.payload)
        synthesizer.callback = params["callback"]
        self.synthesizers.append(synthesizer)
        return synthesizer


def install_cosy(monkeypatch, payload: bytes) -> CosyFactory:
    factory = CosyFactory(payload)
    monkeypatch.setattr(tts_cosy, "_default_synthesizer_factory", factory)
    return factory


def install_doubao(monkeypatch, payload: bytes) -> list:
    """注入 MockTransport；适配器把多行 JSON 里的 base64 音频块拼回完整 mp3。"""
    requests: list[httpx.Request] = []
    middle = max(1, len(payload) // 2)
    lines = [
        {"code": 0, "data": base64.b64encode(payload[:middle]).decode()},
        {"code": 0, "data": base64.b64encode(payload[middle:]).decode()},
        {"code": 20000000, "message": "ok"},
    ]
    body = ("\n".join(json.dumps(line) for line in lines) + "\n").encode("utf-8")

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=body)

    monkeypatch.setattr(tts_doubao, "_default_transport", lambda: httpx.MockTransport(record))
    return requests


def install_edge(monkeypatch, payload: bytes, words: list[dict]) -> dict:
    """向 sys.modules 注入假 edge_tts；Communicate 契约与真 SDK 一致。"""
    state: dict = {"built": []}
    module = types.ModuleType("edge_tts")

    class Communicate:
        def __init__(self, **params):
            self.params = params
            state["built"].append(params)

        async def stream(self):
            middle = max(1, len(payload) // 2)
            for chunk in (payload[:middle], payload[middle:]):
                yield {"type": "audio", "data": chunk}
            for word in words:
                yield {"type": "WordBoundary", **word}

    module.Communicate = Communicate
    monkeypatch.setitem(sys.modules, "edge_tts", module)
    return state


def blocked_seedream(monkeypatch) -> list:
    """任何出网都直接失败：用来证明某条路径一次付费调用都没有。"""

    def handler(request):
        raise AssertionError("本用例不应发出出图请求")

    return install_seedream(monkeypatch, handler)


# ---------------------------------------------------------------------------
# 媒体夹具：真实 PNG / WAV / MP3
# ---------------------------------------------------------------------------

def _png(width: int, height: int, color: str = "#405060") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _seedream_ok(payload: bytes) -> dict:
    return {"model": image_seedream.DEFAULT_MODEL,
            "data": [{"b64_json": base64.b64encode(payload).decode("ascii")}],
            "usage": {"generated_images": 1, "total_tokens": 8100}}


def _sine(path: Path, *, container: str = "wav", duration: float = 1.5, frequency: int = 220,
          sample_rate: int = 24000) -> bytes:
    args = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
            "-i", f"sine=frequency={frequency}:duration={duration}",
            "-ac", "1", "-ar", str(sample_rate)]
    if container == "mp3":
        args += ["-c:a", "libmp3lame", "-b:a", "128k"]
    args.append(str(path))
    subprocess.run(args, check=True, capture_output=True)
    return path.read_bytes()


@pytest.fixture(scope="module")
def sheet_png() -> bytes:
    return _png(2560, 1440)


@pytest.fixture(scope="module")
def cosy_wav(tmp_path_factory) -> bytes:
    return _sine(tmp_path_factory.mktemp("cosy") / "zh.wav")


@pytest.fixture(scope="module")
def edge_mp3(tmp_path_factory) -> bytes:
    return _sine(tmp_path_factory.mktemp("edge") / "en.mp3", container="mp3")


@pytest.fixture(scope="module")
def doubao_mp3(tmp_path_factory) -> bytes:
    return _sine(tmp_path_factory.mktemp("doubao") / "zh.mp3", container="mp3")


# ---------------------------------------------------------------------------
# 夹具：建库 / JWT 作者 / G0 已批准（沿用 tests/test_studio_casting_api.py 的写法）
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
    # 占位密钥：假传输下不出网，只为让适配器通过配置校验。
    monkeypatch.setenv("ARK_API_KEY", "offline-ark-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "offline-dashscope-key")
    # 占位 Key：MockTransport 下不出网，只为让适配器通过配置校验。
    monkeypatch.setenv("VOLC_SPEECH_API_KEY", "offline-volc-key")
    monkeypatch.delenv("SEEDREAM_IMAGE_MODEL", raising=False)

    accounts = {}
    for username in ("owner", "other", "outsider"):
        user = run(database.get_or_create_user(username))
        accounts[username] = {
            "Authorization": f"Bearer {create_token(username, user['session_version'])}"}

    calls: dict = {"scheduled": [], "image": 0, "cosy": 0, "edge": 0}
    gates = {"g0": True}

    async def fake_episodes(pid, owner):
        project = await store.get_project(pid, owner)
        return {"g0_approved": gates["g0"],
                "breakdown_id": project.get("breakdown_id") if gates["g0"] else None,
                "episodes": [{"no": 1, "title": "第一集"}]}

    async def available(username):
        return [{"id": pid, "label": pid, "available": True, "model": model}
                for pid, model in (("claude", "claude-sonnet-5-5"), ("qwen", "qwen3.8-max"),
                                   ("deepseek", "deepseek-v4-pro"))]

    monkeypatch.setattr(casting_jobs, "_schedule", lambda jid: calls["scheduled"].append(jid))
    monkeypatch.setattr(brain_jobs, "_schedule", lambda jid: calls["scheduled"].append(jid))
    monkeypatch.setattr(breakdown_plan, "get_episodes", fake_episodes)
    monkeypatch.setattr(brain, "provider_options", available)

    return {"client": client, "headers": accounts, "calls": calls, "gates": gates,
            "studio_dir": Path(os.environ["FIONA_STUDIO_DIR"]).resolve()}


def auth(casting, name="owner"):
    return casting["headers"][name]


# ---------------------------------------------------------------------------
# 建数据 / 常用动作
# ---------------------------------------------------------------------------

async def new_project(owner="owner", title="定妆项目", aspect="16:9"):
    project = await store.create_project(owner, title, aspect)
    bid, stamp = "bd-" + uuid.uuid4().hex, store.utcnow()
    async with store.connection(transaction=True) as db:
        await db.execute("""INSERT INTO studio_breakdowns(id,project_id,owner,snapshot_no,provider,
            status,settings_json,import_json,created_at,updated_at)
            VALUES(?,?,?,1,'claude','done','{}','{}',?,?)""", (bid, project["id"], owner, stamp, stamp))
        await db.execute("UPDATE studio_projects SET breakdown_id=? WHERE id=? AND owner=?",
                         (bid, project["id"], owner))
    return await store.get_project(project["id"], owner)


async def new_bible(project, owner="owner", *, kind="character", name="阿宁", appearance="短发、旧棉袄",
                    role="主角", description="小镇邮差", needs_author=0):
    bible_id = str(uuid.uuid4())
    async with store.connection(transaction=True) as db:
        await db.execute("""INSERT INTO studio_bible(id,project_id,owner,breakdown_id,kind,name,
            aliases_json,role,description,appearance,appearance_source,excerpt,needs_author,episodes_json,
            merged_into,archived,updated_at)
            VALUES(?,?,?,?,?,?,'[]',?,?,?,'author','',?,'[]',NULL,0,?)""",
                         (bible_id, project["id"], owner, project["breakdown_id"], kind, name, role,
                          description, appearance, needs_author, store.utcnow()))
    return bible_id


async def new_asset(project, owner="owner", *, item_id=None, role="sheet", version_no=1, kind="image"):
    asset_id = uuid.uuid4().hex
    async with store.connection(transaction=True) as db:
        await db.execute("""INSERT INTO studio_assets(id,project_id,owner,kind,source,rel_path,sha256,
            bytes,meta_json,archived,item_id,version_no,role,created_at)
            VALUES(?,?,?,?,'generated',?,?,10,'{}',0,?,?,?,?)""",
                         (asset_id, project["id"], owner, kind, f"{asset_id}.bin", asset_id * 2,
                          item_id, version_no, role, store.utcnow()))
    return asset_id


def make_project(casting, owner="owner", **kwargs):
    return run(new_project(owner, **kwargs))


def seed_items(casting, project, owner="owner", count=1, **kwargs):
    return [run(new_bible(project, owner, name=f"人物{index}", **kwargs)) for index in range(count)]


def confirm_setup(casting, project, **body):
    payload = {"resolution": "480P", "video_model": "wan", "language": "zh", **body}
    return casting["client"].put(f"/studio/projects/{project['id']}/casting/setup",
                                 json=payload, headers=auth(casting))


def choose_style(casting, project, realism="photoreal", proposal_index=None, custom=None):
    payload = {"realism": realism}
    if proposal_index is None:
        payload["custom"] = custom or CUSTOM_STYLE
    else:
        payload["proposal_index"] = proposal_index
    return casting["client"].put(f"/studio/projects/{project['id']}/casting/style",
                                 json=payload, headers=auth(casting))


def get_state(casting, project, owner="owner"):
    response = casting["client"].get(f"/studio/projects/{project['id']}/casting",
                                     headers=auth(casting, owner))
    assert response.status_code == 200, response.text
    return response.json()


def item_by_bible(state, bible_id):
    for item in state["items"]:
        if item["bible_id"] == bible_id:
            return item
    raise AssertionError(f"没有条目对应总表行 {bible_id}")


def approve(casting, item_id, asset_id):
    return casting["client"].post(f"/studio/casting/items/{item_id}/approve",
                                  json={"asset_id": asset_id}, headers=auth(casting))


def skip_item(casting, item_id):
    return casting["client"].post(f"/studio/casting/items/{item_id}/skip", headers=auth(casting))


def patch_look(casting, item_id, look):
    return casting["client"].patch(f"/studio/casting/items/{item_id}", json={"look": look},
                                   headers=auth(casting))


def prepared_items(casting, *, count=1, **bible):
    """G0 已批准 + 开工已确认 + 风格已选定；返回 (project, [item_id])。"""
    project = make_project(casting)
    assert confirm_setup(casting, project).status_code == 200
    assert choose_style(casting, project).status_code == 200
    bibles = seed_items(casting, project, count=count, **bible)
    state = get_state(casting, project)
    return project, [item_by_bible(state, bible)["id"] for bible in bibles]


def quote_sheets(casting, project, entries, owner="owner"):
    response = casting["client"].post(f"/studio/projects/{project['id']}/casting/sheets/quote",
                                      json={"items": entries}, headers=auth(casting, owner))
    assert response.status_code == 200, response.text
    return response.json()


def start_sheets(casting, project, quote_id, owner="owner"):
    return casting["client"].post(f"/studio/projects/{project['id']}/casting/sheets/start",
                                  json={"quote_id": quote_id}, headers=auth(casting, owner))


def start_style(casting, project, quote_id):
    return casting["client"].post(f"/studio/projects/{project['id']}/casting/style/start",
                                  json={"quote_id": quote_id}, headers=auth(casting))


def audition(casting, project, *, item_id, text, variants, owner="owner"):
    return casting["client"].post(f"/studio/projects/{project['id']}/casting/voices/audition",
                                  json={"item_id": item_id, "text": text, "variants": variants},
                                  headers=auth(casting, owner))


def image_jobs(body):
    return [job for job in body["jobs"] if job["kind"] == "image"]


def tts_jobs(body):
    return [job for job in body["jobs"] if job["kind"] == "tts"]


def run_jobs(jobs):
    for job in jobs:
        assert run(casting_jobs.execute(job["id"])) is True, job["id"]


async def job_row(job_id):
    return await one("SELECT * FROM studio_jobs WHERE id=?", (job_id,))


async def sheet_assets(item_id):
    return await rows("""SELECT * FROM studio_assets WHERE item_id=? AND role='sheet'
        ORDER BY version_no, created_at""", (item_id,))


async def audio_assets(item_id):
    return await rows("""SELECT * FROM studio_assets WHERE item_id=? AND role='audition'
        ORDER BY version_no, created_at""", (item_id,))


async def expire_quote(quote_id):
    async with store.connection(transaction=True) as db:
        await db.execute("UPDATE studio_quotes SET expires_at=? WHERE id=?",
                         ("2000-01-01T00:00:00+00:00", quote_id))


async def force_status(job_id, status, run_token=None):
    """模拟崩溃现场：绕过 CAS 把任务钉在在途状态。"""
    async with store.connection(transaction=True) as db:
        await db.execute("UPDATE studio_jobs SET status=?, run_token=? WHERE id=?",
                         (status, run_token, job_id))


async def mark_style_succeeded(project, proposals=None):
    payload = store._json({"proposals": proposals if proposals is not None else PROPOSALS})
    async with store.connection(transaction=True) as db:
        await db.execute("""UPDATE studio_jobs SET status='succeeded',result_json=?,actual_amount='0',
            finished_at=? WHERE kind='brain' AND task='style_proposals' AND project_id=?""",
                         (payload, store.utcnow(), project["id"]))


def assert_wav_48k_mono16(path: Path) -> None:
    assert path.is_file(), path
    with wave.open(str(path), "rb") as handle:
        assert handle.getframerate() == 48000
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getnframes() > 0


def assert_voice_spec_shape(spec: dict) -> None:
    assert set(spec) == VOICE_SPEC_KEYS


def assert_audition_spec_shape(spec: dict) -> None:
    assert set(spec) == AUDITION_SPEC_KEYS


# ---------------------------------------------------------------------------
# 1. 完整主流程
# ---------------------------------------------------------------------------

def test_full_casting_flow_end_to_end(casting, monkeypatch, sheet_png):
    """开工确认 → 风格报价/确认/落库/选定 → 2 条目各 2 版出图 → 批准 + 跳过 → G1。"""
    client = casting["client"]
    requests = install_seedream(monkeypatch, lambda request: httpx.Response(200, json=_seedream_ok(sheet_png)))

    project = make_project(casting)

    # ② 开工确认
    response = confirm_setup(casting, project)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == STATE_KEYS
    assert body["g0_approved"] is True and body["items"] == []
    assert set(body["setup"]) == SETUP_KEYS
    assert body["setup"]["aspect"] == "16:9" and body["setup"]["sheet_size"] == SHEET_SIZE
    assert body["setup"]["language"] == "zh" and body["setup"]["video_model"] == "wan"
    assert body["setup"]["confirmed_at"]
    assert set(body["style"]) == STYLE_KEYS and body["style"]["chosen"] is None
    assert body["style"]["proposals"] == [] and body["style"]["proposal_job"] is None
    assert body["g1"] == {"approved": False, "total": 0, "done": 0, "skipped": 0}
    assert set(body["prices"]) == PRICE_KEYS
    assert body["prices"]["seedream_cny"] == pytest.approx(float(pricing.seedream_price()))

    # ③ 风格报价 → 确认 → 提案落库
    quote = client.post(f"/studio/projects/{project['id']}/casting/style/quote", headers=auth(casting))
    assert quote.status_code == 200, quote.text
    quote_body = quote.json()
    assert set(quote_body) == QUOTE_KEYS and quote_body["kind"] == "casting_style"
    assert [set(line) for line in quote_body["items"]] == [QUOTE_LINE_KEYS]
    assert quote_body["items"][0]["name"] == "风格提案" and quote_body["items"][0]["versions"] == 1

    started = start_style(casting, project, quote_body["id"])
    assert started.status_code == 200, started.text
    assert casting["calls"]["scheduled"] == [started.json()["style"]["proposal_job"]["id"]]
    assert started.json()["style"]["proposal_job"]["status"] == "queued"

    run(mark_style_succeeded(project))
    state = get_state(casting, project)
    assert set(state["style"]) == STYLE_KEYS
    assert [set(proposal) for proposal in state["style"]["proposals"]] == [PROPOSAL_KEYS] * 2
    assert [proposal["name"] for proposal in state["style"]["proposals"]] == [p["name"] for p in PROPOSALS]
    assert state["style"]["proposal_job"]["status"] == "succeeded"

    # ④ 选定风格（提案 + realism）
    assert choose_style(casting, project, realism="anime", proposal_index=1).status_code == 200
    chosen = get_state(casting, project)["style"]["chosen"]
    assert set(chosen) == CHOICE_KEYS
    assert chosen["source"] == "proposal" and chosen["proposal_index"] == 1
    assert chosen["realism"] == "anime"
    assert chosen["name"] == PROPOSALS[1]["name"] and chosen["visual_style"] == PROPOSALS[1]["visual_style"]
    assert chosen["palette"] == PROPOSALS[1]["palette"] and chosen["camera"] == PROPOSALS[1]["camera"]
    assert chosen["lighting"] == PROPOSALS[1]["lighting"] and chosen["rationale"] == PROPOSALS[1]["rationale"]

    # ⑤ 两个条目，各出 2 版
    bibles = seed_items(casting, project, count=2)
    state = get_state(casting, project)
    ids = [item_by_bible(state, bible)["id"] for bible in bibles]

    sheets_quote = quote_sheets(casting, project, [{"item_id": item_id, "versions": 2} for item_id in ids])
    assert set(sheets_quote) == QUOTE_KEYS and sheets_quote["kind"] == "casting_sheets"
    assert [set(line) for line in sheets_quote["items"]] == [QUOTE_LINE_KEYS] * 2
    assert [line["versions"] for line in sheets_quote["items"]] == [2, 2]
    assert [line["unit"] for line in sheets_quote["items"]] == [pytest.approx(SHEET_PRICE)] * 2
    assert [line["est"] for line in sheets_quote["items"]] == [pytest.approx(SHEET_PRICE * 2)] * 2
    assert sheets_quote["total"] == pytest.approx(SHEET_PRICE * 4)

    started = start_sheets(casting, project, sheets_quote["id"])
    assert started.status_code == 200, started.text
    jobs = image_jobs(started.json())
    assert len(jobs) == 4
    for job in jobs:
        assert set(job) == JOB_KEYS
        assert job["kind"] == "image" and job["status"] == "queued" and job["currency"] == "CNY"
        assert job["reserved_amount"] == pytest.approx(SHEET_PRICE)
        assert job["actual_amount"] is None and job["error_code"] is None
        assert job["item_id"] in ids and job["created_at"]

    # 真实块 B 出图路径 + 真实块 C 提示词，只有传输是假的。
    run_jobs(jobs)
    assert len(requests) == 4
    for request in requests:
        assert request.method == "POST"
        body = image_body(request)
        assert body["size"] == SHEET_SIZE and body["response_format"] == "b64_json"
        assert "image" not in body
        assert "三视图" in body["prompt"] and "原创角色" in body["prompt"]

    # ⑥ 资产落库
    for item_id in ids:
        assets = run(sheet_assets(item_id))
        assert [asset["version_no"] for asset in assets] == [1, 2]
        for asset in assets:
            assert asset["item_id"] == item_id and asset["role"] == "sheet" and asset["kind"] == "image"
            assert (asset["width"], asset["height"]) == (2560, 1440)
            assert asset["archived"] == 0
            path = casting["studio_dir"] / asset["rel_path"]
            assert path.is_file() and path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            meta = json.loads(asset["meta_json"])
            assert meta["size"] == SHEET_SIZE and meta["prompt"]

    for job in jobs:
        row = run(job_row(job["id"]))
        assert row["status"] == "succeeded"
        assert float(row["reserved_amount"]) == 0 and float(row["actual_amount"]) == pytest.approx(SHEET_PRICE)
    assert run(spend.today())["committed_cny"] == pytest.approx(SHEET_PRICE * 4)

    # ⑦ 逐字段形状
    state = get_state(casting, project)
    assert set(state) == STATE_KEYS and set(state["g1"]) == G1_KEYS
    assert state["g1"] == {"approved": False, "total": 2, "done": 0, "skipped": 0}
    for item in state["items"]:
        assert set(item) == ITEM_KEYS
        assert item["kind"] == "character" and item["status"] == "pending" and item["orphaned"] is False
        assert item["approved_asset_id"] is None and item["extra_prompt"] == ""
        assert item["reference_asset_ids"] == [] and item["needs_author"] is False
        assert set(item["voice"]) == VOICE_KEYS
        assert item["voice"] == {"spec": None, "approved_asset_id": None, "auditions": []}
        assert [version["version_no"] for version in item["versions"]] == [1, 2]
        for version in item["versions"]:
            assert set(version) == VERSION_KEYS
            assert version["archived"] is False and version["prompt"]
    kinds = {job["kind"] for job in state["jobs"]}
    assert kinds == {"image", "brain"}

    # ⑧ 批准 1 个、跳过 1 个 → G1 通过
    first = item_by_bible(state, bibles[0])
    second = item_by_bible(state, bibles[1])
    approved = approve(casting, first["id"], first["versions"][0]["asset_id"])
    assert approved.status_code == 200, approved.text
    approved_body = approved.json()
    assert set(approved_body) == ITEM_KEYS
    assert approved_body["status"] == "approved"
    assert approved_body["approved_asset_id"] == first["versions"][0]["asset_id"]
    assert [version["asset_id"] for version in approved_body["versions"]] == \
        [version["asset_id"] for version in first["versions"]]

    skipped = skip_item(casting, second["id"])
    assert skipped.status_code == 200 and skipped.json()["status"] == "skipped"

    final = get_state(casting, project)
    assert final["g1"] == {"approved": True, "total": 2, "done": 2, "skipped": 1}
    assert final["setup"] == state["setup"] and final["style"]["chosen"] == chosen


def test_sheet_prompt_uses_look_and_two_zone_layout(casting, monkeypatch, sheet_png):
    """真实块 C：人物新版式含「细节栏」，并把造型说明逐字段写进 Seedream 提示词。"""
    requests = install_seedream(monkeypatch, lambda request: httpx.Response(200, json=_seedream_ok(sheet_png)))
    project = make_project(casting)
    confirm_setup(casting, project)
    assert choose_style(casting, project).status_code == 200
    bible = seed_items(casting, project, count=1)[0]
    item = item_by_bible(get_state(casting, project), bible)
    look = {"hair": "齐耳短发，发尾略翘", "makeup": "眉尾淡疤，裸色唇",
            "top": "洗旧的灰蓝棉布工装", "bottom": "深灰束脚裤",
            "footwear": "磨白的帆布鞋", "accessories": "旧邮差包",
            "materials": "棉布起球，皮革开裂", "palette": "灰蓝、赭石、米白"}
    response = patch_look(casting, item["id"], look)
    assert response.status_code == 200, response.text
    assert response.json()["look"] == look and response.json()["look_source"] == "author"

    quote = quote_sheets(casting, project, [{"item_id": item["id"], "versions": 1}])
    job = image_jobs(start_sheets(casting, project, quote["id"]).json())[0]
    run_jobs([job])
    assert len(requests) == 1
    prompt = image_body(requests[0])["prompt"]
    assert "细节栏" in prompt
    for value in look.values():
        assert value in prompt


# ---------------------------------------------------------------------------
# 2. Seedream 超时 / 断连
# ---------------------------------------------------------------------------

def test_seedream_timeout_is_uncertain_and_release_clears_reservation(casting, monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("connection reset")

    requests = install_seedream(monkeypatch, handler)
    project, [item_id] = prepared_items(casting)
    quote = quote_sheets(casting, project, [{"item_id": item_id, "versions": 1}])
    job = image_jobs(start_sheets(casting, project, quote["id"]).json())[0]

    assert run(casting_jobs.execute(job["id"])) is True
    assert len(requests) == 1

    row = run(job_row(job["id"]))
    # 传输层异常（超时 / 断连）在适配器里统一归为 uncertain + transport_error。
    assert row["status"] == "uncertain" and row["error_code"] == "transport_error"
    assert float(row["reserved_amount"]) == pytest.approx(SHEET_PRICE)
    assert row["actual_amount"] is None and row["needs_recheck"] == 1
    assert run(spend.today())["committed_cny"] == pytest.approx(SHEET_PRICE)
    assert run(sheet_assets(item_id)) == []

    released = casting["client"].post(f"/studio/jobs/{job['id']}/release",
                                      json={"not_charged": True}, headers=auth(casting))
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "released"
    assert float(run(job_row(job["id"]))["reserved_amount"]) == 0
    assert run(spend.today())["committed_cny"] == 0
    assert len(requests) == 1


# ---------------------------------------------------------------------------
# 3. Seedream 429 / 400 → rejected，不结算、不重试
# ---------------------------------------------------------------------------

def test_seedream_4xx_is_rejected_without_retry(casting, monkeypatch):
    statuses = [429, 400]
    def handler(request):
        return httpx.Response(statuses.pop(0),
                              json={"error": {"code": "rate_limited", "message": "too many requests"}})

    requests = install_seedream(monkeypatch, handler)
    project, ids = prepared_items(casting, count=2)
    quote = quote_sheets(casting, project, [{"item_id": item_id, "versions": 1} for item_id in ids])
    jobs = image_jobs(start_sheets(casting, project, quote["id"]).json())
    assert len(jobs) == 2
    run_jobs(jobs)

    assert len(requests) == 2
    codes = set()
    for job in jobs:
        row = run(job_row(job["id"]))
        assert row["status"] == "rejected"
        assert float(row["reserved_amount"]) == 0 and float(row["actual_amount"]) == 0
        codes.add(row["error_code"])
    assert codes == {"http_429", "http_400"}
    assert run(spend.today())["committed_cny"] == 0
    assert run(rows("SELECT id FROM studio_assets WHERE role='sheet'")) == []


# ---------------------------------------------------------------------------
# 4. 报价只能确认一次 / 过期被拒
# ---------------------------------------------------------------------------

def test_quotes_confirm_once_and_expire(casting):
    client = casting["client"]
    project, [item_id] = prepared_items(casting)

    first = quote_sheets(casting, project, [{"item_id": item_id, "versions": 1}])
    assert start_sheets(casting, project, first["id"]).status_code == 200
    again = start_sheets(casting, project, first["id"])
    assert again.status_code == 409 and "只能确认一次" in again.json()["detail"]
    assert again.headers["cache-control"] == "private, no-store"

    second = quote_sheets(casting, project, [{"item_id": item_id, "versions": 1}])
    run(expire_quote(second["id"]))
    expired = start_sheets(casting, project, second["id"])
    assert expired.status_code == 409 and "过期" in expired.json()["detail"]

    style_quote = client.post(f"/studio/projects/{project['id']}/casting/style/quote",
                              headers=auth(casting)).json()
    assert start_style(casting, project, style_quote["id"]).status_code == 200
    repeated = start_style(casting, project, style_quote["id"])
    assert repeated.status_code == 409 and "只能确认一次" in repeated.json()["detail"]

    style_expired = client.post(f"/studio/projects/{project['id']}/casting/style/quote",
                                headers=auth(casting)).json()
    run(expire_quote(style_expired["id"]))
    assert start_style(casting, project, style_expired["id"]).status_code == 409

    assert len(image_jobs(get_state(casting, project))) == 1


# ---------------------------------------------------------------------------
# 5. 中文试听：CosyVoice + robot:B + 真实 ffmpeg
# ---------------------------------------------------------------------------

def test_chinese_audition_processes_audio_and_settles_by_chars(casting, monkeypatch, cosy_wav):
    factory = install_cosy(monkeypatch, cosy_wav)
    project, [item_id] = prepared_items(casting)

    response = audition(casting, project, item_id=item_id, text=TEXT_ZH, variants=[COSY_VARIANT])
    assert response.status_code == 200, response.text
    jobs = tts_jobs(response.json())
    assert len(jobs) == 1
    assert set(jobs[0]) == JOB_KEYS and jobs[0]["kind"] == "tts" and jobs[0]["status"] == "queued"
    assert jobs[0]["item_id"] == item_id
    assert jobs[0]["reserved_amount"] == pytest.approx(0.01)

    run_jobs(jobs)
    assert len(factory.calls) == 1
    assert factory.calls[0]["voice"] == COSY_VARIANT["voice"]
    assert factory.calls[0]["speech_rate"] == 1.0 and factory.calls[0]["pitch_rate"] == 1.0
    assert factory.synthesizers[0].texts == [TEXT_ZH]
    assert factory.synthesizers[0].closed is True

    row = run(job_row(jobs[0]["id"]))
    assert row["status"] == "succeeded"
    assert float(row["reserved_amount"]) == 0 and float(row["actual_amount"]) == pytest.approx(0.01)
    assert run(spend.today())["committed_cny"] == pytest.approx(0.01)

    assets = run(audio_assets(item_id))
    assert len(assets) == 1
    asset = assets[0]
    assert asset["kind"] == "audio" and asset["role"] == "audition" and asset["version_no"] == 1
    assert asset["has_audio"] == 1
    path = casting["studio_dir"] / asset["rel_path"]
    assert_wav_48k_mono16(path)

    probe = storage.probe_audio(path)
    assert probe["sample_rate"] == 48000 and probe["channels"] == 1
    assert probe["duration_s"] == pytest.approx(asset["duration_s"], abs=0.05)

    meta = json.loads(asset["meta_json"])
    assert meta["spec"] == COSY_VARIANT and meta["text"] == TEXT_ZH
    assert meta["sample_rate"] == 48000
    assert meta["duration_s"] == pytest.approx(asset["duration_s"], abs=0.01)
    assert meta["measured_lufs"] == pytest.approx(-16.0, abs=1.0)

    # 返回给前端的试听条目形状（§8.3）
    item = next(entry for entry in get_state(casting, project)["items"] if entry["id"] == item_id)
    assert set(item["voice"]) == VOICE_KEYS
    entry = item["voice"]["auditions"][0]
    assert set(entry) == AUDITION_KEYS
    assert entry["asset_id"] == asset["id"] and entry["spec"] == COSY_VARIANT
    assert entry["text"] == TEXT_ZH and entry["archived"] is False
    assert entry["duration_s"] == pytest.approx(asset["duration_s"], abs=0.01)
    assert entry["measured_lufs"] == pytest.approx(meta["measured_lufs"])
    assert_audition_spec_shape(entry["spec"])


# ---------------------------------------------------------------------------
# 6. 英文试听：edge-tts 免费
# ---------------------------------------------------------------------------

def test_doubao_audition_end_to_end(casting, monkeypatch, doubao_mp3):
    """真实适配器 + MockTransport + 真实 ffmpeg：mp3 进，48k 单声道 WAV 出。"""
    requests = install_doubao(monkeypatch, doubao_mp3)
    project, [item_id] = prepared_items(casting)

    response = audition(casting, project, item_id=item_id, text=TEXT_ZH, variants=[DOUBAO_VARIANT])
    assert response.status_code == 200, response.text
    job = tts_jobs(response.json())[0]
    assert job["reserved_amount"] == pytest.approx(0.01)
    assert get_state(casting, project)["prices"]["doubao_cny_per_10k_chars"] == pytest.approx(3.0)

    run_jobs([job])
    assert len(requests) == 1, "豆包只允许一次 POST"
    request = requests[0]
    assert str(request.url) == tts_doubao.ENDPOINT
    assert request.headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    body = json.loads(request.content)
    assert body["req_params"]["text"] == TEXT_ZH
    assert body["req_params"]["speaker"] == DOUBAO_VARIANT["voice"]
    assert body["req_params"]["audio_params"] == {"format": "mp3", "sample_rate": 24000,
                                                  "speech_rate": 20}
    assert isinstance(body["req_params"]["additions"], str)
    additions = json.loads(body["req_params"]["additions"])
    assert additions == {"context_texts": [DOUBAO_DIRECTION], "post_process": {"pitch": -3}}

    row = run(job_row(job["id"]))
    assert row["status"] == "succeeded"
    assert float(row["reserved_amount"]) == 0 and float(row["actual_amount"]) == pytest.approx(0.01)
    assert run(spend.today())["committed_cny"] == pytest.approx(0.01)

    assets = run(audio_assets(item_id))
    assert len(assets) == 1
    asset = assets[0]
    path = casting["studio_dir"] / asset["rel_path"]
    assert_wav_48k_mono16(path)
    probe = storage.probe_audio(path)
    assert probe["sample_rate"] == 48000 and probe["channels"] == 1

    meta = json.loads(asset["meta_json"])
    assert meta["spec"] == DOUBAO_VARIANT and meta["text"] == TEXT_ZH
    assert meta["sample_rate"] == 48000
    assert meta["measured_lufs"] == pytest.approx(-16.0, abs=1.0)

    item = next(entry for entry in get_state(casting, project)["items"] if entry["id"] == item_id)
    entry = item["voice"]["auditions"][0]
    assert entry["spec"] == DOUBAO_VARIANT and entry["spec"]["direction"] == DOUBAO_DIRECTION
    assert_audition_spec_shape(entry["spec"])


def test_doubao_audition_blocks_without_key_or_ffmpeg(casting, monkeypatch):
    """缺 Key / 缺 ffmpeg 都在付费请求之前 503；请求数为 0。"""
    requests = install_doubao(monkeypatch, b"unused")
    project, [item_id] = prepared_items(casting)

    monkeypatch.delenv("VOLC_SPEECH_API_KEY", raising=False)
    response = audition(casting, project, item_id=item_id, text=TEXT_ZH, variants=[DOUBAO_VARIANT])
    assert response.status_code == 503 and "VOLC_SPEECH_API_KEY" in response.json()["detail"]
    assert requests == [] and tts_jobs(get_state(casting, project)) == []
    assert run(spend.today())["committed_cny"] == pytest.approx(0)

    monkeypatch.setenv("VOLC_SPEECH_API_KEY", "offline-volc-key")
    monkeypatch.setattr(casting_module.shutil, "which", lambda name: None)
    response = audition(casting, project, item_id=item_id, text=TEXT_ZH, variants=[DOUBAO_VARIANT])
    assert response.status_code == 503 and "ffmpeg" in response.json()["detail"]
    assert requests == [] and tts_jobs(get_state(casting, project)) == []
    assert run(spend.today())["committed_cny"] == pytest.approx(0)


def test_doubao_voice_approve_writes_direction_and_baseline(casting, monkeypatch, doubao_mp3):
    install_doubao(monkeypatch, doubao_mp3)
    project, [item_id] = prepared_items(casting)
    response = audition(casting, project, item_id=item_id, text=TEXT_ZH, variants=[DOUBAO_VARIANT])
    run_jobs(tts_jobs(response.json()))
    item = next(entry for entry in get_state(casting, project)["items"] if entry["id"] == item_id)
    asset_id = item["voice"]["auditions"][0]["asset_id"]
    url = f"/studio/casting/items/{item_id}/voice/approve"

    # 不带 baseline：默认取该条试听的指示。
    body = casting["client"].post(url, json={"asset_id": asset_id}, headers=auth(casting)).json()
    assert body["voice"]["spec"] == {**DOUBAO_VARIANT, "baseline": DOUBAO_DIRECTION}
    assert_voice_spec_shape(body["voice"]["spec"])

    # 带 baseline：角色基调可以改成更短的一句。
    body = casting["client"].post(url, json={"asset_id": asset_id, "baseline": "克制，像在自言自语"},
                                  headers=auth(casting)).json()
    assert body["voice"]["spec"]["direction"] == DOUBAO_DIRECTION
    assert body["voice"]["spec"]["baseline"] == "克制，像在自言自语"
    stored = json.loads(run(one("SELECT spec_json FROM studio_items WHERE id=?", (item_id,)))["spec_json"])
    assert stored["voice"] == body["voice"]["spec"]


# ---------------------------------------------------------------------------
# 6b. 英文试听：edge-tts 免费
# ---------------------------------------------------------------------------

def test_english_audition_is_free_and_outputs_48k_wav(casting, monkeypatch, edge_mp3):
    state = install_edge(monkeypatch, edge_mp3, [{"offset": 1000000, "duration": 1750000, "text": "The"}])
    project, [item_id] = prepared_items(casting)

    response = audition(casting, project, item_id=item_id, text=TEXT_EN, variants=[EDGE_VARIANT])
    assert response.status_code == 200, response.text
    job = tts_jobs(response.json())[0]
    assert job["reserved_amount"] == 0

    run_jobs([job])
    assert len(state["built"]) == 1
    assert state["built"][0]["voice"] == EDGE_VARIANT["voice"]
    assert state["built"][0]["text"] == TEXT_EN

    row = run(job_row(job["id"]))
    assert row["status"] == "succeeded"
    assert float(row["reserved_amount"]) == 0 and float(row["actual_amount"]) == 0
    # §6：edge-tts 预留 0，成功也按 0 结算，不产生费用。
    assert run(spend.today())["committed_cny"] == 0
    assert all(float(record["amount"]) == 0 for record in run(rows(
        "SELECT actual_amount AS amount FROM studio_jobs WHERE kind='tts'")))

    assets = run(audio_assets(item_id))
    assert len(assets) == 1
    assert_wav_48k_mono16(casting["studio_dir"] / assets[0]["rel_path"])
    meta = json.loads(assets[0]["meta_json"])
    assert meta["spec"] == EDGE_VARIANT
    assert storage.probe_audio(casting["studio_dir"] / assets[0]["rel_path"])["sample_rate"] == 48000


# ---------------------------------------------------------------------------
# 7. 选定声线
# ---------------------------------------------------------------------------

def test_voice_approve_writes_selected_spec(casting, monkeypatch, cosy_wav):
    install_cosy(monkeypatch, cosy_wav)
    project, [item_id] = prepared_items(casting)
    response = audition(casting, project, item_id=item_id, text=TEXT_ZH,
                        variants=[COSY_VARIANT, NARRATION_VARIANT])
    jobs = tts_jobs(response.json())
    assert len(jobs) == 2
    run_jobs(jobs)

    item = next(entry for entry in get_state(casting, project)["items"] if entry["id"] == item_id)
    specs = {entry["asset_id"]: entry["spec"] for entry in item["voice"]["auditions"]}
    assert len(specs) == 2
    assert sorted(json.dumps(spec, sort_keys=True) for spec in specs.values()) == \
        sorted(json.dumps(spec, sort_keys=True) for spec in (COSY_VARIANT, NARRATION_VARIANT))
    chosen_asset, chosen_spec = next(iter(specs.items()))

    approved = casting["client"].post(f"/studio/casting/items/{item_id}/voice/approve",
                                     json={"asset_id": chosen_asset}, headers=auth(casting))
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert set(body) == ITEM_KEYS
    assert set(body["voice"]) == VOICE_KEYS
    assert body["voice"]["approved_asset_id"] == chosen_asset
    assert body["voice"]["spec"] == {**chosen_spec, "baseline": None}
    assert_voice_spec_shape(body["voice"]["spec"])
    assert [entry["asset_id"] for entry in body["voice"]["auditions"]] == list(specs)

    stored = json.loads(run(one("SELECT spec_json FROM studio_items WHERE id=?", (item_id,)))["spec_json"])
    assert stored["voice"] == {**chosen_spec, "baseline": None}
    assert run(one("SELECT voice_asset_id FROM studio_items WHERE id=?", (item_id,)))["voice_asset_id"] \
        == chosen_asset


# ---------------------------------------------------------------------------
# 8. 声线目录与前端键名
# ---------------------------------------------------------------------------

def test_voice_catalog_matches_fx_presets_and_frontend_keys(casting):
    response = casting["client"].get("/studio/casting/voice-catalog", headers=auth(casting))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"voices", "fx"}

    assert body["voices"] == voices.VOICE_CATALOG
    assert [set(option) for option in body["voices"]] == [VOICE_OPTION_KEYS] * len(body["voices"])
    assert body["fx"] == {kind: sorted(levels) for kind, levels in audio.FX_PRESETS.items()}
    assert body["fx"] == {"robot": ["A", "B", "Bd", "C", "D", "E"], "beast": ["A", "B", "C"], "inner": ["A"]}

    engines = {}
    for option in body["voices"]:
        engines.setdefault(option["engine"], []).append(option["voice"])
    assert set(engines) == {"doubao", "cosyvoice", "edge-tts"}
    assert DOUBAO_VARIANT["voice"] in engines["doubao"]
    assert COSY_VARIANT["voice"] in engines["cosyvoice"]
    assert EDGE_VARIANT["voice"] in engines["edge-tts"]
    doubao_options = [option for option in body["voices"] if option["engine"] == "doubao"]
    assert len(doubao_options) == 11
    assert all(option["lang"] == "zh" and option["voice"].endswith("_uranus_bigtts")
               and option["label"] and option["note"] for option in doubao_options)

    # 前端 castingFxLabel 里硬编码的特效类别必须都能在目录里找到。
    source = FRONTEND_TS.read_text(encoding="utf-8")
    label = re.search(r"const castingFxLabel[^\n]*", source)
    assert label, "frontend/lib/studio-casting.ts 缺少 castingFxLabel"
    used = set(re.findall(r"(robot|beast|inner)\s*:", label.group(0)))
    assert used == set(body["fx"]) == set(audio.FX_PRESETS)
    for kind in used:
        assert body["fx"][kind], kind
    # 前端类型定义与 §8 的 audio 目录逐字段一致。
    assert "Record<string, string[]>" in source
    assert 'fx: Record<string, string[]>' in source


# ---------------------------------------------------------------------------
# 9. 参考图
# ---------------------------------------------------------------------------

def test_reference_image_is_downscaled_and_project_scoped(casting, monkeypatch, sheet_png):
    bodies: list[dict] = []

    def handler(request):
        bodies.append(image_body(request))
        return httpx.Response(200, json=_seedream_ok(sheet_png))

    install_seedream(monkeypatch, handler)
    project, [item_id] = prepared_items(casting)

    upload = casting["client"].post(f"/studio/projects/{project['id']}/assets", headers=auth(casting),
                                    files={"file": ("ref.png", _png(3200, 1200), "image/png")})
    assert upload.status_code == 201, upload.text
    uploaded = upload.json()
    assert uploaded["kind"] == "image" and "rel_path" not in uploaded
    reference_id = uploaded["id"]

    quote = quote_sheets(casting, project,
                         [{"item_id": item_id, "versions": 1, "reference_asset_ids": [reference_id]}])
    assert quote["total"] == pytest.approx(SHEET_PRICE)
    job = image_jobs(start_sheets(casting, project, quote["id"]).json())[0]
    run_jobs([job])

    assert len(bodies) == 1
    body = bodies[0]
    assert isinstance(body["image"], str) and body["image"].startswith("data:image/")
    payload = base64.b64decode(body["image"].split(",", 1)[1])
    with Image.open(io.BytesIO(payload)) as image:
        assert max(image.size) <= 1536
        assert image.size == (1536, 576)
    asset = run(sheet_assets(item_id))[0]
    assert json.loads(asset["meta_json"])["reference_asset_ids"] == [reference_id]

    # 别的项目的素材（同一个作者）与别人的素材都被拒。
    other_project = run(new_project(title="别的项目"))
    foreign = run(new_asset(other_project))
    outsider_project = run(new_project(owner="other", title="他人项目"))
    outsider_asset = run(new_asset(outsider_project, owner="other"))
    for rejected_id in (foreign, outsider_asset, str(uuid.uuid4())):
        response = casting["client"].post(
            f"/studio/projects/{project['id']}/casting/sheets/quote",
            json={"items": [{"item_id": item_id, "versions": 1, "reference_asset_ids": [rejected_id]}]},
            headers=auth(casting))
        assert response.status_code == 404, (rejected_id, response.text)
        assert response.headers["cache-control"] == "private, no-store"
    assert len(bodies) == 1


def test_derived_reference_is_first_deduped_and_png(casting, monkeypatch, sheet_png):
    """派生：执行期合并（已选定排第一、去重），参考图统一 PNG 字节，多版本每版都派生。"""
    bodies: list[dict] = []

    def handler(request):
        bodies.append(image_body(request))
        return httpx.Response(200, json=_seedream_ok(sheet_png))

    install_seedream(monkeypatch, handler)
    project, [item_id] = prepared_items(casting)

    upload = casting["client"].post(f"/studio/projects/{project['id']}/assets", headers=auth(casting),
                                    files={"file": ("ref.png", _png(1200, 900), "image/png")})
    assert upload.status_code == 201, upload.text
    reference_id = upload.json()["id"]

    # ① 先出一张并批准为已选定版本。
    first = quote_sheets(casting, project,
                         [{"item_id": item_id, "versions": 1, "reference_asset_ids": [reference_id]}])
    run_jobs(image_jobs(start_sheets(casting, project, first["id"]).json()))
    approved_id = run(sheet_assets(item_id))[0]["id"]
    assert approve(casting, item_id, approved_id).status_code == 200

    # ② 第二批：派生 + 显式参考里再带上已选定版本（执行期去重），2 版。
    quote = quote_sheets(casting, project,
                         [{"item_id": item_id, "versions": 2, "derive_from_approved": True,
                           "reference_asset_ids": [reference_id, approved_id]}])
    assert quote["items"][0]["versions"] == 2
    started = start_sheets(casting, project, quote["id"]).json()
    jobs = [job for job in image_jobs(started) if job["status"] == "queued"]
    assert len(jobs) == 2
    run_jobs(jobs)

    assert len(bodies) == 3
    for body in bodies[1:]:
        uris = body["image"] if isinstance(body["image"], list) else [body["image"]]
        assert len(uris) == 2, uris  # 已选定 + 显式，重复的那张被去掉
        for uri in uris:
            assert uri.startswith("data:image/png;base64,")
            payload = base64.b64decode(uri.split(",", 1)[1])
            with Image.open(io.BytesIO(payload)) as image:
                assert image.format == "PNG"

    # 两个新版本都记下「已选定排第一」的参考图清单。
    for asset in run(sheet_assets(item_id))[1:]:
        assert asset["version_no"] in (2, 3)
        assert json.loads(asset["meta_json"])["reference_asset_ids"] == [approved_id, reference_id]


# ---------------------------------------------------------------------------
# 10. 重启恢复
# ---------------------------------------------------------------------------

def test_restart_recovery_marks_inflight_casting_jobs_uncertain(casting, monkeypatch):
    requests = blocked_seedream(monkeypatch)
    factory = install_cosy(monkeypatch, b"never used")

    project, ids = prepared_items(casting, count=2)
    quote = quote_sheets(casting, project, [{"item_id": item_id, "versions": 1} for item_id in ids])
    started = start_sheets(casting, project, quote["id"]).json()
    images = image_jobs(started)
    tts = tts_jobs(audition(casting, project, item_id=ids[0], text=TEXT_ZH,
                            variants=[COSY_VARIANT, NARRATION_VARIANT]).json())
    assert len(images) == 2 and len(tts) == 2

    run(force_status(images[0]["id"], "running", run_token="deadbeef"))
    run(force_status(images[1]["id"], "submitting", run_token="deadbeef"))
    run(force_status(tts[0]["id"], "running", run_token="deadbeef"))
    run(force_status(tts[1]["id"], "submitting", run_token="deadbeef"))

    run(recovery.recover_studio_jobs())

    for job in [*images, *tts]:
        row = run(job_row(job["id"]))
        assert row["status"] == "uncertain", row["id"]
        assert row["error_code"] == "restart_during_submission"
        assert float(row["reserved_amount"]) == pytest.approx(float(job["reserved_amount"]))
        assert row["actual_amount"] is None
    assert requests == [] and factory.calls == []
    assert run(rows("SELECT id FROM studio_assets WHERE role IN ('sheet','audition')")) == []
    # running/submitting 不会被重发，仍是 queued 的也没有被付费执行。
    statuses = {job["id"]: job["status"] for job in get_state(casting, project)["jobs"]}
    assert set(statuses[job["id"]] for job in [*images, *tts]) == {"uncertain"}


# ---------------------------------------------------------------------------
# 11. 门禁与归属
# ---------------------------------------------------------------------------

def test_gates_and_ownership(casting):
    client = casting["client"]
    project, [item_id] = prepared_items(casting)
    asset = run(new_asset(project, item_id=item_id))
    quote = quote_sheets(casting, project, [{"item_id": item_id, "versions": 1}])

    for name in ("other", "outsider"):
        headers = auth(casting, name)
        checks = [
            ("get", f"/studio/projects/{project['id']}/casting", None),
            ("put", f"/studio/projects/{project['id']}/casting/setup",
             {"resolution": "480P", "video_model": "wan", "language": "zh"}),
            ("post", f"/studio/projects/{project['id']}/casting/style/quote", None),
            ("post", f"/studio/projects/{project['id']}/casting/sheets/quote",
             {"items": [{"item_id": item_id, "versions": 1}]}),
            ("post", f"/studio/projects/{project['id']}/casting/sheets/start", {"quote_id": quote["id"]}),
            ("post", f"/studio/projects/{project['id']}/casting/voices/audition",
             {"item_id": item_id, "text": TEXT_ZH, "variants": [COSY_VARIANT]}),
            ("patch", f"/studio/casting/items/{item_id}", {"extra_prompt": "x"}),
            ("post", f"/studio/casting/items/{item_id}/approve", {"asset_id": asset}),
            ("post", f"/studio/casting/items/{item_id}/skip", None),
            ("post", f"/studio/casting/assets/{asset}/archive", None),
        ]
        for method, url, body in checks:
            call = getattr(client, method)
            response = call(url, headers=headers) if body is None else call(url, json=body, headers=headers)
            assert response.status_code == 404, (name, url, response.text)
            assert response.headers["cache-control"] == "private, no-store", (name, url)

    # G0 未批准：状态只读可看，全部写接口 409 且零付费调用。
    gated = make_project(casting, title="门禁项目")
    bible = run(new_bible(gated))
    casting["gates"]["g0"] = False

    state = get_state(casting, gated)
    assert state["g0_approved"] is False and state["setup"] is None
    assert state["style"] == {"chosen": None, "proposals": [], "proposal_job": None}
    assert state["items"] == [] and state["jobs"] == []

    writes = [
        ("put", f"/studio/projects/{gated['id']}/casting/setup",
         {"resolution": "480P", "video_model": "wan", "language": "zh"}),
        ("post", f"/studio/projects/{gated['id']}/casting/style/quote", None),
        ("post", f"/studio/projects/{gated['id']}/casting/sheets/quote",
         {"items": [{"item_id": bible, "versions": 1}]}),
        ("post", f"/studio/projects/{gated['id']}/casting/sheets/start", {"quote_id": "nope"}),
        ("put", f"/studio/projects/{gated['id']}/casting/style",
         {"realism": "photoreal", "proposal_index": 0}),
        ("post", f"/studio/projects/{gated['id']}/casting/voices/audition",
         {"item_id": bible, "text": TEXT_ZH, "variants": [COSY_VARIANT]}),
    ]
    for method, url, body in writes:
        call = getattr(client, method)
        response = call(url, headers=auth(casting)) if body is None else call(url, json=body, headers=auth(casting))
        assert response.status_code == 409, (url, response.text)
        assert response.headers["cache-control"] == "private, no-store"

    assert client.get("/studio/casting/voice-catalog", headers=auth(casting)).status_code == 200
    assert casting["calls"]["scheduled"] == []
    assert run(rows("SELECT id FROM studio_jobs WHERE project_id=?", (gated["id"],))) == []
    assert run(rows("SELECT id FROM studio_assets WHERE project_id=?", (gated["id"],))) == []
