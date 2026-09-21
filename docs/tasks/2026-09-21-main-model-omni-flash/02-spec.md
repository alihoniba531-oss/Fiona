# 规格：主力对话模型切换为 qwen3.8-omni-flash

任务日期：2026-09-21。级别：L1（一个事实变更，多处陈述点同步）。你是独立执行进程，看不到对话上下文；本文件没写的不要自由发挥。

## 1. 目标

把后端主力槽（`MAIN_MODEL`）从 `qwen3.8-max` 换成 `qwen3.8-omni-flash`，并把仓库里所有把「主力模型 = qwen3.8-max」当作事实陈述的地方同步更新。轻量槽 `qwen3.8-flash`、视觉 `qwen-vl-max`、搜索 `qwen-plus`、生图、ASR、TTS、官方搭档 `deepseek-v4-pro` 一律不动。

派单方已用真实密钥探测过 `qwen3.8-omni-flash` 在百炼 OpenAI 兼容接口上的行为：非流式、流式、`response_format=json_object`、`enable_thinking=false` 都正常；开思考时会返回 `reasoning_content` 并消耗 `reasoning_tokens`。现有 `MAIN_EXTRA_BODY = {"enable_thinking": False}` 在全部 10 个 `model=MAIN_MODEL` 调用点都已传入，**不需要改调用点**。

## 2. 白名单（只准改这些）

- `backend/llm.py`：第 72 行常量与第 73、85 行注释。
- `backend/exchange_models.py`：第 30 行的 label 映射，加一条 `"qwen3.8-omni-flash": "Qwen3.8 Omni Flash"`（保留原有两条）。
- `backend/matcher.py` 第 4 行、`backend/model_router.py` 第 4 行的注释。
- `backend/.env.example` 第 13 行注释。
- `CLAUDE.md` 第 10 行、`PLAN.md` 第 43 与 95 行、`docs/ARCHITECTURE.md` 第 127 行。
- `backend/tests/`：仅当某个测试把 `qwen3.8-max` 当作**当前配置**来断言时才改；`test_exchange_exports.py` 第 61 行断言的是「旧快照不得被回填成当前模型」，把 `"qwen3.8-max"` 改成 `"qwen3.8-omni-flash"` 并保留 `"Qwen"`、`"DeepSeek"`、`"deepseek-v4-pro"`；`test_exchange_models.py` 第 42 行引用的是常量，不用改。

**不动**：`frontend/**`、`backend/services/**`、`backend/tools/**`、其他所有 `.py`、`README.md`（它只写「Qwen 主力模型」，不含具体型号）。

## 3. 陈述点清单（改前全库 `grep -rniE "qwen3\.8[ -]max"` 排除 node_modules/.next/.venv/docs/tasks/docs/design 共 12 处（含 test_exchange_exports.py:61），改后除 `exchange_models.py` 的 label 映射保留原键、`PLAN.md` 历史记录段落外，其余必须为 0）

改法：
- `llm.py:72` → `MAIN_MODEL      = "qwen3.8-omni-flash"   # 主力大脑（2026-09-21 由 qwen3.8-max 切换；更早为 DeepSeek deepseek-chat）`
- `llm.py:73` 注释里的 `qwen3.8-max` → `qwen3.8-omni-flash`（思考模式的说明仍成立，派单方实测开思考会返回 reasoning_content）。
- `llm.py:85`、`matcher.py:4`、`model_router.py:4`、`.env.example:13`、`CLAUDE.md:10`、`docs/ARCHITECTURE.md:127`、`PLAN.md:95`：把主力型号改为 `qwen3.8-omni-flash`；`.env.example` 与 `CLAUDE.md` 用小写 id。
- `PLAN.md:43` 是 2026-09-05 的历史记录（「自己的分身发言继续使用 Qwen3.8 Max」），**不改**，但在 `PLAN.md` 「产品定位」或最近一条状态记录后追加一行：`- 2026-09-21：主力对话槽由 qwen3.8-max 切换为 qwen3.8-omni-flash；轻量槽、视觉、搜索、生图、语音与官方搭档模型不变。分身交流中自己的分身随主力槽一起切换。`
- `PLAN.md:95` 所在的列表项同步。

## 4. 验收（在 `backend/` 目录执行，先跑对照再判定）

```bash
grep -c '"qwen3.8-omni-flash"' llm.py                       # 期望 1（改前 0）
grep -c 'MAIN_MODEL      = "qwen3.8-max"' llm.py             # 期望 0（改前 1）
grep -c '"qwen3.8-omni-flash": "Qwen3.8 Omni Flash"' exchange_models.py   # 期望 1（改前 0）
cd .. && grep -rniE "qwen3\.8[ -]max" --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.git . | grep -v "docs/tasks/\|docs/design/\|\.local-exports" | grep -vE "exchange_models.py:.*\"qwen3.8-max\": \"Qwen3.8 Max\"|PLAN.md:43|llm.py:72.*由 qwen3.8-max 切换|PLAN.md:.*由 qwen3.8-max 切换" | wc -l   # 期望 0（改前 12）
cd backend && python -m pytest -q -p no:cacheprovider 2>&1 | tail -3   # 期望全部通过，用例数 = 基线 829 passed
python - <<'PY'
import os; os.environ.setdefault("DEV_MODE","1"); os.environ.setdefault("DASHSCOPE_API_KEY","x"); os.environ.setdefault("JWT_SECRET","x"*40)
import llm, exchange_models
assert llm.MAIN_MODEL == "qwen3.8-omni-flash"
m = exchange_models.get_exchange_model("main"); assert m.model == "qwen3.8-omni-flash" and m.label == "Qwen3.8 Omni Flash", m
print("constants ok")
PY
```

不要启动服务器，不要调用真实模型；真实对话验证由派单方做。

## 5. 报告

写到 `docs/tasks/2026-09-21-main-model-omni-flash/03-report.md`：改了哪些行、§3 清单逐条对应、§4 每条命令原始输出。
