# WO3d 初查（precheck）

- 基线：`d11b60d`；对照：当前工作区 `git diff d11b60d` + `git status --porcelain`（未跟踪新文件已计入）。
- 规格：`docs/tasks/2026-10-16-studio-wo3d-casting/02-spec.md`。
- 性质：**只读**。本次仅新建本报告文件；代码与测试未改动；临时脚本一律放 `$TMPDIR/wo3d_repro`。
- 解释器：`/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python`（Python 3.14 + aiosqlite）。
- 结论口径：**通过** / **不通过** / **存疑**。存疑 = 无法在本沙箱确证（渲染/环境限制）或现状不可达。

## 1. 总表

| # | 清单项 | 结论 | 关键证据 |
|---|---|---|---|
| 1 | 付费请求只发一次 | 通过 | `backend/studio/providers/image_seedream.py:200`（`follow_redirects=False`）、`:202`（单次 stream POST）、`:207-209`（异常不重试）；`providers/tts_cosy.py:179`（单次 `synthesizer.call`）；`providers/tts_edge.py:72`（单次流）；`casting_jobs.py:40-46`（`_ALLOWED_TRANSITIONS` 无回 `queued`）、`casting_jobs.py:306-314`（`_ACTIVE` 守卫）、`casting_jobs.py:340`（CAS `queued→running`）、`store.py:583-586`、`store.py:698-699`（拒绝 `link_task`）|
| 2 | 错误分类 | 通过 | `providers/media_errors.py:10-22`；`providers/image_seedream.py:83-93`（4xx→rejected、429 同 4xx、5xx→uncertain、3xx/其它→uncertain）、`:59-68`（审核→failed）；`providers/tts_cosy.py:39-41`（审核→failed）；测试 `tests/test_studio_media_seedream.py:160,180,195,246,268,282,321`、`tests/test_studio_media_tts.py:202,221,254` |
| 3 | 报价 | 通过 | `casting.py:330-336`（用途/`status!='open'`→409「只能确认一次」/过期 409）、`:339-340`（CAS `WHERE status='open'`）；`store.py:532`（指纹含 `quote_item_id`）；`config.py:105-106`（日 ¥300 / 单次 ¥100）、`spend.py:69-75`（单次上限）、`spend.py:30-45`（日额度含预留+结算+uncertain）；`casting.py:630-651`（试听不弹框但预留）；`casting.py:337`（风格提案预留） |
| 4 | 恢复 | 通过 | `recovery.py:41-50`（image/tts `submitting|running`→`uncertain`，保留预留，`needs_recheck=1`）；`recovery.py:51-65`（i2v 分支）、`:28-40`（brain 分支）未改；`scheduler.py:109`（`casting_jobs.dispatch_queued`）；恢复全程只写 DB |
| 5 | 归属与准入 | 通过 | `store.py:310-315`（`owner=? AND archived=0`→404）；`casting.py:396-408`（`_item_or_404`/`_item_with_bible` 校 project）、`:411-419`（参考图属主+project+kind）、`:546-557`（approve_item）、`:571-575`（archive_asset）；G0 门禁 `casting.py:260,302,323,369,424,477`；阶段前置 `_require_setup`/`_require_style`（`:63-71`） |
| 6 | 存储 | 通过 | `storage.py:118`（`_component` 校验）、`:50-58`（`resolve_path` 拒绝对路径/`..`/越界）、`:289`（扩展名）、`:299-304`（临时文件+fsync+replace 原子写）、`:278,291`（音频 300MB 上限）；`casting_jobs.py:134,139,144,150,158,161`（`asyncio.to_thread` 包裹 PIL/写文件/哈希） |
| 7 | ffmpeg | 通过 | `audio.py:114`（`create_subprocess_exec` 参数列表）、`:220,237`（滤镜单 argv）；`audio.py:127-133`（超时 kill+wait）、`:211`（`TemporaryDirectory` 清理）；`audio.py:41-58`（`FX_PRESETS` 与规格 §10 逐字符一致） |
| 8 | 删号 | 通过 | `database.py:916-919`（`studio_items` 与其余 studio 表在同一事务内 `DELETE`） |
| 9 | 迁移 | **不通过** | `database.py:315-316`（先跑全部 DDL）→ `store.py:160`（新索引引用 `item_id`）→ `store.py:252`（`item_id` 由 `migrate_schema` 才补）。实测旧库 `sqlite3.OperationalError: no such column: item_id` |
| 10 | 密钥与并发 | 通过 | `providers/tts_cosy.py:36`（`_API_KEY_LOCK`）、`:173-174,191`（加锁「设置→调用→恢复」，`finally` 恢复原值）；`brain.py` 侧无全局 key 改写；`media_errors.py:24-25`（`__repr__` 不含请求体）、`providers/base.py` `safe_message` 脱敏；全仓日志/`meta_json`/测试快照未见密钥 |
| 11 | 原文注入 | 通过 | `casting_prompts.py:68-127`（`style_inputs` 只取 name/role/appearance/摘要，按 `_CAPS` 截断，不含 `excerpt`，见 `:72` 注释）；`brain.py:96-101`、`:105,107`（素材标为不可信）；测试 `tests/test_studio_casting_prompts.py:100` |
| 12 | 前端 | 存疑（仅 e） | a–d 通过：`CastingItemCard.tsx:89`（uncertain 仅提示+释放）、`CastingStage.tsx:52-61`（无在途停止轮询）、`CastingQuoteDialog.tsx:9-17,26`（倒计时+硬禁用+无自动确认）、错误态 `CastingStage.tsx:87,90-93` 等；e **存疑**：`CastingItems.tsx:87` |
| 13 | 测试守卫 | 通过 | node/前端：`tests/test_studio_casting_frontend.py:11,20-28`（缺 `frontend/node_modules`/node 即 skip），实测无依赖目录 4 passed/18 skipped；ffmpeg：`tests/test_studio_media_audio.py:20-21`，实测无 ffmpeg 35 passed/17 skipped |

