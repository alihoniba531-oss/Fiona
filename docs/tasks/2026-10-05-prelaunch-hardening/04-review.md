# 复核 第 1 次：重新上线前加固（2026-10-05）

- **复核方式**：Opus 5.5，4 个独立视角：规格与测试、上传去元数据、每日上限与代理信任、运维。每条「必须修复」由反方核实员亲自复现，尽力推翻。
- **主会话机械验证**：
  - 后端全量 `1691 passed`，零 skip；
  - `compileall` 通过；
  - 前端 tsc、build 通过，lint 25 条警告；
  - B5、B7 零命中；
  - 白名单内文件。
- **主会话真实样本**：
  - 带 GPS、XMP、方向、ICC 的 JPEG：广场、聊天落盘、data URI 三条路径都去除干净，方向转正，ICC 保留；
  - 带位置标签、iPhone 机型、旋转矩阵的 mp4 和 mov：标签清除，旋转保留，无残留临时文件。

## 结论：不通过（1 条必须修复）

| 视角 | 结论 | 必须修复 | 可优化 |
|---|---|---|---|
| spec-and-tests | 不通过 | 1 | 13 |
| media | 不通过 | 3 | 8 |
| caps-and-ip | 通过 | 0 | 7 |
| ops | 通过 | 0 | 9 |

## 必须修复（经反方核实）

### [spec-and-tests] M1：GIF 一律强制 disposal=2，每帧都整幅重写，上传后体积膨胀几十到上百倍（存储/带宽/内存放大，聊天发给模型的 data URI 跟着暴涨）（核实：成立）

- **位置**：backend/utils/media.py:120-124（options["disposal"] = 2，对所有动图 GIF 生效）；聊天路径 media.py:320-327、广场 media.py:284-285、存量脚本 scripts/strip_upload_metadata.py:71 都走同一函数
- **证据**：我在 $TMPDIR 下直接调用函数实测（未改仓库）：(1) 400×400 静态噪点背景（量化 64 色）、100 帧、一个 10px 红块在动，用 Pillow 存成 GIF 是 211 KB，走 _save_uploaded_image 后变成 16,155 KB（76.5 倍），data URI 21.5 MB。(2) 816×816、300 帧（总像素 1.998 亿，在规格上限内）、同类内容的 GIF 是 1.09 MB，没超广场 5 MB 上限，走 _save_plaza_upload 后落盘 249.7 MB，耗时 10.8 s，峰值内存 1.34 GB。HEAD 原样保存只占 1.09 MB。对照组：同样重建出来的帧，存 GIF 时不传 disposal 或传 disposal=1，输出 211 KB，和原图一样大；只有 disposal=2 是 16,155 KB。原因是 Pillow 遇到 disposal=2、不透明的帧，每帧都会写整幅画面（我实测输出各帧 tile 都是整幅 (0,0,W,H)），帧间差分全丢了。动画 WebP 不受影响（943 KB 变 1,147 KB）。后果：plaza/post 没有任何限流，登录用户每 10 秒左右就能用 1 MB 的上传塞进约 250 MB 磁盘，看信息流的人也得下载这个大文件；聊天路径会把几十到上百 MB 的 base64 一起放进内存并发给视觉模型（Qwen-VL 对 base64 图有大小上限，原来 211 KB 能正常识别的 GIF，现在很可能被拒，这一点是推断，没有真调模型）。规格说「输出可以比输入大」，但这种放大是 disposal 的实现选择造成的，不是去元数据本身的代价。现有测试只验证透明 GIF 逐帧 RGBA 一致，没有任何断言约束输出体积。
- **修法提示**：只在确实需要擦除的地方用 disposal=2：源图带透明，或者某帧把上一帧不透明的像素变成透明的时候，对上一帧设 2；其余情况不传 disposal（或用 1），让 Pillow 自己做帧间差分裁剪。保留现有三组混合 disposal 的透明 GIF 逐帧 RGBA 一致测试，另加回归测试：静态复杂背景加小块运动的不透明 GIF，两条路径的输出体积都不超过输入的约 2 倍。
- **反方核实**：核实结论：证据成立，没能推翻。仍算「必须修复」，但严重程度有几处说重了，修复建议也不完整。

【复现结果】只在 $TMPDIR 下直接调用函数，没改仓库，git status 前后都是 30 行。
1. 400×400、100 帧、64 色噪点背景加一个 10px 小块在动：输入 213KB，_strip_image_metadata 输出 16,345KB，放大 76.6 倍，和原报告的数字一致。各帧 tile 都是整幅 (0,0,400,400)。对照组用同样重建出来的帧：不传 disposal 是 213KB，disposal=1 是 213KB，disposal=2 是 16,345KB。
2. 原因已在 Pillow 12.3 源码中确认（GifImagePlugin._write_multiple_frames）：上一帧 disposal==2 且没有透明色时，`bbox = (0, 0) + im_frame.size`，帧间差分裁剪被整个跳过。
3. 聊天路径：816×816、300 帧同类内容，输入 0.81MB（base64 后 1.08MB，没超 5MB 上限）。_save_uploaded_image 落盘 198.9MB，返回的 data URI 有 265MB，耗时 11.7s。这个字符串之后在 stream_image 里还会被切片、拼接、JSON 序列化，在内存里存在好几份。HEAD 原样返回，只有约 1MB。
4. plaza/post 确实没挂 @limiter.limit。main.py:113 写明不设全局 default_limits，只有 chat.py:98 挂了 30/minute。前端两条路径都把 GIF 原样上传，不在浏览器里压缩。

【驳不倒，但要更正的地方】
a. 「几十到上百倍」是人造的最坏情况。我拿本机的真实 GIF 测了一遍：
   - Claude.app、GarageBand 里的 16 个带透明的真实 GIF：输出只有输入的 0.2 到 0.9 倍，不膨胀。
   - 不透明的真实录屏，截到 300 帧和 2 亿像素上限以内：python-envs 210 帧 2.6MB 变 14MB（5.4 倍），tqdm 300 帧 673KB 变 4.8MB（7.1 倍），voc-demo 2.4 倍。这三个的输入都是 Pillow 重存过的版本。按每帧折算、跟原始优化编码器比，大约是 11 到 28 倍。
   所以良性用户的受害面集中在不透明的录屏和静态背景动图，典型放大是 5 到 30 倍，不是上百倍。
b. 规格 02-spec.md:73 明写「重编码后输出可以比输入大，不另设输出大小上限」，所以这条不违反任何规格硬规则。它要么归「行为错误」：相对 HEAD 的回归，起因是一个没必要的实现选择；要么归资源耗尽类的安全问题。
c. fix_hint 的第一种写法「源图带透明就用 disposal=2」堵不住恶意构造。我实测：同一噪点背景，只加一个静态透明像素，现有实现照样输出 16,345KB，按这种写法修了也一样大。
   按帧判断的写法（只给「下一帧把不透明像素变透明」的帧设 2）能处理这个样本，但攻击者让某个像素每帧在透明和不透明之间来回切，每帧都会被设成 2，又回到整幅重写。
   所以拒绝服务的放大只靠改 disposal 修不完，还需要 plaza/post 限流或输出上限。规格明确不设输出上限，限流也不在这次的白名单内，这两点要升级给用户拍板，不能算在这一条的修复范围里。
d. 「Qwen-VL 拒收大 base64」没核实到。没查到官方的大小限制，也没确认 qwen-vl-max 支不支持 GIF，只能算推断。

【为什么仍算必须修复】
- 不需要任何特殊构造，一个普通的不透明 GIF 就能把 1MB 放大成约 200MB 的磁盘文件和 265MB 的 data URI，聊天路径每个请求要多占上 GB 内存。
- 良性用户的录屏类 GIF 会稳定膨胀 5 到 30 倍，广场看帖的人要下载的流量也跟着涨。
- 这些都是本次改动相对 HEAD 引入的回归。修起来很便宜：图里没有透明像素被擦除时，不传 disposal（让 Pillow 做帧间差分），或者按帧设置。

建议：保留现有三组混合 disposal 的透明 GIF 逐帧 RGBA 一致测试；另加不透明静态背景加小块运动的体积回归断言，两条路径都要测。恶意构造的透明来回切换导致的放大，另列一条交用户决定：要不要加限流或输出上限。

