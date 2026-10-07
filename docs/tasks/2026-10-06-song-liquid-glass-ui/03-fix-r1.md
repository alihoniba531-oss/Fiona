# 03 第 1 轮返修单（r1）

来源：Claude 机械门禁（全部通过）、实机截图验收（108 张 + 主题交互 8/8 通过）、独立代码复核（38 条意见，经对抗式验证成立 27 条）。下列每一条都要落实；遇到与规格冲突的，以本单为准（本单是规格方的裁决）。改完重跑规格 §10 第 1–7 条。不要回滚已完成的工作，不要提交 commit。

## 必修（P1/P2 与视觉缺陷）

**R1-1 滚动跟随失效（P1，ChatScrollArea.tsx:76）**：消息层铺满后底部让位改在内容层内边距上，ResizeObserver 用默认 content-box 观察，内边距变化（参考图托盘出现、「点此播放」行、多行输入、micNotice）不触发跟随，最新消息被压在输入釉片下且不出现「回到最新」。修法：`observer.observe(content, { box: "border-box" })`（视口同理检查）。验证：贴底时让 `--composer-height` 增大 180px，离底距离应仍为 0。

**R1-2 用户浮签没有右对齐（P1，ChatBubble.tsx:171）**：外层新增块级包裹后，用户分支只剩 `ml-auto max-w-[72%]`，短消息停在列宽约 28% 处。修法：用户分支加 `justify-end`（或恢复 `flex-row-reverse`）。验证：一个字的短消息在 1440 与 390 宽下，浮签右沿贴消息列右沿。

**R1-3 滚动视口缺 scroll-padding（P2，ChatScrollArea.tsx:117）**：键盘焦点会落进页头/输入釉片下面。修法：给滚动视口加与内容内边距一致的 `scroll-padding-top/bottom`（桌面 104px / `calc(var(--composer-height) + 36px)`；手机 `calc(114px + env(safe-area-inset-top))` / `calc(var(--composer-height) + var(--tabbar-h) + env(safe-area-inset-bottom) + 20px)`，按实际内边距取值），和 `.chat-scroll-content` 并列维护。

**R1-4 透镜把滚动文字拉成「条码」（视觉，Claude 实机截图发现）**：手机对话页页头下沿的透镜带，会把滚到页头下方的正文拉成竖条纹（390×844 截图里页头下方那一带清楚可见）；输入釉片上沿（桌面与手机）在用户上翻、正文从下方经过时同理。修法：
- 手机页头：**关闭页头透镜层**（页头是通栏，只有下沿一道透镜带，而那里正是正文经过处）。桌面页头保持现在「裁掉上下透镜带、只留左右两端」的做法不变。
- 输入釉片（桌面）与手机底部釉片：消息层在底部也加渐隐遮罩，让正文在**到达输入釉片上沿透镜带之前**淡出为 0（例如桌面：`#000 calc(100% - var(--composer-height) - 18px - 48px)` → `transparent calc(100% - var(--composer-height) - 18px - 20px)`；手机同理加上 `--tabbar-h` 与安全区），透镜只弯折背后的山水，不再采样正文。与顶部渐隐合成同一个 `mask-image`。
- 验证：构造一段足够长的对话（或用 transform 平移内容层），让正文分别压过手机页头下沿、桌面输入釉片上沿、手机底部釉片上沿，截图确认没有竖条纹；同时确认开放阅读区正文不被压淡（顶部渐隐仍在页头下沿之后 8px 内走完）。

**R1-5 系统触发素瓷时设置页开关状态不对（P2，settings/page.tsx:199）**：开关显示与 `aria-checked` 改用「实际是否素瓷」（effectiveSolid）。系统（`prefers-reduced-transparency` 或 `prefers-contrast: more`）强制素瓷时：开关显示为开、设为 `disabled`，说明行补一句「系统已开启减少透明度或增强对比度，素瓷由系统接管。」；系统未强制时照常可切换手动值。读屏念出的状态必须与画面一致。

**R1-6 抽屉滑入期间玻璃失效（P2，page.tsx:2054、2117）**：tw-animate 的 `animate-in` 会给祖先加 filter，截断 backdrop。修法：Glaze 及其任何祖先都不用 `animate-in/fade/zoom` 这类动 opacity/filter 的类；改为只动 transform 的自定义关键帧（如 `@keyframes glaze-slide-in{from{transform:translateX(-100%)}}`，300ms，`cubic-bezier(.22,.61,.36,1)`），替换当前对话记录抽屉与手机对话目录两处。减弱动态时不动画。

**R1-7 手机页头「免提」开关状态难辨（P2，globals.css:536）**：只清掉未选中项的边框（`.chat-header .chip:not(.chip-on){border-color:transparent}`），选中项保留清釉选中底（`var(--chip)` + 口沿），并给朗读、免提两个按钮加 `aria-pressed`（现有 aria-label 不动）。

**R1-8 768–900px（iPad 竖屏）桌面页头溢出（P2，page.tsx:2124）**：页头网格去掉硬最小值：`grid-cols-[minmax(0,auto)_minmax(48px,1fr)_auto]`，名字 `truncate`，状态字与副标题行 `whitespace-nowrap`，副标题在 `max-lg` 隐藏；若仍挤，在 `max-lg` 下把对话目录列收为页头按钮打开（沿用手机对话框的交互与焦点契约）。验证：768、800、834、1024 宽无溢出、无逐字竖排、「免提」可见。

