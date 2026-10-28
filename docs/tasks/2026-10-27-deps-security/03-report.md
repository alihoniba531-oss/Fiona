# 2026-10-27 依赖安全升级验收报告

工作树：`<本工作树>`  
分支：`fix/deps-security`  
基线：`0c80323`  
规格：`docs/tasks/2026-10-27-deps-security/02-spec.md`

结论：**通过（PASS）**。`next`、`eslint-config-next` 已精确升级到 16.4.3，`Pillow` 已精确升级到 13.0.0；生产依赖审计和 `pip_audit` 均为 0 发现；升级前后路由冒烟与 Pillow 图像路径对比一致。未改业务代码、测试代码或 CI 配置。

## 1. 拆分与代理

只派出以下 3 个代理，均由 `workflow` 工具在同一个 `parallel()` 中并行启动（workflow id `workflow-1`）。每个任务的提示词都包含规格第 2、3 节和它自己的任务项，并明确禁止调用 `subagent`、`subagent_fork`、`workflow`。没有代理失败，没有重派，没有额外代理。

| 代理 | 范围 | 白名单文件 | 结果 |
|---|---|---|---|
| A 前端 | Next.js 16.4.3 / eslint-config-next 16.4.3、路由冒烟、锁文件与前端门禁 | `frontend/package.json`、`frontend/package-lock.json`、新增 `verify/route_smoke.py` | 完成 |
| B 后端 | Pillow 13.0.0、去元数据/参考图/Claude 缩图对比 | `backend/requirements.txt`、新增 `verify/compare_pillow.py` | 完成 |
| C 文档 | 当前版本事实、PLAN 变更记录 | `README.md`、`frontend/README.md`、`CLAUDE.md`、`PLAN.md` | 完成；主代理复核时修正 1 处历史条目误改 |

三个代理的文件范围互不重叠。B 额外用 Pillow 13.0.0 跑了一次后端全量测试，主代理随后又按第 5 节独立跑了一遍。

## 2. 最终修改文件

已跟踪文件：

- `README.md`：技术栈表 Next.js 16.4.3。
- `frontend/README.md`：开头 Next.js 16.4.3。
- `CLAUDE.md`：架构段 Next.js 16.4.3。
- `PLAN.md`：仅追加 2026-10-27 依赖安全升级条目；已存在的 2026-08-26 历史审计快照不改（见 §5）。
- `frontend/package.json`：`next` 16.3.8 → 16.4.3；`eslint-config-next` 16.3.8 → 16.4.3，均为精确版本。
- `frontend/package-lock.json`：只由 `npm install --save-exact next@16.4.3 eslint-config-next@16.4.3` 产生。
- `backend/requirements.txt`：`Pillow==12.3.0` → `Pillow==13.0.0`，其余行不动。

新增文件：

- `docs/tasks/2026-10-27-deps-security/verify/route_smoke.py`
- `docs/tasks/2026-10-27-deps-security/verify/compare_pillow.py`
- `docs/tasks/2026-10-27-deps-security/03-report.md`（本报告）

开工前已存在的未跟踪规格 `docs/tasks/2026-10-27-deps-security/02-spec.md` 未修改。`backend/.venv`、`frontend/node_modules`、`frontend/.next` 均存在但被 `.gitignore` 忽略，不出现在 `git status --porcelain --untracked-files=all` 中。

## 3. A 前端

### A1 升级前基线

- 使用旧锁文件 `npm ci`：exit 0，`added 426 packages, and audited 427 packages`。
- `FIONA_BACKEND_ORIGIN=http://127.0.0.1:8091 npm run build`：exit 0。
- 构建横幅：`▲ Next.js 16.3.8 (Turbopack)`。
- 构建日志：`/tmp/fiona-deps/build-before.log`。
- 旧锁文件副本：`/tmp/fiona-deps/package-lock.before.json`。

### A2/A3 路由冒烟脚本与升级前结果

脚本：`docs/tasks/2026-10-27-deps-security/verify/route_smoke.py`，只使用 Python 标准库；`--frontend-dir`、`--output`、两个端口和超时全部从参数或环境变量读入，没有硬编码本机绝对路径。假后端由当前 Python 的 `-m http.server` 提供无扩展名 `health` 文件，前端用 `npx --no-install next start`；两个子进程使用独立进程组，退出时只停止自己启动的进程组。

