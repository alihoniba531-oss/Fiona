# 热点话题展开层改为磨砂釉（L1）

## 1. 产品目标

「世界」页（`/plaza`，也以 `?embed=1` 嵌在主界面抽屉里）点开任一热点后，会在两列热点榜单上方浮出一层「话题详情」。
现在这层用的是 `.ceramic-card`：`--tile` 底色在昼间只有 50% 不透明、且**没有任何背景模糊**，底下两列榜单的文字清晰地透上来，与详情正文叠在一起，几乎无法阅读。

用户原话：「热点打开之后透明度太高，帮我修改成磨砂的」。

目标：展开层改为**磨砂釉**——底下的榜单、星图被强模糊成一片柔和的色块，只隐约可见明暗，详情正文清晰可读。

## 2. 技术约束

- 只改 `frontend/app/plaza/page.tsx` 一个文件。不改 `globals.css`、不改 `components/Glaze.tsx`、不新增 CSS 类、不引入依赖、不改任何测试。
- 材质必须复用现有组件 `Glaze`（该文件已 `import Glaze from "@/components/Glaze"`），用 `variant="slab"`——这是设计系统里的「厚釉」：`backdrop-filter: var(--bd-strong)`（22px 模糊）+ `var(--glass2)` 釉色。素瓷模式（`[data-solid]`）下这两个 token 会自动变为无模糊 + 不透明底，无需额外处理。
- **必须 `lens={false}`**：边缘透镜会把从下面穿过的文字拉成条码状条纹（本项目已知问题）；展开层底下就是满屏文字。
- 不开 `fur`。

## 3. 任务清单

在 `frontend/app/plaza/page.tsx` 中找到注释 `{/* 热点话题展开层；窄桌面 iframe 仍保留可读宽度。 */}` 下方的内层卡片：

```tsx
<div
  className="ceramic-card topic-drawer-in pointer-events-auto flex flex-col rounded-[18px]"
  style={{ width: "100%", maxWidth: 920, overflow: "hidden", borderColor: "var(--rule)" }}>
  ...
</div>
```

1. 把这个 `<div>` 换成 `<Glaze variant="slab" lens={false} ...>`，闭合标签同步改为 `</Glaze>`。
2. `className` 去掉 `ceramic-card`，其余类原样保留：`topic-drawer-in pointer-events-auto flex flex-col rounded-[18px]`。
3. `style` 保留 `width: "100%"`、`maxWidth: 920`、`overflow: "hidden"`，**删除 `borderColor`**（`Glaze` 的 `glaze-finish` 层已画出釉口沿，再加边框色会多一道线）。
4. 卡片内部（头部、内容区、来源列表、关闭按钮等）**一个字符都不改**。外层定位容器（`absolute z-30 ...` 那个 div）也不改。
5. 同文件里「发布到世界」弹窗等其他 `ceramic-card` 不在本单范围，不要动。

## 4. 验收标准

在 `frontend/` 下执行：

1. `git status --porcelain` —— 除本规格所在的 `docs/tasks/2026-10-07-topic-overlay-frosted/` 外，只有 `M frontend/app/plaza/page.tsx`。
2. `git diff --stat` —— 只有 `frontend/app/plaza/page.tsx`，改动行数 ≤ 10。
3. `npx tsc --noEmit` 退出码 0。
4. `npx eslint app/plaza/page.tsx` 退出码 0。
5. `grep -n 'ceramic-card topic-drawer-in' app/plaza/page.tsx` 无输出；`grep -n 'variant="slab" lens={false}' app/plaza/page.tsx` 恰好 1 行。

不要运行 `npm run build` 或 `npm run dev`（沙箱内 Turbopack 会 EPERM），构建与截图由 Claude 在沙箱外完成。

## 5. 什么时候停下来问

本单不需要停下来问。若发现 `Glaze` 不接受 `style` 或 `lens` 等属性导致类型错误，在总结里说明原因，不要改 `Glaze.tsx`。

---

## 第 2 版（2026-10-07，用户验收后修订——本节覆盖上文 §2–§4）

### 用户反馈

第 1 版改成 `Glaze variant="slab"` 后，用户看完回复：「还是改回去，模糊背景就行」。

**不接受的设计**：热点展开层换成厚釉（`glaze-slab`，72% 不透明釉色）——太实、太闷，丢了原来瓷片的通透感。
**要的是**：外观完全回到原来的 `.ceramic-card` 瓷片（同样的底色、口沿、边框），**只**在它背后加背景模糊，让底下的榜单糊开、不再清晰透字。

### 任务清单（第 2 版）

只改 `frontend/app/plaza/page.tsx`：

1. 把第 1 版的改动**完全撤回**：`<Glaze variant="slab" lens={false} ...>` / `</Glaze>` 改回原来的 `<div ...>` / `</div>`，`className` 恢复为 `"ceramic-card topic-drawer-in pointer-events-auto flex flex-col rounded-[18px]"`，`style` 恢复 `borderColor: "var(--rule)"`。撤回后这一段应与 `git show HEAD:frontend/app/plaza/page.tsx` 逐字节一致。
2. 在这个 `<div>` 的 `style` 对象里、`borderColor` 之后，**新增两行**：
   ```tsx
   backdropFilter: "var(--bd)",
   WebkitBackdropFilter: "var(--bd)",
   ```
   `--bd` 是设计系统已有 token（昼 `blur(16px) saturate(1.5) brightness(1)`，夜同模糊、亮度 .84，素瓷模式自动为 `none`），不要写死数值，不要用 `--bd-strong`。
3. 其他任何地方一个字符都不改；`import Glaze` 保留（文件别处在用）。

### 验收标准（第 2 版）

在仓库根目录执行：

1. `git status --porcelain` —— 除 `docs/tasks/2026-10-07-topic-overlay-frosted/` 外，只有 `M frontend/app/plaza/page.tsx`。
2. `git diff --numstat` —— 恰好 `2	0	frontend/app/plaza/page.tsx`（相对 HEAD 只新增 2 行、删除 0 行）。
3. `git diff` 的两行新增内容就是上面两行 `backdropFilter` / `WebkitBackdropFilter`。
4. 在 `frontend/` 下：`npx tsc --noEmit` 退出码 0；`npx eslint app/plaza/page.tsx` 退出码 0。
5. `grep -c 'variant="slab" lens={false}' frontend/app/plaza/page.tsx` 输出 `0`。

同样不要运行 `npm run build` / `npm run dev`。
