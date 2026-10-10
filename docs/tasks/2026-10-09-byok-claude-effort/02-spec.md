# Claude 思考强度选择（L2，含一列数据库字段）

基线：`main` @ `7163acd`。
- 后端 `python -m pytest -q`：沙箱外 **2818 passed**。
- 前端 `npx eslint .`：**0 errors / 25 warnings**。

本文引用代码以**函数名与原文片段**为准，行号仅供参考。

## 1. 产品目标与已拍板的决定

用户已能用自带的 Claude Key 聊天（上一单「每用户自带聊天模型 BYOK」，规格见 `docs/tasks/2026-10-09-byok-chat-model/`）。目前 Claude 的思考强度在代码里写死为 `low`。本单让用户自己选择。作者已拍板：

1. **只开放三档**：低 / 中 / 高，对应 Anthropic 的 `low` / `medium` / `high`。不开放 `xhigh` / `max`：这两档常要思考数分钟，聊天里容易超时，也更费用户额度。
2. **只对 Claude 生效**：配置的厂商是 `anthropic` 时才显示和生效。其他厂商不显示，请求也不变。
3. **默认低**：已有配置与新配置都默认 `low`，与现状完全一致；用户可随时调高。
4. **入口**：
   - 聊天输入框底栏，在「聊天：Claude（Anthropic）· 型号（不扣草莓）」旁边，一键切换；
   - 设置页「聊天模型」分区里也能选。

   两处都是**立即生效并保存到服务端**（跟随账号，换设备也一样），不需要再点「保存」。

## 2. 已核实的外部事实（来自 Anthropic 官方文档）

- `claude-opus-5-5`、`claude-sonnet-5-5`、`claude-haiku-5-5` 都支持 `output_config={"effort": "low"|"medium"|"high"|"xhigh"|"max"}`。官方默认分别为 medium、high、medium；本项目一律显式传值。
- 三个型号的思考都是自适应、默认开启，思考文本默认不返回（`display` 为 omitted）。现有代码不传 `thinking` 参数，保持不变。
- **`max_tokens` 同时限制「思考 + 正文」**。调高 effort 必须同时放大 `max_tokens`，否则正文可能被截断甚至为空。
- 调高后首个正文字之前会有一段较长停顿（模型在思考），流里会有保活事件，不会因为没有字节而触发读超时。

## 3. 技术约束

- 沿用现有结构，不做无关重构，不引入新依赖。
- **受保护文件**（本单不得修改）：
  - 后端：`backend/llm.py`、`backend/intent_router.py`、`backend/mode_switcher.py`、`backend/crisis_model.py`、`backend/safety.py`、`backend/persona.py`、`backend/tools/`、`backend/utils/safe_http.py`、`backend/byok/url_safety.py`、`backend/byok/crypto.py`、`backend/services/chat_service.py`、`backend/routers/chat.py`；
  - 本单之前就存在、且与 BYOK 无关的全部测试文件。
- **允许修改的既有测试**：`backend/tests/test_byok_*.py` 中的断言，**只有**在它恰好编码了本单要改变的行为时才能改，例如：
  - 公开配置字段的精确集合里加入 `effort`；
  - PATCH 请求体的允许字段；
  - provider 元数据的精确结构。

  每一处都要在报告中列出「原断言 → 新断言 → 依据本规格哪一条」。不得放宽任何其他断言。新用例写进新文件 `backend/tests/test_byok_effort.py`。
- **不得**修改 OpenAI 兼容厂商（dashscope / deepseek / moonshot / zhipu / custom）的任何请求参数。
- **测试连接**（`test_connection`）仍固定 `effort=low`、`max_tokens=1024`，不受用户选择影响。
- 文档里不得写入本机绝对路径。

## 4. 任务清单

### 4.1 数据库：`user_model_configs` 新增 `effort` 列

- `backend/byok/store.py` 的 `USER_MODEL_CONFIGS_DDL` 增加一列：

  ```sql
  effort TEXT NOT NULL DEFAULT 'low'
  ```

  不加 CHECK，合法性在应用层校验，保证新库、老库结构一致。
