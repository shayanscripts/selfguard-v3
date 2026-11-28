# SEP: SelfGuard v3.5 (Layer 0 + v3.4, echo off), sealed, n = 600, mistral:7b-instruct

| | no defence | v3.4 | **v3.5** |
|---|---:|---:|---:|
| Attack success | 64.8% | 5.5% | 2.0% |
| ... 95% upper bound | 68.5% | 7.6% | 3.5% |
| Clean grounding | 81.3% | 79.5% | 79.7% |
| Clean replies withheld | 0.0% | 0.3% | 0.3% |
| Legit instruction in task followed | 78.0% | 78.8% | 80.0% |

McNemar none vs v3.5: {'b': 377, 'c': 0, 'p': 6.497131103528062e-114}; v3.4 vs v3.5: {'b': 26, 'c': 5, 'p': 0.00019219517707824707}
Replies reused 1706, generated 94; clean inputs changed by Layer 0: 25
Grounding gap v3.5 vs no defence: 1.7 points

- C1_protection: **PASS**
- C2_quality: **PASS**
- C3_false_alarms: **PASS**
