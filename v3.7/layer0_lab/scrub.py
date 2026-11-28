"""SelfGuard Layer 0: Instruction Scrub.

Removes sentences in untrusted data that are instructions aimed at the AI, before the model
reads the data. Non-blocking: only flagged segments are deleted, the rest of the document is
kept. The tagger is trained only on instruction-tuning data (Alpaca-cleaned instructions as
positives, Alpaca answers/inputs and benign e-mail/code text as negatives), never on prompt
injection examples (the CommandSans recipe, Das et al., ICLR 2026).

  score(segment) = P_tagger(instruction | segment) + addressee bonus
  segment removed  <=>  score >= threshold
  a removed segment ending in ':' also removes the block it introduces (its "payload").
"""
import re
import pickle

# Generic cues that a sentence addresses the assistant's own output or instructions.
# Fixed before any held-out evaluation; none mention a benchmark's probe wording.
ADDRESSEE = [
    r"\byour (response|reply|answer|output|summary|code implementation|code|codebase|implementation|solution|program|script|explanation|elucidation|algorithm)\b",
    r"\b(in|to|into) your (response|reply|answer|output)\b",
    r"\bignore (all |any )?(the )?(previous|prior|above|earlier)\b",
    r"\b(previous|prior|above) instructions?\b",
    r"\byour (main|primary|original) task\b",
    r"\bas an? (ai|assistant|language model)\b",
    r"\b(ai|assistant|chatbot|language model)\b.*\b(must|should|need to)\b",
]
ADDRESSEE_RE = [re.compile(p, re.I) for p in ADDRESSEE]
BONUS = 0.35

_SENT = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")


def segments(text):
    """Split into (start, end) spans: lines, then sentences inside each line."""
    spans, pos = [], 0
    for line in text.split("\n"):
        start = pos
        if line.strip():
            cuts = [0] + [m.end() for m in _SENT.finditer(line)] + [len(line)]
            for a, b in zip(cuts, cuts[1:]):
                if line[a:b].strip():
                    spans.append((start + a, start + b))
        pos += len(line) + 1
    return spans


def featurize(s):
    s = s.strip()
    return "BOS_" + s


class Tagger:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.vec, self.clf = pickle.load(f)
        self.cache = {}

    def prob(self, segs):
        todo = [s for s in set(segs) if s not in self.cache]
        if todo:
            X = self.vec.transform([featurize(s) for s in todo])
            for s, p in zip(todo, self.clf.predict_proba(X)[:, 1]):
                self.cache[s] = float(p)
        return [self.cache[s] for s in segs]


def score(tagger, segs):
    out = []
    for s, p in zip(segs, tagger.prob(segs)):
        bonus = BONUS if any(r.search(s) for r in ADDRESSEE_RE) else 0.0
        out.append(min(1.0, p + bonus))
    return out


def scrub(text, tagger, threshold=0.5, payload=True):
    """Return (clean_text, removed_spans)."""
    spans = segments(text)
    if not spans:
        return text, []
    segs = [text[a:b] for a, b in spans]
    sc = score(tagger, segs)
    remove = [s >= threshold for s in sc]
    if payload:
        i = 0
        while i < len(spans):
            if remove[i] and segs[i].rstrip().endswith(":"):
                # remove the introduced block: a fenced block, or following lines up to a blank line
                j, fenced = i + 1, False
                while j < len(spans):
                    t = segs[j].strip()
                    if j == i + 1 and t.startswith("```"):
                        fenced = True
                        remove[j] = True
                        if t.count("```") >= 2 and len(t) > 3:
                            break
                        j += 1
                        continue
                    if fenced:
                        remove[j] = True
                        if t.startswith("```"):
                            break
                    else:
                        gap = text[spans[j - 1][1]:spans[j][0]]
                        if gap.count("\n") >= 2:
                            break
                        remove[j] = True
                    j += 1
            i += 1
    removed = [sp for sp, r in zip(spans, remove) if r]
    out, last = [], 0
    for a, b in removed:
        out.append(text[last:a])
        last = b
    out.append(text[last:])
    clean = "".join(out)
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, removed


# ---- context-conditioned scrub (v3.5 Layer 0) ---------------------------------------------
# A segment is an injection only if it is (a) instruction-like and (b) off-topic for the trusted
# task and the rest of the document. Instructions that ARE the material the task asks to process
# ("Solve x^2-5x+6=0" under a maths task) stay; off-topic orders ("Mention the material used to
# make windows" inside a recipe request) go. Addressee cues ("in your response", "ignore previous")
# remove a segment on their own.
CODE_RE = re.compile(r"^\s{2,}\S|[{};]\s*$|^\s*(import|from|return|def|class|echo|print|try|catch|if|for|while|var|let|const|public|private|void|int|#include)\b|[=(){}\[\]].*[=(){}\[\]]")
EXPECTS_INSTR = re.compile(r"\b(prompts?|instructions?|questions?|problems?|equations?|steps?|requests?|queries|query|tasks?|faqs?|calculations?|commands?)\b", re.I)


def scrub_ctx(text, task, tagger, inst_th=0.5, top_th=0.55, top_th_instr=0.45, payload=True):
    """top_th_instr applies when the trusted task itself says the data holds instructions/prompts."""
    from feats import imperative, question, topicality
    if EXPECTS_INSTR.search(task):
        top_th = top_th_instr
    spans = segments(text)
    if not spans:
        return text, []
    segs = [text[a:b] for a, b in spans]
    probs = tagger.prob(segs)
    remove = []
    for (a, b), s, p in zip(spans, segs, probs):
        if any(r.search(s) for r in ADDRESSEE_RE):
            remove.append(True); continue
        if CODE_RE.search(s):
            remove.append(False); continue
        instr = max(p, 0.6 * imperative(s), 0.5 * question(s))
        if instr < inst_th:
            remove.append(False); continue
        rest = text[:a] + text[b:]
        remove.append(topicality(s, task + "\n" + rest) < top_th)
    return _apply(text, spans, segs, remove, payload)


def _apply(text, spans, segs, remove, payload):
    if payload:
        for i in range(len(spans)):
            if remove[i] and segs[i].rstrip().endswith(":"):
                j, fenced = i + 1, False
                while j < len(spans):
                    t = segs[j].strip()
                    if j == i + 1 and t.startswith("```"):
                        fenced = True; remove[j] = True
                        if t.count("```") >= 2 and len(t) > 3: break
                        j += 1; continue
                    if fenced:
                        remove[j] = True
                        if t.startswith("```"): break
                    else:
                        if text[spans[j - 1][1]:spans[j][0]].count("\n") >= 2: break
                        remove[j] = True
                    j += 1
    removed = [sp for sp, r in zip(spans, remove) if r]
    if not removed:
        return text, []
    out, last = [], 0
    for a, b in removed:
        out.append(text[last:a]); last = b
    out.append(text[last:])
    clean = re.sub(r"[ \t]{2,}", " ", "".join(out))
    return re.sub(r"\n{3,}", "\n\n", clean).strip(), removed
