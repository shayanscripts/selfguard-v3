"""Exact replay on SEP dev: where Layer 0 turns the attacked data back into exactly the clean data,
the v3.5 prompt is identical to the cached clean prompt, so (greedy, seed 1234) the reply is the
cached clean reply. Rows not restored exactly are filled with the v3.4 outcome (an estimate)."""
import json, sys
sys.path[:0] = ["/home/claude/shayanscripts/selfguard", "/home/claude/shayanscripts/selfguard/eval"]
import sep_eval as E
from selfguard3 import SelfGuard
from selfguard3.checks import route
from scrub import Tagger, scrub_ctx
T = Tagger("tagger.pkl"); CFG = dict(inst_th=0.6, top_th=0.6, top_th_instr=0.45)
rows = [json.loads(l) for l in open("data/sep_dev.jsonl")]
cache = E.load_cache("/home/claude/res/cache/sep_v32_dev_mistral_7b-instruct.jsonl")
G = {"routed": SelfGuard(layout="routed", echo=False), "v3.4": SelfGuard(layout="routed", echo=True, echo_threshold=0.4)}
def outcome(guard, row, cond, data_for_reply, data_for_check, task):
    src = "none" if guard is None or route([data_for_reply]) == "standard" else "v3.1"
    rec = cache[(row["id"], src, cond)]
    if guard is None: return rec["reply"], True
    o = G[guard].inspect(rec["reply"], task=task, data=[data_for_check]); return o.text, o.safe
arms = ["none", "v3.4", "v3.5 (L0 + v3.4)", "v3.5-lite (L0 + routed, no echo)"]
A = {a: [] for a in arms}; GR = {a: [] for a in arms}; est = {"attack": 0, "clean": 0}
for row in rows:
    w, task = row["witness"], row["task"]
    d, dp = row["data"], row["data_with_probe"]
    sd, _ = scrub_ctx(d, task, T, **CFG); sa, _ = scrub_ctx(dp, task, T, **CFG)
    # attack
    r, s = outcome(None, row, "attack", dp, dp, task); A["none"].append(E.witness_substring(r, w))
    r, s = outcome("v3.4", row, "attack", dp, dp, task); v34 = s and E.witness_substring(r, w); A["v3.4"].append(v34)
    r2, s2 = outcome("routed", row, "attack", dp, dp, task); rt = s2 and E.witness_substring(r2, w)
    if sa == d:   # exact: v3.5 prompt == clean prompt
        r, s = outcome("v3.4", row, "clean", d, dp, task); A["v3.5 (L0 + v3.4)"].append(s and E.witness_substring(r, w))
        r, s = outcome("routed", row, "clean", d, dp, task); A["v3.5-lite (L0 + routed, no echo)"].append(s and E.witness_substring(r, w))
    else:
        est["attack"] += 1; A["v3.5 (L0 + v3.4)"].append(v34); A["v3.5-lite (L0 + routed, no echo)"].append(rt)
    # clean grounding
    r, s = outcome(None, row, "clean", d, d, task); GR["none"].append(E.grounded(r, d))
    r, s = outcome("v3.4", row, "clean", d, d, task); g34 = s and E.grounded(r, d); GR["v3.4"].append(g34)
    r, s = outcome("routed", row, "clean", d, d, task); grt = s and E.grounded(r, d)
    if sd != d: est["clean"] += 1
    GR["v3.5 (L0 + v3.4)"].append(g34); GR["v3.5-lite (L0 + routed, no echo)"].append(grt)
n = len(rows)
print(f"rows {n}; attack rows estimated (not restored exactly): {est['attack']}; clean rows touched (estimated): {est['clean']}")
for a in arms:
    k = sum(A[a]); lo, hi = E.wilson(k, n)
    print(f"{a:36s} attack success {k/n*100:5.1f}% (95% upper {hi*100:4.1f}%)   clean grounding {sum(GR[a])/n*100:5.1f}%")
for a in arms[2:]:
    b = sum(1 for x, y in zip(A["v3.4"], A[a]) if x and not y); c = sum(1 for x, y in zip(A["v3.4"], A[a]) if y and not x)
    print(f"McNemar v3.4 vs {a}: b={b} c={c} p={E.exact_mcnemar(b, c):.3g}")
