import sys, json
sys.path.insert(0, "/home/claude/shayanscripts/selfguard/eval")
import sep_splits as S
rows = json.load(open("/tmp/sepgit/SEP_dataset/SEP_dataset.json"))
out, pool, fresh, used = S.build(rows)   # raises unless dev/first/v30 reproduce published hashes
for n in ("dev", "first_sealed", "v30_sealed"):
    open(f"data/sep_{n}.jsonl", "wb").write(out[n][1])
print("hash-verified; rows", len(rows), "fresh pool untouched:", len(fresh))