### [media] M1：聊天图片在调用者取消后留下孤儿文件，不满足规格 2.1 第 3 点「任何失败（包括 CancelledError）都要删掉临时文件和半成品」（核实：降为可优化）

- **位置**：backend/services/chat_service.py:460；backend/utils/media.py:295-343
- **证据**：实测（$TMPDIR/fiona-review-21/cancel.py）：按 chat_service.py:460 的写法创建任务 asyncio.to_thread(media._save_uploaded_image, b64)，0.3 秒后 cancel()。调用方立即收到 CancelledError，但工作线程继续执行 media.py:331-335（写临时文件后 os.replace）。6 秒后上传目录多出 ['ac9e6e8781af4c89a0a60f657da497fc.webp']。同样的样本走广场路径并取消，没有任何残留。这个文件既不在 messages 表里，也不在 upload_cleanup_queue 里，所以删号流程和定期清理都删不到。任何登录用户只要知道路径都能读取（聊天图不在 main.py:181 的私有前缀里）。这与删号会清理上传文件的承诺相违背。实施方报告第 5 节第 1 条和 CLAUDE.md 也承认这一点没有落实。新测试 test_image_atomic_replace_failure_removes_temporaries 只在线程内部的 os.replace 里抛 CancelledError，没有覆盖调用方被取消这一真实情形。
- **修法提示**：最小修法是在 chat_service.py 中保留原来的 to_thread 调用，套一层 shield，再加完成回调。下面这段约 8 行，要先请作者拍板扩大该文件的白名单：
    upload = asyncio.ensure_future(asyncio.to_thread(_save_uploaded_image, req.image_base64))
    try:
        image_path, validated_image = await asyncio.shield(upload)
    except asyncio.CancelledError:
        def _discard(t):
            if not t.cancelled() and t.exception() is None:
                delete_uploaded_files([t.result()[0]])
        upload.add_done_callback(_discard)
        raise
这样函数名仍在调用时按名查找，测试对 chat._save_uploaded_image 的打桩依然生效。delete_uploaded_files 在第 49 行已经导入。另外不进入循环等待，在 anyio 的取消下也不会空转。还要补一条测试：线程运行期间取消 build_context，等线程结束后断言上传目录为空。
- **反方核实**：我复现了这个现象，结论是问题真实存在，但不该列为「必须修复」，建议降为「可优化」，或作为规格冲突交作者拍板。

一、现象成立。我在 $TMPDIR 写了脚本直接调用 chat_service.build_context，只给会话解析、取历史和 save_message 打桩，_save_uploaded_image 和 media.UPLOADS_DIR 用的是真实实现。在 to_thread 等待期间 cancel，取消瞬间上传目录是空的，6 秒后多出一个 32 位十六进制命名的 .png。这与 M1 的证据一致。

二、规格并不要求这样修，而且规格明文规定了现在这种写法。
- 第 2.1 节白名单规定 chat_service.py「只改调用 _save_uploaded_image 那一行」，并且逐字给出了替换文本 `await asyncio.to_thread(_save_uploaded_image, req.image_base64)`。实施方照抄了这一行，diff 也确实只有 chat_service.py:460 这一行变动。
- 第 3 点「任何失败（包括 CancelledError）都要删掉临时文件和半成品」，针对的是写盘过程中的点号开头临时文件和写了一半的输出。M1 里的孤儿文件是线程完整、成功写完并原子改名的最终文件，在 _save_uploaded_image 看来并没有发生失败。工作线程里根本收不到 CancelledError。
- 要修就得扩白名单，这属于作者拍板的事。fix_hint 自己也写了「要先请作者拍板」。实施方已在 03-report 第 5 节第 1 条和 CLAUDE.md:79 如实上报，没有隐瞒，也没有越权。

三、不是本次改动引入的新问题，而且 fix_hint 也堵不全。chat_service.py:476-480 这段从基线就没改过：同步保存图片之后，下一步是 `await save_message(...)`。save_message 走 aiosqlite，有 BEGIN IMMEDIATE，忙等最长可到 busy timeout，中间有多个 await。我用同一个脚本在线程跑完、save_message 还在等待时 cancel，图片照样成了孤儿，取消前后目录里都是同一个文件。所以基线 9061a52 本来就有这个窗口，现在只是多了一个长度相近的窗口。广场路径也一样：routers/plaza.py:97-98 在 _save_plaza_upload 返回之后、`await save_post` 期间被取消，也会留下孤儿，因此 M1 说的「广场无残留」只覆盖了媒体函数内部。按 fix_hint 只给 to_thread 套 shield，save_message 那段窗口仍然会产生同样的孤儿。真要修，应把「存图加写消息」整段做成取消安全，这超出了本单的白名单。

四、生产环境里几乎触发不到。build_context 运行在 routers/chat.py:154 的普通处理函数里，在 StreamingResponse 之前，而不是在流式生成器里。我核对了本机装的版本：uvicorn 0.47 客户端断开时只标记断开，不取消任务；Starlette 1.3.1 的 BaseHTTPMiddleware（main.py:174）在响应开始前也不会因为断开而取消下游。uvicorn 只有在设置了 timeout_graceful_shutdown 时才会取消任务（server.py:297），而 run.py:10 没有设置。systemd 发 SIGTERM 时，进程会等待在途请求完成，超时后直接 SIGKILL，这种情况基线同样会留下孤儿。剩下唯一能触发的是连发两次信号强制退出的那一两秒。

五、实际伤害很小。孤儿文件已经去掉了元数据（_strip_image_metadata 在写盘之前执行），文件名是 uuid4 十六进制，约 122 位随机，而且请求被取消，这个路径从未返回给任何客户端。所以「知道路径的登录用户都能读」在现实中利用不了。实际影响只有两点：极少数情况下，用户自己的照片在删号后仍留在磁盘上；以及少量磁盘占用。这与基线已有的 save_message 窗口性质相同。

建议：归入「可优化 / 交作者拍板」。如果作者决定修，应把 chat_service.py:460-480 整段（存图到 save_message 提交）和 plaza.py:97-98 一起做成取消安全，并补一条测试：分别在线程运行期间和 save_message 等待期间取消，断言上传目录为空。不要只套 to_thread 这一处。

### [media] M2：重编码的内存放大很严重：2 个槽位的信号量达不到规格「防止并发上传占满内存」的目的（核实：降为可优化）

- **位置**：backend/utils/media.py:72-131（frames 列表 :91/:113 一次留住全部解码帧；exif_transpose :104、convert :110、Image.new 加 paste :111-112 各复制一份整图；WebP 有损编码 :115-126）；backend/routers/plaza.py:83（/plaza/post 没有任何限流）
- **证据**：每个用例都在单独进程里测峰值 RSS（基线约 55MB），全部在现有上限之内：
- 15KB 的动画 WebP（300 帧，816×816，无损纯色）：峰值 895MB；
- 677KB 的 GIF（300 帧，816×816）：1089MB，耗时 3.3 秒；
- 165KB 的 8000×5000 PNG：696MB；
- 1.19MB 的 6000×6000 无损 WebP（重复噪声块）：峰值 1858MB，CPU 7.5 秒，输出 28.7MB（放大 24 倍），聊天路径的 data URI 有 3800 万字符；
- 3 个 GIF 并发上传：信号量确实只放 2 个同时跑，但峰值 2122MB。
也就是说，任何登录用户用 15KB 到 1.2MB 的文件、不限次数（广场发帖不限流），就能让进程反复冲到约 2–3.7GB，小内存机器上会被 OOM 杀掉。进程被 SIGKILL 时 finally 不会执行，上传目录里会留下带 GPS 的 .upload_* 原件，见 O2。HEAD 版本只调用 verify()，不做全量解码，没有这个问题。
- **修法提示**：1. 准入按字节预算，不按次数：解码前就能算出帧数×画布宽×高×通道数，用加权预算（例如在途总量不超过 512MB）或单独的大图槽位；具体数字需要作者拍板。
2. 及时释放中间图像：没有方向标签时跳过 exif_transpose 的复制；convert 和 paste 之后立即 close 上一份。动图帧在可能的情况下保留 P 模式，或者改成逐帧流式写出。
3. 给 /plaza/post 加按账号或按 IP 的限流。
4. 考虑给聊天发往模型的 data URI 设置上限，或另做一份缩小版。
- **反方核实**：现象属实，但它不是实现方违反规格，主要是规格自己定的上限带来的，所以只能算「可优化 / 交作者拍板」，不够「必须修复」。