升级前运行 exit 0，写入 15 个 case：`/tmp/fiona-deps/route-before.json`。

| Cookie | 路径 | 状态 | Location |
|---|---|---:|---|
| 无 | `/`、`/history`、`/settings`、`/agents/abc`、`/novels/abc`、`/studio/abc` | 307 | `/login` |
| 无 | `/login` | 200 | — |
| `fiona_token=x` | `/`、`/history`、`/agents/abc`、`/novels/abc`、`/studio/abc`、`/novels?embed=1` | 200 | — |
| `fiona_token=x` | `/login` | 307 | `/` |
| 无 | `/api/health` | 200 | —，正文 `fiona-stub-ok` |

页面响应的三个头在两个版本中完全一致：

- `Content-Security-Policy`：`default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob: data:; font-src 'self' data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'self'`
- `X-Frame-Options`：`SAMEORIGIN`
- `Permissions-Policy`：`camera=(), geolocation=(), microphone=(self)`

`/api/health` 由 rewrite 转发，三个头为 `null`，升级前后也一致；正文确实是 `fiona-stub-ok`，证明 `/api/:path*` rewrite 生效。

### A4 升级与升级后验证

- `npm install --save-exact next@16.4.3 eslint-config-next@16.4.3`：exit 0。
- `git diff -- frontend/package.json`：只有两个版本值变化，无 `^`；`react`/`react-dom` 仍为 19.2.4。
- 删除 `frontend/node_modules`、`frontend/.next` 后 `npm ci`：exit 0，`added 426 packages`。
- 升级后 `npm run build`：exit 0，横幅 `▲ Next.js 16.4.3 (Turbopack)`，18 条路由与升级前相同。
- 升级后冒烟 exit 0，15 个 case：`/tmp/fiona-deps/route-after.json`。
- 同一构建重复运行第三次（`route-after-2.json`）仍逐字节相同，证明 JSON 不含时间戳/PID 等易变字段。

### A5 升级前后比较与构建警告

- `cmp /tmp/fiona-deps/route-before.json /tmp/fiona-deps/route-after.json`：exit 0，**逐字节相同**。
- 三个文件的 SHA-256 均为：
  `5e1042099f5386268e0a2afa4f4a593702e9656faf01f6c62a69ddbf83d4981a`
- 主代理在最终 `npm ci`/`npm run build` 后又跑了一次冒烟，`route-acceptance.json` 仍为同一 SHA-256。
- 构建日志没有 `Invalid next.config`、`Unrecognized key` 或项目配置 `deprecated` 告警；没有新增 `⚠` 行。A 的两次升级构建都只有相同的 Node 26 既有告警 `DEP0205: module.register() is deprecated`（主代理验收构建没有出现该行）；这不是项目配置告警。

### A6 锁文件变化

锁文件 `lockfileVersion` 3，包条目 501 → 501（不计根 `""` 条目；含根 entry 为 502 → 502），新增 0、删除 0，版本变化 13 个：

| 包 | 旧版本 | 新版本 |
|---|---|---|
| `node_modules/next` | 16.3.8 | 16.4.3 |
| `node_modules/eslint-config-next` | 16.3.8 | 16.4.3 |
| `node_modules/@next/env` | 16.3.8 | 16.4.3 |
| `node_modules/@next/eslint-plugin-next` | 16.3.8 | 16.4.3 |
| `node_modules/@next/swc-darwin-arm64` | 16.3.8 | 16.4.3 |
| `node_modules/@next/swc-darwin-x64` | 16.3.8 | 16.4.3 |
| `node_modules/@next/swc-linux-arm64-gnu` | 16.3.8 | 16.4.3 |
| `node_modules/@next/swc-linux-arm64-musl` | 16.3.8 | 16.4.3 |
| `node_modules/@next/swc-linux-x64-gnu` | 16.3.8 | 16.4.3 |
| `node_modules/@next/swc-linux-x64-musl` | 16.3.8 | 16.4.3 |
| `node_modules/@next/swc-win32-arm64-msvc` | 16.3.8 | 16.4.3 |
| `node_modules/@next/swc-win32-x64-msvc` | 16.3.8 | 16.4.3 |
| `node_modules/fastq` | 1.20.1 | 1.20.3 |

