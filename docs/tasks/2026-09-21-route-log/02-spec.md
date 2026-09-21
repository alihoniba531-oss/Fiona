# 规格：聊天主流程打印模型路由结果

任务日期：2026-09-21。级别：L1。你是独立执行进程，看不到对话上下文；本文件没写的不要自由发挥。

## 1. 目标

后端日志目前看不出每条聊天请求实际调用了哪个模型。要求：在**实际发起模型调用**的位置打印一行 `[路由] slot=<main|light> model=<模型 id>`，轻量槽失败回退到主力时也要打印出来，让日志与真实调用一致（而不是打印路由层的意图）。

## 2. 白名单

只改 `backend/llm.py` 的 `_create_stream_with_fallback` 函数（第 83–107 行附近）。其他任何文件、任何函数一律不动。

## 3. 改法（三处 print，风格与文件内既有 `print(f"[chat] …", flush=True)` 一致）

```python
def _create_stream_with_fallback(use_qwen: bool, messages: list, **kwargs):
    if use_qwen:
        try:
            stream = QWEN_CLIENT.chat.completions.create(model=QWEN_MODEL, ...)   # 原样
            print(f"[路由] slot=light model={QWEN_MODEL}", flush=True)
            return stream, True
        except Exception as e:
            print(f"[路由] slot=light model={QWEN_MODEL} failed type={type(e).__name__}, fallback to main", flush=True)
    stream = client.chat.completions.create(model=MAIN_MODEL, ...)   # 原样
    print(f"[路由] slot=main model={MAIN_MODEL}", flush=True)
    return stream, False
```

- 只加 print，不改任何参数、返回值、异常处理语义（`except` 仍然吞掉异常后回退）。
- 不打印消息内容、用户名或任何请求体字段。
- 函数 docstring 不动。

## 4. 验收（在 `backend/` 目录执行，先跑对照再判定）

```bash
grep -c '\[路由\]' llm.py                    # 期望 3（改前 0）
grep -c 'slot=light model={QWEN_MODEL}' llm.py     # 期望 2
grep -c 'slot=main model={MAIN_MODEL}' llm.py      # 期望 1
git diff --stat -- llm.py | tail -1        # 期望只有 llm.py 一个文件，且插入行数 3、删除行数 0 或 1（若把 `except Exception:` 改成 `except Exception as e:` 算 1 删 1 增）
python -m pytest -q -p no:cacheprovider 2>&1 | tail -1   # 期望 829 passed（基线 829）
```

不启动服务器，不调用真实模型。

## 5. 报告

写到 `docs/tasks/2026-09-21-route-log/03-report.md`：改动行、§4 每条命令原始输出。