## 2. 不通过与存疑逐项展开

### 2.1 清单 9「迁移」——不通过

**现象（实测复现）**
1. 用 `git show d11b60d:backend/studio/store.py` 的 `STUDIO_TABLES_DDL`（旧文件 22–164 行）造出旧库：`studio_assets` 列为 `id,project_id,owner,kind,source,rel_path,sha256,bytes,width,height,duration_s,fps,has_audio,meta_json,archived,created_at`（**无 `item_id`/`version_no`/`role`**），且**无 `studio_items` 表**。
2. 把 `FIONA_DB_PATH` 指向该旧库，调用当前 `database.init_db()`：

```
File ".../backend/database.py", line 316, in init_db
    await db.execute(studio_table_ddl)
sqlite3.OperationalError: no such column: item_id
```

3. 半迁移状态：DDL 元组中位于失败项之前的语句已生效（`studio_items` 已建），但 `studio_assets` 仍无 `item_id`。**重跑同样报错**（不是自愈；因为每次重跑都会先执行到同一失败索引）。

**根因（文件:行）**
- `backend/database.py:315-316`：`for studio_table_ddl in STUDIO_TABLES_DDL: await db.execute(studio_table_ddl)` —— 先执行**全部**建表/索引 DDL。
- `backend/database.py:317`：`await migrate_studio_schema(db)` —— 补列**之后**才执行。
- `backend/studio/store.py:160`：`CREATE INDEX IF NOT EXISTS idx_studio_assets_item ON studio_assets(owner,item_id,role,version_no)` —— 该索引位于 `STUDIO_TABLES_DDL` 元组内，却引用 `item_id`/`role`/`version_no`。
- `backend/studio/store.py:252`：`"studio_assets": {"item_id": ..., "version_no": ..., "role": ...}` —— 这三列只在 `migrate_schema` 里补。

旧库的 `studio_assets` 没有这些列，`CREATE INDEX`（无 `IF NOT EXISTS` 保护列的存在性）在 `migrate_schema` 补列之前就执行，于是必然失败。新库不受影响（DDL 建表时已含这些列），所以现有测试与 conftest 不覆盖该路径。

**可修复性验证（换顺序即通过）**
把 `migrate_schema(db)` 提到 `STUDIO_TABLES_DDL` 循环**之前**后实测：`init_db()` 全流程成功；`studio_assets` 补出 `item_id/version_no/role` 三列，`studio_items` 建表成功。

**失败场景（可直接复现）**
> 任何在 `d11b60d` 上已初始化的生产/开发库，升级到本期代码后启动服务 → `init_db()` 抛 `sqlite3.OperationalError: no such column: item_id` → 后端进程起不来（FastAPI lifespan 失败）。不是数据损坏，但**服务不可用**，且重启不会恢复。

**受影响子项**
- 9a「先用旧库跑当前建表与迁移」：不通过（见上）。
- 9b「新列要补上、迁移可重复执行」：**通过**（补列字典本身正确；在修正顺序后的旧库上连跑 2–3 次 `migrate_schema`，`studio_projects=20`/`studio_assets=19`/`studio_jobs=48` 列数不变，幂等）。但它当前**不可达**，因为 9a 先崩。
- 9c「旧库里能插入 image/tts 任务和 casting 资产」：**存疑**——在顺序修正后的旧库上实测可插入：`kind='image', provider='wan', media_provider='seedream'` 与 `kind='tts', media_provider='cosyvoice'/'edge'` 任务均 `OK`；`role='sheet'`/`'audition'` 的 `studio_assets` 资产（带 `item_id/version_no`）均 `OK`。说明补列口径正确、无需重建 `studio_jobs`（任务写 `provider='wan'`、真实提供方放新列 `media_provider`，故旧库的 `CHECK(provider IN ('wan','seedance'))` 不构成阻塞）。但在**当前代码顺序下该路径不可达**（库起不来），故整体仍记为不通过链条中的存疑项。

