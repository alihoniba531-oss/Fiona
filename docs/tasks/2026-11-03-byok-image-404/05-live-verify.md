# 05 · 用户环境正控（修复后）

日期 2026-11-03 01:01–01:03 EST · 用户同一套环境：后端 8010（`backend-8010.sh`，主检出 `Fiona/backend`，已套用本次 diff，sha256 22303f67…）+ 前端 3000（`baselines/fiona-user-local/fe`，next dev）。

- 两个服务在 01:00 前后都已不在运行（端口空闲），由本会话用 `preview_start`（`fiona-backend-8010` / `fiona-web-3000-dev`）重新拉起；后端进程 01:01:26 启动，晚于改动文件 01:00:11，`GET /` 返回 `{"status":"ok"}`。
- 代码级正控：在主检出 `backend/` 上跑 `verify/repro_byok_image_race.py` → `VERDICT: FIXED`（事件时刻 GET 即 200）；新测试 `4 passed`。
- 浏览器正控（测试账号 imgcheck_dev，开发入口登录）：
  - 刷新后历史里早先那张图 `GET /api/uploads/generated_28605cd7…png → 200`，正常显示。
  - 面板生图 16:9 + Seedream 5.0 Flash「宋末汴水南渡，清晨江面薄雾…」→ `GET /api/uploads/generated_5a7b21fd…png → 200`，卡片正常显示、放大/下载/以此图修改可用（`verify/03-live-platform-after-fix-3000.jpg`）。
- **没能做的**：用户自己的 BYOK Claude 路径需要用户的 Key，本会话不能解密也不能把真实 Key 填进界面；BYOK 路径的正控靠假传输复现脚本（同一份代码、同一条中间件、真实入库）完成。请用户在 3000 上用自带模型再要一张图确认。
- 用户那条失败的卡片（消息 672）：行和文件都在，点「重新加载」即可显示，无需重生成。

状态：改动**未提交**。两处各有一份相同的工作区改动：主检出 `Fiona`（为了让 8010 跑修复后的代码）与 worktree `.worktrees/fiona-byok-image-404`（分支 `fix/byok-image-404`，执行与门禁的原址）。拍板后二选一提交即可。
