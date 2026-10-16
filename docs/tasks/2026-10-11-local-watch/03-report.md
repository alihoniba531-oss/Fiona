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


## R1

日期：2026-10-11。依据 [05-fix-r1.md](05-fix-r1.md) 完成 R1-1 与 R1-2。上文保留首轮实施与验收历史；本节记录返修后的结果。当前测试使用 Swift Testing，不再要求 XCTest 或完整 Xcode；验收目标是提供 Testing.framework 的 Command Line Tools 环境。

### R1 变更文件与规格对应

| 文件 | 变更与返修项 |
| --- | --- |
| [Watcher.swift](../../../watcher-mac/Sources/FionaWatcherCore/Watcher.swift) | R1-1：导入系统 AppKit；新增 MainActor 隔离的 ScreenCaptureApplication。惰性 static let 只执行一次 NSApplication.shared 初始化及 .prohibited 策略。run 在创建监控任务之前等待初始化，唯一实际调用 captureImage 的 captureLoop 入口也先等待初始化，后续调用复用已初始化状态。 |
| [test_local_watch_logic.swift](../../../watcher-mac/Tests/FionaWatcherCoreTests/test_local_watch_logic.swift) | R1-2：规范化、三快照、新增去重及上报边界的 5 个测试改为 Swift Testing；13 个原等值断言与输入保持。 |
| [test_local_watch_scheduling.swift](../../../watcher-mac/Tests/FionaWatcherCoreTests/test_local_watch_scheduling.swift) | R1-2：3 个调度测试改为 Swift Testing；保留 10 个等值断言、两项非空要求及 19 批逐项顺序断言。可变队列先取出结果，再 #require，保证每处只取一次并避免宏展开的不可变接收者编译错误。 |
| [test_local_watch_ocr.swift](../../../watcher-mac/Tests/FionaWatcherCoreTests/test_local_watch_ocr.swift) | R1-2：CoreGraphics 中英文 OCR 测试改为 Swift Testing；保留绘图、全部非空要求、两段文字包含和中文在英文之前的断言；字体 advance 和缺字失败使用 #require。未删除、跳过或放宽 OCR。 |
| [watcher-mac/README.md](../../../watcher-mac/README.md) | 更新测试框架与 CLT 要求，说明截图前只初始化一次 AppKit，.prohibited 不显示 Dock 图标、不抢焦点。其他说明保留。 |
| [test_local_watch_swift_initialization.py](../../../backend/tests/test_local_watch_swift_initialization.py) | 新增 3 项离线源码测试：MainActor 和一次性保护、run 启动前初始化、全部实际截图入口在 captureImage 前初始化。 |
| [test_local_watch_swift_testing.py](../../../backend/tests/test_local_watch_swift_testing.py) | 新增 7 项离线迁移约束：全部 9 个用例可发现、无 XCTest、原断言与 OCR 夹具保留、无跳过/降级/第三方包，以及可变队列宏调用修正。 |
| 本报告及 acceptance/r1-* | 仅在原报告末尾追加本节；保存 R1 命令、退出码、红绿测试及验收原始输出。 |

R1 明确补充使用系统 AppKit 和 Swift Testing，并授权迁移本任务新增的 Swift 测试。未修改 Package.swift、其他 Swift 生产逻辑、后端生产代码、前端或受保护文件；未新增第三方依赖。三个 subagent 分别独占截图实现、测试迁移、README，未传 model 或 reasoning_effort；README 代理另行只读审查全部旧断言。

### R1 先失败再实现

| 修正 | 实现前 | 实现后 | 证据 |
| --- | --- | --- | --- |
| R1-1 截图初始化 | 3 failed，exit 1 | 3 passed，exit 0 | [r1-capture-red.txt](acceptance/r1-capture-red.txt)、[r1-capture-green.txt](acceptance/r1-capture-green.txt) |
| R1-2 Swift Testing 迁移 | 7 failed，exit 1 | 7 passed，exit 0 | [r1-testing-red.txt](acceptance/r1-testing-red.txt)、[r1-testing-green.txt](acceptance/r1-testing-green.txt) |
| 可变队列 #require 编译修正 | 新增契约先失败：1 failed、6 passed，exit 1 | 7 passed，exit 0；最终真实 Swift 编译成功 | [r1-testing-mutating-red.txt](acceptance/r1-testing-mutating-red.txt)、[r1-testing-mutating-green.txt](acceptance/r1-testing-mutating-green.txt) |

上述每个输出均有对应 .exit 与 .command.json。新 Python 测试采用模块级自动 fixture 拦截 socket 与 DNS，只读取工作区源码，不依赖 git 历史或 node_modules；模型调用沿用离线桩。全程未安装包、未启动应用服务、未发起真实网络请求。

### R1 验收结果

Python 使用仓库现有 backend/.venv；npm 离线并禁止自动安装。Swift 工具链为 Apple Swift 6.4，xcode-select 选中 Command Line Tools。完整命令及环境参数保存于各日志旁的 .command.json，所有退出码保存于 .exit；原始错误不在报告展开。

| 验收项 | 实际结果 | 退出码 | 证据 |
| --- | --- | --- | --- |
| git status --porcelain 与 R1 范围审计 | 仅原任务允许范围与两份 R1 新测试；unexpected_changed_files=[] | 0 | [r1-git-status.log](acceptance/r1-git-status.log)、[r1-scope-audit.json](acceptance/r1-scope-audit.json) |
| 受保护文件 diff | 空输出，零 diff | 0 | [r1-protected-diff.log](acceptance/r1-protected-diff.log) |
| database.py | R1 未改；相对原任务基线仍为 199 行新增、0 行删除 | 0 | [r1-database-diff.log](acceptance/r1-database-diff.log)、r1-scope-audit.json |
| 既有后端测试 | git diff --name-only -- backend/tests 为空；任务前 99 个测试 SHA-256 不变，上轮 5 份 local-watch Python 测试也未改 | 0 | [r1-existing-test-diff.log](acceptance/r1-existing-test-diff.log)、r1-scope-audit.json |
| 默认 python -m pytest -q | 3613 passed、6 skipped、1 failed、5 errors；同六项既有回环端口测试因 PermissionError: Operation not permitted 受阻 | 1 | [r1-pytest-full.log](acceptance/r1-pytest-full.log) |
| 仅排除上述六项的补充全量 | 3613 passed、6 skipped、6 deselected、14 warnings | 0 | [r1-pytest-without-loopback.log](acceptance/r1-pytest-without-loopback.log) |
| 本任务全部新 Python 测试 | 138 passed、14 warnings：上轮 128 项加 R1 新增 10 项；原后端/服务 95 项全部通过 | 0 | [r1-pytest-new-final.log](acceptance/r1-pytest-new-final.log) |
| python -m pip check | No broken requirements found | 0 | [r1-pip-check.log](acceptance/r1-pip-check.log) |
| npx tsc --noEmit | 空输出 | 0 | [r1-tsc.log](acceptance/r1-tsc.log) |
| npx eslint . | 0 errors，25 个既有 warnings | 0 | [r1-eslint.log](acceptance/r1-eslint.log) |
| 原样 swift build -c release | 默认编译缓存路径不可写，Operation not permitted，随后出现模块/SDK 诊断 | 1 | [r1-swift-build-release-default.log](acceptance/r1-swift-build-release-default.log) |
| 工作区缓存 swift build -c release | 源码与链接完成；生成 dSYM 时 Operation not permitted | 1 | [r1-swift-build-release-workspace-cache.log](acceptance/r1-swift-build-release-workspace-cache.log) |
| 工作区缓存 native release、关闭 debug info | Build complete；包含新的 AppKit 初始化实现 | 0 | [r1-swift-build-release-native.log](acceptance/r1-swift-build-release-native.log) |
| 原样 swift test | 默认编译缓存路径不可写，未进入测试 | 1 | [r1-swift-test-default.log](acceptance/r1-swift-test-default.log) |
| 最终工作区缓存 swift test | 成功编译、链接、发现并执行全部 9 个 Swift Testing 用例；8 项纯逻辑通过；OCR 抛 .nilError，1 项失败 | 1 | [r1-swift-test-workspace-cache-final.log](acceptance/r1-swift-test-workspace-cache-final.log) |
| git diff --check | 空输出 | 0 | [r1-diff-check.log](acceptance/r1-diff-check.log) |

