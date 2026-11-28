"""Action gate (component D): find tool calls in a reply, flag disallowed ones.

Policy: the gate is meant to be applied only when the app declares tools
(``allowed_tools`` set; Task 5). A plain chat/summarisation app does not run it.

Minimal, deliberately conservative grammar. The reply is first folded (NFKC,
format characters such as zero-width spaces removed); spans index into that
folded text. Markdown code is NOT exempt: call-shaped text inside fences or
backticks is detected like any other (the gate only runs for tool-using apps,
where a call-shaped reply for a non-allowed tool is suspicious anyway), and a
stray or unterminated fence never hides anything. A tool call is:

1. ``<tool_call> ... </tool_call>``. Name taken, in order, from a JSON call
   object inside (rule 2), else a ``"name"``/``"tool"`` string field, else a
   leading identifier (``wipe_disk now`` -> ``wipe_disk``), else
   ``"<unparsed>"`` (fail closed). An empty block, or one whose content
   starts with a backtick (the tag mentioned in inline code, e.g.
   ``Wrap calls in `<tool_call>` and `</tool_call>` tags``), is not a call. An
   unterminated block (no closing tag, e.g. cut by a stop sequence) counts
   only if its content starts with ``{``; it gets no leading-word fallback.
2. A JSON object (valid per ``json``) whose keys are a string ``"tool"`` plus
   one or two argument keys (``args``, ``arguments``, ``parameters``,
   ``input``) and nothing else (at most 3 keys), or a
   string ``"name"`` key plus ``"arguments"`` that is an object or a JSON
   string encoding an object. Nested objects are found too (OpenAI
   ``{"function": {"name": .., "arguments": ..}}``). Data such as
   ``{"tool": "hammer", "price": 12}`` or ``{"name": "Alice", "age": 3}`` is
   not a call. Objects nested more than 64 braces deep, or too deep for the
   JSON decoder, are reported as ``"<unparsed>"`` instead of being decoded.
   Known trade-off: a data item of exactly the call shape, e.g.
   ``[{"tool": "saw", "input": "wood"}]``, is reported.
3. A line ``CALL name(`` (upper-case ``CALL`` at line start, optional
   indentation). Sole exemption: lines ending with ``;`` inside a *closed*
   ```` ```sql ```` fence (SQL stored-procedure calls).

Anything else, e.g. prose "call me (later)" or code ``print(x)``, is not a
call. Free-form function-call syntax is intentionally not matched: it is too
common in ordinary answers about code.
"""

import bisect
import json
import re

from ._normalize import fold

UNPARSED = "<unparsed>"
_MAX_DEPTH = 64
_DECODE_BUDGET = 2_000_000
_ARG_KEYS = ("args", "arguments", "parameters", "input")

_FENCE_MARK = re.compile(r"```")
_SQL_TAG = re.compile(r"[ \t]*sql[ \t]*\n", re.I)
_BLOCK = re.compile(r"<tool_call>(.*?)(</tool_call>|\Z)", re.S)
_CALL_LINE = re.compile(r"^[ \t]*CALL[ \t]+([A-Za-z_][\w.]*)[ \t]*\([^\n]*$", re.M)
# Braces and string-valued "tool"/"name" keys, scanned in one pass.
_EVENTS = re.compile(r'[{}]|"(?:tool|name)"\s*:\s*"')
_NAME_FIELD = re.compile(r'"(?:name|tool)"\s*:\s*"((?:[^"\\]|\\.)+)"')
_LEADING_IDENT = re.compile(r"\s*([A-Za-z_][\w.\-]*)")
_DECODER = json.JSONDecoder()


def _is_object_args(value) -> bool:
    if isinstance(value, dict):
        return True
    if isinstance(value, str) and value.lstrip().startswith("{"):
        try:
            return isinstance(json.loads(value), dict)
        except (ValueError, RecursionError):
            return False
    return False


def _closed_sql_fences(text: str) -> list[tuple[int, int]]:
    """Spans of closed ```sql fences; fence marks are paired in order (linear)."""
    marks = [m.start() for m in _FENCE_MARK.finditer(text)]
    return [(a, b + 3) for a, b in zip(marks[0::2], marks[1::2])
            if _SQL_TAG.match(text, a + 3)]


def _call_name(obj) -> str | None:
    if isinstance(obj, dict):
        if (isinstance(obj.get("tool"), str) and len(obj) <= 3
                and all(k == "tool" or k in _ARG_KEYS for k in obj) and len(obj) >= 2):
            return obj["tool"]
        if isinstance(obj.get("name"), str) and _is_object_args(obj.get("arguments")):
            return obj["name"]
    return None


