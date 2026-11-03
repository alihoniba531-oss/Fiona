# 01 · 复现与归因 — 自带模型（BYOK Claude 智能体）生图后前端「图片加载失败，请重试。」

日期：2026-11-03 · 基线提交 0ca95af（main）· 复现人：Claude

## 症状

用户 2026-11-03 00:59 截图：聊天页自带模型模式（页眉「Chloe｜由你的模型回复」），要求按小说风格生成一张图。
回复里出现生成图卡片，图片区显示「图片加载失败，请重试。」+「重新加载」，卡片底部「AI 生成 / Seedream 5.0 Flash」，
放大 / 下载 / 以此图修改灰显；正文「我用 16:9 横版，按《汴水南渡》的宋末江湖风格画一张……」。

## 用户环境里的证据（只读，未改库）

- 后端 8010：`backend-8010.sh` → 主检出 `Fiona/backend`，`--env-file .env.local`；前端 3000：仓库外 `fe` 副本 `next dev`，`FIONA_BACKEND_ORIGIN=http://localhost:8010`。
  两者 11-02 23:29 / 23:42 起一直在跑，就是出问题时的实例。
- 上传目录 `backend/uploads/local-avatar/`：`generated_7bd2f76e58544c5e8572ac3e3d11f681.png`，2,395,434 字节，权限 0600，
  **mtime 2026-11-03 00:00:21 EST**（本机时区 EST）。没有 `.generated_` 临时残留，清理队列 `upload_cleanup_queue` 为空。
- 库 `backend/local-avatar.db`（拷贝到 scratchpad 后只读查询）：`messages` 第 672 行，assistant，`image_path = /uploads/generated_7bd2f76e…png`，
  正文以「我用 16:9 横版，按《汴水南渡》…」开头，**created_at 2026-11-03 05:00:24 UTC = 00:00:24 EST**；第 671 行是用户那句话（04:59:58 UTC）。
- 结论：图片 00:00:21 落盘并随 SSE 事件推给前端，消息行 00:00:24 才入库。前端收到事件立刻去取图，这 3 秒里后端按「消息归属」校验查不到行，回 404。

## 代码路径

- `backend/services/claude_agent.py` 736–740：收到执行核心的 `generated_image` 事件后直接 `yield` 给客户端；入库 `_save_response` 在 `save_delivered()`（487–502）里，只在整轮结束时调用（834 / 842 / 865）。
- `backend/main.py` 238–244 `_can_view_generated_image`：只查 `messages` 表（`database.message_references_image`）；317 行校验不过 → `404 图片不存在或无权访问`。
- `frontend/components/GeneratedImage.tsx` 60–75：收到 `imageUrl` 就 `apiFetch`，`!response.ok` → 「图片加载失败，请重试。」；「重新加载」只是再 fetch 一次。
- 对照：平台生图 `backend/services/chat_service.py` 1105–1121 **先 `await _save_response` 再 `yield generated_image`**，所以没有这个窗口。

## 机械复现（不花钱，不碰真实库）

`verify/repro_byok_image_race.py`：临时库 + 临时上传目录，`open_agent_stream` 用假传输回放一次 `generate_image` tool_use，
`generate_image` 打桩成真写一张 PNG，`_save_response` 用真实实现，收到 `generated_image` 事件的那一刻用 TestClient 带 `X-Dev-User` GET 图片。

输出（`verify/01-repro-before-fix.txt`）：

```
(0.034, 'file_persisted', '/uploads/generated_…png')
(0.034, 'sse', ['generated_image'])
(0.039, 'client_fetch_at_event', False, (404, 'application/json', 43))
(0.040, 'save_response_begin', …) → (0.042, 'save_response_done', …)
(0.049, 'client_fetch_after_stream', True, (200, 'image/png', 139))
VERDICT: RACE_REPRODUCED
```

## 浏览器对照（用户同一套 3000 / 8010，测试账号 imgcheck_dev，开发入口登录）

面板生图：16:9 + Seedream 5.0 Flash，描述「宋末汴水渡口，雪夜…水墨风格」→ 图片正常显示，
网络面板 `GET http://localhost:3000/api/uploads/generated_28605cd77c9741739d8a384a189fdfc3.png → 200 OK`（`verify/01-platform-image-ok-3000.jpg`）。
说明 Next 的 `/api/:path*` 转发、后端静态服务、鉴权头都正常，差别只在 BYOK 智能体路径的先后顺序。

## 排除的假设

- (a) 前端基址 / dev 代理没转发 `/uploads`：`imageUrl = "/api" + image_path`，`next.config.ts` 的 rewrite 覆盖；平台路径实测 200。排除。
- (b) Seedream 临时 URL 下载失败或落盘后被清理：文件 2.4 MB 在、清理队列空、行里有 image_path。排除。
- (c) 11-02 同步的 11 个前端文件引入回归：`diff -rq` fe 副本与仓库 HEAD 的 frontend 完全一致；GeneratedImage 那次只改 className。排除。
- (d) 去元数据重编码并发 / 503：生成图由 StaticFiles 直出，不经重编码。排除。
- 外部（火山方舟、浏览器）：图已生成并落盘；失败发生在自家中间件。排除。