最终 Swift Testing 的实际验收命令（在 watcher-mac 内）：

```sh
swift test --disable-sandbox --cache-path .build/swiftpm-cache
```

CLANG_MODULE_CACHE_PATH 和 SWIFTPM_MODULECACHE_OVERRIDE 指向工作区的 .build/module-cache。默认构建系统已经正确解析 CLT 自带 Testing.framework，所有测试成功编译，说明原先 XCTest 缺失的编译阻断已消除。OCR 仍在运行阶段抛 .nilError，与首轮沙箱中的 Vision 失败现象一致；具体原因尚未确认，不能视为 OCR 验收通过。

中间诊断也保留：native test 未补 framework 搜索路径时报 no such module Testing，exit 1，见 [r1-swift-test-native.log](acceptance/r1-swift-test-native.log)；补路径的 native 尝试和第一次默认工作区构建暴露两处可变队列 #require 宏展开错误，均 exit 1，见 [r1-swift-test-native-framework.log](acceptance/r1-swift-test-native-framework.log)、[r1-swift-test-workspace-cache.log](acceptance/r1-swift-test-workspace-cache.log)。该编译错误已修复，最终工作区构建实际运行 9 项测试；未通过改 Package 或引入依赖规避问题。

默认全量受阻的六项仍是上文列出的 test_exchange_isolation 两项与 test_safe_http_deadline 四项，名称及完整失败保存在 r1-pytest-full.log；未修改或默认跳过它们。

### R1 作者需在沙箱外复验

1. 在仅安装 Command Line Tools、工具链包含 Testing.framework 的真机重新执行 swift build -c release 与 swift test，确认包括中英文 OCR 的全部 9 个测试通过；无需为本返修安装完整 Xcode。当前沙箱的缓存/dSYM 限制及 OCR .nilError 已如实记录。
2. 运行真实窗口监控，确认首次与后续截图均不再触发 CGS_REQUIRE_INIT；确认无 Dock 图标、不抢焦点。截图入口顺序已通过源码测试，真实截图按返修单交作者验证。
3. 在允许回环端口的环境复跑默认 Python 全量，确认上述六项既有端口测试通过。

本次报告原文保持逐字不变，仅末尾追加 R1；其他实现保持不动，未触发规格第 5 节停下来的条件。


## R2

日期：2026-10-11。依据 [05-fix-r2.md](05-fix-r2.md) 完成 R2-1 至 R2-5 全部必改项，参考 [04-review.md](04-review.md) 独立复核原文。本节追加记录本轮变更与验收，前文及 R1 保持逐字不变。

返修单已记录作者方的真机结果：R1 后截图不再崩溃，Safari 端到端的关键词、数值、AI 三种提醒均写入聊天，仅安装 Command Line Tools 的环境中 Swift Testing 全部 9 项通过。这是作者方已完成的验收；下表另外记录本轮沙箱执行结果，两者分别保留。

### R2 变更文件与逐项对应

本轮修改 8 个既有文件、新增 3 个测试文件，共 11 个实现、测试及报告文件；另保存 acceptance/r2-* 验收证据。

| 文件 | 变更与对应要求 |
| --- | --- |
| [backend/services/local_watch.py](../../../backend/services/local_watch.py) | R2-1：先校验 alert 为严格布尔；false 直接成功返回，不校验 summary；true 仍要求非空字符串且去除首尾空白后为 1–80 字。R2-2：统一五种 Unicode 负号及全角数字、小数点、百分号。R2-5.4：只对完整千分位分组去逗号，1,2345 取 1。对应原规格 2.3。 |
| [backend/database.py](../../../backend/database.py) | R2-3：新增读取实际 assistant 消息正文的函数。R2-4：新增 SELECT 优先、有效设备至少间隔 60 秒更新 last_seen_at 的鉴权函数。R2-5.1：新增三条 CREATE INDEX IF NOT EXISTS。对应原规格 2.1、2.2、2.4；仅新增，不改旧函数。 |
| [backend/routers/local_watch.py](../../../backend/routers/local_watch.py) | R2-3：alerts 返回 content。R2-4：改用新的鉴权函数；失败鉴权按真实客户端 IP 每分钟 30 次；observations 按设备每分钟 60 次，计数在 JSON/参数校验和查规则之前。R2-5.2：心跳按设备每分钟 10 次，同样在校验之前计数。对应原规格 2.2、5。 |
| [frontend/lib/localWatch.ts](../../../frontend/lib/localWatch.ts) | R2-3：LocalWatchAlert 必含 content，插入聊天时直接使用服务端正文。对应原规格 3.2。 |
| [frontend/components/LocalWatchSection.tsx](../../../frontend/components/LocalWatchSection.tsx) | R2-5.3：窗口预填 app_match 与 title_match 均按 Unicode 字符截到 60 字。对应原规格 3.1。 |
| [test_local_watch_backend_r2.py](../../../backend/tests/test_local_watch_backend_r2.py) | 新增 24 项离线测试：正文读取与隔离、索引、无效令牌只读、60 秒更新间隔、并发、IP/观察/心跳限流及校验顺序。 |
| [test_local_watch_service_r2.py](../../../backend/tests/test_local_watch_service_r2.py) | 新增 58 项离线测试：两种模型的 false 成功/true 失败、Unicode 负号、全角数值、千分位，以及 R2-5.5 的隐私断言正控与真实处理。 |
| [test_local_watch_frontend_r2.py](../../../backend/tests/test_local_watch_frontend_r2.py) | 新增 10 项无包 Node/源码测试：逐字使用 content、规则改名/删除、忙时排队与去重，以及实际窗口预填表达式和提交参数的 60 字边界。 |
| [test_local_watch_backend.py](../../../backend/tests/test_local_watch_backend.py) | 仅在本任务新增的 alerts 字段白名单断言中加入 content，遵循 R2-3 的新响应契约。 |
| [test_local_watch_frontend.py](../../../backend/tests/test_local_watch_frontend.py) | 按 R2-3 明确要求，仅为两条提醒夹具补 content，并将一处正文期望改为服务端正文；其余测试与断言保留。 |
| 本报告 | 仅末尾追加 R2；证据另存 acceptance/r2-*。 |

