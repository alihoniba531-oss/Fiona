# 验收报告

执行目录：`backend/`

## 改动行

- `backend/llm.py:97`：`print(f"[路由] slot=light model={QWEN_MODEL}", flush=True)`
- `backend/llm.py:99`：`except Exception as e:`
- `backend/llm.py:100`：`print(f"[路由] slot=light model={QWEN_MODEL} failed type={type(e).__name__}, fallback to main", flush=True)`
- `backend/llm.py:109`：`print(f"[路由] slot=main model={MAIN_MODEL}", flush=True)`

## §4 原始输出

### `grep -c '\[路由\]' llm.py`

```text
3
```

### `grep -c 'slot=light model={QWEN_MODEL}' llm.py`

```text
2
```

### `grep -c 'slot=main model={MAIN_MODEL}' llm.py`

```text
1
```

### `git diff --stat -- llm.py | tail -1`

```text
 1 file changed, 11 insertions(+), 9 deletions(-)
```

### `python -m pytest -q -p no:cacheprovider 2>&1 | tail -1`

未激活仓库虚拟环境时的首次原始输出：

```text
zsh:1: command not found: python
```

激活 `backend/.venv` 后，原样复跑该命令的原始输出：

```text
829 passed, 13 warnings in 18.42s
```

## 对照判定

- 三项日志计数依次为 3、2、1，符合预期。
- `git diff --stat` 限定结果只有 `llm.py`；插入/删除总数包含任务开始前该文件已有的未提交改动，故原始总数不是本任务三行日志的独立统计。
- 在仓库虚拟环境中测试为 829 passed，符合基线。
