# 复核 第 2 次：返修后核验（2026-10-06）

- **复核方式**：Opus 5.5，2 个视角。只核验第 1 次复核的必须修复是否消除，以及返修顺带的可优化改动有没有引入回归；新发现一律记为可优化。
- **主会话机械验证**（沙箱外）：后端全量 `1755 passed`；tsc、build 通过，lint 25 条警告；已有测试只删除 `test_tts_ws_limits.py`。

## 结论：通过

## media：通过

| 条目 | 已消除 | 证据 |
|---|---|---|
| F1 GIF disposal（必须修复） | 是 | media.py:99/128/142-145 现在只在『源图 info 有 transparency』或『任一重建 RGBA 帧 alpha 最小值<255』时才整段设 disposal=2，不透明动图不再传 disposal。在 $TMPDIR 自造样本，两条路径分别实测：(1) 400×400、64 色噪点背景、10px 块移动、100 帧：输入 220,943 B，chat 和 plaza 都输出 220,943 B（1.000 倍），100/100 帧 RGBA 逐帧一致，总时长 8000/8000 ms；(2) 816×816、300 帧：输入 854,722 B，两路径都是 1.000 倍，300/300 帧一致，单次约 12.6 s。ffmpeg 8.1.2 用 palettegen/paletteuse 生成的不透明 GIF 为 1.085–1.205 倍，逐帧一致。透明 GIF：测试里的三组 8×8 混合 disposal（[2,2,2]、[1,2,3]、[1,3,1]）以及 60 帧精灵动画（disposal 0..3 交替 / 全 1 / 全 2 / 1 与 3 交替），两路径的原始 RGBA 和归一化 RGBA 逐帧全部一致，体积 1.00–2.23 倍，都在 3 倍以内。无点文件残留。复核员说的『只加一个静态透明像素』仍会放大约 32 倍，属于返修单允许的『源图有透明』，交用户决定。 |
| 第2节-1 上传临时原件（启动清扫 / 点文件 404 且未登录 401 / 备份排除） | 是 | 进程内 TestClient 进入 lifespan（未起服务）：只删除了 mtime 超过 1 小时的 .upload_old；新的 .upload_fresh、.upload_ 目录、.upload_ 符号链接、旧 plaza_*、.generated_* 都保留。点文件访问：/uploads/.upload_fresh、sub/../.upload_fresh、%2Eupload_fresh、.upload_dir/inner 四种写法，未登录时 GET 返回 401 并清除 fiona_token；带 Bearer 时 GET 和 HEAD 都返回 404，正文不泄露。普通文件鉴权后 200。DEV 回环匿名访问点文件 401，访问普通文件 200。deploy/fiona-backup.sh 在临时目录实跑（本机 bsdtar 3.5.3），退出码 0；包内只有 plaza_a.png、sub/ok.txt、visible..dots.png，.upload_tmp、.generated_x.png、.hiddendir/、sub/.dot、sub/.hid/ 全部排除。保留期清理：子目录里 2020 年的同名旧文件保留，顶层的旧文件被删。 |
| 第2节-2 广场事件循环排队 / 聊天超时 503 / anyio 取消不忙等 | 是 | 默认线程池设为 3 线程，同时发 8 个真实 GIF 广场上传，期间空操作 to_thread 最大延迟 0.2 ms，8 个全部成功。人为占满两个 _REENCODE_SLOTS 后发聊天图片：10.0 s 后返回 503『服务器繁忙，请稍后再发图片』，目录为空。anyio 任务组在重编码期间取消：墙钟 1.05 s，事件循环线程 thread_time 只有 0.002 s，没有忙等，目录为空。连续两次显式 asyncio cancel：取消后立即查看和 worker 结束后查看，目录都为空（由完成回调兜底清理）。 |
| 第2节-3 内存优化不改输出语义 | 是 | 写了一个按第 0 轮语义的参照实现：始终 exif_transpose，始终 convert 复制，透明判定规则与本轮相同。拿它和现实现对比 91 个用例，输出字节全部相同。用例覆盖 JPEG RGB/L/CMYK、PNG RGB/RGBA/L/LA/P/1/I;16、WebP RGB/RGBA，方向值 无/1/2/3/5/6/8；另有 P+trns、RGB/L tRNS、动画 WebP、不透明和透明 GIF、MPO o=6。8000×5000 PNG 峰值 RSS：现实现 357 MiB，参照 663 MiB，与报告表一致。 |
| 第2节-4 聊天取消孤儿文件清理 | 是 | 用真实的 _save_uploaded_image 和约 1 s 的 GIF 调 chat_service.build_context（只给会话解析和取历史打桩）。0.2 s 时 asyncio task.cancel：取消瞬间目录为空，线程完成后目录仍为空。anyio move_on_after(0.2) 也是：立即返回，循环线程 CPU 0.000 s，线程完成后无残留。chat_service.py 只在调用处改了 shield 加完成回调。 |
| 第2节-7 tRNS 透明 | 是 | RGB 带 tRNS(1,2,3) 两路径输出 mode=RGBA，像素为 [(1,2,3,0),(200,10,10,255)]；L 带 tRNS 9 输出 LA，像素为 [(9,9,9,0),(200,200,200,255)]。91 用例比对中 tRNS 样本也与参照一致。 |
| 第2节-8 清理脚本（失败非 0 / 跳过干净文件 / 权限保持） | 是 | CLI 在临时目录实跑，目录内放：脏 JPEG(0640)、脏 PNG(0604)、管线产出的干净 WebP 和 GIF、损坏 JPEG、带位置的 mp4、.upload_tmp。dry-run 退出码 0，文件不变。第一次 --apply：已处理 3，失败 1，跳过 2，退出码 1；干净 WebP/GIF 的 mtime 不变；脏图权限仍为 640/604，GPS 标记清零；点文件不在处理范围内。删掉坏文件后第二次 --apply：处理 1（只有视频按设计重新 remux），跳过 4，退出码 0。 |
| 第2节-13 断言加强 | 是 | test_client_ip_trust.py:58-60：不受信的 ::ffff:203.0.113.17 断言等于原字符串。test_upload_metadata.py:127-130：MPO 主帧为红、附帧为蓝，断言输出是红色主帧。:522-535 两路径的 JPEG 和 WebP 都断言 save 调用带 (格式, quality=90)。git diff 9061a52 --stat -- backend/tests 仍然只有 test_tts_ws_limits.py 被删。 |
| 回归：GPS/位置清理 | 是 | 带 GPS EXIF、Make、XMP(GPSLatitude)、IPTC、PNG tEXt/iTXt、ICC、方向 6 的 JPEG/PNG/WebP，两路径输出的私有标记数都为 0，getexif() 为空，无 xmp，ICC 保留，方向已转正（40×20 变成 20×40，蓝条到了顶部）。mp4 和 mov 带 location / location-eng / com.apple.quicktime.location.ISO6709 / model / title / handler 标签：ffprobe 只剩 major_brand 等基础标签，原始字节中位置、型号等标记都为 0，H.264+AAC 双轨保留，90° 显示矩阵保留。 |