一、数字能复现。每个用例单独起一个进程，用 ru_maxrss 测峰值，基线约 52MB。文件放在 $TMPDIR/m2check，我自己生成：
- 15KB 的动画 WebP（300 帧，816×816）：888MB；
- 677KB 的 GIF（300 帧，816×816）：1087MB，耗时 3.4 秒；
- 127KB 的 8000×5000 PNG：694MB；
- 6000×6000 的 WebP：1849MB，耗时 8.1 秒，输出 28.7MB。
和对方的数字一致。

二、峰值的大头是规格要求的，任何符合规格的实现都躲不掉。我写了一个「最省内存」的对照版：只解码一次，不做 exif_transpose 的复制，模式相同时不 convert，新建图像再 paste，然后保存。在同一台机器上测：
- 动画 WebP：882MB，实现版 888MB；
- GIF：1095MB，实现版 1087MB；
- PNG：374MB，实现版 694MB；
- 大 WebP：1560MB，实现版 1849MB。
动图的情况下，可避免的部分几乎为零。原因是规格 §2.1-1 明确允许「帧数 ≤300，且帧数×宽×高 ≤2 亿像素」，按 RGB 或 RGBA 算，单单留住帧就要 600–800MB。而且 Pillow 的 save_all 必须拿到整个 append_images 列表，GIF 写出时也会把全部帧留在 im_frames 里，没法流式写出。
大单帧图的情况下，规格要求保留 4000 万像素上限，并且 webp 要原样转成 webp、quality=90，libwebp 光解码就到 629MB。
实现方多出来的部分（media.py:104 的 exif_transpose 复制，:110 的 convert 复制），只在单帧大图上多出约 290–320MB，属于优化项。

三、信号量按规格实现了，也确实起作用。media.py:51 是 BoundedSemaphore(2)，:74 和 :136 都包住了重编码。三个 GIF 并发时峰值 1847MB；把信号量换成 100 个槽位后是 2806MB。规格 §2.1-1 只要求「同时最多 2 个重编码」，没规定内存预算。「2 个槽位 × 每个任务约 1GB」正是规格所设参数的必然结果。对方的修复建议也写了「具体数字需要作者拍板」，这说明它是规格层面的决策，不是实现缺陷。

四、其余几条论据都不支持「必须修复」：
- data URI 有 3800 万字符：规格明写「重编码后输出可以比输入大，不另设输出大小上限」。
- /plaza/post 不限流：plaza.py 没出现在 diff 里，HEAD 就是这样，也不在本单白名单和要求之内。
- 拿 HEAD 只调用 verify() 来对比不公平：S8 本身就要求全量解码再重编码。
- OOM 之后留下 .upload_* 原件：要先被 OOM 杀掉才会发生，而文档没有规定服务器内存。这条应该归到 O2 去单独评估。

建议：降为「可优化」，并列给作者拍板：
- 是否把动图的 2 亿像素上限或大图槽位调低；
- 是否改成按像素加权准入；
- 是否给广场发帖加限流；
- 单帧路径去掉多余的复制（约省 300MB）。

### [media] M3：信号量在默认线程池的线程里阻塞等待，会把全应用的 asyncio.to_thread 都饿死，聊天流式输出跟着卡住（核实：降为可优化）

- **位置**：backend/utils/media.py:74、:136（with _REENCODE_SLOTS 写在工作线程内部）；:184（广场用默认执行器）；backend/services/chat_service.py:460
- **证据**：实测（$TMPDIR/fiona-review-21/starve.py）：把默认执行器设成 6 个线程，等同于 2 vCPU 主机上 min(32, cpu+4) 的取值。同时提交 8 个广场上传（每个 15KB 的动画 WebP）后，一个空操作 asyncio.to_thread(lambda: None) 等了 5.73 秒，平时是 0.000 秒。原因是 2 个线程在重编码，其余 4 个线程卡在 BoundedSemaphore 上，把池子占满了。共用这个池的有：聊天流式逐块读取 asyncio.to_thread(next, iterator, …)（chat_service.py:125）、SQLite 槽位状态、ASR 的 to_thread、各个 matcher/extractor 的模型调用，以及 tts.py:121 的 run_in_executor(None, …)。广场发帖不限流，一个用户就能让所有人的聊天流停顿几十秒；以 M2 中 7.5 秒一张的样本算，8 张排队约停 30 秒。
- **修法提示**：广场路径：在派发到线程之前，先在事件循环上拿 asyncio.Semaphore(2)，或改用专用的 ThreadPoolExecutor(max_workers=2) 配合 loop.run_in_executor，排队就不会占用默认池。聊天路径受规格限定必须用 to_thread：在 _save_uploaded_image 里改成 _REENCODE_SLOTS.acquire(timeout=几秒)，超时返回 503「服务器繁忙」，不要无限期占着默认线程。同时给 /plaza/post 加限流。
- **反方核实**：机制确实存在，但原证据的前提是错的，伤害被明显夸大。也不违反规格，应降为「可优化」。

1. 线程池大小用错了。生产环境的默认执行器不是 min(32, cpu+4)=6。backend/main.py:91-93 在 lifespan 里执行 set_default_executor(ThreadPoolExecutor(max_workers=_default_pool_workers()))，main.py:62-67 的默认值是 32（FIONA_DEFAULT_POOL_WORKERS）。DEPLOYMENT.md:120 和 .env.example:54 写明这 32 个线程「留给聊天槽位和流读取」，这是基线 9061a52 就有的。原 starve.py 手动把执行器改成 6 个线程，不代表应用的真实配置。

2. 我按生产配置复测（$TMPDIR/fiona-m3-counter/starve32.py：32 线程，同样用 webp300ll.webp 并发调 _save_plaza_upload，单张约 3 秒）：
   - 1 张：探针等待 0.00s；
   - 8 张（原证据的场景）：0.00s，原报告的 5.73s 和「8 张停约 30 秒」在真实配置下复现不出来；
   - 33 张：3.00s；
   - 40 张：15.65s。
   也就是说，要让池子饿死，得同时有至少 33 个图片上传在途。用户正常在界面上一张张发帖触发不了，只有持邀请码的已登录账号写脚本并发刷才会出现。而且每个成功的上传都会生成一条带 owner 的公开广场帖。

3. 不违反规格。02-spec 第 2.1 节第 1 条明确要求：广场路径用 asyncio.to_thread；聊天路径改成 await asyncio.to_thread(_save_uploaded_image, ...)；再加一个进程级的有界信号量。在聊天路径上，信号量只能在工作线程里等，这是规格设计本身决定的。fix_hint 里给聊天路径加「超时返回 503」是规格之外的新行为。另外对聊天路径来说，改动前 _save_uploaded_image 是同步跑在事件循环上的，会阻塞整个服务，现在比改动前好。

4. 剩下成立的部分：
   - 广场路径在工作线程里阻塞等 threading.BoundedSemaphore（media.py:74/136/184），排队的上传会占用默认池线程；
   - 这和 utils/slow_pool.py 的设计意图相反：它特意在事件循环上用 asyncio 信号量排队，好让慢任务不占线程和执行器队列；
   - /plaza/post（routers/plaza.py:83）没有限流，是原有缺口。
   所以有一个「已登录用户恶意高并发上传，能让所有人的聊天流停十几秒以上」的新拒绝服务途径。建议作为加固项：广场路径在派发到线程之前，先在事件循环上拿一个 asyncio 层的闸门，同时给 /plaza/post 加限流。它不满足「违反规格硬规则、普通使用下行为错误、数据丢失」中的任何一条。

## 可优化

