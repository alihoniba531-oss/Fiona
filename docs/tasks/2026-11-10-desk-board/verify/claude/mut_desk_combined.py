"""案头第一期 · 组合变异：两处「单独拆一道不变红」的双重保险，两道一起拆必须变红。

用法：python3 -I mut_desk_combined.py <克隆副本根目录>
"""
import io, os, re, subprocess, sys
ROOT = os.path.abspath(sys.argv[1]); PY = os.path.join(ROOT, "backend/.venv/bin/python")
p = os.path.join(ROOT, "frontend/components/desk/DeskDock.tsx"); orig = io.open(p, encoding="utf-8").read()
ok = []
def run(label, text, expect):
    io.open(p, "w", encoding="utf-8").write(text)
    try:
        r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", "--no-header", "tests/test_desk_dock_races_frontend.py"], cwd=os.path.join(ROOT, "backend"), capture_output=True, text=True, timeout=900)
        failed = [f.split("::")[-1] for f in re.findall(r"^FAILED (\S+)", r.stdout, re.M)]
        good = expect in failed
        ok.append(good)
        print("PASS" if good else "FAIL", label, "→", (r.stdout.strip().splitlines() or [""])[-1], failed)
    finally:
        io.open(p, "w", encoding="utf-8").write(orig)
a = orig.replace("    if (selectedBookRef.current !== id || !openRef.current) return;\n    const request = beginDetailRead();", "    const request = beginDetailRead();")
assert a != orig
n1 = a.count(" || selectedBookRef.current !== targetBookId) return;"); a = a.replace(" || selectedBookRef.current !== targetBookId) return;", ") return;")
print("A 去掉的写后判断处数:", n1); assert n1 >= 1
run("A 两道保险都拆（应变红）", a, "test_write_then_switch_book_clears_loading_and_selects_new_book")
b = orig.replace("    if (open) return;\n    cancelReadScopes();\n", "    if (open) return;\n"); assert b != orig
n2 = b.count("!openRef.current"); b = b.replace("!openRef.current", "false")
print("B 中性化的 openRef 判断处数:", n2); assert n2 >= 1
run("B 关闭保护全拆（应变红）", b, "test_close_stops_new_get_requests")
assert io.open(p, encoding="utf-8").read() == orig; print("已按原字节还原")
print(f"== FAIL {ok.count(False)} / {len(ok)}")
