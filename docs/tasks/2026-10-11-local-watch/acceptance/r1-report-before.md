# 实施与验收报告：本机界面监控与提醒

日期：2026-10-11。代码基线：`129b32a`。依据：[已批准规格](02-spec.md)。

实现已完成；新增 Python 测试 **128 项全部通过**，TypeScript、ESLint、依赖一致性检查通过。默认全量 pytest 有 **3603 passed、6 skipped、1 failed、5 errors**；六个失败/错误均为既有测试绑定回环端口时被沙箱拒绝。Swift 的 native release 编译与 8 项纯逻辑检查通过，但原样 build/test、XCTest 和 OCR 未完成环境验收，详见下文。没有将这些受阻项目标记为通过。

## 1. 文件变更

修改既有文件 11 个：

- 后端：`backend/database.py`、`backend/main.py`、`backend/rate_limit.py`。
- 前端：`frontend/app/settings/page.tsx`、`frontend/app/page.tsx`。
- 文档与模板：`README.md`、`CLAUDE.md`、`PLAN.md`、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example`。

新增实现及测试文件 21 个：

- 后端：`backend/routers/local_watch.py`、`backend/services/local_watch.py`。
- 前端：`frontend/components/LocalWatchSection.tsx`、`frontend/lib/localWatch.ts`。
- Python 测试：`backend/tests/test_local_watch_backend.py`、`backend/tests/test_local_watch_service.py`、`backend/tests/test_local_watch_frontend.py`、`backend/tests/test_local_watch_docs.py`、`backend/tests/test_local_watch_integration.py`。
- Swift Package：`watcher-mac/.gitignore`、`watcher-mac/Package.swift`。
- Swift 实现：`watcher-mac/Sources/FionaWatcherCore/LineProcessing.swift`、`OCR.swift`、`Scheduling.swift`、`Watcher.swift`，以及 `watcher-mac/Sources/fiona-watcher/main.swift`。
- Swift 测试：`watcher-mac/Tests/FionaWatcherCoreTests/test_local_watch_logic.swift`、`test_local_watch_ocr.swift`、`test_local_watch_scheduling.swift`。
- Mac 文档与自启示例：`watcher-mac/README.md`、`watcher-mac/launchd/com.fiona.watcher.plist.example`。

另新增本报告和 `acceptance/` 下的原始日志、退出码、命令清单、初始校验值及范围审计。任务前已有的 `02-spec.md` 保留原样，没有把它计入实现变更。

## 2. 实现功能与规格逐项对应

| 规格 | 实现及验证 |
| --- | --- |
| §0 目标与范围 | 本机 OCR → 只上报新增行 → 后端判断 → assistant 提醒写进聊天；只被动读取窗口，无跨程序操作、手机推送或 Windows 改动。截图/整页 OCR 留在 Mac 内存；新增文字不落日志和 trace。 |
| §1 基本要求 | 无第三方依赖的 Swift Package，可执行目标 `fiona-watcher`，最低 macOS 14；只导入规定的系统框架。native release 实际编译成功，标准命令的环境限制单列。 |
| §1.1 子命令 | `list-windows` JSON 清单及小面积无标题窗口过滤；`ocr` 图片 JSON 输出；`run` 默认服务地址与令牌文件；权限必须恰好 600。离线 CLI 错误分支检查通过。 |
| §1.2 心跳、匹配与截图 | 每 30 秒心跳，规则按应用名/标题匹配第一个窗口；另支持 bundle id 匹配。单窗口 ScreenCaptureKit 内存截图，规则间隔限制 2–60 秒。 |
| §1.2 OCR 与新增判定 | 64×64 灰度哈希跳过不变帧；accurate、zh-Hans/en-US、语言纠正；空白规范化及噪声过滤；最近 3 次快照集合，首次只建立基线；单批最多 50 行、4000 字。窗口或匹配条件变化重新建立基线。 |
| §1.2 网络与日志 | 心跳、截图、观察发送使用独立任务；指数退避 1→60 秒，不阻塞其他任务，完整保留待发批次与基线；401 停止所有任务；规则 403/404 等待心跳刷新。只打印规则 id、应用名、新增行数和状态，权限缺失给固定中文指引。 |
| §1.3 附带文件 | 中文 README、launchd 示例、规范化/新增/OCR XCTest，并增加重试调度测试。8 项纯逻辑断言可在本环境执行；XCTest/OCR 实际受阻，未声称通过。 |
| §2.1 数据库 | `CREATE TABLE IF NOT EXISTS` 创建三张监控表；每人最多 3 台有效设备、20 条规则；旧库新增表且原有用户/消息数据不变；删号同事务清理三表。database.py 199 行新增、0 行删除。 |
| §2.2 路由与鉴权 | 设备令牌生成/列表/吊销，规则 CRUD，窗口清单与提醒游标接口；Cookie 用户鉴权、独立 Bearer 设备鉴权并更新在线时间；所有监控响应 private, no-store；窗口按用户内存保存 5 分钟、最多 200 个、标题截 80 字；观察限额与设备 60 次/分钟。 |
| §2.3 判定 | 关键词 casefold 匹配；数值支持负数、小数、千分位、百分号及四种比较；平台复用 QWEN_CLIENT、qwen3.8-flash/JSON/300 tokens/关闭思考/8 秒/不重试；Claude 复用 BYOK 解密、SDK与用户模型，非流式 JSON schema、不带工具、不回退。 |
| §2.3 冷却与额度 | 模型前检查冷却；`FIONA_DAILY_WATCH_JUDGE` 默认 500，使用现有限流存储与北京时间日期键，在开发模式或关闭通用限流时也生效；不扣草莓。 |
| §2.4 提醒与隐私 | 复用 save_message，指定会话无效时回到默认会话；正文使用实际发现的 app_name，否则规则名；记录 watch_alerts 与消息 id。不触发画像、匹配、危机或计费。SQLite 参数 repr 脱敏、AI 请求上下文抑制第三方敏感 DEBUG；trace 仅存许可元数据。AI 等待期间规则改变/删除/停用时丢弃旧判断。 |
| §2.5 开关 | 默认开启；`FIONA_LOCAL_WATCH=0` 在主应用最外层先返回 404，覆盖未登录、设备和 OPTIONS；原有路由不改。 |
| §2.6 提示词 | system 逐字使用规格；user 消息按指定格式，新增行顺序拼接并截到 2000 字。请求参数用离线桩断言。 |
| §3.1 设置页 | 设备、一次性令牌/复制/命令、最近窗口预填、三类规则 CRUD 与示例、Anthropic BYOK 门槛、明确浏览器通知授权、逐字隐私说明。编辑与切换类型通过运行时字段白名单提交，避免服务端元数据造成 422。 |
| §3.2 聊天页 | 登录且页面可见时每 10 秒轮询；首次分页取得最新游标且不回放；隐藏时中止请求，404 停止；当前会话空闲时去重追加，回复/历史加载中保留队列；其他会话可点击提示；通知默认关闭且按账号保存 opt-in。 |
| §4 文档 | 六个指定文件均说明数据流、两项环境变量、令牌安全及全部已知局限；没有新增本机绝对路径。 |
| §5 硬约束 | Swift、后端、前端三个 subagent 按文件独占并行，未指定 model/reasoning_effort；主代理负责文档和独立集成验收。受保护文件和任务前 99 个测试文件校验值不变。新测试仅新文件、均以 test_local_watch_ 开头，模块级阻断 socket/DNS，模型打桩，无 git 历史/node_modules 依赖；未安装包、未发真实网络请求、未启动应用服务。既有端口测试尝试绑定均被沙箱拒绝。 |
| §6 验收 | 所有指定命令均实际运行，输出、退出码保存在 acceptance；结果与作者验证项如下。 |

补充局限：断网期间仍截图并把新增批次留在内存，不任意截断队列；长时间断网时内存可能增长。进程退出后基线与待发批次丢失。窗口最小化、OCR 错字与只能读取当前可见内容等规格局限已写入文档。

## 3. 先失败测试的证据

| 分工/修正 | 实现前失败 | 实现后结果 | 原始证据 |
| --- | --- | --- | --- |
| 后端初版 | 74 errors，缺新增模块，exit 1 | 最终后端/服务 95 passed，exit 0 | backend-red.log / backend-final.log |
| 文档 | 7 failed，exit 1 | 7 passed | docs-red.txt / docs-green.txt |
| 前端初版 | 7 failed，exit 1 | 最终 11 passed | frontend-red.txt / frontend-green.txt |
| 主应用集成 | 15 failed，exit 1 | 15 passed | integration-red.txt / integration-green.txt |
| 复合枚举与实际应用名 | 7 failed，exit 1 | 纳入最终测试 | backend-edge-red.log |
| SQLite 整数边界 | 4 failed，exit 1 | 纳入最终测试 | backend-ids-red.log |
| 判断期间规则变更 | 2 failed、1 passed，exit 1 | 纳入最终测试 | backend-inflight-red.log |
| 前端编辑元数据 | 2 failed、9 passed，exit 1 | 11 passed | frontend-edit-red.txt |
| Swift 初版纯逻辑/OCR | 类型检查缺 LineNormalizer、SnapshotHistory、OCRRecognizer，exit 1；XCTest 同时受环境阻碍 | 实现后编译通过；OCR 仍受阻 | swift-tdd-red-portable.log |
| Swift 独立重试调度 | 缺 ObservationQueue/RetryBackoff，exit 1 | 纯逻辑检查通过 | swift-scheduling-tdd-red.log |
| Swift 完整保留待发批次 | 原实现 actual=8、expected=20，exit 132 | 20 批完整保留检查通过 | swift-preserve-pending-tdd-red.log |

每个日志旁保存对应 `.exit`；后端及最终命令有 `.command.json`，Swift 全部复现参数集中在 [swift-command-manifest.json](acceptance/swift-command-manifest.json)。原始 traceback 仅保存在 acceptance，不在报告展开。

## 4. 第 6 节实际验收

Python 命令在 `backend/` 使用仓库现成 `.venv/bin/python`（通过 PATH 选择），未安装依赖。前端命令在 `frontend/`，设置 npm 离线并禁止自动确认安装。Swift 命令在 `watcher-mac/`。

| 验收项 | 实际输出摘要 | 退出码 | 证据 |
| --- | --- | --- | --- |
| 1. git status --porcelain | 仅规定的后端、前端、文档、本任务新测试与 watcher-mac；范围审计 unexpected_changed_files=[] | 0 | [git-status.txt](acceptance/git-status.txt)、[scope-audit.json](acceptance/scope-audit.json) |
| 2. 受保护文件 git diff --exit-code | 空输出，零 diff | 0 | [protected-diff.txt](acceptance/protected-diff.txt) |
| 3. database.py diff | 199 additions / 0 deletions，无既有表结构变更；只插入建表、删号清理和追加新函数 | 0 | [database-diff.txt](acceptance/database-diff.txt)、scope-audit.json |
| 4. git diff --name-only -- backend/tests | 空输出；99 个任务前测试 SHA-256 均不变 | 0 | [existing-test-diff.txt](acceptance/existing-test-diff.txt)、baseline-sha256.json |
| 5. 默认 python -m pytest -q | 3603 passed、6 skipped、1 failed、5 errors；六项均因沙箱绑定端口失败 | 1 | [pytest-full-final.txt](acceptance/pytest-full-final.txt) |
| 5. 仅排除六项端口受阻测试的补充全量 | 3603 passed、6 skipped、6 deselected、14 warnings | 0 | [pytest-without-loopback.txt](acceptance/pytest-without-loopback.txt) |
| 6. 全部本任务新 Python 测试 | 128 passed、14 warnings：后端 95、前端 11、文档 7、主应用集成 15 | 0 | [pytest-new-final.txt](acceptance/pytest-new-final.txt) |
| 7. python -m pip check | No broken requirements found | 0 | [pip-check.txt](acceptance/pip-check.txt) |
| 8. npx tsc --noEmit | 空输出 | 0 | [tsc-final.txt](acceptance/tsc-final.txt) |
| 8. npx eslint . | 0 errors、25 个既有 warnings | 0 | [eslint-final.txt](acceptance/eslint-final.txt) |
| 9. 原样 swift build -c release | 默认编译缓存不可写，Operation not permitted，随后模块/SDK 诊断 | 1 | [swift-build-release-default.log](acceptance/swift-build-release-default.log) |
| 9. 原样 swift test | 同样默认缓存受阻 | 1 | [swift-test-default.log](acceptance/swift-test-default.log) |
| 9. 工作区缓存 release | 源码编译/链接完成；默认构建系统生成 dSYM 被拒 | 1 | [swift-build-release-workspace-cache.log](acceptance/swift-build-release-workspace-cache.log) |
| 9. native release、关闭 debug info | Build complete，实际可执行文件已链接 | 0 | [swift-build-release-native.log](acceptance/swift-build-release-native.log) |
| 9. 工作区缓存 swift test | unable to resolve module dependency: XCTest；当前命令行工具缺该模块 | 1 | [swift-test-workspace-cache.log](acceptance/swift-test-workspace-cache.log) |
| 9. 同一套 Swift 纯逻辑便携检查 | 8 passed，包含规范化、三快照、单批上限、重试调度及完整批次保留；不是 XCTest 成功声明 | 0 | [swift-portable-final-logic.log](acceptance/swift-portable-final-logic.log) |
| 9. CoreGraphics 中文/英文 OCR 与 CLI | 生成 1200×340 有效 PNG，两个文字区有 5248/7032 黑像素；Vision.perform 抛 Foundation._GenericObjCError，CPU 尝试也失败，原因未确认 | 1 | [swift-portable-final-ocr.log](acceptance/swift-portable-final-ocr.log)、[swift-cli-ocr-generated-png.log](acceptance/swift-cli-ocr-generated-png.log) |
| 9. CLI 离线错误分支、plist | 参数/无效图片/644 令牌按预期 exit 1；plist 校验成功；检查脚本整体成功 | 0 | [swift-cli-offline-smoke.log](acceptance/swift-cli-offline-smoke.log) |
| 10. 报告 | 文件清单、逐项对应、实际输出和外部验证点均列明 | — | 本文件 |
| 补充 git diff --check | 空输出 | 0 | [diff-check.txt](acceptance/diff-check.txt) |

Native release 的实际命令：

```sh
swift build -c release --disable-sandbox --cache-path .build/swiftpm-cache --build-system native -debug-info-format none
```

`CLANG_MODULE_CACHE_PATH` 与 `SWIFTPM_MODULECACHE_OVERRIDE` 指向工作区内 `.build/module-cache`。关闭的是 Swift Package 自身的编译子进程沙箱，不是提升本次环境权限。标准命令仍需要作者在正常 Xcode 环境执行，不能用 native 构建结果代替标准命令验收。

六项既有端口受阻测试，全部原始失败依据为 `PermissionError: Operation not permitted`：

1. `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`
2. `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`
3. `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline`
4. `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work`
5. `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline`
6. `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch`

未改这些测试、未启动真实应用服务。补充验收只在命令行 deselect 上述六项，完整参数保存在 `pytest-without-loopback.command.json`。

## 5. 第 5 节必须测试点覆盖

| 必须测试点 | 结果与证据 |
| --- | --- |
| 1. 令牌 | 明文仅创建返回、库中仅哈希、错误/吊销 401、3 台上限及跨用户隔离，后端测试通过；独立 Cookie/Bearer 主应用测试通过。 |
| 2. 规则 | CRUD、三类型上下界/非法类型、20 条上限、跨用户、PATCH 白名单与复合 JSON、整数溢出，通过。 |
| 3. 心跳 | 不返回 params；清单隔离、5 分钟过期、80 字标题、200 窗口上限，通过。 |
| 4. observations | 缺失/停用/他人规则拒绝、50 行/4000 字边界、时间格式与设备 429，通过。 |
| 5. 判定 | 关键词大小写/首命中；数值全部格式和四种比较；平台参数、JSON 非法/超时；Claude 未启用/失败/请求 schema；冷却不调用模型与每日额度，通过。 |
| 6. 落库 | 正文、实际应用名/规则名回退、指定/失效会话、watch_alerts、余额不变及不调用画像/计费；DEBUG 日志与 trace 均不含 OCR/摘要，通过。并发同规则与 AI 在途删号/停用/删除也通过。 |
| 7. alerts | after 严格大于、50 条上限、字段白名单与用户隔离，通过。 |
| 8. 开关 | 全部接口关闭 404，含未登录和 OPTIONS，private no-store，通过。 |
| 9. 数据库 | 旧库含既有用户/消息及其他表时启动建表，原数据不变；删号清理三表而不影响别人，通过。 |
| 10. 前端 | node 无包抽取执行：首次分页只记游标、隐藏暂停/在途取消、404 停止、当前会话插入去重、默认通知关闭、账号隔离、编辑白名单；逐字隐私源码断言，通过。 |
| 11. 文档 | 六文件关键说明和无本机绝对路径检查，7 项通过。 |
| 12. Swift | native release 与 8 纯逻辑用例通过；标准 build/test 与真实 OCR 环境验收未通过，原因及原始证据已列出，交作者外部验证。 |

## 6. 作者需在沙箱外或真机验证

1. **标准 Swift 验收**：具备完整 Xcode、正确选中工具链的 macOS 14+ 环境执行 `swift build -c release`、`swift test`；确认规范化、新增判定及 CoreGraphics 中文/英文 OCR XCTest 均通过。当前环境 OCR 失败原因未确定，需要优先核查，不应视为已通过。
2. **真实 Mac 窗口**：屏幕录制授权/拒绝授权中文提示；微信、企业微信、钉钉或行情窗口的枚举、首个匹配、最小化与重新打开；首次不上传、静止帧跳 OCR、真实新增行和字数边界。确认截图/整页文字不离开本机。
3. **运行与网络**：30 秒心跳、2–60 秒截图、不同规则独立运行；断网/429/5xx 退避并保留待发批次；恢复后送达；吊销后 401 全局停止；用户停用/删除规则不终止其他规则；Control-C 与 launchd 登录自启、停止行为。
4. **真实厂商调用**：作者服务环境中验证千问 JSON 请求和 Claude 用户模型的 output_config.format 支持、8 秒时限及失败不回退；本任务只用离线桩，未消耗真实额度。
5. **实际浏览器**：令牌只显示一次、剪贴板复制与文件 600 权限；创建/编辑/切换类型/启停规则；窗口预填；首次无历史通知、页面隐藏、忙时排队、跨会话跳转及账号切换；用户主动允许后才弹 Notification；页面关闭仍落库。
6. **全量回归**：在允许回环端口的环境重新执行默认 `python -m pytest -q`，完成上面六项既有端口测试。测试环境应继续使用临时数据库和模型桩。

未发现规格自相矛盾或必须修改受保护文件的实施阻断；未触发第 5 节停下来的条件。环境受阻项目按规格第 6 节记录，不隐去失败，也不回滚已完成工作。