- [spec-and-tests] **O1 按规格上限的动图，单次重编码约占 1.1–1.3 GB 内存；信号量在执行器线程里阻塞等待，会占满默认线程池**（backend/utils/media.py:51、74-113（frames 列表把所有帧都按 RGB/RGBA 整幅留在内存里；threading.BoundedSemaphore 在 to_thread 的工作线程里才去 acquire）；routers/plaza.py:83（plaza/post 没有限流））：实测：一个只有 23 KB 的 816×816×300 帧 GIF，新进程处理峰值约 1.09 GB、耗时 3.4 s；噪点版 1.09 MB 的 GIF 峰值 1.34 GB。两个并发槽位叠加约 2.2–2.7 GB，小内存 VPS 可能被 OOM 杀掉。HEAD 只校验首帧，没有这部分开销。另外，排队的上传在默认线程池（main.py 设为 32 个线程，聊天流式读取 to_thread(next, iterator) 也用它）里阻塞等信号量；广场又没有限流，大量并发上传会让所有用户的聊天流卡住。2 亿像素是规格定的数字，所以归可优化，但规格写信号量的目的就是「防止占满内存」。建议主会话评估：帧按 P 模式保存，或者用生成器流式写出；广场路径改在事件循环一侧用 asyncio 信号量限流后再派发线程；或者调低总像素预算。
- [spec-and-tests] **O2 前端只按 429 状态判断，按 IP 每分钟限流的 429 也会关掉免提，并显示英文提示**（frontend/app/page.tsx:713-716、806-810）：slowapi 的 _rate_limit_exceeded_handler 返回 429 和 {"error": "Rate limit exceeded: 10 per 1 minute"}（/asr/recognize 挂了 10/minute 按 IP）。这个改动之后，同一出口 IP（共用 NAT 或运营商级 NAT）的用户撞上每分钟限流时，免提会被关掉，并显示「Rate limit exceeded: 10 per 1 minute，免提已关闭」；原来只是静默丢掉这一句。字面上符合规格「响应状态是 429」，但很可能不是规格本意。建议同时检查 body 里有 retry_after 或 detail，只对每日上限关闭免提。
- [spec-and-tests] **O3 聊天路径：调用方在等待线程期间取消时，留下没人引用的完整图片文件（已知，实施方已上报）**（backend/services/chat_service.py:460；backend/utils/media.py:295-345）：实施方在未决问题 #1 已如实上报：规格要求这里只能改一行，和「CancelledError 也要清理」互相冲突。我查了 Starlette 的 BaseHTTPMiddleware：客户端断开时不会主动取消正在执行的处理函数，实际主要在关停时才会触发，概率低。但一旦发生，文件没有消息引用，删号也清不掉，又没有全目录孤儿扫描。需要主会话或用户拍板，是否允许在调用端加 shield/清理逻辑。
- [spec-and-tests] **O4 带 tRNS 色键透明的 RGB/L 模式 PNG 重编码后丢失透明**（backend/utils/media.py:105-114（Image.new 重建后只传 icc_profile））：实测：RGB 模式 PNG 用 transparency=(255,0,255) 保存，源图 info.transparency=(255,0,255)，经聊天路径输出后变成 None，背景色直接露出来。P 模式已转 RGBA，没有这个问题。这类图少见，但属于和元数据无关的视觉退化。建议对 RGB/L 模式带 transparency 的图转 RGBA/LA，或显式传 transparency，它不属于元数据。
- [spec-and-tests] **O5 连续相同帧会被 Pillow 合并，「帧数不变」不严格成立**（backend/utils/media.py:115-127（GIF/WebP save_all））：实测：用 ffmpeg 生成的 7 帧完全相同、每帧 100ms 的 GIF，输出变成 1 帧 700ms。播放时序等价，看不出差别，但规格写的是「动图帧数和时长不变」，测试样本每帧颜色都不同，覆盖不到这种情况。建议在报告或文档里说明，或在测试里接受合并后总时长不变。
- [spec-and-tests] **O6 官方每日计数放在了冲突检查之前（偏离规格 :472/:473 的位置），并发测试依赖这个顺序**（backend/exchange_store.py:473-480；tests/test_daily_caps.py:271-291）：实施方已在未决问题 #4 申报。结果是：已达上限、并且还有进行中交流的账号，拿到的是 429 而不是 409。并发测试故意让赢家保持 running，只有在这个顺序下才能得到 [201, 429]。需要用户确认这个优先级。
- [spec-and-tests] **O7 B5 零命中靠测试里拼接字符串绕过 grep**（backend/tests/test_tts_ws_removed.py:10、17（"/tts/" + "ws"））：规格既要求零命中，又要求测试去连 /tts/ws，两者本来冲突，实施方已在未决问题 #13 申报，行为上无害。但以后的 grep 门禁看不到这类引用。我另外用 git grep --untracked 复查，未跟踪文件也是零命中；本机路径 /Users 在所有改动和新增文件里同样零命中。
- [spec-and-tests] **O8 部署手册里回滚一节仍用旧备份命名，并且仍以 root 运行 sqlite3，和新的「以 fiona 运行」约定不一致**（docs/DEPLOYMENT.md:540、547（pre-rollback 的 .backup 用 root 跑；示例文件名仍是 fiona-YYYYMMDD-HHMMSS.db）；:326-333（日常发布依赖已部署代码里有 deploy/fiona-backup.sh））：新脚本产出的文件名是 fiona-db-YYYYMMDDTHHMMSSZ-PID.sqlite3 和 fiona-uploads-…tar.gz；恢复演练一节已改成新名字，回滚一节没改。另外，从旧版本做第一次升级时，git pull 之前 /opt/fiona/deploy/ 还不存在，备份那一步会直接失败。目前服务器是全新重装，所以风险低。
- [spec-and-tests] **O9 卡片详情在缺密钥这种本地失败时也计数**（backend/routers/cards.py:37-39；tools/card_detail.py:91-93）：缺 DASHSCOPE_API_KEY 时，card_detail 在本地直接返回错误，不调用模型，但计数已经扣了。热点展开把同样的检查提前了，卡片没有。规格只点名了 asr/hot，但原则写的是「所有本地校验之后」。
- [spec-and-tests] **O10 备份脚本的保留清理会递归进入子目录**（deploy/fiona-backup.sh:72-73）：find 没有加 -maxdepth 1。运维在备份目录下建的子目录（比如异地同步的暂存目录）里，只要文件名符合 fiona-db-*.sqlite3 或 fiona-uploads-*.tar.gz 并且过了保留期，也会被删。GNU 和 BSD 的 find 都支持 -maxdepth。
- [spec-and-tests] **O11 存量清理脚本和测试的小缺口**（backend/scripts/strip_upload_metadata.py:66-73；tests/test_upload_metadata.py:123-124）：(a) --apply 不判断文件是否已经清理过，重复运行时 JPEG 会以 q90 反复重编码，画质逐代下降；如果有人对已含新上传的生产目录执行，也会这样。(b) MPO 测试只断言 n_frames==1 和格式是 JPEG，没有断言留下的是主帧（红色），而不是附属帧（蓝色）。(c) 没有测试断言 JPEG/WebP 显式传了 quality=90。
- [spec-and-tests] **O12 上传文件权限从 0644 变成 0600（mkstemp 加 os.replace）**（backend/utils/media.py:158-161）：实测落盘文件 mode 是 0o100600。按当前拓扑，/uploads 由 FastAPI（同一账号）提供，不受影响；如果以后改成 Nginx alias 直接出文件，就会 403。实施方在未决问题 #7 提到了 mkstemp 0600，但文档没写。
- [spec-and-tests] **O13 ARCHITECTURE.md 文首的日期整体改成 2026-10-05**（docs/ARCHITECTURE.md:3）：规格要求「只改与本单直接相关的句子」。这句声明全文描述的是 10-05 的代码，但其余章节没有重新核对，有点超出范围，属于轻微问题。
- [media] **O1 在 anyio 取消作用域下，_process_upload_off_loop 会忙等并吃满事件循环线程**（backend/utils/media.py:181-201）：实测（anyio_spin.py）：在 anyio task group 里跑广场上传，0.3 秒后执行 cancel_scope.cancel()。墙钟 2.98 秒，事件循环线程 CPU 却占了 2.38 秒；同样的样本用普通 asyncio cancel，CPU 是 0.00 秒。原因是 anyio 的取消是持续触发的，每次 await asyncio.shield(worker) 都立刻被取消，while 循环就空转到工作线程结束（视频最长 30 秒）。Starlette 1.3.1 的 BaseHTTPMiddleware（require_auth）就在 anyio task group 里运行应用，主要在关停或重启时触发。项目里已有现成做法：chat_service.py:470/623/644 都是 anyio.CancelScope(shield=True) 加 asyncio.shield。建议照搬，用 with anyio.CancelScope(shield=True) 包住这段等待。
- [media] **O2 .upload_* 临时原件（含 GPS）没有兜底清理：备份会打包它，已登录用户按文件名能读到，清理脚本也会跳过**（backend/utils/media.py:158-161；backend/main.py:181；deploy/fiona-backup.sh:64；backend/scripts/strip_upload_metadata.py:30）：source 临时文件是用户上传的原始字节，带 GPS，处理期间（最长 30 秒）会一直留在上传目录里；进程被 OOM 或 SIGKILL 杀掉时（见 M2），它就永久残留：
- 启动时不清扫；
- strip 脚本按规格跳过点开头的文件；
- fiona-backup.sh:64 的 tar -czhf 会把整个目录（包括点文件）打包进备份，04:00 恰好有上传在处理时也会打进去；
- StaticFiles 不过滤点文件，main.py:181 只把 .generated_/.reference_ 当私有，已登录用户知道文件名就能读（名字有 8 位随机串，实际猜不中）。
建议：启动时清扫过期的 .upload_*；把 .upload_ 加进私有或拒绝访问的前缀；备份 tar 加 --exclude='.upload_*'。
- [media] **O3 按手册做生产恢复不会去除旧图元数据：strip 脚本只在演练目录里跑**（docs/DEPLOYMENT.md:494-501、:543-552）：手册只在 "$rehearsal/uploads" 上执行 --apply，又写明「不要把演练目录直接替换生产目录」。真正恢复的那一步（:552「再恢复同一时间点的 /var/lib/fiona/uploads/ 备份，重启服务」）没有对生产上传目录执行 strip。照做的话，旧照片的 GPS 会原样回到线上，所有登录用户都能下载，S8 这个问题在恢复场景下没有闭环。建议补一步：启动服务前，以 fiona 账号对生产上传目录执行 --dry-run 再 --apply，并核对失败数。必须在停服期间做，否则 os.replace 可能把服务刚删掉的文件写回来。
- [media] **O4 strip 脚本的若干细节：有失败仍退出 0、重复执行会累积有损重编码、权限变成 0600 且属主可能变化**（backend/scripts/strip_upload_metadata.py:70-83；backend/utils/media.py:159）：实测 --apply 的输出是「已处理：3；失败：2」，退出码 0。自动化流程靠退出码判断时，会漏掉失败。改写后的文件权限从 0644 变成 0600（mkstemp 的默认权限）；用 root 运行时属主也会变成 root（演练步骤有 chown 兜底）。新上传的文件现在也都是 0600，以前是 0644，所以不要让后端以外的静态服务直接读上传目录。每执行一次 --apply，JPEG 和 WebP 都会再按 q90 有损编码一遍。建议：failed>0 时返回非 0；已经没有元数据的文件跳过；保留原文件的权限位。
- [media] **O5 视频码流内的 SEI user data 原样保留**（backend/utils/media.py:141-149）：用 -c copy remux 后，输出文件里仍然能搜到 x264 的 SEI 文本，以 'x264 - core 165 …' 开头。容器层的标签、mvhd/tkhd/mdhd 的创建时间、字幕轨、数据轨、章节都已清掉（实测）。但有些行车记录仪和无人机会把 GPS 或时间写进 H.264/HEVC 的 SEI，这部分会原样保留。规格没要求处理；需要的话可以评估 -bsf:v filter_units=remove_types=6（H.264）或 HEVC 的 39/40，要先测兼容性。
- [media] **O6 缺少 EOI 或被截断的 JPEG 现在会被拒绝（HEAD 版本会接受）**（backend/utils/media.py:102）：实测：一张去掉末尾 FFD9 的 JPEG，HEAD 的 _validate_decodable_image 接受，新代码返回 400「图片内容损坏或尺寸过大」。截掉 10% 的 JPEG，HEAD 也接受。原因是全量解码会对截断报错。文案没变，但对缺 EOI 这类边缘手机文件是一处兼容性回退，影响不大。
- [media] **O7 GIF 中相同的连续帧会被 Pillow 合并，帧数随之变化**（backend/utils/media.py:117-126）：手工构造一个 4 帧 GIF，帧时长 [100,200,300,400]，第 2、3 帧完全相同。输出变成 3 帧 [100,500,400]：总时长和观感都不变，但和规格「动图帧数和时长不变」的字面不一致。这是 Pillow GIF 编码器的行为，记录下来即可。
- [media] **O8 3GP 输入一律走 -f mp4：老机型的 AMR 音轨或 H.263 可能被拒（未验证）**（backend/utils/media.py:140、:149）：规格写死 3gp 走 -f mp4。mp4 封装器一般不接受 AMR-NB，老机型的 3GP 很可能直接得到 400「请转成 MP4」。本机 ffmpeg 没有 AMR 编码器，无法构造样本，所以没验证。H.264 加 AAC 的 3gp 实测能转成 .mp4。如果确实有影响，可以评估改用 -f 3gp，或者在文档里写明。
- [caps-and-ip] **O1 卡片详情和语音识别在「缺密钥」这道本地检查之前就计数了，报告没有把这一点列进未决问题**（backend/routers/cards.py:37（计数）对照 backend/tools/card_detail.py:91-93；backend/routers/voice.py:536（计数）对照 backend/qwen_asr.py:156-158）：cards.py:37 在调用 card_detail 之前就执行 check_daily_cap。card_detail 内部第 91-93 行发现 DASHSCOPE_API_KEY 为空时直接返回 detail_error，不调用模型，但这次请求已经计数。ASR 也一样：voice.py:536 计数之后，asr_recognize 在 156-158 行发现缺密钥才返回。热点展开的路由（hot.py:33-34）专门把同样的缺密钥检查提到了计数之前，卡片和 ASR 却没有这样做。规格 2.3.4 的总则是「计数点必须放在所有本地校验之后、调用模型之前」。卡片和 ASR 的子条目没有点名缺密钥，所以算不算违规有争议；报告第 51 行写的是「本地参数校验后计数」，未决问题里没提这件事。实际影响很小：只在服务器漏配密钥时发生，而且计数在内存里，重启会清零。如果按 2.3.4 从严解读，可以升为必须修复，做法是照 hot.py 那样在路由里先检查密钥再计数。
- [caps-and-ip] **O2 免提超限提示的标点重复，成了「。，」**（frontend/app/page.tsx:808 与 backend/rate_limit.py:97）：后端 ASR 的超限文案以「。」结尾：「今天的语音识别次数已用完，明天再来吧，可以先打字。」。前端执行 data.error + "，免提已关闭" 后，用户看到的是「……可以先打字。，免提已关闭」。规格原文就是要求直接在后面加这几个字，所以不算违反规格，但显示出来不通顺。可以在前端先去掉末尾的「。」再拼接，也可以由作者调整这句文案。9061a52 里麦克风报错的提示不以句号结尾，所以那条路径没有这个问题。
- [caps-and-ip] **O3 按 IP 每分钟限流返回的 429 也会显示英文提示，并且关闭免提**（frontend/app/page.tsx:713-716、806-810；后端 slowapi 的 _rate_limit_exceeded_handler 和 voice.py:498 的 10/minute 限流）：slowapi 默认返回 429，body 是 {"error": "Rate limit exceeded: 10 per 1 minute"}。前端只看状态码是不是 429，所以输入框旁的麦克风会显示这句英文。免提模式还会显示「Rate limit exceeded: 10 per 1 minute，免提已关闭」，并把免提关掉。按 IP 计数时，同一出口 IP 后面的多个账号（比如公司或家庭 NAT）共用每分钟 10 次。规格写的是「429 时」就提示，所以实现符合规格字面，但这种情况下文案和行为都不合适。可以考虑只在 body 里有 retry_after 字段（每日上限）时才关闭免提，或者给英文文案换成中文兜底。
- [caps-and-ip] **O4 卡片详情触发每日上限时，前端提示的是「查看较频繁，请稍后重试」**（frontend/components/NewsCardContent.tsx:86-87）：这里遇到 !response.ok 时，只要状态是 429 就固定显示「查看较频繁，请稍后重试」，不读取后端的 detail/error 字段。用户今天的次数用完后会被引导反复重试，但到北京零点前每次都会失败。规格 2.3.6 规定前端不改其他文件，所以这是规格本身的缺口，不是实施方的问题。建议另开一单，让这里在 429 时显示后端返回的 error 文案。
- [caps-and-ip] **O5 官方交流的计数位置和规格原文不一致，规格本身在这里前后矛盾**（backend/exchange_store.py:473-480）：规格要求在 :472 与 :473 之间计数，也就是排在所有 ExchangeConflict 检查之后。实际实现放在 initiator 检查之后、pair_key 冲突检查之前。如果按规格的位置放，规格 2.3.7 要求的测试会过不了：当天已用 2 次、并发创建两次时，后一个请求会先撞到「你已有进行中的官方体验」，得到 409，而不是测试期望的 429。现在的写法仍然在同一个 BEGIN IMMEDIATE 事务里，也在 INSERT 之前，404 依然最先检查，行为上的唯一区别是额度用完又有进行中交流的用户会收到 429，而不是 409。报告未决问题第 4 条已经如实列出，需要作者确认。
- [caps-and-ip] **O6 热点路由复制了 topic_expand 内部的两道本地检查，以后改一边容易漏另一边**（backend/routers/hot.py:30-34 与 backend/tools/topic_expand.py:102-108）：路由里的空标题和缺密钥检查，返回的 JSON 和工具内部完全相同。白名单只允许改 hot.py，所以复制是唯一可行的做法。但以后如果工具里改了检查条件或文案，路由不会跟着改，可能导致计数时机或返回内容不一致。test_daily_caps.py:191-200 只检查路由自己的输出，没有检查两边是否一致。
- [caps-and-ip] **O7 不受信的 IPv4 映射对端返回原始字符串；对应测试两种结果都放行，断言偏弱**（backend/rate_limit.py:50-51；backend/tests/test_client_ip_trust.py:58-60）：对端是 ::ffff:203.0.113.17 且不受信时，返回的限流键是 "::ffff:203.0.113.17"，不会展开成 203.0.113.17。规格要求「否则一律用 request.client.host」，所以这个行为是对的。但测试断言写的是 in {"203.0.113.17", "::ffff:203.0.113.17"}，以后行为变了它也照样通过。另外，同一个客户端如果有时显示成映射地址、有时显示成纯 IPv4，会落到两个限流键上，实际影响可以忽略。
- [ops] **O1 上传目录在打包时有文件变动，GNU tar 返回 1，连同已经做好的数据库快照一起被丢弃**（deploy/fiona-backup.sh:64（配合 :3 set -eu 与 :42-46 cleanup））：脚本开了 set -eu，tar 非 0 就立即退出。此时 published=0，cleanup 会把已经通过 integrity_check 的 $db_temp 也一起删掉。Linux 生产机用的是 GNU tar：打包期间如果有文件被删（File removed before we read it）或被改（file changed as we read it），退出码是 1（TAREXIT_DIFFERS）。后端往上传目录写文件的方式是先写点开头的临时文件再 os.replace，清理循环每 15 分钟删一次文件，聊天和广场上传也随时可能落盘。04:00 撞上的概率不高，但一旦撞上，当天就一份备份也没有，而失败原因只是媒体包有一处差异。本机只有 bsdtar，它遇到这种情况不返回 1，所以没法实测，这一条是读代码和 GNU tar 文档得出的。建议：数据库快照先单独发布；或者只把 tar 的退出码 1 当告警，记日志后继续。
- [ops] **O2 保留期清理会递归进子目录，误删子目录里同名格式的手工备份**（deploy/fiona-backup.sh:72-73；docs/DEPLOYMENT.md:422）：实测：在 FIONA_BACKUP_DIR/manual-pre-release/ 下放两个 20 天前的 fiona-db-keepme.sqlite3 和 fiona-uploads-keepme.tar.gz，运行一次脚本后两个都被删了。文档写的是「默认只删除本脚本命名的…旧备份，不删除其他文件」，这和实际行为不一致：运维为了长期保留，把发布前备份挪进子目录，到期照样被删。find 默认不跟随符号链接，所以不会删到备份目录以外。建议加 -maxdepth 1（GNU 和 BSD 的 find 都支持）。
- [ops] **O3 数据库文件只读时 /health 仍然返回 200**（backend/main.py:257）：SQLite 的 mode=rw 遇到操作系统层面写保护的文件会自动退成只读打开。实测把已经迁移好的 WAL 库 chmod 0400 后调用 main.health()，结果是 (200, {"status": "ok"})。现实场景：恢复时 root 用 cp 覆盖了库文件，属主变成 root:root 0644。这时服务可以启动（init_db 里的写操作都被 _safe_migrate 或 try 吞掉了），/health 也报 ok，但所有写请求都失败。规格没有要求检查可写性，所以只列为可优化。建议加一条 os.access(database.DB_PATH, os.W_OK)，失败项名称仍归入 "database"。
- [ops] **O4 HEAD /health 返回 405，用默认 HEAD 方法的外部拨测会一直误报**（backend/main.py:237；docs/DEPLOYMENT.md:507）：进程内用 TestClient 实测（不启动服务）：GET /health 返回 200，HEAD /health 返回 405（FastAPI 的 @app.get 不会自动加 HEAD）。文档说「任何外部拨测服务」都可以，但不少拨测服务的 HTTP 监控默认发 HEAD。建议在文档里写明拨测必须用 GET，或者把路由改成 api_route(methods=["GET","HEAD"])。另外顺带发现：GET /health/（多一个斜杠）不在公开路径里，带 Cookie 访问会得到 401 并删掉 Cookie。这只影响拼错的路径，可以忽略。
- [ops] **O5 systemd 版本低于 254 时，启动失败（退出码 3）会无限自动重启，不会进入 failed 状态，OnFailure 通知也不会触发**（docs/DEPLOYMENT.md:514（以及 :167 的 Restart=on-failure、RestartSec=3））：run.py 的退出码判断本身没问题：读了 uvicorn 0.47 的 Server.startup，lifespan 失败时 should_exit 被置位，started 一直为 False，所以退出 3；导入失败和端口占用由 uvicorn 自己 sys.exit(1)。但文档说退出 3「便于 systemd 记录 failed 并触发通知」，这句话依赖 systemd 版本。从 254 起，默认 RestartMode=normal，每次失败都会先进入 failed 状态，OnFailure 会触发。254 之前（如 Debian 12 的 252、Ubuntu 22.04 的 249），自动重启期间单元不进入 failed。按默认 StartLimitIntervalSec=10s、StartLimitBurst=5，加上 RestartSec=3 和启动本身耗时，10 秒内凑不满 5 次启动，结果就是无限重启，OnFailure 永远不触发。这条来自对 systemd 行为的记忆，需要在目标机上验证。建议在 [Unit] 里加 StartLimitIntervalSec=300、StartLimitBurst=5，或者在文档里注明版本差异，并以外部 /health 拨测为主要告警手段。
- [ops] **O6 migrate.py 依赖模型密钥；各种失败的提示都把人引向「检查结构和消息归属」**（backend/migrate.py:102-107（init_db → exchange_store → llm.py:69 的 make_dashscope_client））：实测：去掉 DASHSCOPE_API_KEY 后运行 migrate.py --db <WAL 旧库>，退出码 1，输出「失败 type=OpenAIError：迁移失败，请在副本上检查结构和消息归属后重试。」，同时打印了 [init_db] post owner backfill failed type=RuntimeError（因为缺 JWT_SECRET）。服务器上按文档带 --env-file 运行没有问题。但文档建议的「定期取回演练」通常在没有服务配置的机器上做，这时报错会把人引去查消息归属。临时目录放不下大库导致的 OSError，提示也是同一句。建议：对 OpenAIError 和 OSError 给出不同的提示；或者在文档里写明演练时必须带 --env-file，或至少提供 DASHSCOPE_API_KEY 和 JWT_SECRET。
- [ops] **O7 --in-place 会改写指定的库，却完全不显示是哪个库**（backend/migrate.py:82-85）：redirect_stderr 把 configure_database 打印的「数据库：<绝对路径>」吞掉了。其他管理脚本的约定（CLAUDE.md）是「核对输出的数据库绝对路径」；migrate.py 的 --in-place 是写操作，运维却无从确认目标库。报告未决问题第 9 条承认是有意隐藏的。规格只禁止输出行内容，没有禁止输出路径。建议至少在 --in-place 时打印目标库的绝对路径，或者要求先确认。
- [ops] **O8 回滚恢复一节的示例名还是旧命名；发布前的备份 14 天后会被自动清理**（docs/DEPLOYMENT.md:547、:540、:326-332）：新脚本产出的文件名是 fiona-db-YYYYMMDDTHHMMSSZ-PID.sqlite3 和 fiona-uploads-…tar.gz，但「回滚与恢复」一节的 install 示例仍是 /var/backups/fiona/fiona-YYYYMMDD-HHMMSS.db，媒体恢复也没给命令（演练一节有）。日常发布现在也调用这个脚本，产出的发布前回滚点同样会在 14 天后被 find 删掉，文档没有提醒运维单独保留。这两点都是文档和代码对不上，不影响脚本本身。
- [ops] **O9 /health 无需登录、不限流，每次请求都新建 aiosqlite 线程和连接，连接没有整体超时**（backend/main.py:256-258）：timeout=1.0 只是 SQLite 的忙等超时，不是打开连接的整体超时（实测 WAL 库被另一个连接 BEGIN EXCLUSIVE 时 /health 0 秒返回 200，正常读不受影响）。规格明确要求不挂限流，所以只是提醒：可以在 Nginx 对 /api/health 加 limit_req，或只放行拨测来源；必要时给连接加 asyncio.wait_for。