`fastq` 是 `eslint-config-next@16.4.3 → @next/eslint-plugin-next → fast-glob → @nodelib/fs.walk → fastq` 的传递依赖。A 用升级前 `package.json` + 旧锁文件在 `/tmp/fiona-deps/repro-frontend` 重放同一条 `npm install`，得到与工作树逐字节相同的 `package.json` 和 `package-lock.json`，证明它是该指定命令的确定性产物，不是 `npm audit fix`、`--force` 或手工改锁文件。锁文件还包含两个不改变已安装版本的依赖范围元数据变化：`next` 的 `sharp` 范围 `^0.35.4→^0.35.5`，`eslint-config-next` 的 `eslint-plugin-react-hooks`/`typescript-eslint` 范围更新；没有新增或删除包。

### A7 lint / TypeScript / audit

| 命令 | 退出码 | 原始摘要 |
|---|---:|---|
| `npm run lint` | 0 | `✖ 25 problems (0 errors, 25 warnings)` |
| `npx tsc --noEmit` | 0 | 无输出 |
| `npm audit --audit-level=high --omit=dev` | 0 | `found 0 vulnerabilities` |
| `npm audit --audit-level=high` | 1 | `1 high severity vulnerability`：`zod <4.6.6`，GHSA-mrhx-c7xc-m3w5 |

- lint 与升级前日志逐字节相同，仍是 0 errors / 25 warnings。
- `zod 4.4.3` 是 `eslint-config-next → eslint-plugin-react-hooks → zod` 的开发依赖；升级前后锁文件里的版本不变，生产依赖审计为 0。按规格“全量 audit 仅记录”，未用 `npm audit fix`。

## 4. B 后端

### B1/B2 升级、环境与检查

- `backend/requirements.txt` 仅 `Pillow==12.3.0` → `Pillow==13.0.0`，其余行不动。
- 新建 `backend/.venv`：Python 3.14.6。
- `backend/.venv/bin/python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt`：exit 0。
- `import PIL; PIL.__version__`：`13.0.0`。
- `pip check`：exit 0，`No broken requirements found.`（沙箱提示 pip 缓存目录不可写，已用 `PIP_CACHE_DIR`/`--cache-dir` 规避）。
- `compileall`：exit 0，无输出，排除 `.venv`。
- `pip_audit -r backend/requirements.txt --progress-spinner off`：exit 0，`No known vulnerabilities found`。

首次 `pip_audit` 有一条沙箱缓存权限警告，原文为：

```text
WARNING:pip_audit._cache:Failed to write to cache directory, performance may be degraded: [Errno 1] Operation not permitted: '~/Library/Caches/pip-audit/...'
No known vulnerabilities found
```

指定 `/tmp` 缓存后干净复跑仍为 0 发现；这是环境缓存权限警告，不是审计发现。

### B3 对比脚本

`docs/tasks/2026-10-27-deps-security/verify/compare_pillow.py`：

- 只使用 Python 标准库 + Pillow；夹具全部在内存生成，不读仓库外文件。
- `run --output ... --pixels ...`：调用 Fiona 真实函数，记录 format、size、mode、帧数、每帧时长、loop、info 键集合、EXIF 标签数/标签、ICC 是否存在及 sha256、XMP/GPS/tEXt 残留、首帧 RGBA 的 sha256 和原始像素文件。
- `compare --before ... --after ... --before-pixels ... --after-pixels ... --output ...`：比较成败、异常类型/状态码/文案、format、size、mode、帧数、时长、loop、returned media_type/size、ICC、元数据残留；info/EXIF/png chunk 差异只记录；像素按通道计算平均绝对差和最大差，任一通道平均值 > 1.0 即失败。
- 输出 JSON 不含时间戳或绝对路径；像素文件名稳定。
- 脚本没有硬编码本机绝对路径（已用 grep 检查）。

### B4 升级前后运行

升级前使用主检出只读解释器：

```bash
PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=<worktree>/backend \
FIONA_UPLOADS_DIR=/tmp/fiona-deps/uploads \
<Fiona 主检出>/backend/.venv/bin/python \
docs/tasks/2026-10-27-deps-security/verify/compare_pillow.py run \
--output /tmp/fiona-deps/pillow-before.json \
--pixels /tmp/fiona-deps/pillow-before-pixels
```

