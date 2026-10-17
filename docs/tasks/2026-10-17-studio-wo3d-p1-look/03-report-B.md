# 块 B 报告：提示词与造型说明任务

## 改动文件

| 文件 | 位置 | 内容 |
|---|---|---|
| `backend/studio/casting_prompts.py` | 12–17 | `LOOK_FIELDS`（顺序与中文标签照契约）、`LOOK_MAX_CHARS = 200` |
| 同上 | 21–34 | 新版 character / prop 版式；location 不变；`_FRAME` 改为按 kind 取用，角色与道具的留白、纯白背景、无文字说明只保留一份 |
| 同上 | 149–178 | `CASTING_LOOK_SCHEMA` 及构造辅助：`looks[]`，`kind` 只允许 character / prop，`look` 必填字段按 kind 取自 `LOOK_FIELDS`，所有对象 `additionalProperties: false` |
| 同上 | 181–235 | `look_inputs`：最多 10 条、只收 character / prop、每条只带六个约定字段、synopsis 截到 600 字、style 取 name / visual_style / palette / lighting / realism；不带 excerpt |
| 同上 | 260–270 | `_look_line`：按 `LOOK_FIELDS` 顺序拼「造型：发型……；妆容……；……」，空字段跳过，未知字段忽略，单字段限 200 字 |
| 同上 | 273–297 | `_render`：造型行紧跟在「定妆人物：名称」之后、外形之前；版式、锁定特征、负向、原创声明位置不变 |
| 同上 | 300–365 | `build_sheet_prompt(..., look=None)`；裁剪顺序 extra_prompt → description → 风格段 → appearance → 造型说明；参考图说明仍为最后兜底 |
| `backend/studio/prompts/casting_look.md` | 1–11 | 新导演任务模板：只按外形 / 描述 / 锁定特征 / 风格补全；锁定特征优先；要求写颜色、面料、款式、磨损，禁止「普通衣服」类空话；每字段 ≤60 字；沿用不可信素材措辞 |
| `backend/tests/test_studio_casting_prompts.py` | 30–56 | 更新新版式断言 |
| 同上 | 200–259 | 造型行顺序 / 空字段跳过 / 道具字段 / 场景忽略 look / 裁剪顺序 / 参考图兜底 |
| 同上 | 261–295 | `CASTING_LOOK_SCHEMA` 接受两类、拒绝缺字段、多余字段、错 kind、超长字段与顶层多余字段，并验证 Claude schema 转换 |
| 同上 | 297–340 | 模板要求与 `look_inputs` 的摘要、600 字截断、10 条上限、无 excerpt |

未改动块 A / 块 C 的文件。报告本身为本文件。

## 逐项对应

- **§2.1 造型字段**：`LOOK_FIELDS` 与 `LOOK_MAX_CHARS` 名字、顺序、中文标签完全照契约；未新增数据库列。
- **§2.2 导演任务 `casting_look`**：
  - `CASTING_LOOK_SCHEMA` 形状为 `{"looks":[{"item_id","kind","look"}]}`；`kind` 用 `enum` 表达 character / prop 二选一，`look` 用 `anyOf` 按 kind 分支，分支内必填全部对应字段且禁止额外字段。
  - `look_inputs` 不含 `excerpt` 或任何原文摘录；`synopsis` 压到 600 字以内；`items` 最多 10 条。
  - `casting_look.md` 覆盖契约的全部四类要求；不可信素材句与 brain 现有措辞一致。
- **§2.4 出图提示词**：
  - character / prop 已替换为「左侧三视图 + 右侧细节栏」的 16:9 横幅版式；location 原样保留。
  - 造型行紧跟主体名称、位于外形之前；空字段跳过，字段顺序严格按 `LOOK_FIELDS`。
  - 总长仍由 `PROMPT_LIMIT = 1800` 控制；裁剪顺序严格为 extra_prompt → description → 风格段 → appearance → 造型说明。
  - 版式、主体名称、locked_features、负向、原创声明在裁剪循环中不参与，始终完整。
  - 旧 `_FRAME` 中与新版式重复的留白 / 纯白 / 文字限制已合并到按 kind 的 frame，不再重复或矛盾；保留「边缘清晰便于抠像」。

## 测试结果

```text
cd backend
/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/test_studio_casting_prompts.py
24 passed
```

```text
cd backend
/Users/yangjing/Desktop/ai-workspace/Fiona/backend/.venv/bin/python -m pytest -q tests/ -k studio
1597 passed, 5550 deselected, 32 warnings in 67.62s
```

32 条 warning 均为既有 `slowapi` 的 `asyncio.iscoroutinefunction` DeprecationWarning，与块 B 无关。块 A 的集成测试已用真实 `casting_prompts` 跑过 Seedream 请求体，包含新版式「细节栏」关键字。

## 未完成项

无。

需主控确认的一处解释：按「造型说明紧跟在『主体名称』之后」的字面要求，造型行放在标题行与版式行之间；如果希望改为「版式行之后、外形行之前」，只需调整 `_render` 中该行的插入位置，不影响契约的其他部分。

另：契约未把参考图说明列入五段裁剪顺序，块 B 保持其原有的最后兜底位置，避免先删参考图说明。
