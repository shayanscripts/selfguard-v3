"""Message layouts (component A, role displacement).

Two layouts are built from the same inputs:

``standard``
    ``[system: system + JOINER + task]`` (or ``[system: task]`` without a system
    prompt), then ``[user: JOINER.join(data)]``. The user turn is kept even when
    ``data`` is empty.

``displaced``
    ``[system: system]`` (only when a system prompt is given), then
    ``[assistant: JOINER.join(data)]`` (omitted when ``data`` is empty), then
    ``[user: task]``.

Zero-added-text invariant (tested): message contents consist only of the
caller's strings and ``JOINER`` separators. The two layouts differ only in
where the task sits, so::

    chars(standard) - chars(displaced) == len(JOINER) if system else 0

where ``chars`` is the sum of ``len(content)``. The difference is the single
joiner that glues system prompt and task in the standard layout; ``displaced``
never adds anything. An empty-string system prompt counts as "no system".
"""

from typing import Literal

JOINER = "\n\n"
MODES = ("standard", "displaced")


def build(task: str, data: list[str], system: str | None,
          mode: Literal["standard", "displaced"]) -> list[dict]:
    """Return chat messages (``{"role", "content"}`` dicts) for ``mode``."""
    if mode not in MODES:
        raise ValueError(f"unknown layout mode {mode!r}; expected one of {MODES}")
    if isinstance(data, (str, bytes)) or not all(isinstance(d, str) for d in data):
        raise TypeError("data must be a list of strings")
    joined = JOINER.join(data)
    if mode == "standard":
        head = system + JOINER + task if system else task
        return [{"role": "system", "content": head},
                {"role": "user", "content": joined}]
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    if data:
        messages.append({"role": "assistant", "content": joined})
    messages.append({"role": "user", "content": task})
    return messages


def added_chars(standard: list[dict], displaced: list[dict]) -> int:
    """Total content characters of ``standard`` minus those of ``displaced``."""
    return (sum(len(m["content"]) for m in standard)
            - sum(len(m["content"]) for m in displaced))