## 逐条核验记录

### spec-and-tests

- 第 0 节硬规则：git status --porcelain --untracked-files=all 列出的改动和新增文件全部在第 2 节各块白名单内（包括 deploy/ 新目录的三个文件、docs/tasks 的 02/03）；没改 requirements、package.json、lockfile 或 .github/workflows
- 已有测试：git diff --stat 9061a52 -- backend/tests 只有 test_tts_ws_limits.py 整文件删除；conftest 和 _fakes 没动；6 个新测试文件都是未跟踪的新文件
- 新测试里没有 xfail/importorskip；只有两类 skipif（没有 ffmpeg、没有 sqlite3），skip 原因写清楚了；没有用条件分支让测试在缺环境时假绿
- 2.1 测试逐条对照：JPEG（GPS、XMP、Artist、拍摄时间、Orientation=6，外加 IPTC/APP13）、PNG（tEXt、iTXt XMP、ICC、eXIf）、GIF（comment）、WebP（EXIF、XMP、ICC）、MPO；广场和聊天两条路径都断言了私密串消失、data URI 等于落盘字节、getexif 为空、info 无 exif/xmp/comment、宽高对调、ICC 保留、帧数/时长/loop 不变、超帧拒绝、MPO 单帧；原始字节正控有效；视频 argv（-nostdin、0:V:0、0:a:0?、-map_metadata、-map_chapters、-dn、-sn、+bitexact、faststart、-f、timeout=30）、503/400、临时文件清理；真 ffmpeg 集成测试先正控 location 标签和 90 度旋转存在
- 2.2：路由已删、WebSocket 和 ws_authenticate 两个 import 已删；另外三个 TTS 路由没改；新测试含 peer 和 stream 的正控，以及非 4401 断言；git grep --untracked 零命中
- 2.3：四个变量每次调用时读取，非法值回落默认并只告警一次；北京日期经 database._today_shanghai 取；只在 limiter.enabled 且 DEV_MODE!=1 时生效；官方计数在 BEGIN IMMEDIATE 内、用指定 SQL，404 仍在最前；三个内存计数都在本地校验之后；429 的 detail/error/retry_after 和 Retry-After 形状正确；前端两处 429 处理和文案改动符合规格；test_daily_caps 覆盖规格第 7 点每一项（N/N+1、换账号、换日、开发模式和关闭限流器、本地失败不计数、改成 1 立即生效、并发抢最后名额、不存在的 ID 返回 404）
- 2.4：_client_ip 函数签名不变，可信代理每次调用时读取，支持 CIDR 和 IPv4 映射地址，testclient 和 None 情形正确，docstring 已更新；is_loopback_client 没改；测试覆盖规格列出的 5 项
- 2.5：/health 在公开路径里，没挂限流，用 mode=rw URI 加 timeout=1，检查 5 道迁移和 users 表、上传目录 os.access，响应不含路径；run.py 加了 started 判断后 exit(3)；清理循环捕获 Exception，CancelledError 照常传播；测试覆盖规格列出的 8 项
- 2.6：migrate.py 默认在副本（含 -wal/-shm）上跑，--db 优先、--in-place 才写原库、只跑 init_db、缺库退出 2、不打印行内容、有孤立消息提示；init_db 本身没有上传或恢复副作用；备份脚本 umask 077、在线 .backup、integrity_check、同一时间戳、0600、按 mtime 保留、检查属主、失败非零退出，GNU 和 BSD 写法兼容；timer 是北京时间 04:00、Persistent=true
- 文档：DEPLOYMENT 补了第 5 道迁移、ffmpeg 版本、环境变量表、Nginx 两个头（示例配置三个 location 都设了）、首次验证改用 /health、定时备份、恢复演练（只读 schema、迁移演练、孤立消息、uploads/ 前缀和 strip-components、JWT_SECRET、去元数据脚本）、监控告警（外部拨测、journalctl、OnFailure、消费告警）、发布前检查和下线记录；README、ARCHITECTURE、PLAN、CLAUDE 的 TTS WebSocket 说法都已同步，内容和代码一致
- 公开文件本机路径：所有改动和未跟踪文件里 /Users、/private/tmp、/var/folders 零命中（规格和报告本身引用规则的地方除外）
- 实测（只在 $TMPDIR，用后已删）：HEVC hvc1 的 mov 经 remux 后标签保留、location 被清掉；CMYK JPEG 和 16 位 PNG 往返正确；不透明 GIF 输出各帧是整幅、浏览器端不会出现透明空洞；GIF disposal=2 体积放大（见 M1）；动图内存峰值（见 O1）；tRNS 丢失（见 O4）；重复帧合并（见 O5）

