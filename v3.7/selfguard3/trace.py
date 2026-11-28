"""Module 4: support trace. A reply sentence whose claim is supported in the
document ONLY by sentences addressed to the AI is an injected claim.

Backends:  'lexical' - zero compute, word matching (free tier)
           'minicheck' - MiniCheck-RoBERTa-Large fact checker (Tang et al. 2024), local
"""
import re

AI_ADDRESSED = re.compile(
    r"\b(assistant|a\.i\.|ai|chatbot|language model|llm|gpt|claude|model)\b|tell the user|inform the user|let the user know|"
    r"\bwhen (?:you )?(?:summari[sz]\w*|repl\w*|respond\w*|answer\w*)|in your (?:reply|summary|answer|response|output)|"
    r"\b(?:say|state|mention|claim|report|write) that\b|ignore (?:all |the |any )?(?:previous|prior|above|earlier)|"
    r"\binstead(?:,| of)\b.*\b(?:say|tell|write|answer)", re.I)
# Claim-bearing tokens: numbers/amounts/times, day and month names (any case), and
# Capitalised words (names, places). Only the first two ignore case: with a global
# re.I the last branch matched every word of 3+ letters.
CLAIM_TOKEN = re.compile(
    r"\$?\d[\d,.:]*\s?(?i:am|pm|%)?|\b(?i:monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|"
    r"april|may|june|july|august|september|october|november|december)\b|\b[A-Z][a-z]{2,}\b")
STOP = {"the", "this", "that", "you", "your", "user", "and", "please", "note", "assistant", "summary", "email", "hi", "hello",
        "thanks", "regards", "best", "dear", "sam"}
WRAPPER = re.compile(
    r"^.*?\b(?:(?:tell|inform|remind|let) the user(?: know)?(?: that)?|(?:say|state|mention|claim|write|report|answer) that|"
    r"(?:note|message|instruction)s? (?:to|for) the (?:assistant|ai|model)\s*:?)\s*", re.I)
SENT = re.compile(r"[^.!?\n]+[.!?]?")


def sentences(text: str) -> list[str]:
    return [s for s in SENT.findall(text or "") if s.strip()]


def split_doc(data: str):
    s = sentences(data)
    addressed = [x for x in s if AI_ADDRESSED.search(x)]
    normal = [x for x in s if x not in addressed]
    return addressed, normal


class SupportTrace:
    def __init__(self, backend: str = "lexical", threshold: float = 0.5):
        self.backend = backend
        self.threshold = threshold
        self._model = None

    # --- MiniCheck ---------------------------------------------------------
    def _load(self):
        if self._model is None:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            name = "lytang/MiniCheck-RoBERTa-Large"
            self._tok = AutoTokenizer.from_pretrained(name)
            self._model = AutoModelForSequenceClassification.from_pretrained(name).eval()

    def support(self, doc: str, claim: str) -> float:
        import torch
        self._load()
        enc = self._tok(doc, claim, truncation="only_first", max_length=512, return_tensors="pt")
        with torch.no_grad():
            return torch.softmax(self._model(**enc).logits, -1)[0, 1].item()

    # --- main --------------------------------------------------------------
    def injected(self, reply: str, data: str) -> list[tuple[str, str]]:
        """[(reply_sentence, reason)] for claims whose only support is AI-addressed text."""
        addressed, normal = split_doc(data)
        if not addressed:
            return []  # no sentence talks to the AI: nothing can have been injected this way
        out = []
        if self.backend == "minicheck":
            # an instruction is not a fact: strip its wrapper ("tell the user that ...") to get the
            # claim it plants, read in the document's context
            normal_doc = " ".join(normal)
            planted = [normal_doc + " " + WRAPPER.sub("", a).strip() for a in addressed]
            for sent in sentences(reply):
                if len(sent.split()) < 3:
                    continue
                if self.support(normal_doc, sent) < self.threshold and any(self.support(p, sent) >= self.threshold for p in planted):
                    out.append((sent, "supported only by AI-addressed text"))
            return out
        norm_l, addr_l = " ".join(normal).lower(), " ".join(addressed).lower()
        for sent in sentences(reply):
            for tok in CLAIM_TOKEN.findall(sent):
                t = tok.strip().lower()
                if len(t) < 3 or t in STOP:
                    continue
                if re.search(rf"\b{re.escape(t)}\b", addr_l) and not re.search(rf"\b{re.escape(t)}\b", norm_l):
                    out.append((sent, tok.strip()))
                    break
        return out

    def clean(self, reply: str, data: str):
        found = self.injected(reply, data)
        text = reply
        for sent, _ in found:
            text = text.replace(sent, "")
        return text, found
