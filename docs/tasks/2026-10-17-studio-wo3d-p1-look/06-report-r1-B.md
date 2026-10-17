# WO3d-P1 返修 R1：块 B（提示词）报告

- 范围：`02-spec.md` §3 的块 B 文件，外加 `backend/studio/prompts/style_proposals.md`。
- 只改块 B 文件；未联网、未读 `.env`、未提交。

## 改动文件

- `backend/studio/casting_prompts.py`
- `backend/studio/prompts/casting_look.md`
- `backend/studio/prompts/style_proposals.md`
- `backend/tests/test_studio_casting_prompts.py`
- `docs/tasks/2026-10-17-studio-wo3d-p1-look/06-report-r1-B.md`

## 逐项对应

### 可 7：造型行改为「标题 → 版式 → 造型 → 外形」

- `casting_prompts.py:276`：先输出版式。
- `casting_prompts.py:278`：再输出造型行。
- `casting_prompts.py:305`：同步更新 `build_sheet_prompt` 文档字符串。
- 裁剪逻辑未改：仍是 extra_prompt → description → 风格 → appearance → 造型 → 参考图说明。
- 测试：`test_studio_casting_prompts.py:200` 改为断言
  `标题 < 版式 < 造型 < 外形`；原有 1800 字与裁剪顺序测试继续通过。

### 可 8：`casting_look.md` 措辞

- `casting_look.md:1`：声明本任务是「造型设计」，允许补全原文未写到的服装、妆容、配饰与材质。
- `casting_look.md:3`：明确这是全局「不得编造人物外形」的例外，但不得与原文外形和锁定特征矛盾。
- `casting_look.md:5`：说明 `synopsis` 只用来判断时代、身份和处境，不作为外形事实。
- `casting_look.md:9`：明确某项没有内容时写「无」，不能留空。
- `casting_look.md:11`：禁止真实品牌、真人姓名，以及服装或道具上的文字字样、字母、logo、标签。
- 渲染侧：`casting_prompts.py:260-269` 的 `_look_line` 将值为「无」的字段视为空并跳过。
- 测试：
  - `test_studio_casting_prompts.py:224`：人物和道具的「无」字段都被跳过。
  - `test_studio_casting_prompts.py:319`：模板包含空值、synopsis 用途、造型设计例外、品牌与文字禁令。

### 可 10（提示词部分）：`style_proposals.md` 旧版式文案

- `style_proposals.md:5`：人物与道具改为「一图两区：三视图加细节栏」。
- 测试：`test_studio_casting_prompts.py:330` 断言新文案存在、旧说法「道具按三视图加一处细节特写」不存在。

## 测试结果

先在新测试 + 旧实现上确认失败：

```text
4 failed, 23 deselected
```

失败项：

- `test_look_line_follows_look_fields_and_skips_empty`
- `test_look_line_skips_fields_marked_none`
- `test_casting_look_template_handles_empty_synopsis_design_scope_and_brands`
- `test_style_proposals_uses_one_image_two_zone_layout`

改完后：

```text
cd backend && <py> -m pytest -q tests/test_studio_casting_prompts.py
27 passed in 1.19s

cd backend && <py> -m pytest -q tests/ -k studio
1600 passed, 5550 deselected, 32 warnings in 69.17s
```

## 未完成项

- 无。
