# WO3a 返修单 R3：CI 兼容（前端测试在缺少 frontend/node_modules 时必须跳过）

背景：GitHub CI 的 backend 作业不执行 npm ci。WO2 的 `test_studio_frontend_shell.py` 用 node 去 require 前端依赖时，因为缺包报 MODULE_NOT_FOUND，导致 main 的 CI 变红。main 已用 57cf1c8 修复，修法见该提交。

**R3-1** 逐一检查 `backend/tests/test_studio_*.py` 里所有用 node 驱动（subprocess 调用 node、require、转译 TS、SSR 渲染）的测试，包括 `test_studio_brain_frontend.py`、`test_studio_wo3_polish_frontend.py`、`test_studio_brain_r1_frontend.py`，以及其他 studio 前端测试。在每次调用 node 之前加判断：`frontend/node_modules` 里实际 require 的包（typescript、react、react-dom/server 等）不存在时，执行 `pytest.skip("frontend dependencies unavailable: ...")`。参照 main 的 57cf1c8，以及 `backend/tests/test_novel_p2_r1.py` 的 `probe()`。原有断言一条不改。

**R3-2 两种环境都要验证**
- 先把 `frontend/node_modules` 临时改名为 `frontend/node_modules.__hidden`，在 `backend/` 下跑全量 `python -m pytest -q`：0 failed，所有依赖 node 的测试都是 skip。
- 再改回原名，跑一遍全量：0 failed。
- 两次结果都写进 03-report 的「R3」一节。
- **跑完一定要把目录名恢复原样。**

约束不变：不联网，不提交，不改非工作室的测试，派子代理时不要传 model 和 reasoning_effort。
