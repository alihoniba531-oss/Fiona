"""第五批变异测试：把实现的关键处逐一改坏，对应测试必须变红；按字节还原。

用法：python3 -I mut_b5.py <工作树>
每项先在未变异状态跑一次目标测试（必须绿），再变异跑一次（必须红且红在指定用例），最后还原并核对字节一致。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

WT = os.path.abspath(sys.argv[1])
PY = os.path.join(WT, "backend/.venv/bin/python")
ENV = {k: v for k, v in os.environ.items() if k.upper() not in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}}

# (编号, 文件, 旧字节, 新字节, 目标测试文件, 期望变红的用例名片段)
MUTS = [
    ("M1 T1 去掉平台模式费用守卫", "frontend/app/page.tsx",
     b': showCost && <span className={cn("min-w-0 truncate", lowBalance && "text-[color:var(--seal)]")} title={labelTitle}>{label}',
     b': <span className={cn("min-w-0 truncate", lowBalance && "text-[color:var(--seal)]")} title={labelTitle}>{label}',
     "tests/test_ui_closeout_cost_hint.py", "cost_hint"),
    ("M2 T1 低余额不再朱色", "frontend/app/page.tsx",
     b'const lowBalance = balance !== null && balance < 30;', b'const lowBalance = false;',
     "tests/test_ui_closeout_cost_hint.py", "cost_hint"),
    ("M3 T1 行不再按内容隐藏", "frontend/app/page.tsx",
     b'!hasContent && "max-md:hidden"', b'false && "max-md:hidden"',
     "tests/test_ui_closeout_cost_hint.py", "cost_hint"),
    ("M4 T2 原生框回到 Tab 序列", "frontend/app/history/page.tsx",
     b'tabIndex={-1}', b'tabIndex={0}',
     "tests/test_ui_closeout_history_keyboard.py", "history_keyboard"),
    ("M5 T2 两个 aria-label 对调", "frontend/app/history/page.tsx",
     None, None, "tests/test_ui_closeout_history_keyboard.py", "history_keyboard"),
    ("M6 T3 一处遮罩换回任意值", "frontend/components/SongProjectCard.tsx",
     b'scrim-dialog', b'backdrop:bg-[color:var(--scrim)]',
     "tests/test_ui_closeout_dialog_scrim.py", "dialog_scrim"),
    ("M7 T3 去掉夜间兜底", "frontend/app/globals.css",
     b'.dark .scrim-dialog::backdrop { background:var(--scrim, rgba(0,0,0,.45)); }', b'.dark .scrim-dialog::backdrop { background:var(--scrim); }',
     "tests/test_design_system_gate.py", "test_token_layer"),
    ("M8 T3 去掉一个对话框的类", "frontend/components/ConfirmDialog.tsx",
     b'className="confirm-dialog scrim-dialog"', b'className="confirm-dialog"',
     "tests/test_ui_closeout_dialog_scrim.py", "dialog_scrim"),
    ("M9 T4 F7 退回前缀匹配", "backend/tests/test_design_system_gate.py",
     b'if TYPE_WORD_RX.match(val):', b'if re.match(r"(?:number|string|undefined|null|boolean|any|unknown|React\\.|CSSProperties|Property\\.)", val):',
     "tests/test_design_system_gate.py", "test_selfcheck_source_rules"),
    ("M10 T5 开场 group 加 onKeyDown", "frontend/app/page.tsx",
     b'<div role="group" aria-label="\xe5\xbc\x80\xe5\x9c\xba" className="flex flex-wrap justify-center gap-2">',
     b'<div role="group" aria-label="\xe5\xbc\x80\xe5\x9c\xba" onKeyDown={() => {}} className="flex flex-wrap justify-center gap-2">',
     "tests/test_ui_closeout_structure_guards.py", "structure_guards"),
    ("M11 T5 隐私首段包进条件", "frontend/components/ChatModelSection.tsx",
     None, None, "tests/test_ui_closeout_structure_guards.py", "structure_guards"),
]


def pytest(target):
    p = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", target], cwd=os.path.join(WT, "backend"), env=ENV,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    return p.returncode, p.stdout + p.stderr


def swap_labels(data: bytes) -> bytes:
    a = 'aria-label="从（开始日期）"'.encode(); b = 'aria-label="到（结束日期）"'.encode()
    tmp = b"\x00SWAP\x00"
    return data.replace(a, tmp).replace(b, a).replace(tmp, b)


def wrap_privacy(data: bytes) -> bytes:
    lines = data.split(b"\n")
    idx = [i for i, l in enumerate(lines) if l.strip().startswith("<p className={noteClass}>启用后，".encode())]
    assert len(idx) == 1, idx
    i = idx[0]
    lines.insert(i, b"      {needsKey && <>")
    lines.insert(i + 3, b"      </>}")
    return b"\n".join(lines)


fails = 0
for mid, rel, old, new, target, want in MUTS:
    path = os.path.join(WT, rel)
    with open(path, "rb") as fh:
        orig = fh.read()
    rc0, out0 = pytest(target)
    if rc0 != 0:
        print(f"FAIL {mid}: 未变异时目标测试已红\n{out0[-600:]}"); fails += 1; continue
    if old is None:
        mutated = swap_labels(orig) if "aria-label" in mid else wrap_privacy(orig)
    else:
        assert orig.count(old) >= 1, (mid, "旧串不存在")
        mutated = orig.replace(old, new, 1)
    assert mutated != orig, mid
    try:
        with open(path, "wb") as fh:
            fh.write(mutated)
        rc, out = pytest(target)
        red = [l for l in out.splitlines() if l.startswith("FAILED") and want in l]
        ok = rc != 0 and bool(red)
        print(f"{'PASS' if ok else 'FAIL'} {mid}  rc={rc} red={len(red)} {red[0][:140] if red else out.splitlines()[-1][:140]}")
        fails += 0 if ok else 1
    finally:
        with open(path, "wb") as fh:
            fh.write(orig)
        with open(path, "rb") as fh:
            assert fh.read() == orig, (mid, "还原失败")
print(f"== FAIL {fails} / {len(MUTS)}")
sys.exit(fails)
