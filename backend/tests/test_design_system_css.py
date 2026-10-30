"""离线检查设计系统生成后的 CSS（设计系统 T3-4）。

用 frontend/node_modules 里的 @tailwindcss/node compile 加 @tailwindcss/oxide
Scanner，按真实 app/globals.css 与 app/、components/、lib/ 源码编译，不写盘、
不跑 next build。依赖缺失时 skip；本机门禁要求不 skip。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
REQUIRED_PACKAGES = ["@tailwindcss/node", "@tailwindcss/oxide"]
MIN_SCANNED_FILES = 130

PROBE = r"""
const { createRequire } = require('module');
const packages = JSON.parse(process.argv[1]);
const req = createRequire(process.argv[2]);
const missing = packages.filter(name => {
  try { req.resolve(name); return false; }
  catch { return true; }
});
process.stdout.write(JSON.stringify(missing));
"""

RUNNER = r"""
const fs = require('fs');
const path = require('path');
const { createRequire } = require('module');

(async () => {
  const frontend = path.resolve(process.argv[1]);
  const req = createRequire(path.join(frontend, 'package.json'));
  const twNode = await import(req.resolve('@tailwindcss/node'));
  const { Scanner } = req('@tailwindcss/oxide');

  const cssPath = path.join(frontend, 'app', 'globals.css');
  const css = fs.readFileSync(cssPath, 'utf8');
  const compiler = await twNode.compile(css, {
    base: path.dirname(cssPath),
    from: cssPath,
    onDependency: () => {},
  });
  const scanner = new Scanner({ sources: [
    { base: path.join(frontend, 'app'), pattern: '**/*', negated: false },
    { base: path.join(frontend, 'components'), pattern: '**/*', negated: false },
    { base: path.join(frontend, 'lib'), pattern: '**/*', negated: false },
    { base: path.join(frontend, 'components', 'ui'), pattern: '**/*', negated: true },
  ] });
  const out = compiler.build(scanner.scan());
  const files = scanner.files || [];

  // 反向：全文扫描，不按块切；嵌套块前面的声明也算。
  const TOKEN = /^var\(--fs-(?:11|12|13|15|16-5|18|22|30|46|76)\)$/;
  const ALLOWED_LITERAL = new Set([
    'inherit', '1em', '75%', '80%', 'max(var(--fs-16-5), 1em)',
  ]);
  const violations = [];
  for (const m of out.matchAll(/(?<![\w-])(font-size|font)\s*:\s*([^;{}]+)/gi)) {
    const value = m[2].trim();
    const bare = value.replace(/\s*!important$/, '');
    if (!TOKEN.test(bare) && !ALLOWED_LITERAL.has(bare)) {
      violations.push({
        prop: m[1],
        value,
        at: out.slice(Math.max(0, m.index - 80), m.index)
          .replace(/\s+/g, ' ').trim().slice(-60),
      });
    }
  }
  const colorViolations = [];
  for (const m of out.matchAll(/(?<![\w-])color\s*:\s*var\(--fs-[^;}]*/g)) {
    colorViolations.push({ value: m[0], at: '字号变量被编译成颜色' });
  }

  // 正向：单独编译 12 个类，逐条比对归一化后的规则体。
  const EXPECT = {
    '.text-fs-11': 'font-size: var(--fs-11);',
    '.text-fs-12': 'font-size: var(--fs-12); line-height: var(--tw-leading, calc(16 / 12));',
    '.text-fs-13': 'font-size: var(--fs-13); line-height: var(--tw-leading, calc(20 / 13));',
    '.text-fs-15': 'font-size: var(--fs-15); line-height: var(--tw-leading, 1.5);',
    '.text-fs-16\\.5': 'font-size: var(--fs-16-5);',
    '.text-fs-18': 'font-size: var(--fs-18);',
    '.text-fs-22': 'font-size: var(--fs-22); line-height: var(--tw-leading, calc(28 / 22));',
    '.text-fs-30': 'font-size: var(--fs-30);',
    '.text-fs-30\\!': 'font-size: var(--fs-30) !important;',
    '.text-fs-46': 'font-size: var(--fs-46);',
    '.text-fs-76': 'font-size: var(--fs-76);',
    '.max-md\\:text-fs-11': '@media (width < 48rem) { font-size: var(--fs-11); }',
  };
  const probe = compiler.build([
    'text-fs-11', 'text-fs-12', 'text-fs-13', 'text-fs-15', 'text-fs-16.5',
    'text-fs-18', 'text-fs-22', 'text-fs-30', 'text-fs-46', 'text-fs-76',
    'max-md:text-fs-11', 'text-fs-30!',
  ]);
  function blockOf(text, selector) {
    const i = text.indexOf(selector + ' {');
    if (i < 0) return null;
    let depth = 0;
    let j = text.indexOf('{', i);
    const start = j;
    for (; j < text.length; j++) {
      if (text[j] === '{') depth++;
      else if (text[j] === '}' && --depth === 0) break;
    }
    return text.slice(start + 1, j).replace(/\s+/g, ' ').trim();
  }
  const mismatches = [];
  for (const [selector, want] of Object.entries(EXPECT)) {
    const got = blockOf(probe, selector);
    if (got !== want) mismatches.push({ selector, want, got });
  }

  process.stdout.write(JSON.stringify({
    scannedFiles: files.length,
    violationCount: violations.length,
    violations: violations.slice(0, 5),
    colorViolationCount: colorViolations.length,
    colorViolations: colorViolations.slice(0, 5),
    mismatchCount: mismatches.length,
    mismatches,
  }));
})().catch(err => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
"""


def require_node_tailwind_dependencies():
    assert (FRONTEND / "app" / "globals.css").is_file(), (
        "frontend/app/globals.css is missing; the generated CSS cannot be verified"
    )
    if shutil.which("node") is None:
        pytest.skip("Node.js is unavailable; generated-CSS assertions skipped")
    try:
        result = subprocess.run(
            [
                "node",
                "-e",
                PROBE,
                json.dumps(REQUIRED_PACKAGES),
                str(FRONTEND / "package.json"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("Node.js/Tailwind toolchain is unavailable")
    missing = json.loads(result.stdout)
    if missing:
        pytest.skip("Frontend dependencies unavailable: " + ", ".join(missing))


def test_generated_css_font_sizes():
    require_node_tailwind_dependencies()
    completed = subprocess.run(
        ["node", "-e", RUNNER, str(FRONTEND)],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)

    assert result["scannedFiles"] >= MIN_SCANNED_FILES, (
        "Tailwind 只扫描到 %d 个文件，少于 %d 个，扫描面丢了"
        % (result["scannedFiles"], MIN_SCANNED_FILES)
    )

    problems = []
    if result["violationCount"] or result["colorViolationCount"]:
        problems.append(
            "反向：font-size/font 违规 %d 条，color: var(--fs- 违规 %d 条"
            % (result["violationCount"], result["colorViolationCount"])
        )
        for item in result["violations"]:
            problems.append("  BAD %s: %s <- %s" % (item["prop"], item["value"], item["at"]))
        for item in result["colorViolations"]:
            problems.append("  BAD color: %s <- %s" % (item["value"], item["at"]))
    if result["mismatchCount"]:
        problems.append(
            "正向：12 个类里 %d 条规则体不符" % result["mismatchCount"]
        )
        for item in result["mismatches"]:
            problems.append(
                "  MISMATCH %s\n    期望 %s\n    实际 %s"
                % (item["selector"], item["want"], item["got"])
            )

    assert not problems, (
        "生成的 CSS 不符合设计系统字阶：\n" + "\n".join(problems)
    )