**可优化**

- 【建议优先】F1 透明触发条件过宽：media.py:99 只要首帧元数据声明了 transparency 就整段设 disposal=2，不管有没有像素真的透明。实测：自造 400×400 噪点 GIF，只在首帧 GCE 声明一个未使用的透明索引（各帧 alpha 全 255），两路径都从 220,943 B 涨到 16,739,099 B（75.8 倍），与 F1 原症状相同。本机腾讯会议 7 个真实 GIF 中有 6 个各帧 alpha 全为 255 却声明了透明：remote_control 2.80 倍、ai_helper_universal 2.24 倍、home_page 1.98 倍；只清掉首帧透明标志（解码逐帧一致）后分别降到 1.15、1.07、1.20 倍。建议删除第 99 行这个元数据条件，只保留第 128 行按像素 alpha 的判定，并补一条『声明了透明但没有透明像素』的体积回归测试。
- 真实透明 GIF 重编码后有轻微色偏：GarageBand Loop.gif 和腾讯会议 ai_helper_guide_tips.gif，按时间对齐后 alpha 完全一致，但 RGB 最大通道差 24–29，平均不超过 2.8。原因是 Pillow 把 RGBA 重新量化成调色板。强制 disposal=2 的结果完全相同，说明第 0 轮就已存在，不是本轮回归。可以考虑在动图帧可行时保留 P 模式和原调色板。
- 备份排除点文件只在 macOS bsdtar 上实测过，本机没有 GNU tar。生产 Linux 上 --exclude='.*' 的匹配语义（no-anchored、wildcards-match-slash）按手册推断一致，建议在目标机跑一次 tar -tzf 核对。
- 已知并已披露：伪装成 .gif 的 APNG（例如 wemeet_app_loading.gif）按 PNG 处理，只留主帧，38 帧变 1 帧，动画丢失。规格只要求 GIF/WebP 保留动画；如果用户会上传 APNG 表情，建议另行评估。

## caps-ops-docs：通过