运行前确认 `PIL.__version__ == "12.3.0"`；exit 0。升级后使用工作树 `.venv` 同样运行，确认 13.0.0；exit 0。两轮均为 9 个成功用例、4 个预期 HTTP 400。主提取出的结果文件是 `/tmp/fiona-deps/pillow-before.json`、`/tmp/fiona-deps/pillow-after.json`。

成功用例在两版本中的结果（完全一致）：

| 用例 | format | size | mode | 帧数 | 时长 | loop | ICC |
|---|---|---|---|---:|---|---|---|
| strip JPEG（GPS/Orientation=6/ICC/XMP） | JPEG | 800×1200 | RGB | 1 | `[null]` | null | 有 |
| strip MPO 两帧 | JPEG | 1000×700 | RGB | 1 | `[null]` | null | 无 |
| strip PNG（tEXt/iCCP/调色板透明） | PNG | 600×400 | RGBA | 1 | `[null]` | null | 有 |
| strip GIF 三帧透明 | GIF | 240×160 | P | 3 | `[100,200,300]` | 0 | 无 |
| strip WebP 静态 EXIF | WEBP | 900×600 | RGB | 1 | `[0]` | 1 | 无 |
| strip WebP 三帧动画 | WEBP | 320×200 | RGB | 3 | `[120,180,240]` | 0 | 无 |
| 参考图 EXIF 方向 | PNG | 800×1200 | RGB | 1 | `[null]` | null | 无 |
| Claude JPEG 3000×2000 | JPEG | 2000×1333 | RGB | 1 | `[null]` | null | 无 |
| Claude 透明 PNG 2400×1800 | PNG | 2000×1500 | RGBA | 1 | `[null]` | null | 无 |

四个预期失败用例在两版本中也完全相同：

- 8000×6000 PNG：HTTP 400 `图片内容损坏或尺寸过大`
- 301 帧 GIF：HTTP 400 `动图帧数过多，请压缩后再发`
- 参考图超长比例：HTTP 400 `参考图片过长或过窄，请裁剪到 4:1 以内的比例`
- 参考图超大像素：HTTP 400 `参考图片尺寸过大，请选择不超过四千万像素的图片`

### B5 对比结论

主代理用升级后的 Pillow 13.0.0 重新执行 `compare`：

```text
Pillow before=12.3.0 after=13.0.0 cases=13
...
RESULT: PASS
PILLOW_COMPARE_EXIT=0
```

- `pass: true`
- 13/13 `match`，0 mismatch，0 problems
- 9 个成功用例的像素：每通道平均绝对差 `0.0`，最大差 `0`，像素 sha256 全部相同
- info 键名差异：0 条
- EXIF 标签数/标签差异：0 条
- 两个保留 ICC 的用例，ICC sha256 均为
  `ee02182b6200fda47aa0a41b35614ebf65a9c6171972c03896605c9a4874215e`
- XMP/GPS/tEXt 残留全部为 false；JPEG 输出 EXIF 标签数 0、GPS IFD 0；PNG strip 输出 chunk 为 `IHDR,iCCP,IDAT,IEND`，无文本 chunk。

### B 的额外回归

B 在升级后的虚拟环境里跑了：

- 全量 `python -m pytest -q`：`7744 passed, 35 warnings in 332.33s`，0 failed、0 skipped。
- `tests/test_upload_metadata.py`：`74 passed in 5.34s`。
- 24 个导入 PIL 的测试文件子集：`1149 passed, 33 warnings`。

规格写 `tests/test_upload_metadata.py` 有 30 个用例；实测该文件有 30 个 `def test`、23 处 `parametrize`，参数化展开后为 74 个用例。以实测为准记录，未修改测试；这是描述数量差异，不影响回归结论。

B 第一次全量测试曾因本机 `NO_PROXY` 含 `[::1]` 导致 httpx 收集阶段报 `Invalid port: ':1]'`（17 个 collection error），设置干净的 `NO_PROXY=localhost,127.0.0.1,::1` 重跑通过。这是本机环境问题，主代理验收也使用了同样清理；不是 Pillow 或代码失败。

## 5. C 文档

### C1 搜索命令与命中

使用并复核了两条搜索（`docs/tasks` 按规格排除）：