R2-3 的 content 取自与提醒同用户、同会话、同 message_id 的 assistant 消息，不由当前规则名重拼；改名或删规则后正文仍与库中一致。消息已删除或引用不匹配时返回空字符串，避免伪造正文或读取他人的内容；after、50 条上限及用户隔离保留。为满足 database.py 只允许新增，旧的 authenticate_watch_device 与 list_watch_alerts 原样保留，路由改用新增函数。

R2-4 对伪造、吊销或已删除用户的令牌只读查询，不执行 BEGIN、UPDATE 或 commit；合法设备使用数据库时间及带条件的 UPDATE，60 秒内后续请求不更新。并发测试使用 SQLite trigger 确认实际 last_seen_at 更新只有一次。失败鉴权限流覆盖缺失/错误认证头及无效令牌，不信任 X-Forwarded-For；超限返回 429、Retry-After 与 private, no-store。非法 JSON、422 和缺失规则的 404 均计入对应设备额度。

R2-5 三个索引为 watch_rules(username)、watch_alerts(username, id)、watch_alerts(rule_id, id)，旧库重复启动测试通过；watch_devices(token_hash) 的 UNIQUE 保留。千分位覆盖 1,234.50%、-1,234,567.89，以及 1,2345、1,23,456 等非法分组。隐私测试先故意把新增文字和摘要写入日志，确认同一断言抛 AssertionError，清空夹具日志后再经两种模型桩、真实处理与 SQLite trace 验证不泄漏；真实处理的安全元数据仍被记录。

原规格逐节对应：第 0 节目标与第 1 节 Mac 行为保留；第 2 节按以上后端修订；第 3 节按正文与预填修订；第 4 节原六份功能文档未改，文档测试通过；第 5 节约束审计与测试纪律见下；第 6 节全部检查均已执行并记录实际退出码。R1 的 AppKit 初始化及 Swift Testing 迁移未改。

### R2 约束与先失败再实现

三个实施 subagent 分别独占服务、数据库/路由、前端及各自新增测试，另由 subagent 只读复核；交接后才追加报告与审计证据。派代理未传 model 或 reasoning_effort。新测试使用模块级自动 fixture 拦截 socket 和 DNS，千问与 Claude 都打桩，前端仅执行独立 Node 逻辑，不依赖 git 历史或 node_modules。全程离线、未安装包、未启动应用服务、未发起真实模型请求。

| 红绿阶段 | 改代码前 | 最终结果 | 证据 |
| --- | --- | --- | --- |
| R2-1、R2-2、R2-5.4/5 服务测试 | 36 failed、22 passed，exit 1 | 新增 58 项与原服务 40 项合计 98 passed，exit 0 | [r2-service-red.txt](acceptance/r2-service-red.txt)、[r2-service-green.txt](acceptance/r2-service-green.txt) |
| R2-3/4、R2-5.1/2 后端测试 | 24 failed，exit 1 | 新增 24 passed，exit 0；后端与集成回归共 94 passed，exit 0 | [r2-backend-red.txt](acceptance/r2-backend-red.txt)、[r2-backend-green.txt](acceptance/r2-backend-green.txt)、[r2-backend-regression.txt](acceptance/r2-backend-regression.txt) |
| R2-3 新 alerts 字段契约 | 更新期望后先执行：1 failed，exit 1 | 纳入最终本任务测试，全部通过 | [r2-alert-contract-red.log](acceptance/r2-alert-contract-red.log)、[r2-pytest-new.log](acceptance/r2-pytest-new.log) |
| R2-3、R2-5.3 前端测试 | 9 failed、1 passed，exit 1 | 新增 10 项与原前端 11 项合计 21 passed，exit 0 | [r2-frontend-red.txt](acceptance/r2-frontend-red.txt)、[r2-frontend-green.txt](acceptance/r2-frontend-green.txt) |

每份运行输出均有同名 .exit 与 .command.json，记录完整命令和环境参数。正控新增时即可识别故意泄漏，因此该测试在服务红阶段已经通过；生产修复前需要失败的行为测试均已实际失败。

受保护文件零 diff。任务前已有的 99 个后端测试 SHA-256 全部不变。本任务新增测试中的两份 R2-3 契约变更见 [r2-contract-tests.diff](acceptance/r2-contract-tests.diff)：后端只改一个字段白名单断言，前端只改两份夹具和一处正文期望；反向撤销这些变更后哈希与 R2 开始快照一致。其余已有测试及 watcher-mac 全部不变。database.py 相对 R2 开始仅新增 50 行、删除 0 行，见 [r2-database-increment.diff](acceptance/r2-database-increment.diff)；相对原任务 git 基线累计新增 249 行、删除 0 行。范围及报告追加校验见 [r2-scope-audit.json](acceptance/r2-scope-audit.json)。

### R2 全部验收结果

Python 使用仓库已有 backend/.venv；前端命令设置 npm_config_offline=true、npm_config_yes=false。Swift 使用现有 Command Line Tools。下表列出规格第 6 节每项实际结果；原始 traceback 只存 acceptance/。

| 验收项 | 实际结果 | 退出码 | 证据 |
| --- | --- | --- | --- |
| git status --porcelain、文件范围审计 | 仅允许范围内文件；unexpected_changed_files=[] | 0 | [r2-git-status.log](acceptance/r2-git-status.log)、[r2-scope-audit.json](acceptance/r2-scope-audit.json) |
| 受保护文件 git diff --exit-code | 空输出，零 diff | 0 | [r2-protected-diff.log](acceptance/r2-protected-diff.log) |
| git diff -- backend/database.py | 累计 +249/-0；本轮 +50/-0，旧内容全保留 | 0 | [r2-database-diff.log](acceptance/r2-database-diff.log)、r2-database-increment.diff |
| git diff --name-only -- backend/tests | 空输出；另以快照确认任务前 99 个测试不变及两份任务内契约调整范围 | 0 | [r2-existing-test-diff.log](acceptance/r2-existing-test-diff.log)、r2-scope-audit.json |
| 默认 python -m pytest -q | 3705 passed、6 skipped、1 failed、5 errors、14 warnings；六项既有端口测试受沙箱 PermissionError 限制 | 1 | [r2-pytest-full.log](acceptance/r2-pytest-full.log) |
| 仅排除上述六项的补充全量 | 3705 passed、6 skipped、6 deselected、14 warnings | 0 | [r2-pytest-without-loopback.log](acceptance/r2-pytest-without-loopback.log) |
| 本任务全部新测试 | 230 passed、14 warnings；R1 后的 138 项加 R2 新增 92 项，无失败或跳过 | 0 | [r2-pytest-new.log](acceptance/r2-pytest-new.log) |
| python -m pip check | No broken requirements found | 0 | [r2-pip-check.log](acceptance/r2-pip-check.log) |
| npx tsc --noEmit | 空输出 | 0 | [r2-tsc.log](acceptance/r2-tsc.log) |
| npx eslint . | 0 errors、25 个既有 warnings | 0 | [r2-eslint.log](acceptance/r2-eslint.log) |
| 原样 swift build -c release | 默认编译缓存路径不可写，Operation not permitted；随后出现模块/SDK 诊断 | 1 | [r2-swift-build-release-default.log](acceptance/r2-swift-build-release-default.log) |
| 工作区缓存 native release、关闭 debug info | Build complete | 0 | [r2-swift-build-release-native.log](acceptance/r2-swift-build-release-native.log) |
| 原样 swift test | 同一默认编译缓存限制，未进入测试 | 1 | [r2-swift-test-default.log](acceptance/r2-swift-test-default.log) |
| 工作区缓存 swift test | 编译、链接并执行 9 个 Swift Testing 用例；8 项通过，OCR 仍抛 .nilError，1 项失败 | 1 | [r2-swift-test-workspace-cache.log](acceptance/r2-swift-test-workspace-cache.log) |
| git diff --check | 空输出 | 0 | [r2-diff-check.log](acceptance/r2-diff-check.log) |