| 条目 | 已消除 | 证据 |
|---|---|---|
| 返修单 2-5：卡片详情、ASR 在缺密钥检查之后才计数 | 是 | cards.py:38-42 先检查 DASHSCOPE_API_KEY（与 card_detail.py:91 一样不做 strip），缺失时返回同一个 detail_error，然后才调用 check_daily_cap。voice.py:536-540 在 base64、空音频、413、PCM、ffmpeg 这些本地检查全部通过后，先按 qwen_asr.py:156 的语义（做 strip）检查密钥，再计数。工具里剩下的 10MB data URI 检查在路由层到不了：ffmpeg -t 120，WAV 最大约 3.8MB。test_daily_caps.py:254-287 把额度设为 1，用 None、空串、空白三种密钥共 5 例反复请求，calls 始终为空；补回密钥后第 1 次返回 200，第 2 次返回 429，可以证明缺密钥的请求没有计数。 |
| 返修单 2-6：page.tsx 只对带 retry_after 的 429 提示并关闭免提；IP 每分钟 429 维持原状；去句号后再拼接 | 是 | 与 9061a52 相比，前端只多了 9 行，是在两处 `if (data.text)` 之前各加一个 `res.status===429 && "retry_after" in data` 分支。rate_limit.daily_cap_response 返回的 body 带 detail/error/retry_after；slowapi 的 _rate_limit_exceeded_handler（已读 venv 源码）只返回 {error}，没有 retry_after，所以按 IP 每分钟限流的 429 仍走原来的 data.text 分支，不提示也不关免提。免提路径的写法是先 setHandsFree(false)，再 setMicNotice(data.error.replace(/。$/, "") + "，免提已关闭")，与 9061a52 处理麦克风报错的顺序一致；全文件只有 :389 的初始化和 :2072 的开启免提两处会 setMicNotice(null)，没有依赖 handsFree 的 effect 会把提示清掉。免提状态机的其余部分没动（handsFreeRef 的同步、onstop 的守卫、TTS 结束后重新开麦的条件都未改）。ASR 文案「……可以先打字。」去掉末尾句号后再拼接，不会出现「。，」。 |
| 返修单 2-9：tar 退出码为 1 时保留数据库快照、最终仍非 0；find 加 -maxdepth 1 | 是 | 在 $TMPDIR 造了一个 WAL 库，另开连接持有 BEGIN IMMEDIATE 未提交写事务，用 tar 桩（先调真 tar，再 exit 1）跑 deploy/fiona-backup.sh。结果：退出码 1，stderr 有「数据库快照已保存…媒体备份可能不完整」和「备份以失败状态结束」两句；快照 integrity_check=ok，只含已提交的 1,2,3，journal_mode=delete，权限 0600；媒体包已发布且不含点文件（包括子目录里的 .hidden）；顶层 20 天前的 fiona-db-OLD.sqlite3 和 fiona-uploads-OLD.tar.gz 被删，这一步是正控；keep/ 子目录下同名的两个旧文件和 notes.txt 都保留。另做正控：同一目录去掉 -maxdepth 用 find 跑一遍，会命中子目录那两个文件，加上 -maxdepth 1 后零命中。变体：tar 桩直接 exit 1、不生成包时，只发布数据库，退出码 1；tar 返回 2 时什么都不发布，退出码 2；正常运行退出码 0，配对的两份都在。仓库测试 test_migrate_and_backup.py:235/297 覆盖同样的场景。 |
| 返修单 2-10：/health 加可写检查、支持 GET/HEAD、总超时；只读库返回 503、不建库 | 是 | main.py:283 用 os.access(DB_PATH, W_OK) 检查，失败归入 database，且发生在连库之前；:305/:306 分别注册 GET 和 HEAD；:310 用 wait_for 设 3 秒总超时，超时归入 database。在 $TMPDIR 用 init_db 建了临时库，通过 TestClient 实测（不启动服务）：正常时 GET 和 HEAD 都是 200，HEAD 无 body；chmod 0400 后 GET 和 HEAD 都是 503 {failed:[database]}，改回 0600 后恢复 200；库路径不存在时返回 503，目录内容前后一致，没有建库；把 aiosqlite.connect 打桩成阻塞 10 秒，GET 和 HEAD 都在 3.0 秒返回 503 database；带无效 Cookie 访问 GET 和 HEAD 都是 200，不发 Set-Cookie；POST 返回 405。 |
| 返修单 2-11：migrate.py --in-place 打印目标库路径，失败提示分类 | 是 | migrate.py:103-104 在配置检查和迁移之前打印「原库迁移目标：<绝对路径>」。在 $TMPDIR 实测：--in-place 迁移 WAL 旧库，第一行就是路径，退出码 0，迁移后有 5 道迁移；缺 DASHSCOPE_API_KEY 或缺 JWT_SECRET 时退出码 2，提示「…用 --env-file 加载含 DASHSCOPE_API_KEY 和 JWT_SECRET 的服务配置」；库文件 chmod 000 时（副本模式）报 PermissionError，提示「磁盘或 IO 错误…」，退出码 1；只读库加 --in-place 时报 OperationalError（SQLITE_READONLY），同样给 IO 提示，退出码 1；有孤立消息的库报 RuntimeError，提示「迁移失败，请在副本上检查结构和消息归属」，退出码 1；缺库时退出码 2，不建库，也不建上传目录。所有输出都不含行内容。 |
| 返修单 2-12：DEPLOYMENT 等文档与代码一致、命令可照抄、恢复流程对生产上传目录执行 strip、ARCHITECTURE 日期句还原 | 是 | 「回滚与恢复」一节改用 fiona-db-…-PID.sqlite3 和 fiona-uploads-…tar.gz，并补上媒体恢复命令（DEPLOYMENT:557-577）。:343 说明发布前备份 14 天后清理、需另存，子目录不清理。:572-579 在停服状态下，以 sudo -u fiona 对 /var/lib/fiona/uploads 先 dry-run 再 apply，核对退出码和失败数后才启动。我在 $TMPDIR 按这段命令照做：用空的 0600 env 文件加 FIONA_UPLOADS_DIR，dry-run、apply、再 apply 都正常；带 GPS 和方向标签的 JPEG 经清理后 EXIF 为空、方向已转正、权限 0644 保持不变，第二次 apply 两个文件都跳过。:515 规定外部拨测用 GET。:161/:200 在两个 unit 的 [Unit] 加了 StartLimitIntervalSec=300 和 StartLimitBurst=5，:524 解释 systemd 版本差异。:71 写明 0600、只能经后端访问、GIF 连续相同帧合并、3GP/AMR 可能失败。:430 描述的 tar=1 和 -maxdepth 行为与脚本一致。ARCHITECTURE.md 前 6 行与 9061a52 逐字相同，日期句仍是 2026-09-25。CLAUDE、PLAN、README 里的每日上限、health、备份描述都与代码一致。deploy/fiona-backup.sh 在磁盘上是 0755。已有测试的 diff 仍只有 test_tts_ws_limits.py 被删除；git status 35 行，前后不变。 |

