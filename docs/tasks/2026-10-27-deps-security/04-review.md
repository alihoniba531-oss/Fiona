# 独立复核（2026-10-28，订阅 Opus 5.5；本月 dsh 上的 Opus 预算已低于 5 美元，按规则改用订阅）

## 结论：通过，必须修复项：无

三处版本变更、锁文件、Pillow 13 与 Next.js 16.4.3 的影响面均独立核对，结果与主会话门禁一致。另有一条行为变化需作者知悉（重复 Orientation 标签，见第 2 节），PLAN 条目据此补了「已知差异」。复核只读工作树，实验在复核方自己的临时目录里做；工作树前后状态一致，主检出只做过只读的 git 读取和只读的解释器运行。

## 1. 依赖与锁文件：通过

- `git diff 0c80323` 只改三处：`next`、`eslint-config-next` 16.3.8 → 16.4.3（精确版本），`Pillow==12.3.0` → `13.0.0`。`requirements-dev.txt` 与 `.github` 未动。
- 锁文件逐包比对：无新增、无删除。版本变化 13 个：`next`、`@next/env`、`@next/eslint-plugin-next`、`eslint-config-next` 及 8 个 `@next/swc-*`（16.3.8 → 16.4.3），`fastq` 1.20.1 → 1.20.3。另有两处只改依赖范围、不改已装版本（`next` 对 `sharp` 的范围；`eslint-config-next` 对 `eslint-plugin-react-hooks`、`typescript-eslint` 的范围）。
- 所有 `resolved` 指向 `https://registry.npmjs.org/`，无缺 integrity 的条目；逐包用 `npm view <包>@<版本> dist.integrity dist.tarball _npmUser` 对照，13 个全部一致，发布者均为 GitHub Actions 可信发布，`next@16.4.3` 与 `fastq@1.20.3` 带 SLSA provenance。
- `fastq` 为何变：依赖链 `@next/eslint-plugin-next` → `fast-glob` → `@nodelib/fs.walk` → `fastq ^1.6.0`，属于被升级包子树的重新解析；用基线 package.json 与锁文件在临时目录重放 `npm install --save-exact next@16.4.3 eslint-config-next@16.4.3 --package-lock-only`，同样得到 1.20.3。1.20.3 于 2026-08-29 发布，维护者未变，带 provenance，无供应链风险迹象。
- `npm audit --package-lock-only --omit=dev --audit-level=high`：0 漏洞。全量审计只剩开发依赖 `zod <4.6.6`，基线即有，CI 该步为 `continue-on-error`。

## 2. Pillow 13 影响面：通过，1 处已知差异

- 在 `backend/`（排除 .venv）搜 `_show|ImageCms|product_name|product_info|Makernote|get_child_images|fromarray|ImageColor|getcolor|Tiff|ICO|ImageShow`，无真实命中。
- 规格有一处不准：「重复 TIFF 标签」这条 Fiona 是间接用到的，`getexif()` 与 `ImageOps.exif_transpose` 解析 EXIF 走 TIFF IFD 解析，13 新增 `if tag in self._tagdata: continue`（保留第一个值，12 保留最后一个）。
- 两版 PIL 源码 diff 逐项看过：`exif_transpose` 删掉 xmp 为 tuple 的分支（两版 JPEG 插件里 xmp 都是 bytes，走不到）；JPEG 注释超 65533 字节改抛 ValueError；I 模式存 PNG 由截成 I;16 改为直接报错（Fiona 无此路径，16 位灰度读进来是 I;16，其余路径先转 RGB/RGBA）；GIF 多帧差分改写但语义等价；`_decompression_bomb_check` 新增 `error_only`，只对 WebP 多一道拦截，未放宽限制。
- 复核方自做实验：用 Pillow 12 生成 18 个夹具（不透明 / 透明动图 GIF、透明动图 WebP、两种顺序的重复 Orientation JPEG、16 位灰度 PNG、超长与普通 tEXt 的大 PNG、超长 comment 的大 GIF、CMYK JPEG、带 tEXt 的 APNG、LA / 1 位 / L+tRNS / RGB+tRNS PNG、带 EXIF+XMP+ICC 的 WebP、带 COM+EXIF 的大 JPEG），同一份字节喂给两个解释器，跑 `_strip_image_metadata`、`scripts/strip_upload_metadata._has_image_metadata`、`normalize_reference_upload`、`_claude_image_source`、`studio.brain._image_source`、`casting_jobs._reference_bytes_sync`、`video_seedance.prepare_first_frame`、`video_wan.prepare_first_frame`、`storage.inspect_image`、`image_generation._png_dimensions`，逐帧比较像素。
- 结果：18 个夹具里 14 个全部函数输出完全一致（动图逐帧像素 sha 一致）。差异两类：
  - **重复 Orientation（需知悉）**：EXIF 里有两个取值不同的 Orientation 时，strip 后 12 得到 300×200、13 得到 200×300，`normalize_reference_upload` 同样翻转；另一种顺序结果相反。只发生在畸形文件上，不涉及隐私，元数据照样清干净，不崩溃。
  - 超长 comment 发给 Claude 的缩图副本：12 抛 `OSError`，13 抛 `ValueError`，两版都是失败，调用链无按异常类型区分的分支；且聊天发给 Claude 的是已清理元数据的副本，实际走不到。无害。
