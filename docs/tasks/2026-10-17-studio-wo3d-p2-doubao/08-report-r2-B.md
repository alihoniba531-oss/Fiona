# WO3d-P2 返修 R2：块 B（提示词）报告

- 范围：`07-fix-r2-rules.md` 块 B。
- 只改块 B 名下文件；未联网、未读 `.env`、未提交。

## 改动文件

- `backend/studio/prompts/casting_look.md`
- `backend/studio/casting_prompts.py`
- `backend/tests/test_studio_casting_prompts.py`
- `docs/tasks/2026-10-17-studio-wo3d-p2-doubao/08-report-r2-B.md`

## 逐项对应

### B1. `casting_look.md` 补充常态造型规则

- `casting_look.md:10`：新增「只描述角色的『常态造型』」段落，明确被风吹乱、淋湿、受伤、脏污、汗湿、狼狈等临时状态一律不写；拿不准时写这些状态发生之前的样子。
- `casting_look.md:12`：发型要求写清长度、分缝、层次、是否扎起或盘起、发色，整体整齐有型、轮廓清楚，禁止「凌乱」「碎发遮脸」。
- `casting_look.md:12`：锁定特征与外形里的疤痕、胎记、纹身、痣等标志性特征要写明位置并清晰露出，不得被头发、帽子、口罩或配饰遮挡。
- `casting_look.md:12`：妆容按身份写素颜、淡妆、舞台妆等，不写「憔悴」「狼狈」这类临时状态。
- 对应测试：`test_casting_look_template_requires_normal_state_neat_hair_and_visible_marks`（`test_studio_casting_prompts.py:362`），逐项断言常态造型、六类临时状态、发型六要素、整齐度用词、露出要求、三类妆容与禁用词。

### B2. 人物版式追加造型指示，并保持 1800 字裁剪规则

- `casting_prompts.py:25-27`：`_LAYOUTS["character"]` 追加「发型整齐有型、轮廓清楚；标志性特征（疤痕、胎记等）清晰可见，不被头发或配饰遮挡；呈现角色常态造型，不表现风吹、淋湿、受伤等临时状态。」
- 场景与道具版式未改。
- 对应测试一：`test_character_layout_requires_neat_hair_and_visible_marks`（`test_studio_casting_prompts.py:350`）断言人物提示词含新句，且场景与道具不含这些字样。
- 对应测试二：`test_prompt_limit_holds_for_worst_case_with_full_look_and_many_notes`（`test_studio_casting_prompts.py:139`）构造最坏情况：600 字锁定特征、8×200 字造型、超长风格/外形/说明/补充要求、40 条参考图说明，断言总长 ≤ `PROMPT_LIMIT`（1800）、锁定特征与新版式句完整保留。
- 固定段实测：600 字锁定特征 + 80 字名字时，加入新句后不可裁剪部分约 1039 字，仍为 1800 字预算留出约 761 字余量。

## 测试结果

先写新测试并在旧代码上运行，确认失败：

```text
3 failed, 27 deselected
FAILED test_prompt_limit_holds_for_worst_case_with_full_look_and_many_notes
FAILED test_character_layout_requires_neat_hair_and_visible_marks
FAILED test_casting_look_template_requires_normal_state_neat_hair_and_visible_marks
```

修改后：

- `cd backend && <py> -m pytest -q tests/test_studio_casting_prompts.py` → `30 passed`
- `cd backend && <py> -m pytest -q tests/ -k studio` → `1679 passed, 5550 deselected, 32 warnings`（warnings 均为既有 slowapi/asyncio 弃用告警）

## 未完成项

无。