**建议修复方向**：在 `database.py` 里把 `migrate_studio_schema(db)` 移到 `STUDIO_TABLES_DDL` 循环之前；或把 `idx_studio_assets_item`/`idx_studio_items_project`（`store.py:160-161`）从 DDL 元组移入 `migrate_schema`（在补列之后创建）。

### 2.2 清单 12e「390px 无横向滚动」——存疑

**静态判断（倾向安全）**：宽度链 `StudioShell.tsx:19`（`overflow-hidden`）→ `:21`（`overflow-y-auto`）→ `:22`（`px-4`，390 视口 → 358px）→ `CastingItems.tsx:66`（`p-4` → 326px）→ `:79`（`ceramic-card p-3` → **302px**）。代码大量使用 `min-w-0`/`flex-wrap`/`break-words`/`w-full`，无表格、无 `min-w-[…]`、无 `100vw`；`StudioShell.tsx:22` 还把 `.tag` 覆盖为 `whitespace-normal`。

**风险点**：`frontend/components/studio/CastingItems.tsx:87` 把 36 字符的素材 UUID（`backend/studio/store.py` 的 `uuid4()`）直接放进 `.chip`，同一 chip 内还有「移除」按钮。`frontend/app/globals.css:357` `.chip{white-space:nowrap;height:32px}`、`:347` `.btn{white-space:nowrap;...}`：chip 不可换行、不可收缩（无 `min-w-0`/`truncate`/`break-all`），固有宽 ≈ UUID 宽 + 约 85px；要落在 302px 容器内需 UUID ≲ 约 217px。

**为何存疑**：本沙箱无法渲染实测（Chrome / playwright `chrome-headless-shell` 均因 mach port 权限被拒，exit 134/133）。按 Noto Serif SC 12px 数字/小写 advance ≈ 0.51–0.56em 估算，36 字 UUID 约 205–225px，**正好跨在阈值两侧**。

**失败场景**：参考图上传成功（`references` 非空）后在 390px 视口，若该 UUID 实际宽度 ≥ 约 218px，nowrap chip 会把约 305px 的 flex 行撑出 302px 容器 → `main`（`overflow-y-auto` 使 `overflow-x` 计算为 `auto`）出现横向滚动条。

**次要观察（非不通过）**：同一 chip 内 `.chip{height:32px}` 与按钮 `min-h-10`（40px）高度不匹配，竖直溢出 8px，可能与下一行视觉重叠。

**建议**：在真实浏览器（或临时放宽沙箱渲染权限）下量一次 chip 宽度；或在 `CastingItems.tsx:87` 给 UUID 加 `truncate`/`break-all` + `min-w-0`。

## 3. 建议 Sonnet 复核重点关注

1. `backend/database.py:315-317` —— 建表 DDL 循环先于 `migrate_schema`，是清单 9 不通过的根因；请确认修复顺序与回归测试（需新增「旧库 → `init_db()`」用例，现有 conftest 全用新库，覆盖不到）。
2. `backend/studio/store.py:160-161` —— 新索引 `idx_studio_assets_item` / `idx_studio_items_project` 位于 DDL 元组且引用仅由 `migrate_schema` 补的列（`item_id`/`role`/`version_no`）；与上一条二选一修复即可，但需确认没有第三条同类索引。
3. `frontend/components/studio/CastingItems.tsx:87`（配合 `frontend/app/globals.css:357`）—— 390px 下 nowrap chip 内 36 字 UUID + 按钮的横向溢出阈值，本次唯一的前端存疑点，建议真机量宽。
4. `backend/studio/casting_jobs.py:290` —— `fingerprint=sha256(job_id)` 逐任务唯一，**不是**幂等键；防重复完全依赖 `_ACTIVE` 守卫（`:306-314`）+ CAS `queued→running`（`:340`）。请确认在「调度器 tick 重入 / 并发确认 / 多事件循环」下没有绕过 CAS 的路径。
5. `backend/studio/casting_jobs.py:306-314` —— `_ACTIVE`/`_SEMAPHORES` 以 `asyncio.get_running_loop()` 为键，跨 loop 不共享；若生产存在多 loop，仅靠 CAS 兜底，建议确认预期。
6. `backend/studio/casting_prompts.py:68-127` 与 `backend/studio/brain.py:96-101,105-107` —— 「原文只取摘要」有测试（`tests/test_studio_casting_prompts.py:100`），但「原文/来源数据标为不可信」**无专门断言**；建议补一条断言锁定不可信措辞，防止后续改动悄悄移除。