### media

- 只读：只用 git diff 9061a52 和 status 查看改动；所有实验都在 $TMPDIR/fiona-review-21 下进行，FIONA_UPLOADS_DIR 和 FIONA_DB_PATH 都指向临时目录；没改仓库（status 仍是 33 行），没跑 pytest，没启动服务，没读 .env
- 图片两条路径（广场和聊天，含 data URI）都实测零泄漏，getexif 为空：PNG 的 eXIf（IDAT 前后两种位置）/tEXt/zTXt/iTXt XMP/私有辅助块/tIME；单帧 WebP 和无损 WebP 的 EXIF/XMP；GIF 的 comment 和 XMP 应用扩展（单帧、动图）；CMYK JPEG 的 COM/EXIF（只有 ICC 保留，符合规格）；灰度 JPEG；MPO 附属帧的 COM 和 EXIF 都没写出，只输出主帧 JPEG
- 颜色模式：P 加 tRNS 转为 RGBA、I;16、1、LA 都保持正确；灰度透明 GIF 和三帧动图逐帧 RGBA 一致；Orientation=6 转正（包括 IDAT 之后的 eXIf）；EXIF 损坏的 JPEG 不会被误拒
- 动图炸弹：帧数×画布面积在解码前就会被挡住；35 万帧的 5MB GIF 扫描 n_frames 只需 0.3 秒，随后返回 400；画布按帧扩张时也会逐帧检查
- 真 ffmpeg 8.1.2 实测：mp4 的 location/title/comment/creation_time/handler_name 全部清除，mvhd/tkhd/mdhd 的时间归零，90 度旋转和视频流都保留；Apple keys 的 mov、mov_text 字幕加章节、带 webvtt/章节/流标签的 webm（VP9+Opus）全部清干净；3gp 输出为 .mp4；H.264 或 VP9+AAC 的 mkv、只有封面的 mp4 都返回 400；缺 ffmpeg 返回 503，且不留残余；输出扩展名和容器一致
- 取消和清理：广场路径在 asyncio 取消下没有残留；聊天路径在调用者取消后留下孤儿文件（M1）；3 个并发上传确实最多 2 个同时处理
- strip_upload_metadata.py：默认 dry-run 不改任何文件（哈希一致）；--apply 只改 plaza_* 和 32 位十六进制命名的文件；generated_、reference_、点文件、符号链接、目录都不动；坏图和 mp3 计入失败但不中断；--env-file 不存在时退出 1，只打印异常类型；目录不存在时退出 2；输出只有计数和类型
- voice.py 的 ffmpeg 参数没动；chat_service.py 只改了第 460 行；_validate_decodable_image 只在 media.py 内部被调用，放宽 MPO 不会让其他路径原样保存
- 实验脚本：$TMPDIR/fiona-review-21/（exp1.py、measure.py、measure2.py、starve.py、cancel.py、anyio_spin.py、amplify.py、vexp.py、strip/）

