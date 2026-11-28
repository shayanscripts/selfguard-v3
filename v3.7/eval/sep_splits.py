"""SEP splits for SelfGuard: deterministic, rebuilt from the public SEP archive. Never prints
row text, only counts and hashes; refuses to overwrite.

  python eval/sep_splits.py dev                # data/sep/dev.jsonl (600 rows, development only)
  python eval/sep_splits.py sealed --dry-run   # counts for the fresh v3.4 sealed split
  python eval/sep_splits.py sealed             # data/sealed_v34.jsonl (600 fresh rows)

Archive: https://github.com/egozverev/Should-It-Be-Executed-Or-Processed (main branch zip),
saved as Should-It-Be-Executed-Or-Processed-main.zip (or pass --zip / set SEP_ZIP). Its SHA-256
must match ARCHIVE_SHA256.

How rows are chosen: probes (info.appended_task_id) and subtasks (info.subtask) are each split
into two disjoint seeded halves. The dev split is 600 rows from dev probes x dev subtasks; the
first sealed test was 600 rows from test probes x test subtasks; v3.0's sealed split was 600
further test-pool rows; the v3.4 sealed split is 600 more test-pool rows that are in none of
those. Every sample is stratified over position x insistent. The three earlier splits are
rebuilt in memory and checked against their published SHA-256 before anything is written.
"""
import argparse
import hashlib
import json
import os
import random
import sys
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_SHA256 = "275f3536fc89d0aa99d10e14d6b7313a3258092f002b966e2bdfb951cc66cc19"
MEMBER = "Should-It-Be-Executed-Or-Processed-main/SEP_dataset/SEP_dataset.json"
PARTITION_SEED = 20261117
N = 600
# published hashes of the earlier splits (each must be reproduced exactly)
DEV_SHA256 = "43c1521b6413a3ec0480d1a87e510d6d3627a67b8a72dbe00422f6ea3b0262cc"
FIRST_SEALED_SHA256 = "cd22d956fbc895572d75a31d265ec3b89de7fa8911182e8157936511da1205dc"
V30_SEALED_SHA256 = "f2a8adbec7ccc9c98b5cb485504b91b37eb0e0d8eb2d83d2ffd0278b95a90fc8"
V30_SEED, V34_SEED = 20261118, 20261122


def row_id(task, task_with_probe, data, data_with_probe):
    joined = "\x00".join((task, task_with_probe, data, data_with_probe))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]


def convert(row):
    info = row["info"]
    task, task_with_probe = row["system_prompt_clean"], row["system_prompt_instructed"]
    data, data_with_probe = row["prompt_clean"], row["prompt_instructed"]
    return {"id": row_id(task, task_with_probe, data, data_with_probe), "task": task,
            "task_with_probe": task_with_probe, "data": data, "data_with_probe": data_with_probe,
            "witness": row["witness"], "probe_id": info["appended_task_id"], "subtask": info["subtask"],
            "position": info["appended_type"], "insistent": info["is_insistent"]}


def _halves(values, rng):
    items = sorted(set(values), key=repr)
    rng.shuffle(items)
    cut = len(items) // 2
    return set(items[:cut]), set(items[cut:])


def partition(rows, seed=PARTITION_SEED):
    """(dev_probes, test_probes, dev_subtasks, test_subtasks)."""
    rng = random.Random(seed)
    dev_p, test_p = _halves((r["info"]["appended_task_id"] for r in rows), rng)
    dev_s, test_s = _halves((r["info"]["subtask"] for r in rows), rng)
    return dev_p, test_p, dev_s, test_s