```bash
grep -RIn --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.git --exclude-dir=docs/tasks \
  -E 'Next\.js[[:space:]]*16\.[0-9]+\.[0-9]+|next[= ]16\.[0-9]+\.[0-9]+|Pillow[= ]1[0-9]\.[0-9]+\.[0-9]+|Pillow==1[0-9]' \
  README.md frontend/README.md CLAUDE.md PLAN.md docs

grep -RIn --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=.git --exclude-dir=docs/tasks \
  -E '16\.3\.(3|8)|16\.2\.6|Pillow' \
  README.md frontend/README.md CLAUDE.md PLAN.md docs
```

改动前命中与处理：

| 位置 | 原文/性质 | 处理 |
|---|---|---|
| `README.md:25` | 技术栈表 `Next.js 16.3.3`，当前事实 | 改为 `16.4.3` |
| `frontend/README.md:3` | 开头 `Next.js 16.3.3`，当前事实 | 改为 `16.4.3` |
| `CLAUDE.md:8` | 架构段 `Next.js 16.2.6`，当前事实 | 改为 `16.4.3` |
| `PLAN.md:252` | 位于「2026-08-26 历史审计结果」的快照，`Next.js 16.3.3` | **不改**；C 初判为当前基线并误改，主代理复核后恢复原文 |
| `PLAN.md:338` | 2026-08-26 历史条目「Next.js 升级至 16.3.3」 | 不改 |
| `docs/ARCHITECTURE.md:444` | 只写 `Pillow` 库名，无版本号 | 不改 |

另有 `Next.js 16` 大版本表述（`frontend/README.md:9`、`CLAUDE.md:87`、`PLAN.md:238`、`docs/ARCHITECTURE.md:114`），升级后仍准确，不改；`PLAN.md:5` 的 `Next.js 14` 位于明确的历史说明中，不改；`docs/DEPLOYMENT.md:16` 只写 `Next.js`，无版本号，不改。

Pillow 当前版本号在文档中无命中；`backend/requirements.txt` 的 `Pillow==13.0.0` 由 B 修改。

### C2 PLAN 变更记录

`PLAN.md` 末尾在 2026-10-18 写歌条目之后追加：

`## 2026-10-27：依赖安全升级（Next.js 16.4.3 与 Pillow 13.0.0）`

条目包含三个 GHSA 漏洞编号、两项修复版本、Pillow 37 个已知漏洞，以及主代理验收后的数字摘要。`PLAN.md` 的两个 2026-08-26 历史条目未改。

### C3 最终状态

当前事实处为 `README.md:25`、`frontend/README.md:3`、`CLAUDE.md:8` 和新增 `PLAN.md:499` 的 16.4.3；`PLAN.md:252`/`:338` 保留历史 16.3.3，符合「已有历史条目不修改」。`docs/tasks/` 下已跟踪文件零改动。

## 6. 主代理验收

### 6.1 白名单与版本 diff

撰写本报告前的 `git status --porcelain --untracked-files=all`：

```text
 M CLAUDE.md
 M PLAN.md
 M README.md
 M backend/requirements.txt
 M frontend/README.md
 M frontend/package-lock.json
 M frontend/package.json
?? docs/tasks/2026-10-27-deps-security/02-spec.md
?? docs/tasks/2026-10-27-deps-security/verify/compare_pillow.py
?? docs/tasks/2026-10-27-deps-security/verify/route_smoke.py
```

写入本报告后只多出白名单内的：

```text
?? docs/tasks/2026-10-27-deps-security/03-report.md
```

`02-spec.md` 开工前即存在，未被写入。没有任何业务代码、测试、CI 配置或其它依赖文件出现在改动集合中。`backend/.venv`、`frontend/node_modules`、`frontend/.next` 均未出现在未跟踪列表（被忽略）。

`git diff 0c80323 -- frontend/package.json backend/requirements.txt` 只有三处版本变化：`next`、`eslint-config-next`、`Pillow`；`git diff --check` exit 0。

### 6.2 后端全量

在 `backend/` 运行：

