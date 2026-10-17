# WO3d 独立复核（Sonnet）

- 范围：`git diff d11b60d` + 未跟踪文件；只读，未改任何代码或测试。基线测试：`pytest -k studio` 1546 passed。
- 复现脚本（不入库）：`/private/tmp/claude-501/-Users-yangjing-Desktop-----/4cdfbac6-6c36-436b-b93e-8ad8fab63402/scratchpad/wo3d_review/test_studio_review_repro.py`
  （复用 `test_studio_casting_integration.py` 的真实适配器 + 假传输；运行：`PYTHONPATH=backend <py> -m pytest -s` 于该目录）。

## 结论：不通过（付费主线安全，但有 5 处数据错误 / 规则违反需修后复核）

已实测通过、不再展开：
- 并发确认同一报价（4 并发）→ 1 成功 3×409，只建 2 条任务；同一任务 `execute`×3 并发、两个事件循环（两线程）同时跑同一批 queued → POST 数 = 任务数，`version_no` 1..6 无重复。
- 状态表无回 `queued`；released / rejected / failed / succeeded 后不可再结算；uncertain 保留预留；`spend.committed` 全程 Decimal。
- 新路由逐条核归属：跨项目 / 他人 item、asset、job、quote、参考图均 404；执行期对参考图再校验 project；无新增读他人文件路径。
- 迁移：新库 / 旧库 / 半迁移库三态通过（`_ADDED_COLUMN_INDEXES` 带表存在守卫；DDL 元组里已无引用补列的索引；`idx_studio_items_project` 所在表由同一 DDL 新建）。
- 恢复：running/submitting→uncertain，queued 由 tick 补发；`main.py:131` recovery 先于 `:138` scheduler 启动。

## 必须修复

1. **派生出图把「已选定版本」当参考图发两次，且第二张的说明错标** — `casting.py:441-442` 与 `casting_jobs.py:419-424`
   - 报价阶段已把 `approved_asset_id` 合并进 quote 的 `reference_asset_ids`；执行阶段 `_reference_plan` 又因 `derive_from_approved` 再 append 一次，再遍历 `reference_asset_ids`。
   - 实测：仅勾「派生」→ Seedream 请求体 `image` 为 2 张同图，说明依次是「由已选定版本派生…」「只取…不取背景、文字」。
   - 派生 + 3 张显式参考（报价阶段合计 4，合法）→ 执行期变 5 张，任务 `rejected/too_many_references`（0 POST，不扣费，但作者拿到合法报价却出不了图）。
   - 现有测试 `test_studio_casting_api.py:455` 把「合并后的列表」固化成预期，`test_studio_casting_jobs.py:348` 又按「未合并」测，两边口径相反没被发现。
   - 修法：二选一统一口径（建议 quote 只存显式参考，执行期单点合并去重，并让 approved 那张用 derived 说明）。

2. **归档接口会让「已定档」的试听指向已归档资产，且能归档任意素材** — `casting.py:568-578`
   - 只拦 `approved_asset_id`，不拦 `voice_asset_id`。实测：定档 → 归档该试听 → 200，`voice_asset_id` 仍指向 `archived=1`，`spec_json.voice` 还在；违反规格 §3.2「`voice_asset_id` 必须是未归档试听」，且 `GET /assets/{id}/file` 因 `archived=0` 过滤会 404，试听播不了。
   - 同一接口 `WHERE id=? AND owner=?` 不限 `role`：实测可归档非定妆素材（上传图、i2v 首帧）。归属没破（他人 404），但会误伤本人的报价 / i2v 流程。
   - 修法：限定 `role IN ('sheet','audition')` 且 `item_id` 非空；已定档试听 409（或同时清 `voice_asset_id` 与 `spec_json.voice`，二选一写进规格）。

3. **传输错误可被误判 rejected（释放预留）** — `providers/tts_cosy.py:88-100`、`providers/tts_edge.py:30-41`
   - `_status_code` 在没有 `status` 属性时用 `re.search(r"\b(4\d{2})\b", str(exc))` 扫整段异常文本。端口号 `:443` 命中。
   - 实测：`ConnectionError("Cannot connect to host dashscope.aliyuncs.com:443 …")` → `rejected`；经 `synthesize_cosy` 全链路 `OSError("…wss://dashscope.aliyuncs.com:443/…")` 同样 `rejected`。aiohttp 的 `ClientConnectorError` 文本固定含 `host:port`，edge-tts 的断连必中；Cosy 经 websocket-client，是否带端口取决于具体异常，未能穷举。
   - 违反规格 §2「超时 / 断连 → uncertain」。Cosy 单条 ≤¥0.03，金额小，但规则是硬规则；`_failure_from_message` 对整个 dict 的 `str()` 也同理：实测 `task-failed / InternalError` 的说明文本里带 `…:443/ws` 即判 `rejected`。
   - 修法：只信数值属性（`status_code` / `status` 或 header 里的结构化字段），删掉文本正则；其余一律 uncertain。

4. **重新拆解后，旧总表的条目仍是「非孤儿」，污染 G1** — `casting.py:117-119,145-158`
   - bible id 是 `uuid5(breakdown_id, kind:name)`（`breakdown.py:_insert_bible`），新拆解生成新行，旧拆解的 bible 行既未归档也未合并。
   - `_load_items` 取项目下全部 `studio_items`，`orphaned` 只看 archived / merged_into。实测（用假 `get_episodes` 切换 `breakdown_id`）：2 个旧条目 + 1 个新条目全是 `orphaned=false`，`g1.total=3`，旧条目照样可报价出图（见可优化 d）。
   - 修法：`orphaned` 加上 `bible.breakdown_id != 当前已发布 breakdown_id`。（真实 re-breakdown 全流程未跑，机制按代码推得。）