本轮默认全量受阻的六项与前两轮一致，完整输出和退出码保留，未修改或默认跳过这些测试：

1. tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
2. tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
3. tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
4. tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
5. tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
6. tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch

补充全量仅在命令行 deselect 上述六项，完整参数见 [r2-pytest-without-loopback.command.json](acceptance/r2-pytest-without-loopback.command.json)。Swift 补充构建在 watcher-mac 内执行 swift build -c release --disable-sandbox --cache-path .build/swiftpm-cache --build-system native -debug-info-format none；补充测试执行 swift test --disable-sandbox --cache-path .build/swiftpm-cache，CLANG_MODULE_CACHE_PATH 与 SWIFTPM_MODULECACHE_OVERRIDE 均指向工作区 .build/module-cache。全部 Swift 文件未改，沙箱 OCR 运行错误原因仍未确认；不把该结果记作通过，也不据此否定返修单中作者已完成的 CLT 9 项通过结果。

### R2 作者需在沙箱外或真机复验的点

1. 本轮后端与前端部署后，验证 Unicode 负号/全角行情、false 空摘要不出现失败日志；确认新提醒实时正文、刷新正文与数据库一致，并覆盖规则改名及删除。
2. 在实际浏览器验证超长应用名/标题窗口预填各为 60 字，含 emoji/中文，保存不再因长度返回 422。
3. 在允许网络与端口的环境复验失败鉴权每 IP 30 次、心跳每设备 10 次、观察每设备 60 次及 429；确认无效请求也计数，合法设备 60 秒内不重复更新 last_seen_at。真实部署的客户端 IP 获取也应核对。
4. 在允许回环端口的环境复跑默认 python -m pytest -q，补齐上述六项既有端口测试。在 CLT 真机对交付状态执行 swift build -c release 与 swift test，记录标准命令结果；R1 截图和 9 项 Swift 测试已由作者验收，本轮未修改其文件，沙箱仍不能完成同等环境验收。

R2 五项及全部子项均已完成，未触发规格第 5 节停下来的条件。前文保留，未回滚已有实现；所有环境受阻检查按实际输出与退出码记录。


## R3

日期：2026-10-11。依据 [05-fix-r3.md](05-fix-r3.md) 完成 R3-1、R3-2、R3-3，原规格及 R1/R2 已实现行为继续保留。本节仅在原报告末尾追加，前文保持逐字不变。

### R3 变更文件与规格对应

本轮修改 13 个既有文件、新增 6 个实现/测试文件，共 19 个；另保存 acceptance/r3-* 验收证据。

| 文件 | 改动与对应要求 |
| --- | --- |
| [Watcher.swift](../../../watcher-mac/Sources/FionaWatcherCore/Watcher.swift) | R3-1、原规格 1.2：在实际截图失败/成功路径更新状态并输出日志，成功更新在未变化帧跳过 OCR 之前；每次心跳增加 capture_status。运行期间窗口清单获取失败仍继续心跳，保留原始错误；首次没有录屏权限仍显示原中文指引并退出。 |
| [CaptureStatus.swift](../../../watcher-mac/Sources/FionaWatcherCore/CaptureStatus.swift)（新增） | R3-1：可注入 Date 与 NSError 的纯状态机。按规则及错误身份各自节流 60 秒，恢复记一次，since 仅状态切换时更新。窗口未找到为 window_not_found；健康状态显式编码 error:null。日志仅取原始域/码，不读取窗口文字或错误描述。 |
| [Package.swift](../../../watcher-mac/Package.swift) | 新增独立 FionaWatcherCaptureStatusTests target；旧测试 target、目录及内容保留，无第三方依赖。既有 Python 契约要求原 Tests 目录保持三份 Swift 测试，因此新增测试使用独立目录。 |
| [test_local_watch_capture_status.swift](../../../watcher-mac/CaptureStatusTests/test_local_watch_capture_status.swift)（新增） | R3-1：8 项 Swift Testing，通过模拟错误与时钟覆盖 60 秒边界、规则隔离、A→B→A、恢复、匹配重置、since、JSON/null、窗口缺失与隐私。无需真实截图。 |
| [backend/routers/local_watch.py](../../../backend/routers/local_watch.py) | R3-2、原规格 2.2：接收并校验截图状态，按设备/用户/数据库在内存保存，服务器收到时间为 5 分钟有效期依据；GET rules 增加 capture，原始错误在后端映射为固定中文提示。兼容旧心跳，不改数据库。 |
| [frontend/lib/localWatch.ts](../../../frontend/lib/localWatch.ts) | R3-2、原规格 3.1：新增可选 capture 类型与状态文本函数，兼容旧响应；规则草稿明确排除 capture，提交仍采用精确白名单。 |
| [frontend/components/LocalWatchSection.tsx](../../../frontend/components/LocalWatchSection.tsx) | R3-2/3：每条规则显示状态，正常显示「监控中」，异常用醒目颜色；可见页面每 10 秒刷新，账号切换及卸载时清理；说明区补充锁屏/休眠限制及安全权衡。 |
| [test_local_watch_capture_backend_r3.py](../../../backend/tests/test_local_watch_capture_backend_r3.py)（新增） | 53 项离线测试：保存/覆盖/恢复/过期、中文映射、旧心跳、跨用户/设备/数据库隔离、撤销/删号、删除规则同步、字段校验与限流顺序。 |
| [test_local_watch_capture_frontend_r3.py](../../../backend/tests/test_local_watch_capture_frontend_r3.py)（新增） | 12 项离线源码/无包 Node 测试：状态行及颜色、后端文案、旧响应、表单排除状态、说明和可见页面刷新/清理。 |
| [test_local_watch_swift_capture_r3.py](../../../backend/tests/test_local_watch_swift_capture_r3.py)（新增） | 5 项离线接线测试：实际心跳、截图失败与未变化帧恢复、枚举失败、独立 Swift Testing 目标及日志隐私。 |
| [test_local_watch_capture_docs_r3.py](../../../backend/tests/test_local_watch_capture_docs_r3.py)（新增） | 7 项离线文档测试：要求各份文档说明锁屏/休眠无法监控、系统设置位置、延长自动锁定时间及自行权衡安全，无本机绝对路径。 |
| [README.md](../../../README.md)、[CLAUDE.md](../../../CLAUDE.md)、[PLAN.md](../../../PLAN.md)、[ARCHITECTURE.md](../../../docs/ARCHITECTURE.md)、[DEPLOYMENT.md](../../../docs/DEPLOYMENT.md)、[backend/.env.example](../../../backend/.env.example)、[watcher-mac/README.md](../../../watcher-mac/README.md) | R3-3、原规格 4：七份文档补充「屏幕锁定或显示器休眠时 macOS 不允许截取窗口，期间无法监控」及延长锁定时间的安全权衡，并说明日志/状态行为。 |
| 本报告 | 原规格 6：末尾追加 R3，列出实际命令结果、退出码与外部验证点。 |

