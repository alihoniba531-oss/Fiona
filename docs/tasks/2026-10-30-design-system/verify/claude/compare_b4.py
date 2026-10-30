"""比对 measure_b4.py 的两份输出：python3 -I compare_b4.py <HEAD 目录> <候选目录> [--shots <候选截图目录>]

【改】HEAD 应失败、候选应通过；【回归】两边都要过（以 HEAD 为基准不得变差）。退出码 = 失败项数。
"""
import collections, json, os, sys

SCALE = {11.0, 12.0, 13.0, 15.0, 16.5, 18.0, 22.0, 30.0, 46.0, 76.0}


def load(d):
    return {(r["state"], r["vp"], r["theme"]): r for r in json.load(open(os.path.join(d, "measure.json"), encoding="utf-8"))}


def frames(r):
    out = {}
    for i, f in enumerate(r.get("frames", [])):
        key = ("main" if f["main"] else f["path"])
        while key in out: key += "+"
        out[key] = f
    return out


def lum(rgb):
    def ch(x):
        x = x / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(rgb[0]) + 0.7152 * ch(rgb[1]) + 0.0722 * ch(rgb[2])


def cr(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def parse_rgb(s):
    nums = s[s.index("(") + 1:s.index(")")].replace("/", ",").split(",")
    return tuple(round(float(x)) for x in nums[:3])


def main():
    H, C = load(sys.argv[1]), load(sys.argv[2])
    shots = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
    fails = []

    def report(name, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail else ""))
        if not ok: fails.append(name)

    keys = sorted(set(H) & set(C))
    bad_states = [k for k in keys if not H[k]["ok"] or not C[k]["ok"]]
    report("0 两边状态都量到了", len(keys) >= 90 and not [k for k in bad_states if not (k[0] == "studio" and k[1] == "m390")],
           f"{len(keys)} 个状态；失败 {bad_states[:6]}")
    keys = [k for k in keys if k not in bad_states]

    # 1 字号普查
    def census(R):
        viol = collections.Counter(); ex = {}
        for k in keys:
            for fk, f in frames(R[k]).items():
                for t in f["texts"]:
                    v = round(t["fs"], 2)
                    if v not in SCALE:
                        viol[v] += 1; ex.setdefault(v, f"{k[0]}/{k[1]} {t['tag']} {t['text'][:16]}")
        return viol, ex
    hv, _ = census(H); cv, cex = census(C)
    report("1【改】HEAD 有字阶外字号（正控）", bool(hv), f"{dict(sorted(hv.items())[:12])}")
    report("1【改】候选所有可见文字字号 ∈ 字阶", not cv, f"{dict(cv)} 例 {list(cex.items())[:5]}")

    # 2 地标
    land_bad = []
    for k in keys:
        hf, cf = frames(H[k]), frames(C[k])
        for fk in hf:
            if fk not in cf: continue
            hl = {(l["sel"], l["i"]): l for l in hf[fk]["land"]}; cl = {(l["sel"], l["i"]): l for l in cf[fk]["land"]}
            for lk, a in hl.items():
                b = cl.get(lk)
                if not b: land_bad.append((k, fk, lk, "缺失")); continue
                d = max(abs(a[q] - b[q]) for q in ("x", "y", "w", "h"))
                if d > 2: land_bad.append((k, fk, lk, round(d, 1)))
    report("2【回归】地标位置尺寸差 ≤ 2px", not land_bad, f"{len(land_bad)} 处 {land_bad[:6]}")

    # 3 手机输入区空闲高度
    comp = [l["h"] for k in keys if k[0] == "home" and k[1] == "m390" for fk, f in frames(C[k]).items() if fk == "main" for l in f["land"] if l["sel"] == ".chat-composer"]
    report("3【回归】手机输入区空闲高度 ≤ 140px", bool(comp) and max(comp) <= 140, f"{comp}")

    # 4 横向溢出
    ov = [(k, fk, hf_ov, cf["overflowX"]) for k in keys for fk, cf in frames(C[k]).items()
          for hf_ov in [frames(H[k]).get(fk, {}).get("overflowX", 0)] if cf["overflowX"] > max(hf_ov, 0)]
    report("4【回归】不新增横向溢出", not ov, f"{ov[:6]}")

    # 5 裁切文字
    clip = []
    for k in keys:
        hf, cf = frames(H[k]), frames(C[k])
        for fk, f in cf.items():
            hc = collections.Counter(t["text"] for t in hf.get(fk, {}).get("texts", []) if t["clipped"])
            for t in f["texts"]:
                if t["clipped"]:
                    if hc[t["text"]] > 0: hc[t["text"]] -= 1
                    else: clip.append((k, t["text"][:20]))
    report("5【回归】不新增被裁切的文字", not clip, f"{len(clip)} 处 {clip[:8]}")

    # 6 短标签换行
    def wrapped(t):
        return not t["ctl"] and t["len"] <= 12 and t.get("lines", 0) > 1
    wr = []
    for k in keys:
        hf, cf = frames(H[k]), frames(C[k])
        for fk, f in cf.items():
            hw = collections.Counter(t["text"] for t in hf.get(fk, {}).get("texts", []) if wrapped(t))
            for t in f["texts"]:
                if wrapped(t):
                    if hw[t["text"]] > 0: hw[t["text"]] -= 1
                    else: wr.append((k[0], k[1], k[2], t["text"]))
    report("6【回归】≤12 字短标签不新增换行", not wr, f"{len(wr)} 处 {sorted(set(wr))[:10]}")

    # 7 手机可点区域
    tap = []
    for k in keys:
        if k[1] != "m390": continue
        hf, cf = frames(H[k]), frames(C[k])
        for fk, f in hf.items():
            cl = collections.defaultdict(list)
            for t in cf.get(fk, {}).get("taps", []): cl[(t["tag"], t["text"])].append(t)
            seen = collections.Counter()
            for t in f["taps"]:
                if min(t["w"], t["h"]) < 40: continue
                key = (t["tag"], t["text"]); i = seen[key]; seen[key] += 1
                cands = cl.get(key, [])
                if i < len(cands) and min(cands[i]["w"], cands[i]["h"]) < 40:
                    tap.append((k[0], k[2], t["text"][:14], round(min(cands[i]["w"], cands[i]["h"]), 1)))
    report("7【回归】手机上原本 ≥40px 的可点区域不跌破 40", not tap, f"{len(tap)} 处 {tap[:8]}")

    # 8 文字一一对应（同一画面、同一框架、同样的文字；位置容差 ±48px）
    tot = hit = 0; miss = []
    dys = []
    for k in keys:
        hf, cf = frames(H[k]), frames(C[k])
        for fk, f in hf.items():
            pool = collections.defaultdict(list)
            for t in cf.get(fk, {}).get("texts", []): pool[t["text"]].append(t)
            for t in f["texts"]:
                tot += 1
                cands = pool.get(t["text"], [])
                best = min(cands, key=lambda c: abs(c["y"] - t["y"]) + abs(c["x"] - t["x"]), default=None)
                if best and abs(best["y"] - t["y"]) <= 48 and abs(best["x"] - t["x"]) <= 48:
                    hit += 1; dys.append(abs(best["y"] - t["y"])); cands.remove(best)
                else:
                    miss.append((k[0], k[1], t["text"][:16]))
    rate = hit / tot if tot else 0
    dys.sort()
    print(f"INFO 8 按位置就近配对（±48px）{hit}/{tot} = {rate:.4f}；位移中位 {dys[len(dys)//2] if dys else 0:.1f}px、p95 {dys[int(len(dys)*.95)] if dys else 0:.1f}px；超出容差例 {miss[:4]}")
    mtot = mhit = 0; honly = []; conly = []
    for k in keys:
        hf, cf = frames(H[k]), frames(C[k])
        for fk in set(hf) | set(cf):
            a_ = collections.Counter(t["text"] for t in hf.get(fk, {}).get("texts", []))
            b_ = collections.Counter(t["text"] for t in cf.get(fk, {}).get("texts", []))
            mtot += sum(a_.values()); mhit += sum((a_ & b_).values())
            honly += [(k[0], k[1], t[:16]) for t in (a_ - b_).elements()]; conly += [(k[0], k[1], t[:16]) for t in (b_ - a_).elements()]
    report("8【回归】每个画面的可见文字与 HEAD 逐段相同（不计位置）", mtot > 1000 and not honly and not conly,
           f"{mhit}/{mtot}；只在 HEAD {len(honly)} {honly[:4]}；只在候选 {len(conly)} {conly[:4]}")

    # 11 行高：字号没变的，行高不得比 HEAD 低 2px 以上；字号变了的，按字号比例折算后不得低 2px 以上
    lhbad = []; morelines = []
    for k in keys:
        if k[2] != "day": continue   # 行高与主题无关，只看昼
        hf, cf = frames(H[k]), frames(C[k])
        for fk, f in hf.items():
            pool = collections.defaultdict(list)
            for t in cf.get(fk, {}).get("texts", []): pool[(t["tag"], t["text"])].append(t)
            for t in f["texts"]:
                c = pool.get((t["tag"], t["text"]))
                if not c: continue
                b = min(c, key=lambda x: abs(x["y"] - t["y"]) + abs(x["x"] - t["x"])); c.remove(b)
                floor = min(t["lh"], t["lh"] * (b["fs"] / t["fs"] if t["fs"] else 1)) - 2   # 行盒不缩，或按字号比例缩，都算保住
                if b["lh"] < floor: lhbad.append((k[0], k[1], t["tag"], t["text"][:12], round(t["fs"], 1), round(b["fs"], 1), round(t["lh"], 1), round(b["lh"], 1)))
                if b.get("lines", 0) > t.get("lines", 0) > 0: morelines.append((k[0], k[1], t["text"][:14], t["lines"], b["lines"]))
    report("11【回归】行高不比 HEAD 低 2px 以上（字号变小的按比例折算）", not lhbad, f"{len(lhbad)} 处 {sorted(set(lhbad))[:8]}")
    print(f"INFO 11 行数比 HEAD 多的文字块 {len(set(morelines))} 处（只报告，不判失败）：{sorted(set(morelines))[:12]}")

    # 9 遮罩颜色
    bd = [(k, H[k]["backdrop"], C[k]["backdrop"]) for k in keys if H[k].get("backdrop") != C[k].get("backdrop")]
    report("9【回归】两个对话框的遮罩颜色与 HEAD 相同", not bd, f"{bd[:4]}")

    # 10 夜间「永久删除账号」朱字对比度（候选截图取底色）
    if shots:
        from PIL import Image
        res = []
        for th in ("night", "night-solid", "day", "day-solid"):
            k = ("settings-del", "d1440", th)
            if k not in C: continue
            for fk, f in frames(C[k]).items():
                for t in f["texts"]:
                    if t["text"] == "永久删除账号" and t["tag"] != "BUTTON":
                        p = os.path.join(shots, f"settings-del-d1440-{th}.png")
                        if not os.path.exists(p): continue
                        im = Image.open(p).convert("RGB")
                        box = (int(t["x"]), int(t["y"]), int(t["x"] + t["w"]), int(t["y"] + t["h"]))
                        if box[1] < 0 or box[3] > im.height: continue
                        bg = collections.Counter(list(im.crop(box).get_flattened_data() if hasattr(im, 'get_flattened_data') else im.crop(box).getdata())).most_common(1)[0][0]
                        res.append((th, round(cr(parse_rgb(t["color"]), bg), 2), t["color"], bg))
        report("10【改】设置页「永久删除账号」朱字对其背景 ≥ 4.5", bool(res) and all(r[1] >= 4.5 for r in res), f"{res}")

    print("== FAIL", len(fails), fails)
    return len(fails)


if __name__ == "__main__":
    sys.exit(main())
