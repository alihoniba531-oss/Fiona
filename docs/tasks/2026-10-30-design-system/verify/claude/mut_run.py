import subprocess, sys, os, re, shutil
M, PY = sys.argv[1], sys.argv[2]
F = lambda p: os.path.join(M, p)
def sub(path, old, new, count=1):
    s = open(F(path), encoding="utf-8").read(); assert old in s, (path, old[:40])
    open(F(path), "w", encoding="utf-8").write(s.replace(old, new, count))
def append(path, text):
    with open(F(path), "a", encoding="utf-8") as fh: fh.write(text)
def newfile(path, text): open(F(path), "w", encoding="utf-8").write(text)
G = "frontend/app/globals.css"; C = "frontend/components/StarChart.tsx"
MUTS = [
 ("text-fs-13 → text-sm", lambda: sub("frontend/components/LocalWatchSection.tsx", "text-fs-13", "text-sm"), ["test_font_size_rules"]),
 ("写 text-fs-16-5", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = <div className="text-fs-16-5">z</div>\n'), ["test_font_size_rules"]),
 ("写 text-[14px]", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = <div className="text-[14px]">z</div>\n'), ["test_font_size_rules", "test_generated_css_font_sizes"]),
 ("style fontSize: 14", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = <div style={{ fontSize: 14 }}>z</div>\n'), ["test_font_size_rules"]),
 ("mobile:text-fs-13${x}", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = (x: string) => <div className={`mobile:text-fs-13${x}`}>z</div>\n'), ["test_font_size_rules"]),
 ("<small> 删 text-fs-11", lambda: sub("frontend/components/AgentExchangeWorkspace.tsx", '<small className="text-fs-11 ', '<small className="'), ["test_font_size_rules"]),
 (".zz{font-size:14px}", lambda: append(G, "\n.zz { font-size: 14px; }\n"), ["test_font_size_rules", "test_generated_css_font_sizes"]),
 ("改回 text-muted-foreground", lambda: sub("frontend/components/MyAgentWorkspace.tsx", "text-[color:var(--ink2)]", "text-muted-foreground"), ["test_color_rules"]),
 ("写 text-[var(--ink2)]", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = <div className="text-[var(--ink2)]">z</div>\n'), ["test_color_rules"]),
 ("写 var(--rec)", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = <div style={{ color: "var(--rec)" }}>z</div>\n'), ["test_color_rules"]),
 ("写 bg-(--slip)", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = <div className="bg-(--slip)">z</div>\n'), ["test_color_rules"]),
 ("写 text-[color:var(--ink3)]", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = <div className="text-[color:var(--ink3)]">z</div>\n'), ["test_role_rules"]),
 ("非 Seal 写 var(--stamp)", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = <div style={{ color: "var(--stamp)" }}>z</div>\n'), ["test_role_rules"]),
 ("文字色加 /60", lambda: newfile("frontend/components/ZzMut.tsx", 'export const z = <div className="text-[color:var(--ink)]/60">z</div>\n'), ["test_role_rules"]),
 ("夜 --seal 改回 #BF4537", lambda: sub(G, "--seal: #E56F5D;", "--seal: #BF4537;", 2), ["test_token_contrast", "test_token_layer"]),
 ("夜 --chip 0.60", lambda: sub(G, "--chip: rgba(74,63,52,0.42);", "--chip: rgba(74,63,52,0.60);"), ["test_token_contrast"]),
 ("13 档行高 1.4", lambda: sub(G, "--text-fs-13--line-height: calc(20 / 13);", "--text-fs-13--line-height: 1.4;"), ["test_token_layer", "test_generated_css_font_sizes"]),
 ("护栏挪进 @layer base", lambda: (sub(G, '@media (width < 48rem) {\n  :root:not([data-shell="desktop"]) input,', '@layer base { @media (width < 48rem) {\n  :root:not([data-shell="desktop"]) input,'), sub(G, "    font-size: max(var(--fs-16-5), 1em);\n  }\n", "    font-size: max(var(--fs-16-5), 1em);\n  }\n}\n")), ["test_token_layer"]),
 ("utils.ts 改回默认 twMerge", lambda: newfile("frontend/lib/utils.ts", 'import { clsx, type ClassValue } from "clsx"\nimport { twMerge } from "tailwind-merge"\n\nexport function cn(...inputs: ClassValue[]) {\n  return twMerge(clsx(inputs))\n}\n'), ["test_cn_keeps_size_and_color"]),
]
TESTS = ["tests/test_design_system_gate.py", "tests/test_design_tokens_contrast.py", "tests/test_design_system_cn.py", "tests/test_design_system_css.py"]
env = {k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")}
env["PYTHONDONTWRITEBYTECODE"] = "1"
def run():
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *TESTS], cwd=F("backend"), capture_output=True, text=True, env=env)
    return set(re.findall(r"^FAILED \S+::(\w+)", r.stdout, re.M)), r.stdout
base_red, out = run()
print("基线红：", sorted(base_red) or "无", "|", out.strip().splitlines()[-1])
paths = ["frontend/components/LocalWatchSection.tsx", "frontend/components/AgentExchangeWorkspace.tsx", "frontend/components/MyAgentWorkspace.tsx", G, "frontend/lib/utils.ts"]
backup = {p: open(F(p), "rb").read() for p in paths}
ok = 0
for name, fn, need in MUTS:
    fn(); red, _ = run()
    for p, b in backup.items(): open(F(p), "wb").write(b)
    if os.path.exists(F("frontend/components/ZzMut.tsx")): os.remove(F("frontend/components/ZzMut.tsx"))
    hit = all(n in red for n in need); ok += hit
    print(f"{'OK ' if hit else 'MISS'} {name:26s} 必须红 {need}  实际红 {sorted(red)}")
after, _ = run(); print("还原后红：", sorted(after) or "无", f"；{ok}/{len(MUTS)} 项达标")
