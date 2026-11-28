"""Post-hoc: attribute the judge's v3.7-vs-none outcomes to their cause (no new generations or judge calls).
Each differing clean row is put in one class: withheld (reply check blocked it), layer0 (Layer 0 changed
the document), displaced (routing chose the low-authority layout, Layer 0 changed nothing), reply_text_edited (standard layout, same raw reply, the reply checks altered the shown text).
  python eval/judge_breakdown.py   -> results/judge_breakdown_sealed_mistral.json
"""
import json, os, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [HERE, os.path.join(HERE, "eval")]
import sep_eval as E  # noqa: E402
from selfguard3 import SelfGuard  # noqa: E402
from selfguard3.checks import route  # noqa: E402
from selfguard3.scrub import Layer0  # noqa: E402

rows = [json.loads(l) for l in open(os.path.join(HERE, "data", "sealed_v34.jsonl"), encoding="utf-8") if l.strip()]
tag = "sealed_mistral_7b-instruct"
base = E.load_cache(os.path.join(HERE, "results", "cache", f"sep_v35base_{tag}.jsonl"))
gen = {}
for l in open(os.path.join(HERE, "results", "cache", f"sep_v35_{tag}.jsonl"), encoding="utf-8"):
    d = json.loads(l); gen[(d["row"], d["cond"])] = d["reply"]
jc = {}
for l in open(os.path.join(HERE, "results", "cache", "judge_quality_sealed_mistral.jsonl"), encoding="utf-8"):
    d = json.loads(l); jc[d["key"]] = d["out"]
l0, sg = Layer0(os.path.join(HERE, "models", "tagger.pkl")), SelfGuard(layout="routed", echo=False)
out = {}
for r in rows:
    task, data = r["task"], r["data"]
    rn = base[(r["id"], "none", "clean")]["reply"]
    sd = l0(data, task)
    src = "none" if route([sd]) == "standard" else "v3.1"
    rv = base[(r["id"], src, "clean")]["reply"] if sd == data else gen[(r["id"], "clean")]
    o = sg.inspect(rv, task=task, data=[data])
    rv = o.text if o.safe else ""
    if rn.strip() == rv.strip():
        continue
    cls = "withheld" if not o.safe else "layer0" if sd != data else "displaced" if src == "v3.1" else "reply_text_edited"
    j1, j2 = jc[f"{r['id']}|ab"][:1].upper(), jc[f"{r['id']}|ba"][:1].upper()
    v = "v3.7" if (j1, j2) == ("A", "B") else "none" if (j1, j2) == ("B", "A") else "tie"
    out.setdefault(cls, {"v3.7": 0, "none": 0, "tie": 0})[v] += 1
json.dump(out, open(os.path.join(HERE, "results", "judge_breakdown_sealed_mistral.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