- 复跑 `compare_pillow.py`：13/13 match，9 个有像素的用例 max_abs_diff 全为 0、sha 相同。Pillow 13.0.0 未被撤回，cp314 的 manylinux x86_64 与 macOS arm64 wheel 都在，CI 能装。

## 3. Next.js 16.4 影响面：通过，客户端 JS 留给主会话用浏览器看

- 严格路由匹配只校验 catch-all 与并行路由拓扑；`frontend/app` 下无 `[...x]`、`@slot`、拦截路由、`route.ts`，只有 3 个 `[id]` 动态路由，不受影响。
- `proxyClientMaxBodySize`、`allowedDevOrigins` 在 16.4.3 的 config-schema 里仍有效，无弃用告警。
- 把工作树 frontend 克隆到临时目录、在 3093 端口 `next start` 扩展测试：`/agents/me`、`/studio/kb`、`/novels/new`、`/plaza`、`/match`、`/community`、`/profile` 无 Cookie 307 到 `/login`、有 Cookie 200；`/history/`、`/agents//abc` 308 去多余斜杠；`/agents/abc/def`、`/nonexistent` 404；`/studio/abc?embed=1` 无 Cookie 307 到 `/login?embed=1`；首页 13 个 script/css 资源全部 200。
- 导出名混淆与共享 runtime 只作用于客户端 bundle；前端只有静态可分析的 `import * as THREE/React`，无动态 `import()`；sw.js 自毁式、不缓存 chunk。但没有自动检查执行过客户端 JS，建议合入前用浏览器看一眼首页、抽屉 iframe、3D 星图、工作室页的控制台。
- CI `setup-node@v4` + `node-version: 20` 装 20.x 最新版，满足 next 的 `>=20.9.0`；新包里只有 next 声明 engines。

## 4. 验证脚本证明力：基本可用，缺口如下

- 两个脚本无硬编码绝对路径；夹具确实带 GPS、XMP、tEXt、ICC、两帧 MPO 与动图，并用 `_require` 自检；比较逻辑无恒真分支。
- 反向实验：把 after.json 里 `strip_webp_static_exif` 改成残留 Make/Model/DateTime，compare 仍 PASS，只记一条 allowed difference。「必须没有」的检查只覆盖 XMP、GPS、text，不覆盖一般 EXIF；符合规格 B5 字面要求，且 `tests/test_upload_metadata.py` 30 个用例（断言 `not image.getexif()` 且 info 无 exif/xmp/comment）在 13 下通过兜底。
- 像素只比首帧，动图第 2 帧起不比（复核方实验已补，逐帧一致）。夹具由各自版本现场生成，两版 libjpeg-turbo 不同（3.1.4.1 / 3.2.0），输入字节可能不同；本次结果 0 差。
- compare 子命令也要 import PIL，用系统 python3 跑会报 `ModuleNotFoundError`，须用装了 Pillow 的解释器。
- `route_smoke.py` 反向实验：先在目标端口起一个无关 http.server 再跑脚本，exit 0、`errors []`，量到的是无关服务。脚本不检查端口空闲，也不确认应答的是自己起的进程；若有陈旧 next 进程，after 会量到旧构建。

## 5. 文档：通过

`README.md:25`、`frontend/README.md:3` 16.3.3 → 16.4.3，`CLAUDE.md:8` 16.2.6 → 16.4.3，准确。全库搜 `16.3.3|16.3.8|16.2.6|Pillow 1[0-2]|12.3.0`（排除 docs/tasks 与锁文件）只剩 `PLAN.md` 两处 2026-08-26 的历史条目，不改是对的。PLAN 新条目的漏洞编号、数字、zod 说明核对无误；「用户可见行为不变」一句与第 2 节差异不完全相符，已改写并补已知差异。

## 6. 「何时停下来问」：无该停未停

首次全量测试 17 个 collection error 源于本机 `NO_PROXY` 含 `[::1]`，环境问题，实现方如实记录并用干净环境重跑；fastq 变化已标「需人工确认」；zod 告警按规格仅记录。规格「重复 TIFF 标签没用到」与事实不符属规格疏漏，不算实现方违规。

## 需作者知悉 / 拍板（不阻塞合入）

1. 重复 Orientation 标签时 Pillow 13 以第一个值生效，旋转方向与 12 相反（已写进 PLAN 已知差异）。
2. 接受 `fastq` 1.20.3 这一处传递依赖刷新（建议接受）。

## 可优化项

- `compare_pillow.py`：残留检查加 EXIF 标签数为 0、PNG eXIf、JPEG COM；动图逐帧比像素；夹具生成一次两版共用；说明改用装了 Pillow 的解释器。
- `route_smoke.py`：启动前确认端口空闲，并核对应答的是自己启动的进程（如校验 BUILD_ID）。
- 题外：主检出与本机试用副本的 `node_modules` 里装的是 next 16.3.3，锁文件写的是 16.3.8；合入后 `npm ci` 即可。
