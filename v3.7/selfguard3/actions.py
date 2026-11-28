"""Module 2: value locks on actions + the 'cashier' (human approval).

An action may run only if every sensitive value in its arguments comes from
trusted text. Anything else is held for a human, or refused if none is there.
Risky verbs (send, pay, delete, ...) driven by a document always ask.
"""
import re
from dataclasses import dataclass, field
from .values import TrustSet, values

# actions that are dangerous even without any outside value in them
SENSITIVE_ACTION = re.compile(r"password|passcode|credential|secret|token|2fa|permission|role|admin|update_user", re.I)

RISKY = ("send", "forward", "email", "mail", "pay", "transfer", "delete", "remove", "post", "share", "upload", "exec", "run")

# Word stems in the user's request that license each kind of risky action.
_MESSAGE = ("send", "email", "e-mail", "mail", "repl", "respond", "forward", "messag", "writ", "contact", "notif")
_MONEY = ("pay", "transfer", "wire", "send", "refund", "settle", "reimburs")
_DELETE = ("delet", "remov", "eras", "clear", "clean", "purg", "discard", "trash", "cancel", "unsubscrib")
_PUBLISH = ("post", "publish", "shar", "upload", "send")
_EXEC = ("run", "exec", "launch", "install", "script", "command")
LICENSE = {"send": _MESSAGE + _MONEY, "forward": _MESSAGE, "email": _MESSAGE, "mail": _MESSAGE,
           "pay": _MONEY, "transfer": _MONEY, "delete": _DELETE, "remove": _DELETE, "post": _PUBLISH,
           "share": _PUBLISH, "upload": _PUBLISH, "exec": _EXEC, "execute": _EXEC, "run": _EXEC,
           "invite": ("invit", "add", "onboard")}
assert set(RISKY) <= set(LICENSE)


def _name_words(name: str) -> list[str]:
    """send_money / sendMoney / send-money -> ['send', 'money']"""
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", name or "")]


def unlicensed_risky(name: str, task: str) -> list[str]:
    """Risky verbs in the action name that nothing in the user's request asks for."""
    verbs = [w for w in _name_words(name) if w in LICENSE]
    if not verbs:
        return []
    asked = re.findall(r"[a-z-]+", (task or "").lower())
    stems = {s for v in verbs for s in LICENSE[v]}
    return [] if any(w.startswith(s) for w in asked for s in stems) else verbs


@dataclass
class Verdict:
    decision: str                      # "allow" | "confirm" | "block"
    untrusted: list = field(default_factory=list)
    reason: str = ""


class ActionLock:
    def __init__(self, trust: TrustSet, approver=None, task: str | None = None):
        self.trust = trust
        self.approver = approver  # callable(name, args, verdict) -> bool, or None
        self.task = task          # the user's request; None skips the risky-verb rule (v3.0 behaviour)

    def check(self, name: str, args: dict) -> Verdict:
        found = set()
        for v in (args or {}).values():
            found |= values(str(v))
        bad = sorted(v for v in found if v not in self.trust)
        if bad:
            return Verdict("confirm", bad, "uses values not found in trusted text")
        if SENSITIVE_ACTION.search(name or ""):
            return Verdict("confirm", [], "changes credentials, access or settings")
        if self.task is not None and unlicensed_risky(name, self.task):
            return Verdict("confirm", [], "risky action the user's request does not ask for")
        return Verdict("allow")

    def decide(self, name: str, args: dict) -> Verdict:
        """check() and, when a human is needed, ask the approver (no approver = block)."""
        v = self.check(name, args)
        if v.decision == "confirm":
            ok = bool(self.approver and self.approver(name, args, v))
            return Verdict("allow" if ok else "block", v.untrusted, v.reason + (" (approved)" if ok else ""))
        return v
