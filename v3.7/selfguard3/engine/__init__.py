"""SelfGuard's frozen reply-check engine.

The instruction finder (extract), the displaced layout, the obedience check, provenance, the
system-prompt leak check and their helpers. The code is frozen: these modules are the exact
logic SelfGuard v3's sealed SEP test was scored with, at obedience threshold 0.80 and the
options in ``frozen_config.json``. Their SHA-256 hashes are recorded there and checked by
``tests/test_engine.py``, so do not edit them in place: change behaviour in ``selfguard3``.
``selfguard3.checks`` runs the checks.
"""
