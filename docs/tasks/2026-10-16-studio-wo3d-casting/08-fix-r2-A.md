# R2-A 后端编排（先读 08-fix-r2-common.md）

## 只许改的文件
- `backend/studio/casting.py`
- `backend/studio/casting_jobs.py`
- `backend/studio/store.py`
- `backend/routers/studio.py`
- 测试：`backend/tests/test_studio_casting_api.py`、`test_studio_casting_jobs.py`、`test_studio_casting_integration.py`、`test_studio_casting_migration.py`

## 要修的项
- **必须修复 1、2、4、5**：按公共说明里的口径改。
  - 修复 1 要同时统一 `test_studio_casting_api.py:455` 和 `test_studio_casting_jobs.py:348` 两处口径相反的断言。
- **可优化 a**：`start_sheets` 里的确认报价和建任务放进同一个 `BEGIN IMMEDIATE` 事务。撞到日上限或中途失败时，报价保持 open，不被烧掉。
- **可优化 b**：执行前的预检失败（参考图已归档、文件缺失、HTTPException 等）归为 `rejected` 并释放预留，不能落到 uncertain。`start_sheets` 时也重新校验一次引用。
- **可优化 c**：试听里只要包含 CosyVoice 变体，就先用 `shutil.which("ffmpeg")` 和 `shutil.which("ffprobe")` 预检，缺了返回 409/503，此时不发任何付费请求。
- **可优化 d、e、f**：
  - d、e 按公共说明处理。
  - f：自定义风格的 `name` 和 `visual_style` 必须非空，否则 422。
- **可优化 g（后半）**：`casting_jobs.execute` 里的 `get_job`（约 342 行）以及所有可能抛错的 DB 读取都移进 try，任何异常都不能让任务停在 running。
- **可优化 i、存疑 1**：参考图统一输出 PNG 字节（与 `tools/image_generation.py:526` 一致），保证与 `data:image/png` 标签一致。
- **可优化 j**：在 `store.py` 的 `_ADDED_COLUMN_INDEXES` 里加一条部分唯一索引 `(item_id, role, version_no) WHERE item_id IS NOT NULL`，带表存在守卫。迁移测试补一条用例，验证新旧库都能建出这条索引。
- **可优化 k**：提交失败清理文件时，先确认没有别的资产引用同一个 `rel_path`，确认无引用才删。
- **可优化 m（前半）**：PATCH 条目时 `locked_features` 上限改为 600 字，超出返回 422。

## 验证
```
cd backend && <py> -m pytest -q tests/test_studio_casting_api.py tests/test_studio_casting_jobs.py tests/test_studio_casting_integration.py tests/test_studio_casting_migration.py
cd backend && <py> -m pytest -q tests/ -k studio
```
