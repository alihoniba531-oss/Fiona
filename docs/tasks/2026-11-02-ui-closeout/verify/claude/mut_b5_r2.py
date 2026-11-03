"""第五批 R2 变异测试：复核方证明在 R1 新测试下「全绿」的六处写坏，R2 之后对应真实用例（非自检）必须变红；按字节还原。

用法：python3 -I mut_b5_r2.py <工作树>
每项先在未变异状态跑一次目标测试（必须绿），再变异跑一次（必须红，且至少一条 FAILED 是非 selfcheck 的真实用例，且含指定片段），最后还原并核对字节一致。
"""
from __future__ import annotations

import os
import subprocess
import sys

WT = os.path.abspath(sys.argv[1])
PY = os.path.join(WT, "backend/.venv/bin/python")
ENV = {k: v for k, v in os.environ.items() if k.upper() not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}}

HIST = "frontend/app/history/page.tsx"
PAGE = "frontend/app/page.tsx"
T_HIST = "tests/test_ui_closeout_history_keyboard.py"
T_COST = "tests/test_ui_closeout_cost_hint.py"
T_SCRIM = "tests/test_ui_closeout_dialog_scrim.py"


def m17(d: bytes) -> bytes:  # 两个原生框去掉 aria-hidden
    old = b'aria-hidden="true"\n                  tabIndex={-1}'
    assert d.count(old) == 2, d.count(old)
    return d.replace(old, b'tabIndex={-1}')


def m18(d: bytes) -> bytes:  # tabIndex={-1} 从原生框挪到按钮
    a = b'                  tabIndex={-1}\n'; b = b'                  type="button"\n'
    assert d.count(a) == 2 and d.count(b) == 2, (d.count(a), d.count(b))
    out = d.replace(a, b'').replace(b, b + a)
    assert out.count(b'tabIndex={-1}') == 2
    return out


def swap(d: bytes, x: bytes, y: bytes) -> bytes:
    assert d.count(x) >= 1 and d.count(y) >= 1
    tmp = b"\x00SWAP\x00"
    return d.replace(x, tmp).replace(y, x).replace(tmp, y)


def e1(d: bytes) -> bytes:  # 扫描目录全部不存在
    for name in (b"frontend/app", b"frontend/components", b"frontend/lib"):
        old = b'ROOT / "' + name + b'",'
        assert d.count(old) == 1, (name, d.count(old))
        d = d.replace(old, b'ROOT / "' + name.replace(b"frontend/", b"frontend/nope-") + b'",')
    return d


# (编号, 文件, 变异函数, 目标测试文件, FAILED 行必须含的片段)
MUTS = [
    ("R1 M17 原生框去掉 aria-hidden", HIST, m17, T_HIST, "history_keyboard"),
    ("R2 M18 tabIndex 挪到按钮", HIST, m18, T_HIST, "test_date_buttons_stay_in_tab_order"),
    ("R3 rawChip 键对调", HIST, lambda d: swap(d, b'rawChip === "from"', b'rawChip === "to"'), T_HIST, "history_keyboard"),
    ("R4 E1 扫描目录不存在", "backend/" + T_SCRIM, e1, T_SCRIM, "test_no_backdrop_tailwind_variants_remain"),
    ("R5 M19 首次恒为 false", PAGE, lambda d: d.replace(b"setFirstVisit(firstVisitDecided.current);", b"setFirstVisit(false);", 1), T_COST, "cost_hint"),
    ("R6 M20 去掉 ref 守卫", PAGE, lambda d: d.replace(b"if (firstVisitDecided.current === null) firstVisitDecided.current", b"firstVisitDecided.current", 1), T_COST, "cost_hint"),
    ("R7 M21 余额不看 lowBalance", PAGE, lambda d: d.replace("{lowBalance && <>，还剩".encode(), "{<>，还剩".encode(), 1), T_COST, "cost_hint"),
]


def pytest(target):
    p = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", target], cwd=os.path.join(WT, "backend"), env=ENV,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    return p.returncode, p.stdout + p.stderr


fails = 0
for mid, rel, fn, target, want in MUTS:
    path = os.path.join(WT, rel)
    with open(path, "rb") as fh:
        orig = fh.read()
    if rel == PAGE:
        assert orig[:3] == b"\xef\xbb\xbf", "page.tsx 缺 BOM"
    rc0, out0 = pytest(target)
    if rc0 != 0:
        print(f"FAIL {mid}: 未变异时目标测试已红\n{out0[-600:]}"); fails += 1; continue
    mutated = fn(orig)
    assert mutated != orig, (mid, "变异无效")
    try:
        with open(path, "wb") as fh:
            fh.write(mutated)
        rc, out = pytest(target)
        failed = [l for l in out.splitlines() if l.startswith("FAILED")]
        real = [l for l in failed if "selfcheck" not in l]
        hit = [l for l in failed if want in l]
        ok = rc != 0 and bool(real) and bool(hit)
        print(f"{'PASS' if ok else 'FAIL'} {mid}  rc={rc} failed={len(failed)} real={len(real)} {real[0][:150] if real else (failed[0][:150] if failed else out.splitlines()[-1][:150])}")
        fails += 0 if ok else 1
    finally:
        with open(path, "wb") as fh:
            fh.write(orig)
        with open(path, "rb") as fh:
            assert fh.read() == orig, (mid, "还原失败")
print(f"== FAIL {fails} / {len(MUTS)}")
sys.exit(fails)