- `backend/database.py` 的 `init_db` 中，紧跟在执行 `USER_MODEL_CONFIGS_DDL` 之后，用现有 `_safe_migrate` 执行：

  ```sql
  ALTER TABLE user_model_configs ADD COLUMN effort TEXT NOT NULL DEFAULT 'low'
  ```

  老库（已有该表、但没有这一列）启动时自动补列，已有行取 `'low'`。
- 不新增迁移版本号，`/health` 不变。

### 4.2 存储与接口（`backend/byok/store.py`、`backend/byok/providers.py`、`backend/routers/chat_model.py`）

1. **常量**：`providers.py` 新增

   ```python
   CLAUDE_EFFORTS = ("low", "medium", "high")
   DEFAULT_EFFORT = "low"
   ```

   并加 `validate_effort(value)`：
   - 不是这三个字符串之一 → `ConfigurationError("思考强度只能是低、中、高")`。
2. **provider 元数据**：`public_provider_metadata()` 为每家厂商增加两个字段：
   - `efforts`：anthropic 为 `["low","medium","high"]`，其余为 `null`；
   - `default_effort`：anthropic 为 `"low"`，其余为 `null`。
3. **公开配置**：`_PUBLIC_FIELDS` 加入 `effort`，GET 返回 `config.effort`。
   - 数据库里读到的值若不在三档内（理论上不会发生），对外与内部一律按 `"low"` 处理，不报错。
4. **PUT `/chat-model`**（保存配置）：请求体**不接受** `effort`，仍是 `extra=forbid`。
   - 保存时保留原有 `effort`：`ON CONFLICT ... DO UPDATE` 不改 `effort`。
   - 新插入的行用默认值 `'low'`。
   - 从其他厂商换成 anthropic、或从 anthropic 换走时，`effort` 原样保留，只是非 anthropic 时不生效。
5. **PATCH `/chat-model`**：请求体从只接受 `{"enabled"}` 扩展为 `{"enabled"?: bool, "effort"?: str}`，至少要有一个字段，否则 400「请求格式不正确」。校验仍沿用现有的「不经 Pydantic 默认 422、固定文案」写法。
   - 带 `effort` 时：
     - 校验值；
     - 当前配置的厂商不是 anthropic → 400「只有 Claude 支持思考强度」；
     - 修改 effort **不要求** Key 可解密，`needs_reentry` 状态也能改。
   - 带 `enabled` 时：行为完全不变（开启时仍要求 status ok）。
   - 两者同时带时，在同一事务里处理；任一校验失败则整体不改。
   - 响应体仍为 `{"config": 公开配置}`，带 `no-store`。
   - 限流沿用现有的 `10/minute`。
   - 函数可以把 `set_enabled` 扩展或改名为 `update_options(username, *, enabled=None, effort=None)`，调用方同步修改。
6. **内部配置**：`get_internal_config` 返回的 dict 带 `effort`。

### 4.3 Claude 请求参数（`backend/byok/client.py`）

普通聊天和镜子模式下，anthropic 分支按配置的 `effort` 取值。非法值或缺失按 `low` 处理。

| effort | output_config.effort | max_tokens 普通 / 镜子 | 本条总时限 |
|---|---|---|---|
| low | `low` | 4096 / 2048（与现状相同） | `total_seconds()`（默认 120 秒） |
| medium | `medium` | 8192 / 4096 | `total_seconds()` |
| high | `high` | 16384 / 8192 | `min(240, total_seconds() * 1.5)`（默认 180 秒） |

- 正文字符上限仍为普通 4000、镜子 600，不变。
- 测试连接仍为 `low` / 1024 / `total_seconds()`。
- 总时限要通过参数传给 `_Resources`，例如 `_Resources(deadline_seconds)`；默认值仍是 `total_seconds()`，使非 Claude 路径行为不变。
- R2 留下的中断与关闭分离、发送前检查 `resources.closed` 等逻辑，一行都不能改坏。
- Opus / Sonnet 的 `betas` 与 `fallbacks="default"` 不变。
- 不传 `thinking`，不传采样参数。

