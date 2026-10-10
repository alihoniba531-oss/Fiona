# 返修单 R1b（更正 R1-5 的代理变量）

日期：2026-10-09。与 `02-spec.md`、`05-fix-r0.md`、`05-fix-r1.md` 同等效力，冲突处以本单为准。

## 起因

`05-fix-r1.md` 的 R1-5 写了「改变请求目标、请求头、凭据或**代理**的变量一并加入 `FORBIDDEN_ENV`」，措辞过宽。实施方据此把 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY` 及其大小写形式共 8 项加入了禁用清单。这与产品要求冲突：

- Anthropic 的接口不对中国大陆提供服务，作者本机与可能的服务器都靠出站代理访问 Claude 与其他厂商。禁用代理变量会让 BYOK 在这些环境里整体不可用。
- 代理变量由运维控制，属于服务器出站配置，不是攻击面。预设厂商都走 HTTPS，经代理时是 CONNECT 隧道、端到端 TLS，代理看不到 Key。
- 自定义地址已经 `trust_env=False`，并用固定 IP 连接（6.3.3），不受代理影响。这一点保持不变。

## 要求

1. 从 `byok/crypto.py` 的 `FORBIDDEN_ENV` 中删除全部代理变量（8 个名字），连同代理变量名大小写不敏感的匹配逻辑一起删除。保留 `ANTHROPIC_CUSTOM_HEADERS`，清单变为 11 项。
2. 预设厂商（含 Claude）照常遵循服务器的 `HTTP(S)_PROXY` / `ALL_PROXY` / `NO_PROXY`。custom 不信任环境代理，现有测试已覆盖「设置 `HTTPS_PROXY` 不影响 custom 连接目标」，保持不变。
3. 测试：
   - 本轮新增的「代理变量使 BYOK 不可用」断言，属于编码了被本单撤销行为的断言，按 `05-fix-r1.md` 第 0 节规则改为：设置任一代理变量（含小写、混合大小写）时 `availability()` 仍为可用，SDK 构造器照常被调用。
   - 新增一条断言：预设厂商的 openai 客户端在 `HTTPS_PROXY` 存在时仍可构造并按 SDK 默认读取代理，custom 不读取。可用构造参数或 httpx mounts 判断，不发真实网络请求。
4. 文档：README、CLAUDE、PLAN、`docs/ARCHITECTURE.md`、`docs/DEPLOYMENT.md`、`backend/.env.example` 中「十九项」改回「十一项」，删去代理变量相关表述，并补一句：「预设厂商（含 Claude）遵循服务器的 HTTP(S)_PROXY / NO_PROXY 出站代理设置；自定义地址不使用环境代理。」
5. `03-report.md` 第 5 节审计表把 8 个代理变量改为「不加入」，理由写「运维控制的出站代理；预设走 HTTPS 隧道；custom 已 `trust_env=False` 并固定 IP」。R1 返修表的 R1-5 行同步更正。

## 验收

第 7 节第 1–6 条重跑；`grep -n "PROXY\|proxy" backend/byok/crypto.py` 无输出；全量 pytest 通过数不少于本轮前。
