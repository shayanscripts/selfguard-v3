"""Text utilities shared by the detection layers.

Detection never runs on raw text: zero-width characters, bidi marks and
fullwidth letters can split or disguise words. Everything here is used only
for *matching*; text sent to or returned from the model is never rewritten.

- ``fold``: NFKC, then remove every format character (Unicode category
  ``Cf``: ZWSP, ZWJ, LRM/RLM, RLO, BOM, ...). Case is kept.
- ``normalise``: ``fold`` + casefold + whitespace runs collapsed to one space.
- ``sentences``: sentence spans of the **raw** text (so callers can report the
  original sentence). Boundaries: a run of ``.``/``!``/``?``/``．`` followed
  by whitespace or the end (so ``3.14`` and ``e.g.x`` do not split), any run
  of ``。！？`` (CJK/fullwidth, no space needed), and newlines.
- ``words`` / ``content_words``: ``\\w+`` tokens of the normalised text;
  content words drop one-letter tokens (digits kept) and a small stopword
  list for en/de/fr/es/it/pt. The lists are merged, so a word that is a
  stopword in one language (e.g. "die", "son") is dropped in all: a small,
  accepted loss for language-agnostic matching.

All functions are linear in the input length.
"""

import re
import unicodedata

_WS = re.compile(r"\s+")
_WORD = re.compile(r"\w+")
# The look-behind makes only the first terminator of a run a match start, so a
# long run of dots costs O(run), not O(run^2).
_BOUNDARY = re.compile(r"(?<![.!?．])[.!?．]++(?=\s|$)|[。！？]+|\n")

_STOP_EN = """
a an the and or but if then else than so as at by for from in into of off on onto out over
to up with without about above after again against all am any are aren't be because been
before being below between both can could did do does doing down during each few further had
has have having he her here hers herself him himself his how i is it its itself just me more
most my myself no nor not now only other our ours ourselves own same she should some such
that their theirs them themselves there these they this those through too under until very
was we were what when where which while who whom why will would you your yours yourself
yourselves also may might must shall s t d ll m re ve
"""
_STOP_DE = """
der die das den dem des ein eine einen einem einer eines und oder aber wenn dann als auch
an am auf aus bei bis durch für gegen im in ins mit nach seit über um unter von vor zu zum
zur ist sind war waren bin bist sein seine ihr ihre ich du er sie es wir mich mir dich dir
uns euch sich nicht kein keine noch nur schon sehr so wie was wer wo wann warum welche
welcher welches dass ob hat haben hatte wird werden wurde kann können muss soll mein dein
"""
_STOP_FR = """
le la les un une des du de d l et ou mais si donc car que qui quoi dont où ce cet cette ces
il elle ils elles on je tu nous vous me te se lui leur leurs mon ma mes ton ta tes son sa ses
notre nos votre vos au aux dans en par pour sur avec sans sous chez est sont était être avoir
a ai as ont pas ne plus très tout tous toute toutes y n s qu c j
"""
_STOP_ES = """
el la los las un una unos unas y o pero si que qué quien quién cual cuál de del al en con por
para sin sobre entre es son era ser estar está están fue ha han he lo le les se me te nos os
mi mis tu tus su sus nuestro nuestra vuestro yo él ella ellos ellas nosotros usted ustedes no
muy más ya como cómo cuando cuándo donde dónde este esta estos estas ese esa esos esas
"""
_STOP_IT = """
il lo la i gli le un uno una e ed o ma se che chi cui di del dello della dei degli delle a al
allo alla ai agli alle da dal dalla in nel nello nella nei negli nelle con su sul sulla per tra
fra è sono era essere ha hanno ho non più molto come quando dove questo questa questi queste
quello quella mi ti ci vi si io tu lui lei noi voi loro mio mia tuo tua suo sua
"""
_STOP_PT = """
o a os as um uma uns umas e ou mas se que quem qual de do da dos das em no na nos nas por pelo
pela para com sem sobre entre é são era ser estar está estão foi tem têm há não mais muito
como quando onde este esta estes estas esse essa isso isto eu tu ele ela eles elas nós vós
você vocês me te lhe meu minha seu sua ao à aos às
"""

STOPWORDS_BY_LANG = {
    lang: frozenset(_WORD.findall(src.casefold()))
    for lang, src in (("en", _STOP_EN), ("de", _STOP_DE), ("fr", _STOP_FR),
                      ("es", _STOP_ES), ("it", _STOP_IT), ("pt", _STOP_PT))
}
STOPWORDS = frozenset().union(*STOPWORDS_BY_LANG.values())


def fold(text: str) -> str:
    """NFKC-normalise ``text`` and strip all ``Cf`` (format) characters."""
    text = unicodedata.normalize("NFKC", text)
    if text.isascii():
        return text
    drop = {ord(c): None for c in set(text) if unicodedata.category(c) == "Cf"}
    return text.translate(drop) if drop else text


def normalise(text: str) -> str:
    """``fold`` + casefold + collapse whitespace runs to one space (stripped)."""
    return _WS.sub(" ", fold(text).casefold()).strip()


def words(text: str) -> list[str]:
    """Word tokens (``\\w+``) of the normalised text, in order."""
    return _WORD.findall(fold(text).casefold())


def is_content(word: str) -> bool:
    """True for a normalised token that is not a stopword and not one letter."""
    return (len(word) > 1 or word.isdigit()) and word not in STOPWORDS


def content_words(text: str) -> frozenset[str]:
    """Normalised non-stopword tokens of ``text``."""
    return frozenset(w for w in words(text) if is_content(w))


def sentences(text: str) -> list[tuple[int, int]]:
    """``(start, end)`` spans of the sentences of ``text`` (raw offsets, trimmed)."""
    spans = []
    pos = 0
    for m in _BOUNDARY.finditer(text):
        _add_span(text, pos, m.end() if m.group() != "\n" else m.start(), spans)
        pos = m.end()
    _add_span(text, pos, len(text), spans)
    return spans


def _add_span(text: str, a: int, b: int, spans: list) -> None:
    seg = text[a:b]
    stripped = seg.strip()
    if not stripped or not fold(stripped).strip():
        return
    lead = len(seg) - len(seg.lstrip())
    spans.append((a + lead, a + lead + len(stripped)))