```bash
NO_PROXY='localhost,127.0.0.1,::1' no_proxy='localhost,127.0.0.1,::1' \
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

结果：

```text
7744 passed, 35 warnings in 298.06s (0:04:58)
PYTEST_EXIT=0
```

0 failed、0 skipped，passed 数与基线 7744 相同；`frontend/node_modules` 已就位，前端相关测试未跳过。日志：`/tmp/fiona-deps/accept-pytest.log`。

### 6.3 后端其它门禁

| 命令 | 退出码 | 原始摘要 |
|---|---:|---|
| `.venv/bin/python -m pip check` | 0 | `No broken requirements found.` |
| `.venv/bin/python -m compileall -q -x '(^|/)\.venv/' backend` | 0 | 无输出 |
| `.venv/bin/python -m pip_audit -r backend/requirements.txt --progress-spinner off --cache-dir /tmp/fiona-deps/pip-audit-cache` | 0 | `No known vulnerabilities found` |

`pip check` 在沙箱里另有一条 pip 缓存目录不可写警告，不影响结果；`pip_audit` 使用 `/tmp` 缓存后无该警告。工作树 Pillow 版本实测 `13.0.0`。

### 6.4 前端门禁

主代理重新执行：

```text
npm ci                                      exit 0  added 426 packages, and audited 427 packages
npm run lint                                exit 0  ✖ 25 problems (0 errors, 25 warnings)
npx tsc --noEmit                            exit 0  无输出
FIONA_BACKEND_ORIGIN=... npm run build      exit 0  ▲ Next.js 16.4.3 (Turbopack)，18/18 静态页
npm audit --audit-level=high --omit=dev     exit 0  found 0 vulnerabilities
npm audit --audit-level=high                exit 1  1 high severity vulnerability: zod <4.6.6
```

- `npm ci` 的 `1 high severity vulnerability` 是上面已说明的 dev-only `zod 4.4.3`，生产审计为 0。
- 构建日志：`/tmp/fiona-deps/accept-build.log`；无 `Invalid next.config`、`Unrecognized key` 或项目配置 `deprecated` 告警。
- 主体验收构建后再次执行路由冒烟：`ROUTE_EXIT=0`、`wrote 15 cases`，结果与升级前逐字节相同（`ROUTE_BYTES_IDENTICAL`）。

### 6.5 对比结论

- **A5**：`route-before.json`、`route-after.json`、主代理 `route-acceptance.json` 三份 SHA-256 完全一致；状态码、Location、三个响应头、`/api/health` 正文全部一致。
- **B5**：13/13 match，0 problems，像素差 0；info/EXIF 差异 0；ICC sha256 一致；XMP/GPS/tEXt 全部无残留。**两项对比结论均为“一致”。**

### 6.6 主检出

- 开工前和验收后的 `<Fiona 主检出>` `git status --porcelain --untracked-files=all` 逐字节相同（`MAIN_STATUS_IDENTICAL`），未修改、未安装、未升级、未删除。
- 主检出 `backend/.venv` 的 Pillow 仍为 **12.3.0**；只读运行了升级前对比。
- 工作树 3091/8091 在冒烟后均 free；未占用 3000、8000、8010。

## 7. 未完成/需要人工确认

1. **未提交、未推送**。按仓库约定没有 Git commit；GitHub Actions 的实际 Node 20 CI 需作者推送 `fix/deps-security` 后确认。本地使用 Node 26.4.0 / npm 11.17.0、Python 3.14.6。
2. **全量 `npm audit --audit-level=high` 仍有 dev-only `zod 4.4.3` high 告警**（GHSA-mrhx-c7xc-m3w5），升级前已存在，按规格只记录、不修。生产 `--omit=dev` 为 0。
3. **`fastq` 的 1.20.1 → 1.20.3** 是指定 `npm install` 的确定性传递依赖刷新，已用旧锁文件重放复现；没有新增/删除包，也没有手动改锁文件。若要求锁文件只允许 Next 家族变化，这里需要人工确认是否接受该 npm 解析结果。
4. **本机 `NO_PROXY` 环境问题**：含 `[::1]` 时 httpx 会在 pytest 收集阶段报 `Invalid port: ':1]'`；验收用干净的 `NO_PROXY` 重跑通过。这是沙箱环境，不是代码/依赖变更。
5. **规格数量差异**：`tests/test_upload_metadata.py` 是 30 个测试函数、参数化后 74 个用例；实测 74 passed。未改测试，按实测记录。
6. **C 的一处误改已纠正**：`PLAN.md:252` 属于 2026-08-26 历史审计快照，C 初判为当前基线改成 16.4.3；主代理按「PLAN 已有历史条目不改」恢复为 16.3.3。当前版本的记录在 `PLAN.md:499` 的新条目中。
