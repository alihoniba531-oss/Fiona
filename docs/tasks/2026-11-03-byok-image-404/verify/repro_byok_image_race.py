"""用法：<backend>/.venv/bin/python repro_byok_image_race.py <backend 目录>
复现：BYOK Claude 智能体生图 → generated_image 事件先于消息入库 → 图片请求 404。
全部在临时库/临时上传目录里跑，不碰真实库；模型调用用假传输回放 tool_use，不调 Seedream。"""
import asyncio, json, os, sys, time
from io import BytesIO
ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.getcwd()  # backend 目录
import tempfile
HERE = tempfile.mkdtemp(prefix="byok-image-race-")
os.environ["FIONA_DB_PATH"] = os.path.join(HERE, "fiona.db")
os.environ["FIONA_UPLOADS_DIR"] = os.path.join(HERE, "uploads")
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["DEV_MODE"] = "1"
os.environ.setdefault("FIONA_BYOK_SECRET", "0" * 64)
# 占位值：部分模块在导入时就构造客户端；脚本全程假传输，不会真实外呼。
os.environ.setdefault("DASHSCOPE_API_KEY", "placeholder-not-used")
os.environ.setdefault("JWT_SECRET", "placeholder-not-used")
sys.path[:0] = [ROOT, os.path.join(ROOT, "tests")]
os.chdir(ROOT)
from PIL import Image
import main
import database
import services.chat_service as chat
import services.claude_agent as agent
from tools.image_generation import _persist_png
from test_claude_agent_runtime import FakeStream, message, call
from fastapi.testclient import TestClient

USER = "imgrace-user"
buf = BytesIO(); Image.new("RGB", (64, 36), "red").save(buf, format="PNG"); PNG = buf.getvalue()
timeline = []
t0 = time.monotonic()
def mark(*items): timeline.append((round(time.monotonic() - t0, 3),) + items)

async def fake_generate_image(prompt, aspect_ratio="1:1", *, model_id=None):
    image_path, w, h = _persist_png(PNG)
    mark("file_persisted", image_path)
    return {"image_path": image_path, "model": model_id or "doubao-seedream-5-0-flash", "width": w, "height": h}

real_save = chat._save_response
async def traced_save(ctx, state, image_path=None):
    mark("save_response_begin", image_path)
    await real_save(ctx, state, image_path=image_path)
    mark("save_response_done", image_path)

streams = [
    FakeStream(message("tool_use", content=[call("generate_image", {"prompt": "宋末江湖，汴水渡口", "aspect_ratio": "16:9"})]), "我用 16:9 横版画一张。"),
    FakeStream(message(text="画好了。"), "画好了。"),
]
chat.generate_image = fake_generate_image
chat.image_model_available = lambda model: True
chat._save_response = traced_save
chat.check_chat_daily_cap = lambda *a, **k: None
async def _noop(*a, **k): pass
chat._normal_followups = _noop
chat.set_message_image_summary = _noop
chat.detect_mode = lambda *a, **k: "friend"
agent.open_agent_stream = lambda config, messages, **kw: streams.pop(0)

client = TestClient(main.app, client=("127.0.0.1", 50123))
def http_get(path):
    r = client.get(path, headers={"X-Dev-User": USER})
    return r.status_code, r.headers.get("content-type", ""), len(r.content)

async def run():
    await database.init_db()
    await database.get_or_create_user(USER)
    ctx = chat.ChatContext(USER, "画一张", False, None, "画一张", [], 0, "persona",
                           [{"role": "user", "content": "画一张"}], conversation_id=None,
                           byok_config={"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5-5", "api_key": "fake"})
    state = chat.ChatState(trace={}, sys_prompt_final="persona")
    image_path = None
    results = {}
    async for event in agent.stream_claude_agent(ctx, state):
        if not (isinstance(event, str) and event.startswith("data: ")):
            continue
        payload = json.loads(event[6:])
        mark("sse", sorted(payload.keys()))
        if "generated_image" in payload:
            image_path = payload["generated_image"]["image_path"]
            # 前端 GeneratedImage 在收到事件的同一刻就 apiFetch(imageUrl)
            results["helper_at_event"] = await main._can_view_generated_image(USER, image_path)
            results["http_at_event"] = await asyncio.to_thread(http_get, image_path)
            mark("client_fetch_at_event", results["helper_at_event"], results["http_at_event"])
    results["helper_after_stream"] = await main._can_view_generated_image(USER, image_path)
    results["http_after_stream"] = await asyncio.to_thread(http_get, image_path)
    mark("client_fetch_after_stream", results["helper_after_stream"], results["http_after_stream"])
    results["file_exists_after"] = os.path.exists(os.path.join(os.environ["FIONA_UPLOADS_DIR"], os.path.basename(image_path)))
    results["billable"] = state.billable; results["response_saved"] = state.response_saved
    return results

results = asyncio.run(run())
print("=== timeline ===")
for row in timeline: print(row)
print("=== results ===")
for k, v in results.items(): print(f"{k}: {v}")
print("VERDICT:", "FIXED" if results["http_at_event"][0] == 200 and results["http_after_stream"][0] == 200 else "RACE_REPRODUCED")