### caps-and-ip

- 只读复核，基线是 9061a52，结论来自落盘代码。我没有跑 pytest，没有启动服务，没有读 .env；实测都是在 TMPDIR 临时目录里用 python -c 直接调用函数
- rate_limit.daily_caps_enabled() 每次调用时读取 limiter.enabled 和 DEV_MODE 是否不等于 "1"，写法与 auth_dep._dev_mode 一致；exchange_store 和 check_daily_cap 都是在调用时判断
- 官方交流：计数在 create_official_exchange 已有的 BEGIN IMMEDIATE 事务里、INSERT 之前；SQL 与规格逐字一致；created_at 用的是 SQLite 的 CURRENT_TIMESTAMP（UTC），加 8 小时后与 database._today_shanghai() 比较，后者按模块属性调用；get_official_agent 的 404 仍在事务之前最先检查；OfficialDailyCapExceeded 继承 ValueError，不继承 ExchangeConflict；路由在 except ExchangeConflict 之前捕获它并返回 429；create_official_exchange 没有其他调用方；官方交流没有重启或重试的入口；DELETE FROM agent_exchanges 只在删号流程里出现，没有绕过上限的办法；没有新增表，也没有新增迁移版本
- 热点、卡片、ASR 三项：计数键是 ("daily", kind, user, database._today_shanghai())，包含账号和北京日期；_DailyLimitItem 固定了 key_for，所以改额度时同一天已用的次数不丢，过期时间为 86400 秒。实测：第 3 次返回 429，换账号不受影响，调高额度立即放行，DEV_MODE=1 时跳过
- 计数时机：热点在空标题和缺密钥提前返回之后才计数；ASR 在 base64、空音频、413 大小、PCM 时长、ffmpeg 超时、ffmpeg 缺失、转码失败全部通过之后才计数；卡片在 pydantic 校验之后计数（缺密钥那一点见 O1）；上游失败不退还
- 四个 FIONA_DAILY_* 环境变量调用时读取；非法值（0、-1、空串、x、带空格）回落默认值，每个变量只告警一次，已实测
- 429 响应：状态码 429，头里有 Retry-After，实测为 44745 秒，到北京次日零点向上取整，最小 1 秒；body 同时有 detail、error、retry_after；四类文案和官方的 N 都与规格逐字一致
- 前端 page.tsx：两处改动都只在 res.status===429 时生效，其他失败行为不变；免提的收尾方式与 9061a52 处理麦克风报错的写法一致（先 setHandsFree(false) 再 setMicNotice），不存在依赖 handsFree 的 effect 会清掉提示，也没有冲突；apiFetch 遇到 429 不会抛错；AgentExchangeWorkspace 只改了一句说明，apiJson 会优先显示 detail
- _client_ip：只有对端在受信列表里时才读 X-Real-IP 和 XFF 最后一段；CIDR 和 IPv4 映射地址都会展开后比较；实测 ::ffff:0:0/80、::/0、0.0.0.0/0、空配置、配置项带空格都不会报错；非 IP 字符串原样作为限流键；client 为 None 时按 127.0.0.1 处理；FIONA_TRUSTED_PROXIES 调用时读取；函数签名不变，limiter._key_func is _client_ip 为 True；voice.py:285 的换票限流沿用这个函数
- auth_dep.py、database.py、qwen_asr.py、tools/ 相对 9061a52 零改动，is_loopback_client 没有被改
- rate_limit 新增了 import database，没有形成循环导入；管理脚本和 migrate.py 都是在 configure_database 之后才导入 database，DB_PATH 的绑定顺序不受影响；main.py 也是先 load_dotenv 再导入
- 调用这三个付费函数的路径没有其他绕过点：topic_expand、card_detail、asr_recognize 都只有被加了上限的这三个路由调用
- 2.3 和 2.4 改动的文件都在白名单内；文档里的环境变量表、Nginx 两个代理头、内存计数重启清零的说明已经写上

