"""离线检查 frontend/lib/utils.ts 的 tailwind-merge 配置（设计系统 T3-3）。

用 node 加载 frontend/node_modules 里的 clsx、tailwind-merge，并用 TypeScript
把 utils.ts 转译后调用 cn()。依赖缺失时 skip；本机门禁要求不 skip。
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
UTILS = FRONTEND / "lib" / "utils.ts"
REQUIRED_PACKAGES = ["typescript", "clsx", "tailwind-merge"]

# spec T3-3 表：每个用例是（说明，cn 入参，期望输出）。行号与规格表一致。
CN_CASES = [
    (
        "1",
        ["text-fs-13", "text-[color:var(--ink2)]"],
        "text-fs-13 text-[color:var(--ink2)]",
    ),
    (
        "2",
        ["text-[color:var(--ink)]", "text-fs-16.5"],
        "text-[color:var(--ink)] text-fs-16.5",
    ),
    ("3", ["text-fs-12", "text-fs-13"], "text-fs-13"),
    ("4", ["max-md:text-fs-11", "max-md:text-fs-12"], "max-md:text-fs-12"),
    ("5", ["text-[13px]", "text-fs-13"], "text-fs-13"),
    ("6", ["leading-6", "text-fs-13"], "text-fs-13"),
    ("7a", ["text-fs-22 leading-[inherit]"], "text-fs-22 leading-[inherit]"),
    ("7b", ["text-fs-15 text-pretty"], "text-fs-15 text-pretty"),
    (
        "8",
        [
            "btn btn-quiet h-8 px-2.5 text-fs-12",
            "text-[color:var(--seal)] bg-[color:var(--seal-soft)]",
        ],
        "btn btn-quiet h-8 px-2.5 text-fs-12 "
        "text-[color:var(--seal)] bg-[color:var(--seal-soft)]",
    ),
]


def _tokens():
    return ["11", "12", "13", "15", "16.5", "18", "22", "30", "46", "76"]


CASES = CN_CASES + [
    (
        "token-" + token,
        ["text-fs-" + token, "text-[color:var(--ink)]"],
        "text-fs-" + token + " text-[color:var(--ink)]",
    )
    for token in _tokens()
]

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
const frontend = path.resolve(process.argv[1]);
const utilsPath = path.join(frontend, 'lib', 'utils.ts');
const req = createRequire(path.join(frontend, 'package.json'));
const ts = req('typescript');
const source = fs.readFileSync(utilsPath, 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2019 },
}).outputText;
const loaded = { exports: {} };
new Function('exports', 'module', 'require', '__filename', '__dirname', compiled)(
  loaded.exports, loaded, req, utilsPath, path.dirname(utilsPath)
);
const cases = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(cases.map(args => loaded.exports.cn(...args))));
"""


def require_node_merge_dependencies():
    assert UTILS.is_file(), (
        "frontend/lib/utils.ts is missing; the tailwind-merge configuration "
        "cannot be verified"
    )
    if shutil.which("node") is None:
        pytest.skip("Node.js is unavailable; tailwind-merge assertions skipped")
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
        pytest.skip("Node.js/TypeScript/tailwind-merge is unavailable")
    missing = json.loads(result.stdout)
    if missing:
        pytest.skip("Frontend dependencies unavailable: " + ", ".join(missing))


def test_cn_keeps_size_and_color():
    require_node_merge_dependencies()
    completed = subprocess.run(
        [
            "node",
            "-e",
            RUNNER,
            str(FRONTEND),
            json.dumps([case[1] for case in CASES], ensure_ascii=False),
        ],
        cwd=str(FRONTEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert completed.returncode == 0, completed.stderr
    actuals = json.loads(completed.stdout)
    assert len(actuals) == len(CASES)

    failures = []
    for (label, args, expected), actual in zip(CASES, actuals):
        if actual != expected:
            failures.append(
                "case %s: cn(%s) -> %r; expected %r"
                % (label, ", ".join(repr(arg) for arg in args), actual, expected)
            )
    assert not failures, (
        "tailwind-merge configuration does not keep size and color classes:\n"
        + "\n".join(failures)
    )