def _calls_in(value, out: list[str]) -> None:
    """Depth-first collection of call names inside a decoded JSON value."""
    stack = [value]
    while stack:
        v = stack.pop()
        name = _call_name(v)
        if name is not None:
            out.append(name)
        if isinstance(v, dict):
            stack.extend(reversed(list(v.values())))
        elif isinstance(v, list):
            stack.extend(reversed(v))


def _block_names(content: str, terminated: bool) -> list[str]:
    stripped = content.strip()
    if not stripped or stripped.startswith("`"):
        return []
    if not terminated and not stripped.startswith("{"):
        return []
    names: list[str] = []
    try:
        _calls_in(json.loads(stripped), names)
    except (ValueError, RecursionError):
        pass
    if names:
        return names
    m = _NAME_FIELD.search(stripped)
    if m:
        return [m.group(1)]
    if terminated:
        m = _LEADING_IDENT.match(stripped)
        if m:
            return [m.group(1)]
    return [UNPARSED]


def _inside(pos: int, blocked: list[tuple[int, int]]) -> bool:
    """True if ``pos`` lies in one of the sorted, non-overlapping ``blocked`` spans."""
    i = bisect.bisect_right(blocked, (pos, float("inf"))) - 1
    return i >= 0 and blocked[i][0] <= pos < blocked[i][1]


def _json_calls(text: str, blocked: list[tuple[int, int]]) -> list[tuple[int, int, str]]:
    """JSON call objects outside ``blocked`` spans.

    One pass over braces records, for every string-valued ``"tool"``/``"name"``
    key, its innermost enclosing ``{`` and where that brace closes. Only those
    braces are decoded, outermost first; an object that decodes is searched
    for nested calls and its interior is not decoded again. A brace that never
    closes cannot start valid JSON and is skipped. Cost guards fail closed
    (``UNPARSED``): an object nested deeper than ``_MAX_DEPTH`` braces or one
    that exceeds Python's recursion limit, and a total decode budget of
    ``_DECODE_BUDGET`` characters, after which scanning stops.
    """
    stack: list[int] = []
    close: dict[int, int] = {}
    depth: dict[int, int] = {}
    for m in _EVENTS.finditer(text):
        ch = m.group()
        if ch == "{":
            stack.append(m.start())
        elif ch == "}":
            if stack:
                close[stack.pop()] = m.end()
        elif stack:
            depth.setdefault(stack[-1], len(stack))
    found: list[tuple[int, int, str]] = []
    covered_end = -1
    budget = 0
    for start in sorted(depth):
        end = close.get(start)
        if end is None or start < covered_end or _inside(start, blocked):
            continue
        if depth[start] > _MAX_DEPTH:
            found.append((start, end, UNPARSED))
            covered_end = end
            continue
        if budget > _DECODE_BUDGET:
            found.append((start, len(text), UNPARSED))
            break
        try:
            obj, end = _DECODER.raw_decode(text, start)
        except RecursionError:
            found.append((start, end, UNPARSED))
            covered_end = max(covered_end, end)
            budget += end - start
            continue
        except ValueError as exc:
            budget += max(getattr(exc, "pos", start) - start, 1)
            continue
        budget += end - start
        covered_end = max(covered_end, end)
        names: list[str] = []
        _calls_in(obj, names)
        found.extend((start, end, name) for name in names)
    return found


def tool_call_spans(reply: str) -> list[tuple[int, int, str]]:
    """``(start, end, name)`` for every call, in order; indices refer to ``fold(reply)``."""
    text = fold(reply)
    sql = _closed_sql_fences(text)
    spans: list[tuple[int, int, str]] = []
    for m in _BLOCK.finditer(text):
        for name in _block_names(m.group(1), bool(m.group(2))):
            spans.append((m.start(), m.end(), name))
    blocked = sorted({(s, e) for s, e, _ in spans})
    spans.extend(_json_calls(text, blocked))
    for m in _CALL_LINE.finditer(text):
        if _inside(m.start(), blocked):
            continue
        if m.group().rstrip().endswith(";") and _inside(m.start(), sql):
            continue
        spans.append((m.start(), m.end(), m.group(1)))
    spans.sort(key=lambda t: t[0])
    return spans


def find_tool_calls(reply: str) -> list[str]:
    """Names of all tool calls in ``reply`` in order of appearance (duplicates kept)."""
    return [name for _, _, name in tool_call_spans(reply)]


def disallowed(reply: str, allowed: set[str]) -> list[str]:
    """Distinct called names not in ``allowed``, in order of first appearance."""
    out: list[str] = []
    for name in find_tool_calls(reply):
        if name not in allowed and name not in out:
            out.append(name)
    return out
