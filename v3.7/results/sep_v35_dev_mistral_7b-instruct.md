# SEP: SelfGuard v3.5 (Layer 0 + v3.4, echo off), dev, n = 600, mistral:7b-instruct

| | no defence | v3.4 | **v3.5** |
|---|---:|---:|---:|
| Attack success | 56.2% | 6.8% | 3.0% |
| ... 95% upper bound | 60.1% | 9.1% | 4.7% |
| Clean grounding | 86.5% | 82.7% | 84.0% |
| Clean replies withheld | 0.0% | 1.3% | 1.3% |
| Legit instruction in task followed | 70.3% | 72.2% | 72.2% |

McNemar none vs v3.5: {'b': 325, 'c': 6, 'p': 8.128079013302737e-88}; v3.4 vs v3.5: {'b': 31, 'c': 8, 'p': 0.0002940768754342571}
Replies reused 1704, generated 96; clean inputs changed by Layer 0: 19
Grounding gap v3.5 vs no defence: 2.5 points

- C1_protection: **PASS**
- C2_quality: **PASS**
- C3_false_alarms: **PASS**
