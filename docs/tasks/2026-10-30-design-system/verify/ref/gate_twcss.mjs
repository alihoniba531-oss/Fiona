// 第四批「生成 CSS」检查（T3-4 的参考实现）：用仓库自带 Tailwind 4.3（@tailwindcss/node + oxide Scanner）按真实 globals.css 编译，
// 只扫 app/ components/ lib/（排除 components/ui/）。只读：不写仓库、不起服务器、不跑 next build。
// 用法：node gate_twcss.mjs <frontend 目录> [--node-modules <含 node_modules 的 frontend 目录>]
// 两部分：① 反向：生成 CSS 里每一条 font-size / font 的值都合法；② 正向：10 个令牌（加两个变体）编译结果与期望逐条相同。
// 退出码 = 违规条数 + 正向不符条数；扫描文件少于 130 个时为 99。
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";

const FRONT = path.resolve(process.argv[2] || ".");
const args = process.argv.slice(3);
const opt = k => (args.includes(k) ? args[args.indexOf(k) + 1] : null);
const NM = path.resolve(opt("--node-modules") || FRONT);
const req = createRequire(path.join(NM, "package.json"));
const twNode = await import(req.resolve("@tailwindcss/node"));
const { Scanner } = req("@tailwindcss/oxide");

const cssPath = path.join(FRONT, "app/globals.css");
const css = fs.readFileSync(cssPath, "utf8");
const cssForCompile = NM === FRONT ? css : css.replace(/@import\s+"(\.[^"]+)"/g, (_m, rel) => `@import "${path.join(path.dirname(cssPath), rel)}"`);
const compiler = await twNode.compile(cssForCompile, { base: NM === FRONT ? path.dirname(cssPath) : path.join(NM, "app"), from: cssPath, onDependency: () => {} });
const scanner = new Scanner({ sources: [
  { base: path.join(FRONT, "app"), pattern: "**/*", negated: false },
  { base: path.join(FRONT, "components"), pattern: "**/*", negated: false },
  { base: path.join(FRONT, "lib"), pattern: "**/*", negated: false },
  { base: path.join(FRONT, "components/ui"), pattern: "**/*", negated: true },
] });
const out = compiler.build(scanner.scan());
const files = scanner.files || [];

// ① 反向：全文扫描（不按块切，嵌套块前面的声明也算）
const TOKEN = /^var\(--fs-(?:11|12|13|15|16-5|18|22|30|46|76)\)$/;
const ALLOWED_LITERAL = new Set(["inherit", "1em", "80%", "75%", "max(var(--fs-16-5), 1em)"]); // 预检的 h1-h6/code/small/sub/sup 与手机输入框护栏
const bad = [];
for (const m of out.matchAll(/(?<![\w-])(font-size|font)\s*:\s*([^;{}]+)/gi)) {
  const v = m[2].trim().replace(/\s*!important$/, "");
  if (!TOKEN.test(v) && !ALLOWED_LITERAL.has(v)) bad.push({ prop: m[1], value: m[2].trim(), at: out.slice(Math.max(0, m.index - 80), m.index).replace(/\s+/g, " ").trim().slice(-60) });
}
for (const m of out.matchAll(/(?<![\w-])color\s*:\s*var\(--fs-[^;}]*/g)) bad.push({ prop: "color", value: m[0], at: "字号变量被编译成颜色" });

// ② 正向：固定一组类名单独编译，逐条比对
const EXPECT = {
  ".text-fs-11": "font-size: var(--fs-11);",
  ".text-fs-12": "font-size: var(--fs-12); line-height: var(--tw-leading, calc(16 / 12));",
  ".text-fs-13": "font-size: var(--fs-13); line-height: var(--tw-leading, calc(20 / 13));",
  ".text-fs-15": "font-size: var(--fs-15); line-height: var(--tw-leading, 1.5);",
  ".text-fs-16\\.5": "font-size: var(--fs-16-5);",
  ".text-fs-18": "font-size: var(--fs-18);",
  ".text-fs-22": "font-size: var(--fs-22); line-height: var(--tw-leading, calc(28 / 22));",
  ".text-fs-30": "font-size: var(--fs-30);",
  ".text-fs-30\\!": "font-size: var(--fs-30) !important;",
  ".text-fs-46": "font-size: var(--fs-46);",
  ".text-fs-76": "font-size: var(--fs-76);",
  ".max-md\\:text-fs-11": "@media (width < 48rem) { font-size: var(--fs-11); }",
};
const probe = compiler.build(["text-fs-11", "text-fs-12", "text-fs-13", "text-fs-15", "text-fs-16.5", "text-fs-18", "text-fs-22", "text-fs-30", "text-fs-46", "text-fs-76", "max-md:text-fs-11", "text-fs-30!"]);
function blockOf(text, sel) {
  const i = text.indexOf(sel + " {");
  if (i < 0) return null;
  let depth = 0, j = text.indexOf("{", i);
  const start = j;
  for (; j < text.length; j++) { if (text[j] === "{") depth++; else if (text[j] === "}" && --depth === 0) break; }
  return text.slice(start + 1, j).replace(/\s+/g, " ").trim();
}
const mismatch = [];
for (const [sel, want] of Object.entries(EXPECT)) {
  const got = blockOf(probe, sel);
  if (got !== want) mismatch.push({ sel, want, got });
}

console.log(`scannedFiles=${files.length} font-size/font 违规=${bad.length} 令牌编译不符=${mismatch.length}`);
for (const b of bad.slice(0, 30)) console.log(`  BAD ${b.prop}: ${b.value.padEnd(24)} ← ${b.at}`);
if (bad.length > 30) console.log(`  … 另 ${bad.length - 30} 条`);
for (const m of mismatch) console.log(`  MISMATCH ${m.sel}\n    期望 ${m.want}\n    实际 ${m.got}`);
if (files.length < 130) { console.log("FAIL 扫描文件少于 130 个，扫描面丢了"); process.exit(99); }
process.exit(Math.min(bad.length + mismatch.length, 98));
