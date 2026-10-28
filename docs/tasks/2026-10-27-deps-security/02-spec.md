# 依赖安全升级：Next.js 16.4.3 与 Pillow 13.0.0（2026-10-27）

## 1. 目标与场景

Fiona 推送到 main（0c80323）后，CI「Quality」只在两个依赖漏洞审计步骤上变红，其余步骤（lint、TypeScript、构建、后端全量测试、compileall、pip check）全部通过：

- 前端 `npm audit --audit-level=high --omit=dev`：`next 16.0.0 - 16.4.0` 有 1 项严重级漏洞（GHSA-2464-fhr4-w9xw 图片优化接口处理 SVG 时未鉴权远程代码执行；GHSA-p3m5-59mp-jv5r Server Actions 拒绝服务；GHSA-673q-mjm6-r5xr `use cache` 未鉴权远程代码执行），修复版本 16.4.3。
- 后端 `pip_audit -r requirements.txt`：`pillow 12.3.0` 有 37 个已知漏洞，修复版本 13.0.0。

本任务把这两个依赖升到修复版本，让 CI 恢复全绿，**用户可见行为不变**。Pillow 负责聊天、广场和参考图上传的去元数据（隐私关键路径），按高风险改动处理。

## 2. 现状事实（Claude 已核实，你实测不符时以实测为准并停下来说明）

- 基线提交 `0c80323`，工作树 `<本工作树>`，分支 `fix/deps-security`。基线实测：后端全量 `7744 passed, 0 skipped`；`npm run lint` 0 errors、25 warnings；`npx tsc --noEmit` 退出码 0；`npm run build` 成功。
- `frontend/package.json`：`"next": "16.3.8"`（dependencies）、`"eslint-config-next": "16.3.8"`（devDependencies），均为精确版本。`react` / `react-dom` 为 `19.2.4`。
- `backend/requirements.txt`：`Pillow==12.3.0`。CI 用 Python 3.14、Node 20；本机基础解释器 `python3.14`（3.14.6），Node 26。
- 新版本均已在官方源发布：`next@16.4.3` 与 `eslint-config-next@16.4.3` 发布于 2026-10-23，`engines.node >= 20.9.0`，peer `react ^19`；`Pillow 13.0.0` 发布于 2026-10-16，`requires_python >= 3.11`，有 cp314 macOS arm64 wheel。
- Pillow 13.0.0 的不兼容变更：删除 `Image._show`、`ImageCms.ImageCmsProfile.product_name/product_info`、`ExifTags.IFD.Makernote`；`Image.Image.get_child_images()` 移到 `ImageFile.ImageFile`；`Image.fromarray()` 的 `mode` 参数在改变数据类型时被移除；I 模式存 PNG 不再截到 16 位；`ImageColor.getcolor()` 对 RGBa/La 返回预乘值；重复 TIFF 标签改为保留第一个值；小 ICO 保存规则变化。Claude 已在 `backend/`（不含 .venv）全文搜索，**以上 API 一个都没用到**。用到 Pillow 的模块：`utils/media.py`（上传去元数据 `_strip_image_metadata`、校验 `_validate_decodable_image`）、`utils/reference_images.py`（`normalize_reference_upload`）、`services/claude_agent.py`（`_claude_image_source` 缩图）、`tools/image_generation.py`、`studio/`（storage、brain、casting_jobs、两个视频 provider）、`scripts/strip_upload_metadata.py`、`scripts/_capture_wechat.py`。后端有 24 个测试文件导入 PIL，`tests/test_upload_metadata.py`（30 个用例）是去元数据的主要回归保护。
- Next.js 16.4.0 的默认值变化里与 Fiona 可能相关的：严格路由匹配默认开启、构建默认开启 Turbopack 导出名混淆、`experimental.turbopackSharedRuntime` 默认开启。Fiona 没有用 `next/image`、`"use cache"`、Server Actions。`next.config.ts` 用了 `experimental.proxyClientMaxBodySize`、`headers()`（CSP 等）、`rewrites()`（`/api/:path*` → `FIONA_BACKEND_ORIGIN`）、`allowedDevOrigins`。`frontend/proxy.ts`：生产模式下未登录（无 `fiona_token` Cookie）访问受保护页面 307 跳 `/login`；动态路由有 `app/agents/[id]`、`app/novels/[id]`、`app/studio/[id]`。
- 执行环境（Claude 已实测你的沙箱）：可以联网下载；但沙箱不能写 `~/.npm`，npm 会报 `EPERM ... root-owned files`，这不是真的权限坏了。所有 npm 命令前设 `export npm_config_cache=/tmp/fiona-npm-cache`；pip 设 `export PIP_CACHE_DIR=/tmp/fiona-pip-cache`。
- 本工作树里还没有 `frontend/node_modules` 和 `backend/.venv`。**用户本机正在用 `<Fiona 主检出>`（主检出）跑 8010 后端，绝对不得在主检出里安装、升级或删除任何东西，也不得修改主检出的任何文件**；主检出的 `backend/.venv/bin/python` 只允许以只读方式运行（加 `PYTHONDONTWRITEBYTECODE=1`），用来跑「升级前」的对比脚本。
- 端口：只用 3091（next start）和 8091（假后端）。不得占用或停止 3000、8000、8010。
- 沙箱兜底：如果你的沙箱不允许监听端口（A3、A4 的冒烟），或不允许运行主检出的解释器（B4 的「升级前」），照样把脚本写完、把能跑的部分跑完，记下错误原文写进报告，这一步留给 Claude 在门禁里跑；这种情况不算「停下来」的理由。

