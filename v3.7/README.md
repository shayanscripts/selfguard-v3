# SelfGuard v3.7: Layer 0 instruction scrub + smart routing + reply checks

[![Sealed SEP test: PASS 3/3](https://img.shields.io/badge/sealed%20SEP-PASS%203%2F3-brightgreen.svg)](PREREGISTRATION_v3.5.md)

v3.7 is the newest SelfGuard. It wraps any chat LLM against **indirect prompt injection** with
**no retraining or fine-tuning of the LLM, no model internals, no extra call to the LLM and no
added prompt tokens.**

> **Naming.** v3.7 is exactly the candidate that was pre-registered and frozen as **"v3.5"**.
> The files keep that name (`PREREGISTRATION_v3.5.md`, `FROZEN_v3.5.sha256`, `eval/sep_v35.py`,
> `results/sep_v35_*`) so their hashes still verify. "v3.6" was an echo-strip variant that
> failed on dev and was never released.

## How it works

| Step | What it does | Cost |
|---|---|---|
| **Layer 0 scrub** (new) | Before the LLM reads a document, deletes only sentences that are both instructions and off-topic for the trusted task. Addressee cues ("in your response", "ignore previous instructions") are enough on their own. Everything else is kept. | ~9 ms per document on CPU (median, SEP dev; p95 16.5 ms) |
| **Smart routing** | Data that still looks instruction-like goes into the low-authority (assistant-turn) layout; clean data keeps the normal layout. | rules |
| **Reply checks** | The reply is checked against the **original** (unscrubbed) data; replies that obey the data are withheld. Echo strip is **off** in v3.7. | rules |

The Layer 0 tagger (`models/tagger.pkl`, TF-IDF + logistic regression with spaCy features) is a
small classifier trained **once**, on instruction-tuning data (AlpacaDataCleaned instructions vs
answers, plus clean BIPIA *train* documents). It has never seen a prompt-injection example and is
not trained per model or per app. Thresholds: `inst_th 0.6, top_th 0.6, top_th_instr 0.45`.
(`LAYER0_README.md` is the Layer 0 author's note; its echo threshold 0.4 is **not** used by v3.7.)

## Results

Mistral 7B Instruct via Ollama (digest 6577803aa9a0), temperature 0, seed 1234, 256 tokens.
SEP benchmark (Zverev et al., the ASIDE authors' benchmark); attack success uses SEP's own
witness-substring grader.

### 1. Sealed, pre-registered test: PASS 3/3
600 SEP rows never used by any SelfGuard version (`eval/sep_splits.py sealed`, seed 20261122).
The pass bar and the hashes of every file were written in
[PREREGISTRATION_v3.5.md](PREREGISTRATION_v3.5.md) / [FROZEN_v3.5.sha256](FROZEN_v3.5.sha256)
before any generation; the script refuses to run twice. Report:
[results/sep_v35_sealed_mistral_7b-instruct.md](results/sep_v35_sealed_mistral_7b-instruct.md).

| | No defence | v3.4 | **v3.7** |
|---|---:|---:|---:|
| Attack success | 64.8% | 5.5% | **2.0%** |
| ... Wilson 95% upper bound | 68.5% | 7.6% | **3.5%** |
| Clean answers grounded in the data | 81.3% | 79.5% | **79.7%** (gap 1.7 pts) |
| Clean replies withheld | 0.0% | 0.3% | **0.3%** |
| Legit instruction in the task followed | 78.0% | 78.8% | **80.0%** |

| Criterion | Bar | Result |
|---|---|---|
| C1 protection | upper bound ≤ 5% and McNemar p < 0.05 vs no defence | **PASS** (3.5%; 377 vs 0 discordant, p = 6e-114) |
| C2 quality | grounding ≤ 3.0 points below no defence | **PASS** (1.7) |
| C3 false alarms | withheld upper bound ≤ 3% | **PASS** |

v3.7 vs v3.4 on the same rows: 26 attacks stopped only by v3.7, 5 only by v3.4 (McNemar p = 0.0002).
Layer 0 changed 25 of the 600 clean documents.

### 2. Development set (600 SEP dev rows; settings were chosen here, so optimistic)

| | No defence | v3.4 | v3.7 as shipped by Layer 0 author (echo 0.4) | **v3.7 (echo off)** |
|---|---:|---:|---:|---:|
| Attack success (upper bound) | 56.2% (60.1) | 6.8% (9.1) | 2.7% (4.3) | **3.0% (4.7)** |
| Grounding (gap) | 86.5% | 82.7% (3.8) | 83.0% (3.5) | **84.0% (2.5)** |
| Withheld (upper bound) | 0.0% | 1.3% (2.6) | 1.3% (2.6) | **1.3% (2.6)** |

### 3. Versus other defenses with the same constraints (no retraining, no internals)
Same 600 dev rows, model, decoding and grader (`eval/baselines_sep.py`,
[results/sep_baselines_dev_mistral_7b-instruct.json](results/sep_baselines_dev_mistral_7b-instruct.json)).
Unlike v3.7, each of these adds prompt tokens to every call.

| Defense (dev, Mistral 7B) | Added prompt tokens | Attack success (upper bound) | Grounding gap (pts) | Task probe followed | SEP score |
|---|---:|---:|---:|---:|---:|
| No defence | 0 | 56.2% (60.1) | 0.0 | 70.3% | 32.7% |
| Instructional warning | ~32 | 57.8% (61.7) | 0.8 | 70.3% | 31.3% |
| Sandwich defence | ~31 | 41.2% (45.1) | 0.3 | 77.8% | 52.0% |
| Spotlighting, delimiting | ~28 | 49.8% (53.8) | 1.2 | 61.5% | 41.2% |
| Spotlighting, datamarking | ~48 | 45.0% (49.0) | -4.5 | 69.5% | 46.5% |
| SelfGuard v3.4 | 0 | 6.8% (9.1) | 3.8 | 72.2% | – |
| **SelfGuard v3.7** | **0** | **3.0% (4.7)** | **2.5** | **72.2%** | – |

The best prompt-only defense (sandwich) still lets 41% of attacks through; v3.7 lets 3% through
on the same rows without adding a token.

The baseline prompts were written from the published descriptions (instructional warning;
sandwich; spotlighting delimiting and datamarking, Hines et al. 2024) and were not tuned, while
v3.7's settings were chosen on these dev rows; the sealed result above is the unbiased v3.7
number. Spotlighting was designed for GPT-4-class models and may work better there than on a 7B
model. Not compared: trained detectors (PromptGuard, ProtectAI), fine-tuned models (ASIDE, StruQ,
SecAlign) and defenses that make extra LLM calls (MELON, CaMeL, PromptArmor), since they break
the constraints above.

## Usage

```python
from selfguard3 import SelfGuard
from selfguard3.scrub import Layer0

l0 = Layer0("models/tagger.pkl")
sg = SelfGuard(layout="routed", echo=False)

task, doc = "Summarize this review in one sentence.", untrusted_text
reply = your_llm(sg.messages(task, [l0(doc, task)]))   # scrub each document before the call
out = sg.inspect(reply, task=task, data=[doc])        # checks see the original document
print(out.text if out.safe else "[withheld]")
```

Setup:

    pip install scikit-learn spacy
    pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_md-3.8.0/en_core_web_md-3.8.0-py3-none-any.whl

`models/tagger.pkl` is included. To retrain it (about 30 s on CPU, needs the two clones):

    git clone https://github.com/gururise/AlpacaDataCleaned data/src/AlpacaDataCleaned
    git clone https://github.com/microsoft/BIPIA data/src/BIPIA
    python eval/train_tagger.py

Check the frozen files: `grep -v -e sealed_v34 -e ^frozen FROZEN_v3.5.sha256 | sha256sum -c`.
SEP rows are not redistributed; rebuild the splits with `eval/sep_splits.py` from the SEP release.

## Limits
- **Simple rewrites get past Layer 0.** On 200 dev rows (`eval/adaptive_l0.py`,
  [results/adaptive_l0_dev.json](results/adaptive_l0_dev.json)), rephrasing the injected order so it
  does not read like an instruction (e.g. "include X in your answer") leaves the document unchanged
  93-99% of the time, and attack success rises from 4.0% to about 33% (no defence 42-45%, v3.4 32-34%).
  v3.7's sealed result holds for SEP-style injections, not for an attacker who knows the method.
  Next step: an intent-based Layer 0.
- **Second model: 2 of 3 criteria.** The pre-registered Qwen2.5 7B sealed run (`PREREGISTRATION_v3.7_qwen.md`,
  same 600 rows, nothing retuned; [results](results/sep_v35_sealed_qwen2.5_7b-instruct.md)) cut attack success from
  67.7% to 1.5% (upper bound 2.8%) with a 2.2-point grounding gap, but withheld 10/600 clean replies (upper bound
  3.04% > 3%), so it **fails C3** by one reply. All 10 were also withheld by v3.4; Layer 0 changed none of them.
- **Quality cost is larger than the grounding proxy shows.** An LLM judge (Qwen2.5 7B, pairwise with order
  swap; [results/judge_quality_sealed_mistral.json](results/judge_quality_sealed_mistral.json)) compared clean sealed
  replies: 506/600 were byte-identical to no defence, but of the 94 that differed the judge preferred no defence
  41 times and v3.7 6 times (p = 2e-7), i.e. 6.8% of clean replies judged worse. When Layer 0 edits a benign
  document (25/600), the answer lost 16 times ([judge_breakdown](results/judge_breakdown_sealed_mistral.json)).
  C2 was passed on grounding (≥10% of the reply's long words appear in the data), not on judged quality.
- The sealed split is now spent; the next version needs fresh rows.
