# 验收脚本与结果（工作室续拆）

派单方在执行者沙箱外跑的验收材料。脚本里的路径都由参数或当前目录决定，不含本机路径。

| 文件 | 作用 |
|---|---|
| `mut_serial.py` | 变异测试：在工作树的写时复制克隆里逐项把实现改坏一处，跑对应的新测试，必须变红；用法见文件开头。`--dry` 只检查锚点是否都能命中。 |
| `seed_serial.py` | 走查造数：在隔离临时库里造一本写到第 5 章的连载书；`--extend` 让它「接着写」到第 12 章（改第 3 章正文、第 4 章标待复核、圣经新登记 C2 阿禾）。 |
| `walk_server.py` | 走查后端：起 FastAPI，并把工作室导演模型换成本地假模型（每次调用先等 4 秒），不访问外部服务、不计真实费用。 |
| `walk_serial.py` | 真实浏览器走查（Playwright）：从书斋「做成片」到首次拆解、同步、续拆、重新批准，共 42 项检查。 |

走查环境要求（导出后再运行）：临时库与临时目录（`FIONA_DB_PATH`、`FIONA_UPLOADS_DIR`、`FIONA_STUDIO_DIR`、`FIONA_SONG_DIR`），`DEV_MODE=1`，`FIONA_NOVEL=1`、`FIONA_NOVEL_USERS=tester`，`FIONA_STUDIO=1`、`FIONA_STUDIO_OWNERS=tester`、`FIONA_STUDIO_REQUIRE_JWT=0`，`FIONA_STUDIO_BRAIN_DEFAULT=qwen`（默认 claude 会让假模型找不到提供方），以及足够的工作室额度变量。后端在候选副本的 `backend/` 下用 `.venv/bin/python walk_server.py` 起在 8064，前端 `FIONA_BACKEND_ORIGIN=http://localhost:8064 next dev -p 3064`，再运行：

```
uv run --no-project --with playwright==1.63.0 python walk_serial.py --base http://127.0.0.1:3064 --extend-cmd "<造数 --extend 命令>" --out <截图目录>
```

`results/`：

- `gate-final-summary.txt`：合并前最后一次门禁（新测试、相关既有测试、后端全量 8352 passed / 0 skipped、无 node_modules 副本）的结果与各步退出码；
- `mutations-r1.txt`：R1 后变异测试，84 项杀 81 项（存活 3 项的判断见 `07-review-r2.md` 与 `02-spec.md` §4.10）；
- `walk-r1.json`：R1 后真实浏览器走查 42/42；
- `head-check-r0.txt`：把三个新测试文件放到基线 `135253f` 上运行的结果（70 failed / 8 passed / 1 error，失败都是旧代码不支持新功能，无收集错误）。