## 3. 约束

- 版本写死：`next` 与 `eslint-config-next` 都是 `16.4.3`（精确版本，不加 `^`），`Pillow==13.0.0`。**除这三项外，`package.json` 与 `requirements*.txt` 里任何依赖的版本都不许改**。锁文件只接受 `npm install` 这两个包本身带出的变化。不用 `npm audit fix`，更不用 `--force`。
- 不改任何业务代码、测试代码、CI 配置。改动前就存在的测试一字不许改。
- 不新增依赖。
- 验证脚本里不得硬编码本机绝对路径，路径一律从命令行参数或环境变量读入。
- **何时停下来问**：下面任何一种情况都停下来，报告证据与你的分析，不要自己改代码绕过：① 升级后有既有测试失败、构建或类型检查失败、lint 出现新的 error 或 warning 数变化；② 升级后 `npm audit --audit-level=high --omit=dev` 或 `pip_audit` 仍有发现（不要顺手去升别的包）；③ 第 4 节的升级前后对比出现不在允许范围内的差异；④ 本规格与你实测的事实不符。只影响「怎么验证」的细节自己决定并在报告里写明理由。任何情况都不回滚已完成的工作。

## 4. 任务清单

用工作流（workflow 工具）并行：在脚本里用 parallel() 同时运行下面 3 个 agent，按文件不重叠拆分；每个 agent 的任务说明要自包含（把本规格第 2、3 节与它自己的那一项抄进去），并写明不得调用 subagent / subagent_fork / workflow。代理失败先读结果再决定，不许盲目重派。主代理只做拆分、派发、汇总、白名单检查、第 5 节验收和报告；报告开头列拆分表，如实列出所有派出过的代理。

### A 前端（只动 `frontend/package.json`、`frontend/package-lock.json`，新增 `docs/tasks/2026-10-27-deps-security/verify/route_smoke.py`）

