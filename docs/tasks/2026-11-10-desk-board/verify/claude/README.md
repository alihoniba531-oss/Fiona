# 案头第一期 · 验收方的脚本与结果

这里是规格作者（验收方）在实施方沙箱之外用的脚本，以及最后一轮的结果。它们不是产品代码，也不进 CI；留在这里是为了以后改案头时能照着再跑一遍。

## 脚本

| 文件 | 作用 | 用法 |
|---|---|---|
| `gate_desk.py` | 机械门禁：规格快照、改动白名单、`page.tsx` 字面量与 BOM、设计门禁、tsc / lint / build、新测试与全量 | `python3 -I gate_desk.py <工作树> spec-hashes.txt [--skip-build] [--skip-full]` |
| `mut_desk.py` | 变异测试：把实现改坏一处，跑 `backend/tests/test_desk_*.py`，必须有非自检用例变红，再按原字节还原 | 在工作树的克隆副本里跑：`python3 -I mut_desk.py <副本>`；`MUT_ONLY="M75 ,M76 "` 只跑指定项，`MUT_DOCK_ONLY=1` 只跑用到容器竞态用例的项 |
| `mut_desk_combined.py` | 两处「单独拆一道不变红」的双重保险，两道一起拆必须变红 | `python3 -I mut_desk_combined.py <副本>` |
| `seed_desk.py` | 给隔离环境造数：一本在等批准细纲的书、一本完结的书和它的两个短片项目 | 先 `. env.example.sh`（改好两个目录），再 `cd <工作树>/backend && .venv/bin/python <本目录>/seed_desk.py` |
| `walk_desk.py` | 真实界面走查（Playwright，1440 / 1280 / 390），只做免费操作 | `uv run --no-project --with playwright==1.63.0 python walk_desk.py --base http://127.0.0.1:3061 --out <截图目录>` |
| `env.example.sh` | 隔离环境的变量（临时库、开发登录、占位密钥） | 见文件里的注释 |

`spec-hashes.txt`、`out/page-tsx-r2.sha256`、`out/r4-files.sha256` 是门禁要读的快照。门禁里写死了这一单的基线（提交 `9adf34c`、全量 7911 条）和各轮的文件哈希，合并之后再跑会报红，那时它只能当写法参考。

变异要在克隆副本里做，不要在真实工作树里做（macOS 上 `cp -cR <工作树> <副本>` 是瞬时的写时复制）。

## 最后一轮的结果（`results/`）

| 文件 | 内容 |
|---|---|
| `gate-r5.txt` | R5 之后的门禁：56 项全过；新测试 100 条、全量 8011 条，0 失败、0 跳过 |
| `mutations-r4.txt` | R4 之后的全部变异（73 项加去 BOM）。当时报红 5 项：M20 是脚本自己的锚点问题（修正后见 `mutations-r4-m20.txt`）；M41、M43 是双重保险（见 `mutations-r4-combined.txt`）；M62、M65 单元测试抓不到，由走查覆盖 |
| `mutations-r4-g9-before-fix.txt` | 第三轮复核指出的问题在 R4 上的复现：M75（非冲突 409 后不替换方案）100 条全过 |
| `mutations-r5-dock.txt`、`mutations-r5-combined.txt` | R5 之后重跑所有用到容器竞态用例的变异：M75 变红；M41、M43、M65 与 R4 时相同 |
| `walk-r4.txt`、`walk-r4.json` | R4 之后的走查：113 项全过。R5 没有改源码，没有重跑 |
| `walk-r4-positive-control.txt` | 走查的正控：把 M62、M65 两处同时改坏后，对应的 5 项检查报红，其余 108 项照常通过 |

走查截图没有放进仓库。

## 单元测试没有覆盖、靠走查覆盖的行为

- 方案已锁定时在修改对话框里再点「保存」，不发请求（M62）。
- 分集的修改 / 合并 / 批准对话框开着时来一张项目卡，不换项目、不关对话框（M65）。

规格 14.2 把给这两处补行为用例列为留给作者裁定的事项。
