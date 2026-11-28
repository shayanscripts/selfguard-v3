"""Train the Layer 0 instruction tagger on instruction-tuning data only (no prompt-injection data).
  git clone https://github.com/gururise/AlpacaDataCleaned data/src/AlpacaDataCleaned
  git clone https://github.com/microsoft/BIPIA data/src/BIPIA
  python eval/train_tagger.py
"""
import json, random, pickle, sys
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion
from sklearn.linear_model import LogisticRegression
import sys, os
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from selfguard3.scrub import segments, featurize
random.seed(7)
SRC = os.environ.get("L0_SRC", os.path.join(HERE, "data", "src"))
A = json.load(open(os.path.join(SRC, "AlpacaDataCleaned/alpaca_data_cleaned.json")))
pos, neg = [], []
for x in A:
    ins = x["instruction"].strip()
    if ins: pos.append(ins)
    for field in ("input", "output"):
        t = x[field]
        neg += [t[a:b] for a, b in segments(t)]
# benign in-domain text from BIPIA *train* contexts (clean, no attacks)
for l in open(os.path.join(SRC, "BIPIA/benchmark/email/train.jsonl")):
    t = json.loads(l)["context"]; neg += [t[a:b] for a, b in segments(t)]
for l in open(os.path.join(SRC, "BIPIA/benchmark/code/train.jsonl")):
    t = "\n".join(json.loads(l)["context"]); neg += [t[a:b] for a, b in segments(t)]
neg = [s for s in neg if len(s.strip()) > 2]
random.shuffle(neg)
neg = neg[:120000]
print("pos", len(pos), "neg", len(neg))
X = pos + neg; y = [1]*len(pos) + [0]*len(neg)
vec = FeatureUnion([
    ("w", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=200000, sublinear_tf=True, token_pattern=r"(?u)\b\w+\b")),
    ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, max_features=200000, sublinear_tf=True)),
])
Xv = vec.fit_transform([featurize(s) for s in X])
clf = LogisticRegression(C=4.0, max_iter=2000, class_weight="balanced")
clf.fit(Xv, y)
os.makedirs(os.path.join(HERE, "models"), exist_ok=True)
pickle.dump((vec, clf), open(os.path.join(HERE, "models", "tagger.pkl"), "wb"))
print("trained")
