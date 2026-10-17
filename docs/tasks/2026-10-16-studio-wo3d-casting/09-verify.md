# WO3d 验收记录

## 机械验证（R2 之后，沙箱外）
- 等同 CI（无 `frontend/node_modules`，提交快照副本）：6979 passed，145 skipped
- 工作区（有 node_modules）：7124 passed
- 前端：`npm run lint` 0 error（25 个 warning 都是已有文件里的）；`tsc --noEmit` 通过；`npm run build` 通过

## 复核
- DeepSeek 按清单初查（`06-precheck.md`）：发现旧库升级时 `init_db` 崩溃，已在 R1 修复，并补了回归测试（`test_studio_casting_migration.py`）
- Sonnet 第 1 轮（`04-review.md`）：不通过，必须修复 5 项
- Sonnet 第 2 轮（`04-review-r2.md`）：通过，必须修复 1–5、可优化 a–k 和 m、存疑 1 全部已修

## 界面核对（演示数据，8061/3061）
- 开工确认、风格提案、定妆版本网格（2560×1440）正常显示
- uncertain 的出图显示「可能已扣费」，并提供「释放」
- 试听音频能播放
- 390px 宽度下没有横向溢出
- G0 未批准时只显示门禁提示

## 留到后续
- `casting.py` 里的 `_single_item` 判断孤儿用的是项目已发布的拆解，`GET /casting` 用的是活动拆解。重新拆解期间，单条目接口返回的 `orphaned` 和列表不一致。前端每次变更后会整体刷新，用户看不出来。修复时要注意：不能在写事务里另开连接去读分集方案。
- 试听条数上限（可优化 l）
- 定妆缩略图：放到 WO5 镜头墙一起做
- 合并后用真实 Key 做冒烟：1 张定妆图 + 1 条中文试听，约 ¥0.3，执行前先报价确认。要核对的点：
  - Ark 是否接受 PNG 参考图的 data URI
  - CosyVoice 按什么口径计字符
  - Seedream 实际单价
  - 冒烟前要先在 venv 里装 `edge-tts==7.3.1`

## 执行者用量
- DeepSeek Flash 共 12 个任务，按空闲时段价约 ¥12.3
