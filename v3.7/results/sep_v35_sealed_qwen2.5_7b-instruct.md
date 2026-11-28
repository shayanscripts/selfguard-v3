# SEP: SelfGuard v3.5 (Layer 0 + v3.4, echo off), sealed, n = 600, qwen2.5:7b-instruct

| | no defence | v3.4 | **v3.5** |
|---|---:|---:|---:|
| Attack success | 67.7% | 6.0% | 1.5% |
| ... 95% upper bound | 71.3% | 8.2% | 2.8% |
| Clean grounding | 83.3% | 80.8% | 81.2% |
| Clean replies withheld | 0.0% | 1.8% | 1.7% |
| Legit instruction in task followed | 79.2% | 79.5% | 79.8% |

McNemar none vs v3.5: {'b': 398, 'c': 1, 'p': 6.196147063758909e-118}; v3.4 vs v3.5: {'b': 32, 'c': 5, 'p': 7.427530363202095e-06}
Replies reused 1706, generated 94; clean inputs changed by Layer 0: 25
Grounding gap v3.5 vs no defence: 2.2 points

- C1_protection: **PASS**
- C2_quality: **PASS**
- C3_false_alarms: **FAIL**
