"""Reply-side checks of the frozen engine (selfguard3/engine), with no secrets and no tool
allowlist:

  1. obedience: the reply carries out an instruction found in a data item
     (highest score over the items, withheld at ``threshold``);
  2. provenance: an untrusted command, path or tool payload in the reply;
  3. leak: the reply reproduces system-prompt text.

Built once per SelfGuard instance; options are validated at construction.
``tests/test_engine.py`` checks the decisions against the recorded freeze.
"""
from dataclasses import dataclass, field

from .engine import extract, layout, leak, obedience, provenance

# the engine's frozen configuration (engine/frozen_config.json)
FROZEN_THRESHOLD = 0.8
FROZEN_OPTIONS = {"USE_RESTATEMENT": True, "USE_ORPHAN": False, "USE_MARKED_NOVEL": False,
                  "USE_SINGLE_NOVEL": False, "USE_ORPHAN_POSITIONAL": False}
LAYOUTS = layout.MODES + ("routed",)


def build_messages(task: str, data: list[str], system: str | None, mode: str) -> list[dict]:
    """Chat messages for ``mode``: 'standard', 'displaced', or 'routed'
    (displaced only when the data holds an instruction-like sentence)."""
    if mode == "routed":
        mode = route(data)
    return layout.build(task, list(data), system, mode)


def route(data) -> str:
    """Smart routing from the pre-registration: displaced iff the finder flags any data item."""
    return "displaced" if any(extract.instructions(d) for d in data) else "standard"


@dataclass
class CheckResult:
    allowed: bool
    score: float = 0.0
    findings: list = field(default_factory=list)


class ReplyChecks:
    def __init__(self, threshold: float = FROZEN_THRESHOLD, options=None, trusted_domains=()):
        self.threshold = threshold
        self.options = dict(FROZEN_OPTIONS if options is None else options)
        obedience.resolve_options(self.options)  # unknown option names fail here, not per call
        self.trusted_domains = {d.lower() for d in trusted_domains}

    def __call__(self, reply: str, *, task: str, data=(), system: str | None = None) -> CheckResult:
        data = list(data)
        res = CheckResult(allowed=True)

        guilty = None
        for i, item in enumerate(data):
            _, s, instr = obedience.check(reply, task, item, self.threshold, options=self.options)
            if s > res.score:
                res.score, guilty = s, (instr, i)
        if guilty is not None and res.score >= self.threshold:
            res.allowed = False
            res.findings.append(("obedience", res.score, guilty[0].text))

        trusted = [t for t in (system, task) if t]
        _, removed, must = provenance.enforce(reply, trusted, self.trusted_domains, data, False)
        if must:
            res.allowed = False
            res.findings.append(("provenance", "untrusted command, path or tool payload in reply"))

        if system and leak.verbatim_leak(reply, system, task):
            res.allowed = False
            res.findings.append(("leak", "reply reproduces system prompt text"))
        return res