原规格逐节对应：第 0 节目标保留；第 1 节增加失败可见性，保留 R1 的 AppKit 初始化和权限指引；第 2 节增加内存状态与中文映射；第 3 节增加逐条状态和锁屏说明；第 4 节七份文档更新；第 5 节约束及新测试审计见下；第 6 节全部检查均实际执行。

每次心跳的 capture_status 包含 rule_id、ok、error、since；error 为原始错误域/码、window_not_found 或 null，since 是状态开始时间。新规则尚未完成截图时可为 false/null；不包含窗口标题、OCR 或错误描述。日志应用名及错误身份清理换行。恢复、错误切换和规则匹配条件重置均不能绕过同规则同错误 60 秒日志限制；成功恢复只记一次。运行阶段枚举失败不会被错误覆盖为 window_not_found，异步截图期间删改规则会丢弃旧结果。

后端收到状态后返回 capture={ok,message,since}；无状态或达到 300 秒时严格返回 {ok:false,message:"监控程序未在运行"}，省略 since。SCStream/ScreenCaptureKit 错误映射为「截图失败：屏幕可能已锁定或显示器已休眠，也可能缺少屏幕录制权限」；未找到窗口映射为「没有找到匹配的窗口（窗口可能已关闭或最小化）」；其余错误为「截图失败，请查看监控程序日志」。不把任意原始错误文字交给页面展示。

每台设备保存自己的完整状态快照，选择每条规则最新有效设备上报；撤销设备或删号后不再显示其状态。since 即使在未来也不会延长有效期。旧心跳缺少 capture_status 仍返回 200，并清除该设备旧状态，不为旧状态续期。合法但已删除、禁用或非本用户规则的状态被过滤，心跳仍返回最新规则，避免用户删规则后监控端无法同步。结构或类型非法的状态返回 422，窗口/状态缓存不会部分更新；原每设备心跳 10 次/分钟限流仍在 JSON 校验之前。

### R3 约束与先失败再实现

三个实施 subagent 按 Swift、后端、前端分文件独占，root 负责七份文档、验收与报告；另一个 subagent 只读复核整体实现。派代理未传 model 或 reasoning_effort。全部新增 Python 测试使用模块级自动 fixture 拦截 socket 与 DNS；需要模型的测试使用现有离线桩，前端仅源码/独立 Node 执行，Swift 使用注入错误与时钟。全程离线，未安装包、未启动应用服务、未发起真实截图或模型请求，新测试不依赖 git 历史或 node_modules。

| 红绿阶段 | 改生产代码前 | 最终结果 | 证据 |
| --- | --- | --- | --- |
| Swift Runner 接线 | 5 failed，exit 1 | 新增 5 项及既有 R1 契约 10 项共 15 passed，exit 0 | [r3-swift-wiring-red.log](acceptance/r3-swift-wiring-red.log)、[r3-swift-wiring-green.log](acceptance/r3-swift-wiring-green.log) |
| 后端状态 | 46 failed、7 passed，exit 1 | 新增 53 passed；后端与集成回归共 147 passed，均 exit 0 | [r3-backend-red.txt](acceptance/r3-backend-red.txt)、[r3-backend-green.txt](acceptance/r3-backend-green.txt)、[r3-backend-regression.txt](acceptance/r3-backend-regression.txt) |
| 前端状态/说明 | 10 failed、2 passed，exit 1 | 新增 12 项与既有前端 21 项合计 33 passed，exit 0 | [r3-frontend-red.txt](acceptance/r3-frontend-red.txt)、[r3-frontend-green.txt](acceptance/r3-frontend-green.txt) |
| 七份文档 | 7 failed，exit 1 | 新增 7 项及既有文档 7 项合计 14 passed，exit 0 | [r3-docs-red.log](acceptance/r3-docs-red.log)、[r3-docs-green.log](acceptance/r3-docs-green.log) |

Swift 单元测试在生产实现前已写入并尝试执行，但早期调用分别被 Testing 宏插件及模块环境错误阻断，不能把它们记作 8 项行为测试实测失败；原始输出见 [r3-swift-unit-red.log](acceptance/r3-swift-unit-red.log)、[r3-swift-unit-red-native.log](acceptance/r3-swift-unit-red-native.log)，均 exit 1。修复前的有效红阶段证据是上述 5 项 Runner 接线实测失败；修复后真实 Swift Testing 执行中新增 8 项全部通过，未删除、跳过或放宽任何旧测试。

本轮 112 份既有 Python/Swift 测试源码哈希不变，测试目录快照中的全部 114 个文件（含数据夹具等）也未改，包含原任务前 99 个后端测试；57 个受保护文件不变。database.py 本轮未改，累计相对原任务 git 基线仍是 +249/-0。范围审计仅排除 tsc 自动生成的 tsconfig.tsbuildinfo 缓存，见 [r3-scope-audit.json](acceptance/r3-scope-audit.json)。

### R3 全部验收结果与缓存清理

Python 使用仓库已有 backend/.venv，前端命令显式设置 npm_config_offline=true、npm_config_yes=false。每份输出有对应 .exit 与 .command.json；Swift 运行另有 .cleanup.json。原始 traceback 只存 acceptance/。

