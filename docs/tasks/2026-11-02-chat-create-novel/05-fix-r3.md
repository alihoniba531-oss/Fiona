# 返修单 R3 —— CI 上三条前端契约测试在缺 node_modules 时直接起 node

## 现象（证据）

合并提交 35a81ea 推到 main 后，GitHub Actions「Quality」工作流（run 41595897533）的 backend 作业失败，frontend 与 desktop-assets 作业绿：

```
FAILED tests/test_novel_chat_create_frontend.py::test_novel_draft_component_renders_loading_state - subprocess.CalledProcessError: Command '['node', '-e', ...]' returned non-zero exit status 1.
FAILED tests/test_novel_chat_create_frontend.py::test_use_conversations_rebuilds_song_and_draft_cards - subprocess.CalledProcessError: ...
FAILED tests/test_novel_chat_create_frontend.py::test_page_open_novel_at_accepts_only_two_shapes - subprocess.CalledProcessError: ...
3 failed, 7618 passed, 272 skipped, 35 warnings in 618.00s
```

原因：CI 的 backend 作业（.github/workflows/quality.yml）只装 Python 依赖，不装 frontend/node_modules。这三条测试在 `subprocess.run(["node", "-e", ...], cwd=ROOT / "frontend", check=True)` 之前没有按仓库既有约定探测依赖并 skip，node 里 `require('typescript')` 失败就抛 CalledProcessError。同文件里经 `shared.render_card` 渲染的用例走了共享 helper 的 skip，没有红。本机有 node_modules，所以 9 条全绿，门禁没覆盖「无 node_modules」环境。

## 既有约定（照搬，不另起写法）

backend/tests/test_novel_chat_frontend.py 第 1–19 行：

```python
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPENDENCIES = {"typescript": "typescript/lib/typescript.js", "react": "react/index.js", "react/jsx-runtime": "react/jsx-runtime.js", "react-dom/server": "react-dom/server.js"}


def render_card(card):
    missing = [name for name, entry in DEPENDENCIES.items() if not (ROOT / "frontend/node_modules" / entry).is_file()]
    if missing:
        pytest.skip("frontend dependencies unavailable: " + ", ".join(missing))
    if not shutil.which("node"):
        pytest.skip("node is unavailable")
    return render_shared_card(card)
```

同文件第 23–34 行的自检 `test_render_skips_before_node_when_any_dependency_is_missing`：parametrize 遍历 DEPENDENCIES；在 tmp_path 下造出除 `missing` 之外全部入口文件；`monkeypatch.setitem(globals(), "ROOT", tmp_path)`；`monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("Node must not start without dependencies"))`；`with pytest.raises(pytest.skip.Exception, match="frontend dependencies unavailable: " + missing)` 调用守卫。

## 必须修复（只改一个文件）

文件：backend/tests/test_novel_chat_create_frontend.py

1. 模块级加 `DEPENDENCIES` 与 `require_node_dependencies()`，写法照上面的约定。
   - 三条用例的 node 脚本实际 require 的包：用例 1 需要 typescript、react、react-dom/server（`React.createElement`，不经 jsx-runtime）；用例 2、3 只需要 typescript。
   - 允许用一个统一的 DEPENDENCIES：`{"typescript": "typescript/lib/typescript.js", "react": "react/index.js", "react-dom/server": "react-dom/server.js"}`，三条用例开头都调 `require_node_dependencies()`。
   - skip 文案与约定一致：`"frontend dependencies unavailable: " + ", ".join(missing)`；无 node 时 `"node is unavailable"`。需要 `import shutil`。
   - 守卫必须在该用例任何 `subprocess.run(["node", ...])` 之前调用；三条用例各有 2 次 node 调用（当前第 178/186、216/231、277/296 行），都要在守卫之后。
2. 加自检用例 `test_node_tests_skip_before_node_when_any_dependency_is_missing`，parametrize 遍历 DEPENDENCIES，做法照 test_novel_chat_frontend.py 第 23–34 行（tmp_path 造缺一项的 node_modules、monkeypatch 本模块的 ROOT 与 subprocess.run、断言 skip 在起 node 之前发生，match 用 `re.escape(missing)`）。
3. 不改任何实现文件，不改任何其他测试文件，不改既有 9 条用例的断言与坏副本逻辑（只在用例开头插守卫调用）。不新增依赖。
4. 把模块 docstring 里「缺 node 或依赖时由共享 helper 按既有约定 skip；验收环境有 frontend/node_modules。」改成准确描述：经 shared.render_card 的用例由共享 helper skip，直接起 node 的三条用例由本文件的 require_node_dependencies 守卫。

## 验收（自跑并在报告里贴输出）

在 worktree 根目录：

```
cd backend && .venv/bin/python -m pytest tests/test_novel_chat_create_frontend.py -q -p no:cacheprovider
```

期望：全部 passed，0 failed，0 skipped（本机有 node_modules）；用例数 = 9 + 新增自检的参数化条数（3 项依赖即 12）。

```
git status --porcelain
```

期望只有 ` M backend/tests/test_novel_chat_create_frontend.py` 与报告文件。

## 停下来问的情形

只有本单与事实矛盾（如引用的约定文件不存在、行号对不上且找不到对应代码）才停；怎么组织 helper 由你定并在报告里说明理由。任何情况不回滚已完成的工作。你实测到的事实优先于本单的断言，不符就停下来说明。

## 报告

把变更总结追加到 docs/tasks/2026-11-02-chat-create-novel/impl/主代理.md 末尾（新节「R3」），五项：改了哪些文件 / 做了什么 / 与本单条目逐项对应 / 测试输出 / 未完成或需人工确认的地方。单文件改动，不拆子代理；不得调用 subagent / subagent_fork / workflow。
