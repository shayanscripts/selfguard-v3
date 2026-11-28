# SelfGuard v3.5 – Layer 0: Instruction Scrub

Runs **before** the model reads untrusted data. Deletes only the sentences that are (a) instructions
and (b) off-topic for the trusted task and the rest of the document; addressee cues ("in your
response", "ignore previous instructions", "your main task") remove a sentence on their own. A removed
sentence ending in ":" also removes the block it introduces (e.g. a code payload). Everything else
in the document is kept, and the v3.4 reply checks still run afterwards.

The tagger is trained only on instruction-tuning data (Alpaca-cleaned instructions vs answers, plus
clean BIPIA *train* e-mails/code as benign text), never on prompt-injection examples.

## Files (copy into the repo root)
- `selfguard3/scrub.py`, `selfguard3/scrub_feats.py` – the layer (`Layer0(...)(text, task)`)
- `eval/train_tagger.py` – trains `models/tagger.pkl` (~30 s on CPU)
- `eval/sep_v35.py` – end-to-end SEP test with your model (reuses cached replies)
- `layer0_lab/` – the offline experiments and their results

## Setup (once)
    pip install scikit-learn spacy
    pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_md-3.8.0/en_core_web_md-3.8.0-py3-none-any.whl
    git clone https://github.com/gururise/AlpacaDataCleaned data/src/AlpacaDataCleaned
    git clone https://github.com/microsoft/BIPIA data/src/BIPIA
    python eval/train_tagger.py

## End-to-end test (Ollama running, mistral:7b-instruct)
    python eval/sep_v35.py --rows data/sep/dev.jsonl --legacy-cache results/cache/sep_v32_dev_mistral_7b-instruct.jsonl

Only ~96 new generations are needed on SEP dev; the rest are reused from the cache because the
prompts are identical. Writes `results/sep_v35_dev_mistral_7b-instruct.{json,md}`.

## Frozen settings
inst_th 0.6, top_th 0.6, top_th_instr 0.45, echo threshold with Layer 0: 0.4 — all chosen on SEP dev.
Do not tune on the sealed split; pre-register v3.5 before any sealed run.
