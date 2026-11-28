"""ASIDE's indirect-injection benchmarks (StruQ, BIPIA-text, BIPIA-code, SEP) on SelfGuard v3.7, reusing
eval/aside_bench.py's items, scoring and the cached no-defence and v3.4 replies (same model, greedy,
seed 1234, 256 tokens). v3.7 = Layer 0 on the data, then SelfGuard(layout="routed", echo=False); the
reply checks see the original data. When Layer 0 leaves the data unchanged the prompt is byte-identical
to v3.4's, so v3.4's raw reply is reused and only re-checked; otherwise a new reply is generated.

Items run in a fixed random order (seed 0), --rotate N per benchmark per round, until --until HH:MM, so
every benchmark holds a growing random sample; partial results are reported with their n.

  python eval/aside_v37.py --aside ../aside-src --rotate 100 --until 13:15
"""
import argparse
import datetime
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "eval")]
import aside_bench as A  # noqa: E402
from llm import LLM  # noqa: E402
from selfguard3 import SelfGuard  # noqa: E402
from selfguard3.scrub import Layer0  # noqa: E402

BENCHES = ("struq", "bipia-text", "bipia-code", "sep")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aside", required=True)
    ap.add_argument("--model", default="mistral:7b-instruct")
    ap.add_argument("--rotate", type=int, default=100)
    ap.add_argument("--until", default="13:15")
    ap.add_argument("--bench", nargs="+", default=list(BENCHES))
    a = ap.parse_args()
    tag = a.model.replace(":", "_")
    llm = LLM(a.model, seed=1234, max_tokens=256)
    l0 = Layer0(os.path.join(HERE, "models", "tagger.pkl"))
    sg = SelfGuard(layout="routed", echo=False)
    h, m = map(int, a.until.split(":"))
    deadline = datetime.datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
    order, base, mine, paths = {}, {}, {}, {}
    for b in a.bench:
        its = A.items(b, a.aside)
        random.Random(0).shuffle(its)
        order[b] = its
        base[b] = {}
        for l in open(os.path.join(HERE, "results", "cache", f"aside_{b}_{tag}.jsonl"), encoding="utf-8"):
            if l.strip():
                d = json.loads(l); base[b][(d["key"], d["arm"])] = d
        paths[b] = os.path.join(HERE, "results", "cache", f"aside_v37_{b}_{tag}.jsonl")
        mine[b] = {}
        if os.path.exists(paths[b]):
            for l in open(paths[b], encoding="utf-8"):
                d = json.loads(l); mine[b][d["key"]] = d
        print(f"{b}: {len(its)} items, {len(mine[b])} done", file=sys.stderr, flush=True)
    A.ARMS = ("none", "v3.4", "v3.7")
    out_path = os.path.join(HERE, "results", f"aside_v37_{tag}.json")
    stats = {b: {"reused": 0, "generated": 0} for b in a.bench}
    rnd = 0
    while True:
        rnd += 1
        left = False
        for b in a.bench:
            todo = [it for it in order[b] if it[0] not in mine[b] and (it[0], "v3.4") in base[b]][:a.rotate]
            left |= bool(todo)
            with open(paths[b], "a", encoding="utf-8") as f:
                for key, instruction, data, _ in todo:
                    sd = l0(data, instruction)
                    if sd == data:
                        reply = base[b][(key, "v3.4")]["reply"]; stats[b]["reused"] += 1
                    else:
                        reply = llm(sg.prepare(instruction, [sd]).messages); stats[b]["generated"] += 1
                    o = sg.inspect(reply, task=instruction, data=[data], canary=None)
                    rec = {"key": key, "arm": "v3.7", "reply": reply, "shown": o.text if o.safe else "", "safe": o.safe,
                           "l0_changed": sd != data}
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()
                    mine[b][key] = rec
        scores = {}
        for b in a.bench:
            cache = dict(base[b]); cache.update({(k, "v3.7"): v for k, v in mine[b].items()})
            sample = [it for it in order[b] if it[0] in mine[b]]
            scores[b] = A.score(b, sample, cache, a.aside)
            scores[b]["l0_changed"] = sum(v["l0_changed"] for v in mine[b].values())
        json.dump({"model": llm.describe(), "stats": stats, "scores": scores}, open(out_path, "w"), indent=1, default=str)
        print(f"round {rnd} {datetime.datetime.now():%H:%M} " + " | ".join(
            f"{b} n={scores[b].get('n_scored')}" for b in a.bench), file=sys.stderr, flush=True)
        if not left or datetime.datetime.now() >= deadline:
            break


if __name__ == "__main__":
    main()
