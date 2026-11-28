"""Leak guard (component D): stop sequences + local verbatim-leak filter.

Only the **system prompt** is protected. The task is not secret, and a reply
that restates the user's question is normal; guarding the task would cut off
or withhold good answers. Both functions keep a ``task`` parameter for a
stable signature, but ignore it.

``stop_sequences`` feeds the provider's ``stop`` parameter so generation halts
as soon as the model starts reciting a system-prompt sentence. Providers match
stop strings exactly, so sequences are slices of the **raw** system text (no
normalisation, original spacing kept). Providers also cap the count (OpenAI:
4), hence at most 4. Sequences shorter than 4 words are dropped because short
phrases ("Be brief.") would cut off ordinary replies.

``verbatim_leak`` is the local backstop (and the only guard for callables
without ``stop`` support): it reports whether any ``n_words``-word window of
the system prompt appears in the reply, comparing case-folded word tokens
after NFKC + format-character stripping (so punctuation, spacing, zero-width
and fullwidth tricks do not hide a leak). A system prompt shorter than
``n_words`` words yields no windows and never triggers.
"""

import re

from ._normalize import fold

MAX_STOP_SEQUENCES = 4
MIN_STOP_WORDS = 4

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_RAW_WORD = re.compile(r"\S+")
_WORD = re.compile(r"\w+")


def stop_sequences(system: str | None, task: str | None = None, k_words: int = 6) -> list[str]:
    """First ``k_words`` words of each system-prompt sentence, as raw text slices.

    Deduplicated (order kept), only sequences of >= 4 words, at most 4.
    ``task`` is ignored (see module docstring).
    """
    out: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(system or ""):
        words = list(_RAW_WORD.finditer(sentence))
        if len(words) < MIN_STOP_WORDS or k_words < MIN_STOP_WORDS:
            continue
        last = words[min(k_words, len(words)) - 1]
        seq = sentence[words[0].start():last.end()]
        if seq not in out:
            out.append(seq)
            if len(out) == MAX_STOP_SEQUENCES:
                break
    return out


def _tokens(text: str) -> list[str]:
    return _WORD.findall(fold(text).casefold())


def verbatim_leak(reply: str, system: str | None, task: str | None = None,
                  n_words: int = 8) -> bool:
    """True if any ``n_words``-word window of ``system`` appears in ``reply``.

    ``task`` is ignored (see module docstring).
    """
    if n_words < 1:
        raise ValueError("n_words must be >= 1")
    toks = _tokens(system or "")
    windows = {tuple(toks[i:i + n_words]) for i in range(len(toks) - n_words + 1)}
    if not windows:
        return False
    r = _tokens(reply)
    return any(tuple(r[i:i + n_words]) in windows for i in range(len(r) - n_words + 1))
