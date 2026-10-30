#!/usr/bin/env python3
"""Run the 19 mutation checks from spec section 7.5, restoring each file byte-for-byte."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BACKUP = Path("/tmp/fiona-design-system-mutation-backups")
TESTS = [
    "tests/test_design_system_gate.py",
    "tests/test_design_tokens_contrast.py",
    "tests/test_design_system_cn.py",
    "tests/test_design_system_css.py",
]
PYTEST_ENV = {
    k: v for k, v in os.environ.items()
    if k.lower() not in {"http_proxy", "https_proxy", "all_proxy", "no_proxy"}
}
PYTEST_ENV["PYTHON_DOTENV_DISABLED"] = "1"

M = []
def add(name, rel, transform, expect, note=""):
    M.append({"name": name, "file": rel, "transform": transform, "expect": expect, "note": note})

CB = "frontend/components/ChatBubble.tsx"
AEW = "frontend/components/AgentExchangeWorkspace.tsx"
CSS = "frontend/app/globals.css"
add("01_text-fs-13_to_text-sm", CB, lambda s: s.replace("text-fs-13", "text-sm", 1), ["test_font_size_rules"])
add("02_text-fs-16-5", CB, lambda s: s + "\n/* mutation: text-fs-16-5 */\n", ["test_font_size_rules"])
add("03_text-14px", CB, lambda s: s.replace('className="', 'className="text-[14px] ', 1), ["test_font_size_rules", "test_generated_css_font_sizes"])
add("04_inline_fontSize14", CB, lambda s: s + "\nconst __mutation = <span style={{ fontSize: 14 }} />;\n", ["test_font_size_rules"])
add("05_text-fs13-dollar", CB, lambda s: s + '\nconst __m2 = "mobile:text-fs-13${x}";\n', ["test_font_size_rules"])
add("06_small_no_fs", AEW, lambda s: s.replace('<small className="text-fs-11 ', '<small className="', 1), ["test_font_size_rules"])
add("07_css_font14", CSS, lambda s: s + "\n.zz { font-size: 14px; }\n", ["test_font_size_rules", "test_generated_css_font_sizes"])
add("08_muted_foreground", CB, lambda s: s.replace("text-[color:var(--ink2)]", "text-muted-foreground", 1), ["test_color_rules"])
add("09_text-var-ink2", CB, lambda s: s + '\nconst __m3 = "text-[var(--ink2)]";\n', ["test_color_rules"])
add("10_var-rec", CB, lambda s: s + '\nconst __m4 = "var(--rec)";\n', ["test_color_rules"])
add("11_bg-parens", CB, lambda s: s + '\nconst __m5 = "bg-(--slip)";\n', ["test_color_rules"])
add("12_text-ink3", CB, lambda s: s + '\nconst __m6 = "text-[color:var(--ink3)]";\n', ["test_role_rules"])
add("13_stamp_outside", CB, lambda s: s + '\nconst __m7 = "var(--stamp)";\n', ["test_role_rules"])
add("14_text_color_alpha", CB, lambda s: s.replace("text-[color:var(--ink2)]", "text-[color:var(--ink2)]/60", 1), ["test_role_rules"])
add("15_night_seal_head", CSS, lambda s: s.replace("  --seal: #E56F5D;\n", "  --seal: #BF4537;\n"), ["test_token_contrast", "test_token_layer"])
add("16_night_chip_060", CSS, lambda s: s.replace("  --chip: rgba(74,63,52,0.42);\n", "  --chip: rgba(74,63,52,0.60);\n"), ["test_token_contrast"])
add("17_line_height_14", CSS, lambda s: s.replace("  --text-fs-13--line-height: calc(20 / 13);\n", "  --text-fs-13--line-height: 1.4;\n"), ["test_token_layer", "test_generated_css_font_sizes"])
GUARD = '''@media (width < 48rem) {
  :root:not([data-shell="desktop"]) input,
  :root:not([data-shell="desktop"]) textarea,
  :root:not([data-shell="desktop"]) select {
    font-size: max(var(--fs-16-5), 1em);
  }

  :root:not([data-shell="desktop"]) .mobile-scrollbar-none {
    scrollbar-width: none !important;
  }
  :root:not([data-shell="desktop"]) .mobile-scrollbar-none::-webkit-scrollbar,
  :root:not([data-shell="desktop"]) .mobile-scrollbar-none *::-webkit-scrollbar {
    width: 0 !important;
    height: 0 !important;
    display: none !important;
  }
}'''
add("18_guard_in_layer", CSS, lambda s: s.replace(GUARD, "@layer base {\n" + GUARD + "\n}", 1), ["test_token_layer"])
# 19 is handled specially: restore HEAD lib/utils.ts
M.append({"name": "19_utils_default_merge", "file": "frontend/lib/utils.ts", "transform": None,
          "expect": ["test_cn_keeps_size_and_color"]})

def sha(b): return hashlib.sha256(b).hexdigest()

def main():
    BACKUP.mkdir(parents=True, exist_ok=True)
    results = []
    for m in M:
        path = ROOT / m["file"]
        original = path.read_bytes()
        digest = sha(original)
        bdir = BACKUP / m["name"]
        bdir.mkdir(parents=True, exist_ok=True)
        (bdir / (path.name + ".bak")).write_bytes(original)
        if m["transform"] is None:
            mutated = subprocess.run(["git", "show", "HEAD:" + m["file"]], cwd=ROOT,
                                     capture_output=True, check=True).stdout
            assert mutated != original
        else:
            text = original.decode("utf-8")
            changed = m["transform"](text)
            assert changed != text, f"{m['name']}: mutation did not change file"
            mutated = changed.encode("utf-8")
        path.write_bytes(mutated)
        proc = subprocess.run(
            [str(ROOT / "backend/.venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "--tb=no", "-rf", *TESTS],
            cwd=str(ROOT / "backend"), env=PYTEST_ENV, capture_output=True, text=True,
        )
        failed = sorted(set(re.findall(r"FAILED tests/[\w./]+::(test_\w+)", proc.stdout)))
        path.write_bytes(original)
        assert sha(path.read_bytes()) == digest, f"{m['name']}: restore sha mismatch"
        expected = m["expect"]
        missing = [t for t in expected if t not in failed]
        results.append({"mutation": m["name"], "file": m["file"], "expected_red": expected,
                        "failed": failed, "missing": missing, "exit": proc.returncode,
                        "ok": not missing})
        print(f"{'PASS' if not missing else 'FAIL'} {m['name']}: failed={failed}")
    out = Path("/tmp/fiona-design-system-mutation-results.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nresults:", out)
    print("all expected red:", all(r["ok"] for r in results))
    return 0 if all(r["ok"] for r in results) else 1

if __name__ == "__main__":
    sys.exit(main())
