"""Module 3: reply tripwire. Untrusted links/e-mails are defanged (unclickable),
untrusted images removed, values hidden by obfuscation flagged."""
import re
from dataclasses import dataclass, field
from .values import EMAIL, URL, TrustSet, canon, deobfuscate, values

IMG = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


@dataclass
class ReplyResult:
    text: str
    safe: bool = True
    findings: list = field(default_factory=list)


def defang(s: str) -> str:
    return s.replace("http", "hxxp").replace(".", "[.]").replace("@", "[at]")


class Tripwire:
    def __init__(self, trust: TrustSet, allow_data_values: bool = False):
        self.trust = trust
        self.allow_data_values = allow_data_values  # e.g. task "list the links in this e-mail"

    def clean(self, reply: str, data: str = "") -> ReplyResult:
        res = ReplyResult(reply)
        ok_data = values(data) if self.allow_data_values else set()
        trusted = lambda v: v in self.trust or v in ok_data  # noqa: E731
        for m in IMG.finditer(reply):
            if not trusted(canon(m.group(1))):
                res.text = res.text.replace(m.group(0), "[image removed]")
                res.findings.append(("image", canon(m.group(1))))
        emails = {canon(e) for e in EMAIL.findall(res.text)}
        for raw in sorted(set(URL.findall(res.text)), key=len, reverse=True):  # e-mails in prose are not clickable; actions are locked
            v = canon(raw)
            if trusted(v) or ("@" not in v and any(v in e for e in emails)):
                continue
            res.text = res.text.replace(raw, defang(raw))
            res.findings.append(("defanged", v))
        shown = {f[1] for f in res.findings}
        plain = values(reply, decode=False)
        for v in values(reply) - plain - shown:
            if not trusted(v):
                res.safe = False
                res.findings.append(("obfuscated", v))
        return res