**可优化**

- 本视角不覆盖 F1（GIF disposal 体积），F1 是否消除以其他视角为准。
- fiona-backup.sh:91-98：tar 返回 1 时仍会执行保留期清理。如果连续多天都是 tar=1，旧的完整媒体包会被轮换掉，留下的都是可能不完整的包。可以考虑 tar=1 时跳过清理，或者只清理数据库。
- --exclude='.*' 只在 macOS 的 bsdtar 上实测过（本机没有 GNU tar）。GNU tar 默认的非锚定匹配按理会得到同样结果，建议在目标 Linux 机上用 tar -tzf 抽查一次，确认备份不含点文件。
- docs/ARCHITECTURE.md:92 写的是「点文件一律返回 404」，但 2026-10-06 调整鉴权顺序后，代码实际是未登录返回 401、登录后返回 404，措辞需要跟着改。DEPLOYMENT 和 CLAUDE 的写法没有问题。
- PLAN.md:122 有错字：「清掃」应为「清扫」。
- migrate.py:118-124：缺库和缺配置共用一句「数据库不存在或配置不可用」，退出码都是 2。DEPLOYMENT:478 只写了「缺库退出 2」，没写缺配置也返回 2，也没提示运维核对 --in-place 打印的目标路径（:498）。
- DEPLOYMENT:579 正文说「以服务账号执行 find … chmod 0600」，但命令本身没带 sudo -u fiona。用 root 照抄执行也没有坏处，只是文字和命令不一致。
- /health 只检查库文件本身是否可写，不检查所在目录是否可写。WAL 模式需要建 -wal/-shm 文件，如果文件可写而目录只读，/health 仍会报 200。这种情况很少见。

## 主会话处理

可优化第 1 条「GIF 只声明透明索引、没有实际透明像素时仍触发 disposal=2，体积放大约 76 倍；本机真实 GIF 7 个中有 6 个属于这种情况」与第 1 次复核的 F1 是同一缺陷换了触发条件，在真实文件中普遍存在。主会话决定作为第 2 轮小返修修复：去掉元数据条件，只按像素透明度判定，并补体积回归测试。修复后由主会话用复核员的样本和本机真实 GIF 亲自验证。