### 4.4 前端

**`frontend/lib/chatModel.ts`**
- 类型增加：`config.effort`；provider 的 `efforts`、`default_effort`。
- 新增 `setChatModelOptions(options: { enabled?: boolean; effort?: "low" | "medium" | "high" }, signal)`，发 PATCH。原 `setChatModelEnabled` 改为调用它。
- 显示文案映射：`low` → 低，`medium` → 中，`high` → 高。

**`frontend/app/page.tsx` 的 `ChatModelFooter`**
- **显示条件**：同时满足以下几条时，在「聊天：…（不扣草莓）」与「改用平台」之间显示一个小的三档切换。
  - `chatMode` 为真；
  - `config.enabled`；
  - `config.provider === "anthropic"`；
  - `config.status === "ok"`。
- **形态**：
  - 一组 `role="radiogroup"`、`aria-label="思考强度"` 的按钮：「思考 低 | 中 | 高」，当前档 `aria-checked`；
  - 左右方向键可切换；
  - 样式沿用底栏现有的 `btn btn-quiet` 体系，不另起风格；
  - 手机宽度下允许换行，不得横向溢出。
- **点击**：发 PATCH `{effort}`。
  - 进行中禁用整组；
  - 成功后更新本地 config 并 `publishChatModelRevision()`；
  - 失败时按 R3-1 的规则显示错误：只有该操作自己产生的错误，才能被它自己或下一次操作清除，后台刷新不得清除。
  - 聊天请求进行中（`loading`）也禁用。
- 每档按钮带 `title` 简短说明，例如：
  - 「低：最快，适合闲聊」
  - 「中：更周全，稍慢」
  - 「高：最周全，最慢、最费你的额度，单条最长约 3 分钟」

**`frontend/components/ChatModelSection.tsx`（设置页）**
- **显示条件**：已保存的配置是 anthropic，且当前所选厂商也是 anthropic 时，在型号下方显示「思考强度」三档（与底栏同一组件或同一写法）。
- 点击立即 PATCH 生效，不受「保存」按钮控制，也不影响「有未保存的修改」的判断。
- 下方说明：「调高后 Claude 会先思考再回答：更周全，但更慢、更费你自己的额度；高档单条最长约 3 分钟。只对 Claude 生效。」
- 尚未保存 Claude 配置、或保存的是其他厂商时，不显示这一组，只在选中 Claude 时提示一句「保存后可选择思考强度」。
- 跨 iframe 同步沿用现有的 `CHAT_MODEL_REV_KEY`：底栏改了，设置抽屉刷新后显示新值；反之亦然。刷新不得覆盖用户的草稿（现有规则）。

**通用**
- 不在 localStorage 存 effort。
- 气泡标注不变。

### 4.5 文档

