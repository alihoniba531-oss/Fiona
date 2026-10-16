# 热修复：工作室前端测试在 CI 缺 frontend/node_modules 时报错

**现象**：GitHub CI 的 backend 作业只执行 checkout 和 pip install，不执行 npm ci。`backend/tests/test_studio_frontend_shell.py` 的 9 条测试用 node 去 require `frontend/node_modules` 里的 typescript 等包，找不到模块就报 MODULE_NOT_FOUND，导致失败。从 91eb53d 起，main 的 CI 一直是红的（run 38920186655、38927335099）。

**修法**（只改这一个测试文件，断言一条不改）：
- 照搬先例：`backend/tests/test_novel_p2_r1.py` 的 `probe()`，或 `backend/tests/test_claude_agent_r1_frontend.py:136-158` 的 `render_card` / 缺包时 skip 的写法。
- 在每次用 Node 驱动之前加判断：`frontend/node_modules/typescript`（以及测试实际 require 的 react、react-dom/server 等包）不存在时，执行 `pytest.skip("frontend dependencies unavailable: ...")`。
- 用 `require.resolve` 探测也可以，与先例保持一致即可。
- 再补一条元测试：模拟缺包的情况，断言测试会 skip，而且不会执行渲染。参照 `test_render_helper_skips_when_any_frontend_package_is_missing`。

**验收**：
1. 有 `frontend/node_modules` 时：`python -m pytest -q tests/test_studio_frontend_shell.py`，全部 pass，数量与修改前一致（9 条，外加新的元测试）。
2. 没有 `frontend/node_modules` 时：在一个不含 `frontend/node_modules` 的仓库副本里跑同一个文件，0 failed，原有的 9 条全部 skip。
3. 不改任何其他文件。不联网，不提交。