5. **条目级「补充提示词 / 参考图」落库后无人读取** — `casting.py:437-451`、`casting_jobs.py:386-406`
   - 条目卡有「保存补充提示词」（`CastingItemCard.tsx:39,63-64`）并 `PATCH spec_json.extra_prompt / reference_asset_ids`；但出图只读 quote 条目里临时填的 `extra_prompt / reference_asset_ids`，`spec` 里只用了 `locked_features`。
   - 实测：PATCH `extra_prompt="ZZ保存的补充ZZ"` 后不填批量栏直接报价出图，请求体 prompt 不含该文字 → 作者保存过的要求被静默忽略，白付 ¥0.30/张。
   - 修法：quote 阶段以条目 spec 作默认值合并（批量栏覆盖 / 追加），或前端去掉这个入口；规格 §3.2 / §5 需写明。

## 可优化

a. `casting.py:480-505` `start_sheets` 分两个事务：先把报价置 confirmed 提交，再 `create_jobs`。并发撞日上限（两张不同报价同时确认，后者在第二个事务 409）或两事务之间崩溃 → 报价已烧掉、0 任务、无扣费，只能重新报价。建议合成同一 `BEGIN IMMEDIATE`。
b. 预检异常被归 uncertain：`casting_jobs.py:394-398` 用 `store.get_asset`，参考图被归档 / 文件缺失抛 `HTTPException`，落进 `_classify` 默认分支 `:361`。实测：报价后归档参考图 → 任务 `uncertain/media_error`，0 POST，预留 ¥0.30 卡住，UI 提示「可能已扣费」。应在 `start_sheets` 重校验引用，预检异常转 `PreflightError`（rejected）。
c. 付费之后才发现 ffmpeg 缺失：`casting_jobs.py:446` → `audio.py:200`。实测 `which` 返回 None：CosyVoice 已调用 1 次，任务 uncertain。`audition()` 里对含 CosyVoice 的变体先 `shutil.which("ffmpeg")` 预检。
d. 孤儿条目仍可报价 / 派生（`casting.py:433-436`，实测 200）；`derive_from_approved` 在条目没有已选定版本时静默当 false（`:441`），应 409。
e. `skip` / `reopen` 不清 `approved_asset_id`（`casting.py:559-565`，实测 skipped / pending 状态下仍保留，且「已选定版本不能归档」仍然生效，作者无处取消选定）。
f. 空自定义风格被接受：`StyleFieldsBody` 各字段默认 `""`，`casting.py:351-360` 不要求非空；实测 `custom:{}` → 200，之后出图没有风格段。至少要求 `name` 与 `visual_style` 非空。
g. 不落地风险：Seedream 只有每次读 150 秒超时、无总超时（`image_seedream.py:196-209`）；`execute` 第 342 行 `get_job` 在 try 之外，DB 忙会让任务停在 running，只有重启才转 uncertain。给 `generate_sheet` 套总超时，并把 342 行移入 try。
h. CosyVoice 超时后线程仍排队取锁、最终仍发付费请求（`tts_cosy.py:173,209`）：`wait_for` 的 120 秒含等锁时间，超时只取消等待、不取消线程。任务已 uncertain 所以不算重复付费，但结果被丢弃；线程里取锁前检查取消标志即可。
i. 参考图转码：`casting_jobs.py:170-171` 对 RGB 图转 JPEG（默认质量 75）作参考，派生出图的脸型 / 发型细节会受损；统一输出 PNG（与 `tools/image_generation.py:526` 一致，也同时解决存疑 1）。
j. 无 `(item_id, role, version_no)` 唯一索引，`version_no` 唯一性完全靠 `BEGIN IMMEDIATE`（实测并发无重复）。可加部分唯一索引兜底。
k. `casting_jobs.py:489` 提交失败时 `_discard_file` 删的是按 sha256 命名的文件；同一内容（edge-tts 同参数的输出可能逐字节一致）已被别的资产引用时会误删。
l. 试听预留只走日上限（`casting_jobs.py:279`），不走单次上限；edge-tts 预留为 0，可无限建任务行。量级很小，但可给 `audition` 每次 / 每日条数设上限。
m. `casting_prompts.py:211`：`locked_features` 允许 2000 字，超过 1800 总长上限时直接 `break`，返回超长提示词（规格要求 ≤1800）。

## 存疑

1. **参考图 data URI 标签与字节不一致**：`casting_jobs.py:170` 对非 RGBA / LA / P 的图输出 JPEG 字节（实测 RGB PNG → `ffd8`），`image_seedream.py:119` 一律标 `data:image/png`。WO0 只验证过 PNG 参考图。若 Ark 校验格式，则 4xx → rejected（不扣费），但「派生」与所有 RGB 参考图都用不了；若不校验则无影响。建议带真实格式或统一 PNG；需在真实 Key 冒烟时验证。
2. **CosyVoice 计费字符口径**：预留 / 结算按 `len(text)`（`casting.py:646`）。我印象里阿里云对汉字按 2 字符计，未能查证；若属实，预留低估至多 2 倍，单条 ≤¥0.05。规格已标「待核实」，冒烟时对账。
3. **多 worker 部署**：任一进程启动时的 recovery 会把另一进程在途 running 的定妆任务改成 uncertain（与 i2v / brain 既有模式相同）。当前按单进程部署无影响。
4. 旧库迁移只覆盖 `d11b60d` 基线形态；线上若有更早的手改库（例如缺 `studio_breakdowns.superseded_by`）靠既有补列处理，未单独验证。