README、CLAUDE.md、PLAN.md、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md` 中描述 BYOK 的位置，补充以下内容：
- Claude 可选思考强度低 / 中 / 高，默认低；
- 各档的 `max_tokens` 与总时限，高档为 `min(240, FIONA_BYOK_TOTAL_SECONDS×1.5)`，必须小于 Nginx 的 300 秒；
- 其他厂商不受影响；
- `user_model_configs` 新增 `effort` 列，老库启动时自动补列（表结构清单处也要更新）；
- 用户的额度消耗会随档位上升。

### 4.6 测试（新文件 `backend/tests/test_byok_effort.py`；沿用现有 byok 测试的断网夹具写法）

1. **老库升级**：用不含 `effort` 列的旧 DDL 建表并插入一行，然后调用 `init_db`。断言：
   - 列已存在；
   - 旧行的 effort 为 `low`；
   - GET 返回 `effort: "low"`；
   - 再调用一次 `init_db` 不报错（幂等）。
2. **元数据与默认值**：
   - 只有 anthropic 的 `efforts` 为三档、`default_effort` 为 `low`，其余为 `null`；
   - 新保存的 Claude 配置 effort 为 `low`。
3. **PATCH effort**：
   - 合法三档逐一成功，GET 反映新值；
   - 非法值（`"xhigh"`、`"max"`、`""`、数字、`null`、多余字段）返回 400 固定文案，且响应不回显输入；
   - 非 anthropic 配置改 effort 返回 400「只有 Claude 支持思考强度」；
   - `needs_reentry` 状态可以改 effort；
   - 同时带 `enabled` 与 `effort` 时：任一非法则整体不改；
   - 空请求体返回 400。
4. **PUT 保留 effort**：先把 effort 改成 `high`，再 PUT 换型号或换 Key，effort 仍为 `high`；PUT 带 `effort` 字段返回 400。
5. **请求参数**：用真实 anthropic SDK + MockTransport（或现有抓包写法）断言请求体：
   - 三档各自的 `output_config` 与 `max_tokens`，普通与镜子模式都要覆盖；
   - 测试连接永远是 `low` / 1024；
   - deepseek 等 OpenAI 兼容厂商即使库里 effort 为 `high`，请求体也与现状逐字相同。
6. **总时限**：monkeypatch `total_seconds` 后断言三档实际传入看门狗的秒数（例如 120 → 120 / 120 / 180；200 → 200 / 200 / 240）。
7. 删号仍删除整行（含 effort），不需要新逻辑，加一条断言即可。

前端没有测试框架，用 `npx tsc --noEmit` 与 `npx eslint .` 把关。浏览器实测由 Claude 在沙箱外完成。

## 5. 验收标准（在仓库根目录执行）

1. `git status --porcelain` 只出现以下变动：
   - 修改：`backend/byok/store.py`、`backend/byok/providers.py`、`backend/byok/client.py`、`backend/routers/chat_model.py`、`backend/database.py`、`frontend/lib/chatModel.ts`、`frontend/app/page.tsx`、`frontend/components/ChatModelSection.tsx`；
   - 若有合乎第 3 节规则的断言修改：`backend/tests/test_byok_*.py`；
   - 新增：`backend/tests/test_byok_effort.py`、本任务目录；
   - 第 4.5 节涉及的文档。
2. `git diff --exit-code -- backend/llm.py backend/intent_router.py backend/mode_switcher.py backend/crisis_model.py backend/safety.py backend/persona.py backend/tools backend/utils/safe_http.py backend/byok/url_safety.py backend/byok/crypto.py backend/services/chat_service.py backend/routers/chat.py` 退出码为 0；且 `git diff --stat -- backend/tests` 中只出现 `test_byok_*.py`。
3. `grep -n "xhigh\|\"max\"" backend/byok/providers.py backend/byok/client.py` 无输出（不得开放这两档）。
4. 在 `backend/` 下：`python -m pip check` 通过；`python -m pytest -q` 中 passed ≥ 2818 + 新增用例数（沙箱内因端口或回环权限导致的既有失败和 skip 可忽略，由 Claude 在沙箱外重跑）。
5. 在 `frontend/` 下：`npx tsc --noEmit` 退出码为 0；`npx eslint .` 为 0 errors，warnings ≤ 25。

不要运行 `npm run build` / `npm run dev`，不要启动后端，不要安装任何包，不要发起任何真实网络请求。

## 6. 什么时候停下来问

- 只有当某项要求**无法实现或互相矛盾**、会影响「做出什么」时，才停下来，在报告里写明原因与证据。例如：anthropic SDK 1.12.1 不接受某档 effort；必须修改受保护文件才能实现。不回滚已完成的工作。
- 只影响「怎么写测试 / 怎么验证」的细节，自行决定并说明。
- 遇到上一单 R2-3 那类「规格示例与既有逻辑矛盾」的情况，**必须停下来问**，不得自行发明规则。