1. **升级前测一遍**：在本工作树 `frontend/` 里用现有锁文件 `npm ci`，`FIONA_BACKEND_ORIGIN=http://127.0.0.1:8091 npm run build`，保存完整构建输出。
2. 写 `verify/route_smoke.py`（只用 Python 标准库）：
   - 在一个临时目录里放一个内容为 `fiona-stub-ok` 的文件 `health`，用 `python3 -m http.server 8091 --bind 127.0.0.1` 起假后端；
   - `FIONA_BACKEND_ORIGIN=http://127.0.0.1:8091 npx next start -p 3091 -H 127.0.0.1` 起前端，等到可访问；
   - 不跟随重定向，依次请求下列路径，记录状态码、`Location` 头，以及 `Content-Security-Policy`、`X-Frame-Options`、`Permissions-Policy` 三个响应头：
     - 无 Cookie：`/`、`/login`、`/history`、`/settings`、`/agents/abc`、`/novels/abc`、`/studio/abc`；
     - 带 `Cookie: fiona_token=x`：`/`、`/login`、`/history`、`/agents/abc`、`/novels/abc`、`/studio/abc`、`/novels?embed=1`；
     - `/api/health`：状态码与正文（应为 `fiona-stub-ok`，证明 rewrite 生效）。
   - 结果写成 JSON（输出路径由参数给出），结束时停掉两个进程。
3. 在升级前的构建上跑一次，结果存 `/tmp/fiona-deps/route-before.json`。
4. **升级**：`npm install --save-exact next@16.4.3 eslint-config-next@16.4.3`，然后删 `node_modules` 与 `.next`，`npm ci`，再构建、再跑一次，结果存 `/tmp/fiona-deps/route-after.json`。
5. 比较两份结果，**必须完全相同**（状态码、Location、三个头、`/api/health` 正文）。构建输出里不得出现 `Invalid next.config`、`Unrecognized key`、`deprecated` 一类关于本项目配置的新警告；有的话原文抄进报告并停下来。
6. 列出锁文件里版本有变化的包（包名、旧版本 → 新版本），以及新增、删除的包，写进报告。
7. 跑 `npm run lint`、`npx tsc --noEmit`、`npm audit --audit-level=high --omit=dev`（期望退出码 0）、`npm audit --audit-level=high`（仅记录结果），原始摘要行写进报告。

### B 后端（只动 `backend/requirements.txt`，新增 `docs/tasks/2026-10-27-deps-security/verify/compare_pillow.py`）

1. 把 `backend/requirements.txt` 的 `Pillow==12.3.0` 改成 `Pillow==13.0.0`，其余行不动。
2. 在本工作树建新虚拟环境：`python3.14 -m venv backend/.venv`（已被 .gitignore 忽略），`backend/.venv/bin/python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt`。确认 `import PIL; PIL.__version__ == "13.0.0"`；跑 `pip check`、`python -m compileall -q backend`（排除 .venv 的写法自定）、`python -m pip_audit -r backend/requirements.txt --progress-spinner off`（期望无已知漏洞）。
3. 写 `verify/compare_pillow.py`：用 Pillow 在内存里**现场生成**夹具（不读仓库外文件），对每个用例调用 Fiona 的真实函数，输出 JSON。用例至少包括：
   - `utils.media._strip_image_metadata`：
     - JPEG：EXIF 带 GPS 与 Orientation=6、带 ICC、带 XMP；
     - MPO：两帧（用 `save_all=True` 以 MPO 保存）；
     - PNG：带 `tEXt`、`iCCP`、调色板透明；
     - GIF：3 帧动画、带透明、不同帧时长、`loop=0`；
     - WebP：静态带 EXIF；以及 3 帧动画；
     - 超限：8000×6000 的 PNG；帧数 301 的 GIF（帧可以很小）。
   - `utils.reference_images.normalize_reference_upload`：带 EXIF 方向的 JPEG、超长比例或超大尺寸各一张（按函数实际接受的 base64 输入构造）。
   - `services.claude_agent._claude_image_source`：一张 3000×2000 的 JPEG 与一张带透明的 PNG（按函数实际接受的 data URI 构造）。
   - 每个用例记录：成功还是异常（异常记类型与 HTTP 状态码 / 文案）；成功时记输出的 format、size、mode、帧数、每帧时长、loop、`info` 的键名集合、`getexif()` 的标签数、是否有 ICC（及其 sha256）、是否残留 XMP / GPS / `tEXt`；首帧转 RGBA 后与另一版本输出的逐像素平均绝对差与最大差（脚本先分别输出像素摘要与原始像素文件到参数给出的目录，再由比较模式计算差值）。
   - 需要设 `FIONA_UPLOADS_DIR` 指向 `/tmp/fiona-deps/uploads`，避免写仓库里的上传目录。
