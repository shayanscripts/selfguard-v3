"""Module 1: sensitive values (links, e-mails, account numbers) and de-obfuscation."""
import base64
import re

TLDS = "com|net|org|io|ru|xyz|info|biz|co|me|app|site|top|cn|tk|ly|gg|dev|ai|online|link|click|live|shop"
URL = re.compile(rf"(?:https?://|www\.)[^\s<>\"')\]]+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:{TLDS})\b(?:/[^\s<>\"')\]]*)?", re.I)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
ACCOUNT = re.compile(r"\b(?:[A-Z]{2}\d{2}[A-Z0-9]{10,30}|\d{8,18})\b")
HOMOGLYPHS = str.maketrans({"а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "і": "i", "ӏ": "l",
                            "​": "", "‌": "", "‍": "", "﻿": ""})


def deobfuscate(text: str) -> str:
    """Undo common hiding tricks so hidden values become visible to the checks."""
    t = (text or "").translate(HOMOGLYPHS)
    t = re.sub(r"hxxp", "http", t, flags=re.I)
    t = re.sub(r"\s*[\[({]\s*(?:\.|dot)\s*[\])}]\s*|\s+dot\s+(?=[a-z])", ".", t, flags=re.I)
    t = re.sub(r"\s*[\[({]\s*(?:@|at)\s*[\])}]\s*", "@", t, flags=re.I)
    t = re.sub(r"(?:(?<!\S)\S ){4,}\S(?!\S)", lambda m: m.group(0).replace(" ", ""), t)  # s p a c e d
    extra = []
    for tok in re.findall(r"[A-Za-z0-9+/=]{16,}", t):
        try:
            dec = base64.b64decode(tok + "=" * (-len(tok) % 4)).decode("utf-8")
            if dec.isprintable():
                extra.append(dec)
        except Exception:
            pass
    return t + ("\n" + "\n".join(extra) if extra else "")


def canon(v: str) -> str:
    v = v.strip().rstrip(".,;:!?").lower()
    v = re.sub(r"^https?://", "", v)
    return re.sub(r"^www\.", "", v).rstrip("/")


def host(v: str) -> str:
    return v.split("/")[0].split("?")[0].split("@")[-1]


def values(text: str, decode: bool = True) -> set[str]:
    t = deobfuscate(text) if decode else (text or "")
    emails = {canon(e) for e in EMAIL.findall(t)}
    urls = {canon(u) for u in URL.findall(t)}
    urls = {u for u in urls if not any(u in e for e in emails)}
    return emails | urls | {canon(a) for a in ACCOUNT.findall(t)}


class TrustSet:
    """Values from trusted text (system prompt, user task, allowlist)."""

    def __init__(self, *texts: str, allow_domains=()):
        self.items = set()
        for t in texts:
            self.items |= values(t or "")
        self.items |= {canon(d) for d in allow_domains}
        self.hosts = {host(v) for v in self.items if "@" not in v}

    def __contains__(self, v: str) -> bool:
        if v in self.items:
            return True
        # a plain link on a trusted site is fine; a query string could carry data out
        return "@" not in v and "?" not in v and host(v) in self.hosts
