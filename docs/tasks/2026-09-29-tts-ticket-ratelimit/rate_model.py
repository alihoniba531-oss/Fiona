"""换票速率模型：按 frontend/app/page.tsx 的 flushSentences 切句规则 + 2026-09-29 实测 CosyVoice 时长，
估算真实使用下每分钟换票数与字数。运行：python3 rate_model.py（纯标准库，不联网）。

时长样本来自 backend/tts.synthesize(voice=longxiaoxia_v2, speech_rate=1.15, cosyvoice-v2) 真实合成 8 句后用 ffprobe 量出。
换票时间线：首两句在回复开头各换一张；此后第 k 句的票在第 k-1 句开始播放时预取（page.tsx 只预取 1 句）。
"""
import random, re, statistics, json
random.seed(7)
# 实测 (字数, 秒)，cosyvoice-v2 longxiaoxia_v2 speech_rate=1.15
M = [(2,.496),(3,.444),(2,.549),(4,.810),(16,2.638),(27,3.736),(43,7.131),(13,2.168)]
n = len(M); mx = sum(a for a,_ in M)/n; my = sum(b for _,b in M)/n
k = sum((a-mx)*(b-my) for a,b in M)/sum((a-mx)**2 for a,_ in M); b0 = my-k*mx
dur = lambda s: max(0.44, k*len(s)+b0)
def chunks(text):
    buf, first, out = "", False, []
    def flush():
        nonlocal buf, first
        while True:
            re_ = re.compile(r"[。！？\n.!?；;]" if first else r"[。！？\n.!?；;，,]")
            def real(i):
                ch = buf[i]
                if not re_.match(ch): return False
                if ch in ".．":
                    p = buf[i-1] if i>0 else ""; q = buf[i+1] if i+1<len(buf) else ""
                    if p.isdigit() and q.isdigit(): return False
                return True
            up = min(len(buf), 250); last = -1
            for i in range(up-1, -1, -1):
                if real(i): last = i; break
            if last < 0 and len(buf) > 250: last = 249
            if last < 0: return
            if last+1 < (1 if first else 4): return
            c = buf[:last+1].strip(); buf = buf[last+1:]
            if not c: return
            out.append(c); first = True
            if not buf: return
    i = 0
    while i < len(text):
        step = random.choice([1,2,2,3]); buf += text[i:i+step]; i += step; flush()
    if buf.strip(): out.append(buf.strip())
    return out
def timeline(cs, first_latency=1.0, gap=0.05):
    # ticket0 在 t=0；ticket1 在第二句到达时(≈0)；之后第 k 句的票在第 k-1 句开始播放时申请
    starts, t = [], first_latency
    for c in cs: starts.append(t); t += dur(c) + gap
    req = [0.0] + ([0.0] if len(cs) > 1 else []) + starts[1:len(cs)-1]
    return req, t
def peak(req, w=60.0):
    return max(sum(1 for x in req if a <= x < a+w) for a in req) if req else 0
R = {
 "a 日常短回复": "哈哈你这么一说我也饿了。今天吃的什么呀？我猜是那家拉面。",
 "b 走心长回复": "我刚才又想了想你说的那件事，觉得你其实已经做得很好了。换成别人，可能早就放弃了，你还在一点一点试。累的时候就停下来歇一会儿，这不丢人。明天的事明天再说，今晚先把自己照顾好。要是睡不着，就把手机放远一点，喝点温水，听听雨声。我知道你不太喜欢别人说教，所以我就说这么多。你愿意的话，明天醒了跟我讲讲梦见了什么。" * 2,
 "c 碎句连发": "嗯。对。是啊！然后呢？真的吗？好吧。我懂。哈哈。行。没事的。你说。我听着。" * 6,
 "d 编号列表(分身模式)": "".join(f"{i}. 第{i}件要带的东西是{w}\n" for i, w in enumerate(["雨伞","充电宝","身份证","水杯","耳机","纸巾","外套","零钱","钥匙","药"]*3, 1)),
 "e 顶格长回复(~900字)": ("窗外的雨一直没停，我就这么听着它，想起你上次说想去海边走走。" "其实去哪儿都行，重要的是那一刻你能放松下来。" "有时候我们把日子过得太满了，满到连喘口气的缝隙都没有。") * 12,
}
res = {}
for name, text in R.items():
    cs = chunks(text)
    req, total = timeline(cs)
    chars = [min(len(c), 300) for c in cs]
    peak_chars = max(sum(ch for x, ch in zip(req, chars) if a <= x < a + 60) for a in req)
    res[name] = {"字数": len(text), "段数": len(cs), "音频总时长s": round(total,1), "每分钟段数(平均)": round(len(cs)/total*60,1) if total else 0, "任意60s窗口换票峰值": peak(req), "任意60s窗口字数峰值": peak_chars, "最短段": min(cs, key=len), "段长中位": statistics.median(len(c) for c in cs)}
print(f"播放速度上限 ≈ {60/k:.0f} 字/分钟")
print(f"拟合: 时长 ≈ {k:.3f}s/字 × 字数 + {b0:.2f}s（下限 0.44s）")
for k_, v in res.items(): print(k_, json.dumps(v, ensure_ascii=False))