4. 分别用「升级前」与「升级后」解释器跑一次：
   - 升级前：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=<本工作树>/backend <Fiona 主检出>/backend/.venv/bin/python verify/compare_pillow.py ...`（只读运行主检出的解释器，它装的是 Pillow 12.3.0；跑之前先打印 `PIL.__version__` 确认是 12.3.0）；
   - 升级后：`PYTHONPATH=<本工作树>/backend backend/.venv/bin/python verify/compare_pillow.py ...`。
5. 比较：每个用例的成败、异常类型与状态码、format、size、mode、帧数、时长、loop、ICC、元数据残留（XMP / GPS / `tEXt` 必须都没有）**必须完全相同**；`info` 键名与 EXIF 标签数如有不同，逐条写进报告并说明原因；像素平均绝对差每通道 ≤ 1.0 视为一致，超过就停下来。把两份 JSON 与比较结论写进报告。

### C 文档（只动 `README.md`、`frontend/README.md`、`CLAUDE.md`、`PLAN.md`，以及 `docs/` 下除 `docs/tasks/` 之外的文件）

1. 全库搜索把 Next.js 或 Pillow 版本当作「当前事实」陈述的地方（例如 `README.md` 技术栈表「Next.js 16.3.3」、`frontend/README.md` 开头「Next.js 16.3.3」、`CLAUDE.md` 架构段「Next.js 16.2.6」），逐处改成 16.4.3 / Pillow 13.0.0。`docs/tasks/` 下的历史任务记录、`PLAN.md` 里已有的历史条目不改。
2. 在 `PLAN.md` 最新的变更记录处追加一条 2026-10-27 条目：两项升级的原因（附上面的漏洞编号）、修复版本、验证结果摘要（数字等主代理验收完再填，由主代理补）。
3. 报告里列出搜索命令、命中的每一处，以及改了哪些、为什么不改其余的。

## 5. 验收（主代理在工作流结束后亲自跑，原始输出摘要写进报告）

1. `git status --porcelain --untracked-files=all` 的改动集合 ⊆ 第 4 节白名单加 `docs/tasks/2026-10-27-deps-security/03-report.md`；`backend/.venv`、`frontend/node_modules`、`.next` 都不出现（被忽略）。
2. `git diff 0c80323 -- frontend/package.json backend/requirements.txt` 只有那三处版本变化。
3. 后端全量：`cd backend && .venv/bin/python -m pytest -q -p no:cacheprovider` 结果 `0 failed`、`0 skipped`，passed 数与基线 7744 相同（frontend/node_modules 已就位，前端相关测试不会跳过）。
4. `pip check`、`compileall`、`pip_audit` 通过；`npm ci`、`npm run lint`（0 errors、25 warnings）、`npx tsc --noEmit`、`npm run build`、`npm audit --audit-level=high --omit=dev` 通过。
5. 第 4 节 A5、B5 的对比结论为「一致」。
6. 主检出 `<Fiona 主检出>` 的 `git status` 与开工前相同，其 `backend/.venv` 里的 Pillow 仍是 12.3.0。
7. 在 `docs/tasks/2026-10-27-deps-security/03-report.md` 写报告：拆分表；修改了哪些文件；与任务清单的逐项对应；各项测试与审计的原始摘要行；锁文件变化清单；两份对比结论；未完成或需要人工确认的地方。