| 验收项 | 实际结果 | 退出码 | 证据 |
| --- | --- | --- | --- |
| git status --porcelain、范围审计 | 仅允许范围内文件；unexpected_changed_files=[]，报告仅追加 | 0 | [r3-git-status.log](acceptance/r3-git-status.log)、[r3-scope-audit.json](acceptance/r3-scope-audit.json) |
| 受保护文件 git diff --exit-code | 空输出，零 diff | 0 | [r3-protected-diff.log](acceptance/r3-protected-diff.log) |
| git diff -- backend/database.py | 本轮 +0/-0；累计 +249/-0 | 0 | [r3-database-diff.log](acceptance/r3-database-diff.log)、r3-scope-audit.json |
| git diff --name-only -- backend/tests | 空输出；另核对 112 份既有 Python/Swift 测试源码及测试目录全部 114 个文件哈希不变 | 0 | [r3-existing-test-diff.log](acceptance/r3-existing-test-diff.log)、r3-scope-audit.json |
| 默认 python -m pytest -q | 3782 passed、6 skipped、1 failed、5 errors、14 warnings；同六项既有回环端口测试因 PermissionError 受阻 | 1 | [r3-pytest-full.log](acceptance/r3-pytest-full.log) |
| 仅排除上述六项的补充全量 | 3782 passed、6 skipped、6 deselected、14 warnings | 0 | [r3-pytest-without-loopback.log](acceptance/r3-pytest-without-loopback.log) |
| 本任务全部新 Python 测试 | 307 passed、14 warnings：R2 后 230 项加 R3 新增 77 项，无失败或跳过 | 0 | [r3-pytest-new.log](acceptance/r3-pytest-new.log) |
| python -m pip check | No broken requirements found；pip 缓存权限提示不影响检查 | 0 | [r3-pip-check.log](acceptance/r3-pip-check.log) |
| npx tsc --noEmit | 空输出 | 0 | [r3-frontend-tsc.txt](acceptance/r3-frontend-tsc.txt) |
| npx eslint . | 0 errors、25 个既有 warnings | 0 | [r3-frontend-eslint.txt](acceptance/r3-frontend-eslint.txt) |
| 先清空 .build，原样 swift build -c release | manifest 编译写默认缓存被沙箱拒绝，随后出现 SwiftShims/SDK 诊断 | 1 | [r3-swift-build-release-default.log](acceptance/r3-swift-build-release-default.log) |
| 先清空 .build，原样 swift test | 同一默认缓存权限限制，未进入测试 | 1 | [r3-swift-test-default.log](acceptance/r3-swift-test-default.log) |
| 空缓存 native release 补充构建 | 完整编译、链接成功，Build complete，30.53 秒 | 0 | [r3-swift-build-release-native.log](acceptance/r3-swift-build-release-native.log) |
| 空缓存 native Swift Testing 补充执行 | 全部 17 项发现并执行：新增 8 项及既有纯逻辑 8 项通过，既有 OCR 抛 .nilError，整体 1 项失败 | 1 | [r3-swift-test-native-plugin.log](acceptance/r3-swift-test-native-plugin.log) |
| Swift 调用前后及交付缓存清理 | 六次调用均先删除 .build、结束后 finally 删除；交接后 root 再执行 rm -rf watcher-mac/.build，最终不存在 | 0 | [r3-swift-cleanup-audit.json](acceptance/r3-swift-cleanup-audit.json)、[r3-swift-final-cache-cleanup.command.json](acceptance/r3-swift-final-cache-cleanup.command.json)、r3-scope-audit.json |
| git diff --check | 空输出 | 0 | [r3-diff-check.log](acceptance/r3-diff-check.log) |

Swift 补充构建使用工作区 module cache、native、关闭 debug info；补充测试另通过命令行显式引用 CLT 已安装的 Testing framework 和宏插件，不改 Package 的现有配置、不安装依赖。完整参数见 [r3-swift-test-native-plugin.command.json](acceptance/r3-swift-test-native-plugin.command.json)。默认工作区构建在空缓存下也遇到宏插件查找问题；沙箱补充执行已确认新增测试通过，但标准命令与真实 OCR 仍不能记作沙箱验收通过。所有特殊参数产物已清除，未向作者交付沙箱 .build。

默认 Python 全量受阻的六项与前轮相同，未修改或默认跳过：

1. tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot
2. tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive
3. tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline
4. tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work
5. tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline
6. tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch

补充全量只在命令行 deselect 这六项，参数与退出码见 [r3-pytest-without-loopback.command.json](acceptance/r3-pytest-without-loopback.command.json)。

### R3 作者需在沙箱外或真机验证

1. 在仅安装 CLT 的真机从空 .build 执行标准 swift build -c release 与 swift test，确认全部 17 项（含新增 8 项及旧 OCR）通过；不要沿用沙箱特殊参数缓存。本轮已删除 .build。
2. 真实 run 监控窗口后锁屏、休眠：确认日志出现规定的原始错误域/码，每规则每同错误 60 秒最多一条；下一次心跳及设置页显示中文异常，期间不产生新提醒。解锁后确认截图恢复日志只记一次、页面恢复「监控中」，并继续监控。
3. 窗口关闭或最小化时确认逐条显示没有匹配窗口；停止监控端超过 5 分钟后显示「监控程序未在运行」。多规则、多设备、删除规则和撤销令牌时核对状态隔离及同步。
4. 在实际浏览器核对醒目异常提示、可见页面自动刷新、账号切换及表单编辑；确认锁屏说明与安全权衡文案可见。在允许回环端口的环境复跑默认 Python 全量，补齐上述六项既有测试。

R3 三项均已完成，未触发规格第 5 节停下来的条件；环境受阻结果及退出码按原样保留。前文未改，既有测试未改，未留下 watcher-mac/.build。


## R4

2026-10-11，按 [05-fix-r4.md](05-fix-r4.md) 完成 R4-1 至 R4-5。全部本任务 Python 测试 **382 passed**，其中 R4 新增 74 项；TypeScript、ESLint、依赖检查通过。默认全量 **3857 passed、6 skipped、1 failed、5 errors**，六项均为既有回环端口测试受沙箱权限限制；仅排除这六项的补充全量通过。Swift 从空缓存补充 release 构建成功，22 项测试实际执行、21 项通过，既有 OCR 仍抛 `.nilError`。原样 Swift 命令受默认缓存权限阻碍，不能记为通过。所有 Swift 调用结束后已删除 `watcher-mac/.build`。

### R4 文件变更与逐项对应

本轮修改四份生产文件、四份本任务测试和本报告，新增四份测试；另新增 `acceptance/r4-*` 验收证据。下表相对 R4 开始时的工作区列出变更，不重复列入前轮或作者已经完成的修改。

