# SEP: SelfGuard v3.5 (Layer 0 + v3.4), dev, n = 600, mistral:7b-instruct

| | no defence | v3.4 | **v3.5** |
|---|---:|---:|---:|
| Attack success | 56.2% | 6.8% | 2.7% |
| ... 95% upper bound | 60.1% | 9.1% | 4.3% |
| Clean grounding | 86.5% | 82.7% | 83.0% |
| Clean replies withheld | 0.0% | 1.3% | 1.3% |
| Legit instruction in task followed | 70.3% | 72.2% | 72.2% |

McNemar none vs v3.5: {'b': 327, 'c': 6, 'p': 2.1071505181634934e-88}; v3.4 vs v3.5: {'b': 31, 'c': 6, 'p': 4.12575900554657e-05}
Replies reused 1704, generated 96; clean inputs changed by Layer 0: 19

- C1_protection: **PASS**
- C2_quality: **FAIL**
- C3_false_alarms: **PASS**
