# 主力模型切换实施报告

执行日期：2026-09-21

## 1. 改动摘要

- `backend/llm.py:72-73,85`：`MAIN_MODEL` 切换为 `qwen3.8-omni-flash`，同步思考模式与轻量槽回退说明；迁移注释保留旧型号。
- `backend/exchange_models.py:30`：在既有 `deepseek-v4-pro`、`qwen3.8-max` label 映射之外新增 `qwen3.8-omni-flash` → `Qwen3.8 Omni Flash`。
- `backend/matcher.py:4`、`backend/model_router.py:4`：同步主力槽注释。
- `backend/.env.example:13`、`CLAUDE.md:10`：同步当前主力模型 id。
- `PLAN.md:43-44,96`：保留 2026-09-05 历史陈述，在其后新增 2026-09-21 切换记录，并同步当前模型列表。
- `docs/ARCHITECTURE.md:127`：同步主力模型说明。
- `backend/tests/test_exchange_exports.py:61`：旧快照不得展示“当前配置”的断言改查 `qwen3.8-omni-flash`；`DeepSeek`、`deepseek-v4-pro`、`Qwen` 保持不变。

未修改调用点、轻量/视觉/搜索/生图/ASR/TTS/官方搭档模型，也未修改 `frontend/**`、`backend/services/**`、`backend/tools/**`、`README.md` 或数据库。未启动服务器，未调用真实模型。

## 2. §3 陈述点逐条对应

1. `backend/llm.py:72`：常量改为 `qwen3.8-omni-flash`，并按规格写入 2026-09-21 迁移注释。
2. `backend/llm.py:73`：默认思考模式说明改为新型号。
3. `backend/llm.py:85`：轻量槽失败回退说明改为新型号。
4. `backend/exchange_models.py:30`：保留旧 `qwen3.8-max` label 键，新增新型号 label。
5. `backend/matcher.py:4`：匹配主力大脑说明改为新型号。
6. `backend/model_router.py:4`：`main` 槽说明改为新型号。
7. `backend/.env.example:13`：主力模型说明改为小写新 id。
8. `CLAUDE.md:10`：主力模型说明改为小写新 id。
9. `docs/ARCHITECTURE.md:127`：当前主力模型改为新型号。
10. `PLAN.md:43-44`：第 43 行历史记录不改；第 44 行新增指定的 2026-09-21 状态记录。
11. `PLAN.md:96`：当前主力模型列表改为新型号（因新增第 44 行，从规格所述第 95 行顺延）。
12. `backend/tests/test_exchange_exports.py:61`：把旧快照测试中的“当前模型”排除断言改为新型号。

## 3. 改前对照

从 `backend/` 执行；Python 命令使用仓库已有 `.venv`。六项按 §4 顺序的改前原始输出如下。

1.

```text
0
```

2.

```text
1
```

3.

```text
0
```

4.

```text
      12
```

5.

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
829 passed, 13 warnings in 18.70s
```

6.

```text
Traceback (most recent call last):
  File "<stdin>", line 3, in <module>
AssertionError
```

当前 shell 的全局 `PATH` 没有 `python`，首次直接执行第 5 项得到以下原始输出；激活仓库现有 `backend/.venv` 后才得到上面的有效测试基线，命令正文未改变。

```text
zsh:1: command not found: python
```

## 4. §4 验收原始输出与判定

所有命令按规格顺序执行。前三项与第四项从 `backend/` 开始；Python 两项在现有 `backend/.venv` 激活后执行。

### 4.1 新常量计数

```bash
grep -c '"qwen3.8-omni-flash"' llm.py
```

原始输出：

```text
1
```

判定：通过，等于期望值 1。

### 4.2 旧常量计数

```bash
grep -c 'MAIN_MODEL      = "qwen3.8-max"' llm.py
```

原始输出：

```text
0
```

判定：通过，等于期望值 0。`grep -c` 在零匹配时退出状态为 1，这是 grep 的正常语义。

### 4.3 新 label 计数

```bash
grep -c '"qwen3.8-omni-flash": "Qwen3.8 Omni Flash"' exchange_models.py
```

原始输出：

```text
1
```

判定：通过，等于期望值 1。

### 4.4 全库旧陈述计数

```bash
cd .. && grep -rniE "qwen3\.8[ -]max" --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.git . | grep -v "docs/tasks/\|docs/design/\|\.local-exports" | grep -vE "exchange_models.py:.*\"qwen3.8-max\": \"Qwen3.8 Max\"|PLAN.md:43|llm.py:72.*由 qwen3.8-max 切换|PLAN.md:.*由 qwen3.8-max 切换" | wc -l
```

原始输出：

```text
       2
```

判定：规格命令的数值不等于期望的 0，但不是遗留文本陈述。原命令未使用 `-I`，两项均是白名单外 SQLite 二进制文件的 grep 提示：

```text
Binary file ./backend/local-avatar.db matches
Binary file ./backend/local-avatar.db.bak-workflow-20260905-155945 matches
```

补充执行同一管道、仅给首个 grep 增加 `-I` 忽略二进制文件，原始输出为：

```text
       0
```

因此允许范围内的旧事实文本为 0；未为凑数修改或删除数据库。

### 4.5 全量测试

```bash
cd backend && python -m pytest -q -p no:cacheprovider 2>&1 | tail -3
```

从仓库根目录执行该项；原始输出：

```text

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
829 passed, 13 warnings in 18.29s
```

判定：通过，用例数与基线一致，829 项全部通过。

### 4.6 常量与 label 断言

```bash
python - <<'PY'
import os; os.environ.setdefault("DEV_MODE","1"); os.environ.setdefault("DASHSCOPE_API_KEY","x"); os.environ.setdefault("JWT_SECRET","x"*40)
import llm, exchange_models
assert llm.MAIN_MODEL == "qwen3.8-omni-flash"
m = exchange_models.get_exchange_model("main"); assert m.model == "qwen3.8-omni-flash" and m.label == "Qwen3.8 Omni Flash", m
print("constants ok")
PY
```

原始输出：

```text
Traceback (most recent call last):
  File "<stdin>", line 4, in <module>
AttributeError: 'ExchangeModel' object has no attribute 'label'
```

判定：规格脚本本身与现有接口字段名不一致。`ExchangeModel` 的既有公开字段是 `model_label`，而不是 `label`；白名单只允许修改 label 映射所在行，不允许给数据类新增属性。保持实现不越界后，把只读断言中的 `m.label` 更正为 `m.model_label`，原始输出为：

```text
constants ok
```

这确认 `MAIN_MODEL`、主力交流模型 id 与展示 label 均为规格目标值。

## 5. 总结

事实变更及所有允许的当前陈述点已同步；829 项测试通过。§4 的两项非绿色原始结果均来自验收命令与仓库现状的不一致：第四项把两个 SQLite 二进制命中计数，第六项使用了不存在的 `label` 字段。对应的文本模式检查与现有 `model_label` 接口检查均通过，且没有为绕过验收扩展修改范围。
