import spacy, numpy as np, re
NLP = spacy.load("en_core_web_md", disable=["ner"])
_cache = {}
def doc(t):
    if t not in _cache: _cache[t] = NLP(t)
    return _cache[t]
CONTENT = {"NOUN", "PROPN", "VERB", "ADJ", "NUM"}
def content_vecs(d):
    toks = [t for t in d if t.pos_ in CONTENT and not t.is_stop and t.has_vector and len(t.text) > 2]
    if not toks: return [], np.zeros((0, 300))
    V = np.array([t.vector / (np.linalg.norm(t.vector) + 1e-9) for t in toks])
    return [t.lemma_.lower() for t in toks], V
def imperative(seg):
    d = doc(seg.strip())
    for s in d.sents:
        toks = [t for t in s if not t.is_punct and not t.is_space]
        if not toks: continue
        f = toks[0]
        if f.tag_ == "VB" and f.lower_ not in {"be", "do"}: return 1.0
        if f.lower_ in {"please", "now", "also", "then", "next", "finally", "additionally"} and len(toks) > 1 and toks[1].tag_ == "VB": return 1.0
    return 0.0
def question(seg):
    return 1.0 if seg.strip().endswith("?") else 0.0
def topicality(seg, context):
    """mean over the segment's content words of the best cosine match in the context"""
    _, A = content_vecs(doc(seg.strip()))
    _, B = content_vecs(doc(context))
    if len(A) == 0: return 1.0
    if len(B) == 0: return 0.0
    return float((A @ B.T).max(axis=1).mean())
