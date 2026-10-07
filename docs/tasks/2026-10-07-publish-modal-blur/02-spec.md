# 「发布到世界」弹窗加背景模糊（L1）

## 1. 产品目标

「世界」页（`/plaza`，也以 `?embed=1` 嵌在主界面抽屉里）点「发布照片」选好文件后，会弹出「发布到世界」窗口。
窗口卡片用的是 `.ceramic-card`：昼间底色只有 50% 不透明、没有背景模糊，背后只有一层很淡的 `--scrim` 遮罩，底下的热点榜单文字会透进卡片。

同页的「热点话题展开层」已在提交 12cfff1 用同样的方式修好（`docs/tasks/2026-10-07-topic-overlay-frosted/02-spec.md` 第 2 版）。用户原话：「发布到世界也改成模糊背景」。

用户已明确的审美取舍（来自上一单验收）：**保留原瓷片的通透外观，只加背景模糊**；不接受换成厚釉 `Glaze variant="slab"` 之类更实的材质。

## 2. 技术约束

- 只改 `frontend/app/plaza/page.tsx` 一个文件。不改 `globals.css`、不改任何组件、不新增 CSS 类、不引入依赖、不改任何测试。
- 模糊值用设计系统已有 token `var(--bd)`（昼 `blur(16px) saturate(1.5) brightness(1)`，夜同模糊、亮度 .84，素瓷模式自动为 `none`）。不要写死数值，不要用 `--bd-strong`。
- 外层遮罩（`fixed inset-0 z-50 ... bg-[color:var(--scrim)]` 那个 div）不改；模糊加在卡片本身上，与热点展开层做法一致。

## 3. 任务清单

在 `frontend/app/plaza/page.tsx` 中找到 `{showModal && (` 下方的卡片 `<div>`——`className` 由 `cn("ceramic-card w-full max-w-sm overflow-hidden rounded-[18px] mobile:overflow-y-auto", ...)` 生成，当前为：

```tsx
style={{ borderColor: "var(--rule)" }}
```

1. 把这个 `style` 改成在 `borderColor` 之后追加两项（可按需换行，保持与文件内其他多项 style 对象相同的写法）：
   ```tsx
   backdropFilter: "var(--bd)",
   WebkitBackdropFilter: "var(--bd)",
   ```
2. 卡片的 `className`、内部内容（头部、预览、表单、按钮等）、外层遮罩，一个字符都不改。
3. 同文件其他任何地方不改。

## 4. 验收标准

在仓库根目录执行：

1. `git status --porcelain` —— 除本规格所在的 `docs/tasks/2026-10-07-publish-modal-blur/` 外，只有 `M frontend/app/plaza/page.tsx`。
2. `git diff -U0 frontend/app/plaza/page.tsx` —— 只涉及这一个卡片的 `style`，新增内容只有 `backdropFilter: "var(--bd)"` 与 `WebkitBackdropFilter: "var(--bd)"`，删除的只有原来那一行 `style={{ borderColor: "var(--rule)" }}`（若改成多行写法）或无删除。
3. `grep -c 'backdropFilter: "var(--bd)"' frontend/app/plaza/page.tsx` 输出 `2`（热点展开层 1 处 + 本卡片 1 处）；`grep -c 'WebkitBackdropFilter: "var(--bd)"' frontend/app/plaza/page.tsx` 输出 `2`。
4. 在 `frontend/` 下：`npx tsc --noEmit` 退出码 0；`npx eslint app/plaza/page.tsx` 退出码 0（第 595 行附近已有的 `<img>` warning 不算）。

不要运行 `npm run build` 或 `npm run dev`（沙箱内 Turbopack 会 EPERM），构建与截图由 Claude 在沙箱外完成。

## 5. 什么时候停下来问

本单不需要停下来问。