| 文件 | 本轮变更与对应条文 |
| --- | --- |
| [backend/routers/local_watch.py](../../../backend/routers/local_watch.py) | R4-1：停用规则优先返回「已停用」；首次未截图和有效设备最近有心跳但缺少规则状态时返回「等待首次截图」，带 `neutral:true`。最近心跳按数据库路径、用户、设备保存在内存，按服务器时间 300 秒过期；吊销及删号立即使来源失效。真实错误继续原映射，无有效心跳时显示未运行。R4-2：失败鉴权调用现有 `rate_limit._client_ip(request)`。R4-3：非法单条截图状态丢弃，合法条目继续保存，重复规则保留首条合法状态；非法容器或超过 20 条仍返回 422，窗口校验与鉴权/心跳限流保留。 |
| [frontend/lib/localWatch.ts](../../../frontend/lib/localWatch.ts) | R4-1：`LocalWatchCapture` 新增可选 `neutral`；状态仍为只读响应元数据，编辑草稿、提交字段和健康提示保留。 |
| [frontend/components/LocalWatchSection.tsx](../../../frontend/components/LocalWatchSection.tsx) | R4-1：中性状态使用普通说明色。R4-5：实际 10 秒定时路径仅 GET `/local-watch/rules`，使用独立账号请求通道，避免取消慢速首次全量读取；保留防重入、页面隐藏取消、账号切换与卸载清理、404 停止。首次加载、用户操作后刷新及模型配置变更仍按原完整刷新。 |
| [watcher-mac/Sources/FionaWatcherCore/CaptureStatus.swift](../../../watcher-mac/Sources/FionaWatcherCore/CaptureStatus.swift) | R4-4：为每条规则单独保存上次恢复日志时间，60 秒内的重复恢复不输出日志；成功状态和 `since` 仍立即更新，移除或同步规则不能绕过节流，原失败日志节流独立保留。 |
| [backend/tests/test_local_watch_capture_backend_r4.py](../../../backend/tests/test_local_watch_capture_backend_r4.py)（新增） | 50 项：中性状态优先级、空/旧心跳、有效设备、300 秒边界、未来设备时间、数据库/用户/设备隔离、撤销/删号、合法与非法混合条目、重复条目、容器上限、窗口旧校验、限流先于解析、可信代理两种真实 IP 头及不可信伪造。 |
| [backend/tests/test_local_watch_capture_frontend_r4.py](../../../backend/tests/test_local_watch_capture_frontend_r4.py)（新增） | 19 项：类型与颜色、原健康文案、执行抽取出的实际定时 effect，仅请求 rules；慢首次加载、防重入、隐藏/恢复、账号切换、卸载、404 和暂时错误后的下一次重试。仅使用系统 Node，无 npm 包依赖。 |
| [backend/tests/test_local_watch_swift_recovery_r4.py](../../../backend/tests/test_local_watch_swift_recovery_r4.py)（新增） | 5 项：编译并执行真实 `CaptureStatus.swift`，用注入时钟覆盖 59.99/60 秒边界、规则隔离、反复失败恢复、移除/同步及失败日志独立节流。Foundation harness 无 SwiftPM/Testing 宏依赖，缓存仅在 pytest 临时目录。 |
| [watcher-mac/CaptureStatusTests/test_local_watch_capture_recovery_r4.swift](../../../watcher-mac/CaptureStatusTests/test_local_watch_capture_recovery_r4.swift)（新增） | 对应上述五种行为的 5 项 Swift Testing；真实全量执行中全部通过。 |
| [backend/tests/test_local_watch_backend_r2.py](../../../backend/tests/test_local_watch_backend_r2.py) | 按 R4 授权清理新增内存状态，并将伪造 XFF 测试对端明确设为不可信 IP，保留原限流与早于解析/规则校验的断言。 |
| [backend/tests/test_local_watch_capture_backend_r3.py](../../../backend/tests/test_local_watch_capture_backend_r3.py) | 按 R4-1/R4-3 更新任务内契约：停用/等待状态、非法单条与重复条目返回 200，非法容器/超限仍 422；保留合法状态、错误映射、隔离、TTL、隐私及限流测试。作者新增完整错误域用例保留。 |
| [backend/tests/test_local_watch_capture_frontend_r3.py](../../../backend/tests/test_local_watch_capture_frontend_r3.py) | 仅将一条颜色源码断言更新为健康或中性状态使用普通说明色。 |
| [watcher-mac/CaptureStatusTests/test_local_watch_capture_status.swift](../../../watcher-mac/CaptureStatusTests/test_local_watch_capture_status.swift) | 仅将 4 秒内第二次恢复的旧日志期望改为不输出，符合 R4-4；其余 8 项测试及断言保留。 |
| [03-report.md](03-report.md) | 仅在末尾追加本节；R4 前 55700 字节完整保留。 |

与原规格各节的对应：第 0 节继续实现本机窗口只读监控；第 1 节本轮只修正恢复日志节流，截图状态、心跳及 OCR 路径保留；第 2 节只修改路由的提示、真实 IP 来源和心跳容错，不改数据库或判定服务；第 3 节增加中性颜色并减少设置页定时读取；第 4 节保留所有既有说明，尤其保留作者 README；第 5 节的范围、依赖、离线及测试约束按下述审计执行，任务内测试冲突按 R4 明确授权调整；第 6 节逐项结果如下。

### R4 先失败再实现与硬约束核对

| 分工 | 改生产代码前的实际红灯 | 最终绿灯 | 证据 |
| --- | --- | --- | --- |
| 后端 R4-1/2/3 | 35 failed、15 passed，exit 1 | 新增 50 passed；后端相关回归 198 passed，exit 0 | [r4-backend-red.txt](acceptance/r4-backend-red.txt)、[r4-backend-green.txt](acceptance/r4-backend-green.txt)、[r4-backend-regression.txt](acceptance/r4-backend-regression.txt) |
| 前端 R4-1/5 | 12 failed、7 passed，exit 1 | 新增 19 项与前轮前端回归合计 52 passed，exit 0 | [r4-frontend-red.txt](acceptance/r4-frontend-red.txt)、[r4-frontend-green.txt](acceptance/r4-frontend-green.txt) |
| Swift R4-4 | 实际 tracker harness 5 failed，exit 1 | harness 与 R3 接线合计 10 passed，exit 0；新增 Swift 5 项全部通过 | [r4-swift-recovery-red.log](acceptance/r4-swift-recovery-red.log)、[r4-swift-recovery-green.log](acceptance/r4-swift-recovery-green.log)、[r4-swift-test-native-plugin.log](acceptance/r4-swift-test-native-plugin.log) |

三个实现 subagent 分别独占后端、前端、Swift 文件；另一个 subagent 只读独立复核五项及硬约束，未发现必改问题。派发均继承模型与推理档位，未传 `model` 或 `reasoning_effort`。

受保护 57 个文件、任务开始前 99 个后端测试、原 Swift `Tests/` 三个文件保持不变。R4 开始时的 119 个测试目录文件中，仅上述四份本任务测试按新条文调整，其余 115 份不变；完整调整 diff 见 [r4-tests-adjustments.diff](acceptance/r4-tests-adjustments.diff)。`database.py` 本轮零修改，累计相对原任务 git 基线 +249/-0。作者 `capture_message` 整函数源码、完整错误域用例以及 `watcher-mac/README.md` 全文均保留。范围与哈希证据见 [r4-scope-audit.json](acceptance/r4-scope-audit.json)。

新测试不读取 git 历史、不依赖 `node_modules`，模块级拦截 socket/DNS，后端模型 SDK 设为禁止调用桩；全程无真实网络请求、无安装包、无启动应用服务。前端验收 CLI 使用工作区已存在的依赖，并设置 npm 离线且禁止自动确认安装。新增 Python 用例为后端 50、前端 19、Swift harness 5，共 74 项；382 总数为 R3 的 307 项、作者补充的 1 个完整错误域参数用例以及 R4 的 74 项。

### R4 全部验收结果与缓存清理

每个命令的实际输出、退出码和参数分别保存在对应 `.log`/`.txt`、`.exit`、`.command.json`。原始 traceback 只保存在 `acceptance/`。