## 应修（P3，成本低、收益明确）

**R1-9** ConversationPicker.tsx:54「历史」「新建」可见文字不在可访问名里：aria-label 改为「历史：当前对话记录」「新建：新对话」（保留原有语义词）。
**R1-10** ConversationPicker.tsx:110 手机对话框里 aside 套 aside：外层 `Glaze` 改 `as="div"`，地标只留内层。
**R1-11** Seal.tsx:5 与 AgentExchangeWorkspace.tsx:167：抽出 `lib/avatarGlyph.ts` 的 `avatarGlyph(avatar?: string): string | null`（trim；有 `Intl.Segmenter` 时按字素取首个，否则 `Array.from(s)[0]`；空或「✨」返回 null），Seal 与 AvatarMark 共用，消除不支持 Intl.Segmenter 的浏览器渲染崩溃与组合 emoji 被切坏。
**R1-12** layout.tsx:37 主题状态防重置：首帧脚本的 `sync()` 每次从 localStorage 重读两个键（失败时回落 dataset）；并加一个 `MutationObserver` 监听 `<html>` 的 class 与 `data-solid`，被外部抹掉时立即重新 sync（注意别和自身写入形成循环）。
**R1-13** page.tsx:2361 抽屉关闭时滑出动画丢失：`transition: transform 360ms cubic-bezier(.22,.61,.36,1), visibility 0s linear ${open ? "0s" : "360ms"}`，四处抽成一个 `drawerStyle(open)`；减弱动态下 `transition-delay` 也归零。
**R1-14** page.tsx:2407 iframe 抽屉（世界/设置）的外壳玻璃几乎全被不透明 iframe 盖住：两个 iframe 抽屉外壳 `lens={false}`、不做 backdrop（只留口沿与着色），加 `overflow-hidden` 让 iframe 吃到圆角。
**R1-15** page.tsx:2486 两处遮罩左缘切进导航釉片 12px：引入 `--rail-w: calc(var(--nav-w) + 12px)`（或按实际外边距），遮罩、抽屉宽度、左釉片宽度、历史抽屉 left 统一引用。
**R1-16** page.tsx:2357 手机端四个右侧抽屉：`max-md:top-0`、`max-md:rounded-none`（顶部补 safe-area 内边距），与手机对话框、历史抽屉的形态统一。
**R1-17** GeneratedImage.tsx:171 大图预览：`dialog::backdrop` 写不依赖继承的具体色（昼 `rgba(31,41,38,.18)`、夜 `rgba(0,0,0,.45)`）；对话框面板用不透明 `var(--hi)`（模态框不是清釉瓷片），口沿与阴影保留。
**R1-18** Sidebar.tsx:122 独立页手机底栏双口沿：非共享模式去掉内层 nav 的 `border-t`，口沿交给 Glaze。
**R1-19** page.tsx:2248 生图模型选择组在 DOM 里渲染了两份：只渲染一份，用 order 或 grid-area 在手机端挪到文本框上方，删掉失效的 order 规则。
**R1-20** 清理残留：删除 `state-dot` 的 JSX 与 CSS、`.glass` 旧选择器、ChatBubble 未用的 `agentAvatar` 字段与传参、page.tsx 里未使用的 effectiveSolid 与对 data-solid 的观察（**设置页的 effectiveSolid 保留，R1-5 要用**）、余额「<100」恒等分支、无边框元素上的 borderColor、重复的 `.dark` 滚动条规则；Sidebar.tsx:97 写成 `aria-controls={drawerId}`。
**R1-21** 中文数字日期格式化重复两份（history/page.tsx:38 等）：抽到 `lib/chineseDate.ts` 共用。
**R1-22** GeneratedImage.tsx:39 模型名前缀硬编码：改为与 `FALLBACK_IMAGE_MODELS` 同处的共享映射函数（显式处理 `-pro` 与未知 id：未知时只显示「AI 生成」，不编造名称）；装裱配方收成 `.mount-frame` 类，reference 变体不再叠行内 style。
**R1-23** MyAgentWorkspace.tsx:143 公开名片开关：说明 `<p>` 加 id，开关加 `aria-describedby` 指向它，读屏能听到关闭的后果说明。
**R1-24** globals.css 分层：把 Glaze 及其变体、对话页专用规则合并进 `@layer components`（同一组件不要一半在层内一半在层外），去掉重复选择器与已失效规则；确需无层的（减弱动态、素瓷降级、`@supports` 退路）集中放在文件末尾并注释原因。改完要用截图确认外观不变。
**R1-25** 字体缓存（部署层，不改 next.config.ts）：在 `docs/DEPLOYMENT.md` 的 Nginx 配置段补一段 `location /fonts/ { …; add_header Cache-Control "public, max-age=31536000, immutable"; }`（或 alias 到 `frontend/public/fonts`），说明切片文件固定不变、换字体须换目录名。本条允许修改 `docs/DEPLOYMENT.md`。

## 返修后输出

1. 每条 R1-x 的改法与位置；2. §10 第 1–7 条重跑结果（第 7 条的文档白名单本轮扩大为 README.md 与 docs/DEPLOYMENT.md）；3. R1-1、R1-2、R1-4、R1-8 的验证方法与结果（无法在沙箱实测的写明，Claude 会实机复验）；4. 未完成或需要确认的地方。