def sample(pool, n, rng, label):
    """n rows with equal allocation over the (position, insistent) strata."""
    strata = {}
    for r in sorted(pool, key=lambda r: r["id"]):
        strata.setdefault((r["position"], r["insistent"]), []).append(r)
    keys = sorted(strata)
    if not keys:
        raise ValueError(f"{label}: empty pool")
    base, extra = divmod(n, len(keys))
    out = []
    for i, k in enumerate(keys):
        want = base + (1 if i < extra else 0)
        if len(strata[k]) < want:
            raise ValueError(f"{label}: stratum {k} has {len(strata[k])} rows, need {want}")
        out.extend(rng.sample(strata[k], want))
    return sorted(out, key=lambda r: r["id"])


def jsonl(rows, sort_keys):
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=sort_keys) + "\n" for r in rows).encode("utf-8")


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    with open(path, "rb") as f:
        return sha256_bytes(f.read())


def build(rows):
    """Every split, rebuilt and checked: {name: (rows, bytes)}."""
    for row in rows:
        if not isinstance(row["info"]["is_insistent"], bool):
            raise TypeError("is_insistent must be bool")
    dev_p, test_p, dev_s, test_s = partition(rows)
    dev_pool = [convert(r) for r in rows if r["info"]["appended_task_id"] in dev_p and r["info"]["subtask"] in dev_s]
    test_pool = [convert(r) for r in rows if r["info"]["appended_task_id"] in test_p and r["info"]["subtask"] in test_s]
    rng = random.Random(PARTITION_SEED + 1)
    dev = sample(dev_pool, N, rng, "dev")
    first = sample(test_pool, N, rng, "first sealed")
    used = {r["id"] for r in dev + first}
    v30 = sample([r for r in test_pool if r["id"] not in used], N, random.Random(V30_SEED), "v3.0 sealed")
    used |= {r["id"] for r in v30}
    fresh = [r for r in test_pool if r["id"] not in used]
    out = {"dev": (dev, jsonl(dev, True)), "first_sealed": (first, jsonl(first, True)),
           "v30_sealed": (v30, jsonl(v30, False))}
    for name, want in (("dev", DEV_SHA256), ("first_sealed", FIRST_SEALED_SHA256), ("v30_sealed", V30_SEALED_SHA256)):
        if sha256_bytes(out[name][1]) != want:
            raise SystemExit(f"{name} split does not reproduce its published hash: stop, do not continue")
    return out, test_pool, fresh, used


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("which", choices=["dev", "sealed"])
    ap.add_argument("--zip", default=os.environ.get("SEP_ZIP", os.path.join(HERE, "Should-It-Be-Executed-Or-Processed-main.zip")))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if sha256_file(a.zip) != ARCHIVE_SHA256:
        sys.exit("SEP archive SHA-256 mismatch: the SEP repo changed since the freeze; stop")
    with zipfile.ZipFile(a.zip) as z:
        rows = json.loads(z.read(MEMBER).decode("utf-8"))
    splits, pool, fresh, used = build(rows)
    print(f"source rows {len(rows)}; dev, first sealed and v3.0 sealed splits reproduce their published hashes")
    if a.which == "dev":
        path, body = os.path.join(HERE, "data", "sep", "dev.jsonl"), splits["dev"][1]
    else:
        strata = {}
        for r in fresh:
            strata[(r["position"], r["insistent"])] = strata.get((r["position"], r["insistent"]), 0) + 1
        print(f"test pool {len(pool)}, already used {len(pool) - len(fresh)}, fresh {len(fresh)}")
        print("fresh rows per stratum (position, insistent):", dict(sorted(strata.items(), key=str)))
        if a.dry_run:
            return
        sealed = sample(fresh, N, random.Random(V34_SEED), "v3.4 sealed")
        assert not {r["id"] for r in sealed} & used
        path, body = os.path.join(HERE, "data", "sealed_v34.jsonl"), jsonl(sealed, False)
    if os.path.exists(path):
        sys.exit("refusing to overwrite " + path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(body)
    if a.which == "sealed":
        os.chmod(path, 0o444)
    print(f"wrote {os.path.relpath(path, HERE)}: {body.count(b'\n')} rows, SHA-256 {sha256_bytes(body)}")


if __name__ == "__main__":
    main()
