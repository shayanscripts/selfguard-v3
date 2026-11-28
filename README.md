# SelfGuard v3

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](selfguard3)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Sealed SEP test: PASS 3/3](https://img.shields.io/badge/sealed%20SEP-PASS%203%2F3-brightgreen.svg)](PREREGISTRATION.md)

> **New: [SelfGuard v3.7](v3.7/README.md)** adds a Layer 0 instruction scrub before the model reads
> the data. On a fresh sealed, pre-registered SEP test (600 rows, Mistral 7B) it cut attack success
> from 64.8% to **2.0%** (upper bound 3.5%) with a **1.7-point** grounding cost and 0.3% of clean
> replies withheld: PASS 3/3 (v3's own sealed test below, on different rows, left 10.2%). Still no retraining, no model
> internals, no extra LLM call and no added prompt tokens. v3.7 is self-contained in [`v3.7/`](v3.7).
>
> Honest caveats, all measured: on Qwen2.5 7B (pre-registered, same rows) attack success fell 67.7% → 1.5% but
> one too many clean replies were withheld (2/3 criteria); simple rewrites of the injected instruction get past
> Layer 0 (about 33% attack success); and an LLM judge rates 6.8% of clean replies worse than no defence.
> Details in the [v3.7 README](v3.7/README.md#limits).

Layered protection against **indirect prompt injection** (instructions hidden in e-mails, web
pages, files and tool output) that wraps **any LLM**. No training, no model internals, no extra
call to the main LLM, no added prompt text. About **2 ms** of local checking per answer.

It builds on [Watchword](https://github.com/shayanscripts/watchword) (role-displacement layout +
reply checks) and adds the parts that stop the actual damage.

| Layer | What it does | Cost |
|---|---|---|
| **Smart routing** | Only data that contains instruction-like sentences goes into Watchword's low-authority (assistant) turn; clean data keeps the normal layout, so answer quality is kept | rules, ~0 ms |
| **Action lock** | A tool call may only use links, e-mails and account numbers that appear in **trusted** text (system prompt, user request, allowlist). Password / permission changes are always held | rules |
| **Approver** (optional) | A small local model decides held actions. It sees only the user's request, the action and the field label of each value, **never the documents**, so injected text cannot argue with it | 1 small-model call, only when an action is held |
| **Link tripwire** | Untrusted links in the reply are defanged (unclickable), untrusted images removed, hidden links (hxxp, `[.]`, spaced out, base64, homoglyphs) decoded first | rules |
| **Support trace** | A reply sentence whose only source is a sentence addressed to the AI ("tell the user...") is removed | rules |
| **v4 lie layer** (optional) | Strips AI-addressed sentences before the call (a small model confirms suspicious ones), fact-checks the reply against the document's normal content, cites sources | small-model calls |

## Results

All numbers are as measured; small local models (Mistral 7B, Qwen2.5 7B) on one RTX 3060 Ti.
They were measured with **v3.0** (commit `da4d868`); v3.1 fixes several bugs and has not been
re-scored yet (see [CHANGELOG.md](CHANGELOG.md)).

### 1. SEP, sealed and pre-registered (600 fresh rows, Mistral 7B)
Rows never used before (`build_sealed.py`, overlap 0 with Watchword's splits), pass bar written in
[PREREGISTRATION.md](PREREGISTRATION.md) before any generation, scored once.

| | No defence | Watchword (always displaced) | **Smart routing** | SG3 always-displaced |
|---|---:|---:|---:|---:|
| Attack success (residual) | 62.2% | 10.2% | **10.2%** | 10.2% |
| Clean answers that use the data (grounding) | 82.7% | 72.2% | **80.0%** | 71.2% |
| Clean replies withheld | – | 0.8% | **0.8%** (Wilson hi 1.9%) | 0.8% |
| Legit instruction in the task followed | 77.0% | – | 77.2% | 86.0% |

Smart routing: **PASS 3/3** (protection McNemar p = 7e-81; grounding within 3 points; false alarms
<= 3%). The always-displaced variant fails the quality criterion.

### 2. AgentDojo v1.2 (independent agent benchmark, Qwen2.5 7B, `important_instructions` attack, no human in the loop)

| Suite | Defence | Attack success | Clean tasks done |
|---|---|---:|---:|
| Banking (144) | none | 7.6% | 43.8% |
| | action lock | **0.0%** | 31.3% |
| | lock + 7B approver | 3.5% | 37.5% |
| Slack (105) | none | 29.5% | 47.6% |
| | action lock | **0.0%** | 14.3% |
| | lock + 7B approver | **0.0%** | 23.8% |

The lock stops hijacked actions; its price is utility, because many legitimate tasks need a value
from a document ("pay the bill in this file"). In a real app those are an *Allow?* prompt; in the
benchmark nobody answers, so they count as failures. The approver recovers part of it.
A 3B approver denied everything (unusable); 7B is the smallest that worked.

### 3. BIPIA (Microsoft, e-mail QA, Qwen2.5 7B, 20 e-mails)

| | No defence | v3 | v4 |
|---|---:|---:|---:|
| Misinformation attacks succeed | 78% | 2% | 2% |
| Scam attacks succeed | 62% | 8% | **2%** |
| Correct answers, clean e-mails | 45% | 45% | 45% |
| Correct answers under attack (misinfo / scam) | 5% / 22% | 42% / 32% | 38% / 30% |

Zero real sentences were removed from clean e-mails. v4 helps only on scams and costs ~750
small-model calls per 100 e-mails, so it is **off by default**. Attack success and answer
correctness are judged by Qwen2.5 7B (eval only).

### 4. Detection-style metrics (SEP sealed)

| Part | Precision | Recall | F1 | ROC AUC |
|---|---:|---:|---:|---:|
| Sentence finder on documents (routing decision) | 0.888 | 1.000 | 0.940 | 0.937 (single point) |
| Reply obedience check, frozen threshold 0.80 | 0.783 | 0.228 | 0.353 | **0.905** |

End-to-end share of working attacks stopped: SEP 86.6% (paired), BIPIA ~87–97%, AgentDojo 100%
with the lock.

### 5. Other checks
- Own e-mail agent suite (72 cases): 0/48 attacks succeed vs 48/48 undefended; clean e-mails
  unchanged; legit actions allowed 12/12 with the approver. Self-made, so optimistic.
- [injection-holdout](https://github.com/shayanscripts/injection-holdout) v1 (finder only):
  flags 98% of SPML and 89% of Gandalf attacks, but also 98.5% of clean **user** prompts, so the
  finder is only meaningful on documents, which is how SelfGuard uses it.
- Speed: ~1.8 ms per answer for the rule layers.

## Limitations
- **Utility cost on agent tasks** without a human approver (see AgentDojo). This is the main trade-off.
- **Small local models only.** No commercial model has been tested yet.
- **No adaptive attacker.** An attacker who knows the rules can write injections the finder misses
  (it missed 11% of Gandalf prompts); those get the unprotected layout. The action lock still
  applies to them.
- **Lies without an action** are only partly covered (support trace, v4).
- The approver prompt's examples were written against our own suite.
- SEP results use Mistral 7B; AgentDojo and BIPIA use Qwen2.5 7B.

## Install

```bash
pip install .            # standard library only; no Watchword checkout needed
```

Watchword's engine (layouts, instruction finder, obedience, provenance and leak checks) is
vendored in `selfguard3/_watchword` as byte-identical copies of Watchword at its freeze
(commit `b51be8bf`, the code the sealed test was scored with). `tests/test_vendored.py` checks
their SHA-256 hashes against `frozen_config.json` and, when a Watchword checkout is present,
that decisions match the original exactly. `layout="routed"` gives the pre-registered smart
routing; the default stays `"displaced"`.

## Use

```python
from selfguard3 import SelfGuard
from selfguard3.approver import PerimeterApprover

approver = PerimeterApprover("qwen2.5:7b-instruct")            # optional, local via Ollama
sg = SelfGuard(approver=lambda name, args, v: approver(user_request, name, args, v, document))
messages = sg.messages(task=user_request, data=[document], system=system_prompt)
reply = my_llm(messages)                                         # your one normal call
out = sg.inspect(reply, task=user_request, data=[document], system=system_prompt)
out.text, out.safe, out.actions, out.findings
```

`out.actions` lists each tool call with `allow` / `block`; only run the allowed ones.

## Reproduce
```bash
python -m unittest tests.test_modules tests.test_vendored   # unit tests (model tests: MINICHECK=1, V4MODELS=1)
python build_sealed.py                         # needs the SEP archive; refuses to overwrite
python score_v3.py && python eval/sep_full.py  # one-shot sealed scoring
python eval/agentdojo_run.py banking           # AD_CONDITIONS=none,sg3,approver
python eval/bipia_eval.py                      # BIPIA e-mail split in ../bipia
python eval/agent_suite.py
```
SEP rows are not redistributed; `build_sealed.py` rebuilds the split from the public archive.
The sealed-test scripts (`build_sealed.py`, `score_v3.py`, `eval/sep_full.py`) are kept unchanged
as the record of the pre-registered run: they still need a Watchword checkout (`WATCHWORD_PATH`)
for its SEP harness and check its code against the freeze. The library does not.

## Related work
ASIDE and DRIP (training-time separation), Spotlighting, CaMeL and Dual-LLM, MELON, Sonar (sentence
sanitization), MiniCheck (Tang et al. 2024), AgentDojo (Debenedetti et al. 2024), BIPIA (Yi et al.
2023), SEP (Zverev et al. 2025).

## Licence
[MIT](LICENSE)