| 验收项 | 实际结果 | exit | 证据 |
| --- | --- | --- | --- |
| 1. `git status --porcelain` 与本轮范围审计 | 累计文件均在本任务允许范围；本轮 9 份既有文件变更、4 份新测试，无越界修改；仅排除 tsc 自动生成的 `tsconfig.tsbuildinfo` | 0 | [r4-git-status.log](acceptance/r4-git-status.log)、[r4-scope-audit.json](acceptance/r4-scope-audit.json) |
| 2. 受保护文件 `git diff --exit-code` | 空输出、零 diff；57 份哈希不变 | 0 | [r4-protected-diff.log](acceptance/r4-protected-diff.log) |
| 3. `git diff -- backend/database.py` | 本轮 +0/-0；累计 +249/-0 | 0 | [r4-database-diff.log](acceptance/r4-database-diff.log)、r4-scope-audit.json |
| 4. `git diff --name-only -- backend/tests` | 空输出；另核对原任务 99 份测试及四份已获授权的任务内调整 | 0 | [r4-existing-test-diff.log](acceptance/r4-existing-test-diff.log)、r4-tests-adjustments.diff |
| 5. 默认 `python -m pytest -q` | 3857 passed、6 skipped、1 failed、5 errors、14 warnings；同六项既有回环端口测试被沙箱拒绝绑定 | 1 | [r4-pytest-full.log](acceptance/r4-pytest-full.log) |
| 5. 仅排除这六项的补充全量 | 3857 passed、6 skipped、6 deselected、14 warnings | 0 | [r4-pytest-without-loopback.log](acceptance/r4-pytest-without-loopback.log) |
| 6. 全部本任务 Python 测试 | 382 passed、14 warnings，无失败或跳过 | 0 | [r4-pytest-new.log](acceptance/r4-pytest-new.log) |
| 7. `python -m pip check` | No broken requirements found；缓存权限提示不影响检查 | 0 | [r4-pip-check.log](acceptance/r4-pip-check.log) |
| 8. `npx tsc --noEmit` | 空输出 | 0 | [r4-frontend-tsc.txt](acceptance/r4-frontend-tsc.txt) |
| 8. `npx eslint .` | 0 errors、25 个既有 warnings | 0 | [r4-frontend-eslint.txt](acceptance/r4-frontend-eslint.txt) |
| 9. 清空 `.build` 后原样 `swift build -c release` | manifest 编译写默认 Clang 缓存被沙箱拒绝，随后出现 SwiftShims/SDK 诊断，未完成构建 | 1 | [r4-swift-build-release-default.log](acceptance/r4-swift-build-release-default.log) |
| 9. 清空 `.build` 后原样 `swift test` | 同一默认缓存权限限制，未进入测试 | 1 | [r4-swift-test-default.log](acceptance/r4-swift-test-default.log) |
| 9. 空缓存 native release 补充构建 | 完整编译、链接成功，Build complete，31.40 秒 | 0 | [r4-swift-build-release-native.log](acceptance/r4-swift-build-release-native.log) |
| 9. 空缓存 native Swift Testing 补充执行 | 22 项实际执行，21 passed：新增恢复节流 5 项、R3 状态 8 项、既有纯逻辑 8 项通过；既有 OCR 1 项 `.nilError` | 1 | [r4-swift-test-native-plugin.log](acceptance/r4-swift-test-native-plugin.log) |
| Swift 前后与最终缓存清理 | 所有 Package 调用从空 `.build` 开始、结束后 finally 删除；root 交接后再执行 `rm -rf watcher-mac/.build`，Python harness 只用临时目录缓存，交付时 `.build` 不存在 | 0 | [r4-swift-cleanup-audit.json](acceptance/r4-swift-cleanup-audit.json)、[r4-swift-final-cache-cleanup.command.json](acceptance/r4-swift-final-cache-cleanup.command.json)、r4-scope-audit.json |
| 10. 报告与补充 `git diff --check` | 仅追加 R4、旧报告字节保留；diff 检查空输出 | 0 | 本节、[r4-diff-check.log](acceptance/r4-diff-check.log)、r4-scope-audit.json |

Swift 补充命令使用工作区 module cache、native 构建系统与关闭 debug info；测试另通过命令行引用 CLT 已安装的 Testing framework 和宏插件。完整参数见 [r4-swift-build-release-native.command.json](acceptance/r4-swift-build-release-native.command.json) 与 [r4-swift-test-native-plugin.command.json](acceptance/r4-swift-test-native-plugin.command.json)。没有修改 Package 或安装依赖来适配沙箱，补充结果不替代标准命令验收；特殊参数产生的 `.build` 已全部删除。

默认全量受阻六项，失败位置均为绑定回环端口时的 `PermissionError: Operation not permitted`：

1. `tests/test_exchange_isolation.py::test_stop_disconnects_async_upstream_and_releases_user_slot`
2. `tests/test_exchange_isolation.py::test_eight_exchanges_and_eight_drip_cards_leave_chat_responsive`
3. `tests/test_safe_http_deadline.py::test_drip_response_obeys_total_wall_clock_deadline`
4. `tests/test_safe_http_deadline.py::test_fast_response_and_redirect_still_work`
5. `tests/test_safe_http_deadline.py::test_drip_headers_obey_total_wall_clock_deadline`
6. `tests/test_safe_http_deadline.py::test_four_stuck_resolutions_do_not_block_another_fetch`

补充全量仅在命令行 deselect 这六项，完整参数见 [r4-pytest-without-loopback.command.json](acceptance/r4-pytest-without-loopback.command.json)，未修改、删除或默认跳过任何原任务测试。

### R4 作者需在沙箱外或真机复验的点

1. CLT 真机从空缓存执行标准 `swift build -c release`、`swift test`，确认全部 22 项含真实中文/英文 OCR 通过。沙箱的标准构建缓存限制与 OCR `.nilError` 仍未完成环境验收；交付已清除 `.build`。
2. 设置页实际确认停用、等待首次截图使用普通说明色；有效心跳停发满 5 分钟后显示未运行，吊销设备及删号立即使该来源失效。保留作者完整错误域映射，真机截图错误仍显示原中文解释。
3. 部署代理环境下，两台不同客户端经可信代理分别累计鉴权失败次数；非可信来源伪造 X-Real-IP/X-Forwarded-For 不改变计数来源。此轮仅复用现有信任代理配置与解析函数。
4. 监控程序遇到包含合法和非法单条状态的心跳仍收到 200 并同步规则；同规则快速失败/恢复时日志每 60 秒最多一条「截图已恢复」，状态与 `since` 即时更新，不含窗口内容。
5. 浏览器网络面板确认设置页每 10 秒仅读取 rules，不重复读取会话、模型、设备及窗口；首次/手动操作仍完整刷新，隐藏暂停、账号切换取消、404 停止。慢速首次完整加载不被状态轮询取消。
6. 在允许绑定回环端口的环境重新执行默认 `python -m pytest -q`，补齐上述六项既有测试。