### ops

- /health 不建库（实测）：只读调用 main.health()，打桩 DB_PATH 指向临时目录里不存在的文件、不存在的父目录、相对路径，三种都返回 503 failed=["database"]，目录中没有新增文件。测试里的路径还含 ?# 字符，as_uri 已正确转义
- /health 与 WAL 库：WAL 库在没有 -wal/-shm 时用 mode=rw 能正常打开，返回 200，关闭后不留侧文件；另一连接持有 BEGIN EXCLUSIVE 写事务时立即返回 200；0 字节文件、损坏文件返回 schema；目录当库返回 database；上传目录缺失返回 uploads
- /health 响应体只有 status/failed，没有路径、异常正文或版本号；在 _AUTH_PUBLIC_PATHS 中，带无效 Cookie 访问时实测不发 Set-Cookie；没有挂限流；原 GET / 不变
- 五道迁移版本常量（agent_store.MIGRATION_VERSION 与 exchange_store 的四个常量）和 database.init_db 实际调用的五个 migrate_* 一一对应，各自 INSERT 的 version 一致
- run.py：读 uvicorn 0.47 server.py 和 lifespan/on.py，Starlette 发 startup.failed 后 should_exit 置位，started 保持 False，于是 sys.exit(3)；导入失败、端口占用时 uvicorn 自己 sys.exit(1)；SIGTERM 由 capture_signals 重新抛出，正常关停不受影响；监听 127.0.0.1:8000 不变
- 清理循环：只在 sleep 之后的单轮调用外包了 except Exception，日志只打印异常类型；CancelledError 属于 BaseException，能正常向外传播
- migrate.py --db 优先级：load_dotenv(override=False)，--db 先写入环境变量，测试也覆盖了；缺库时 configure_database(init_db=False) 抛 AdminConfigError，返回 2 且不建库
- migrate.py 默认副本模式：database 模块的函数调用时按名字读模块全局 DB_PATH，agent_store 用 database.DB_PATH，换成副本路径能生效；只调用 init_db，不调用 recover 或上传清理；实测没有建出上传目录，输出只有版本、表、列名和行数，没有行内容；孤儿消息提示的判定条件与第①道迁移的失败条件一致
- fiona-backup.sh 实测（macOS，环境变量指向临时目录）：WAL 库在另一连接持有未提交写事务时，备份成功且只含已提交的行，journal_mode=delete；数据库包和媒体包同一时间戳，权限 0600；用 80MB 媒体、保留 1 天再跑一次，刚生成的备份没有被误删
- find -mtime 语义：在本机 /usr/bin/find 上用 5 秒、23 小时、24 小时 +100 秒、13.99 天、14 天 +100 秒五档造文件实测，取整方式与 POSIX/GNU 一致（向下取整）。-mtime +(N-1) 在两个平台上都表示「满 N 天才删」，不会删到备份目录以外
- 脚本没有管道，不需要 pipefail；用 stat -c 失败再退回 stat -f 的写法兼容 GNU 和 BSD；tar -h 两个平台都支持；trap 能覆盖 EXIT/HUP/INT/TERM；运行账号与库文件属主不一致时直接拒绝；service 设了 User=fiona、UMask=0077，ReadWritePaths 与文档目录一致；timer 写的是 OnCalendar=*-*-* 04:00:00 Asia/Shanghai 加 Persistent=true；oneshot 默认没有启动超时
- DEPLOYMENT.md：补上了第 5 道迁移；环境变量表的默认值与 rate_limit.py 一致；Nginx 示例三个 location 都设了 X-Real-IP 和 XFF；首次验证改为 /health；日常发布用 sudo -u fiona 跑脚本；恢复演练里 strip 脚本的 FIONA_UPLOADS_DIR 能覆盖 env-file（override=False）；下线记录按规格改了。另外：用旧方式 .backup 得到的 WAL 库，在 macOS 自带 sqlite3 下用 -readonly 打不开（unable to open database file），Homebrew 装的上游 sqlite3 3.53.3 可以；生产 Linux 用的是上游构建，所以不算问题
- 只读约束：没有改仓库文件，git status 条目数与开始时相同（33 条），临时目录已删除

