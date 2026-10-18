| condition | tasks | success | honest | steps (mean) | LLM calls | tokens | human asks | time (s) |
|---|---|---|---|---|---|---|---|---|
| cold | 1 | 1/1 | 1/1 | 20.0 | 22.0 | 55701 | 0.0 | 450 |
| learned | 1 | 1/1 | 1/1 | 25.0 | 31.0 | 94663 | 1.0 | 726 |
| unseen | 2 | 1/2 | 2/2 | 25.5 | 44.5 | 131382 | 0.5 | 396 |

| condition | task | run | result | status | steps | LLM | human | blocks | s |
|---|---|---|---|---|---|---|---|---|---|
| cold | T1_hero | 1 | PASS | completed | 20 | 22 | 0 | 0 | 449.5 |
| learned | T1_hero | 1 | PASS | completed | 25 | 31 | 1 | 1 | 726.4 |
| unseen | T7_nova_hero | 1 | FAIL | gave_up | 24 | 56 | 0 | 0 | 584.2 |
| unseen | T7_nova_hero | 1 | PASS | completed | 27 | 33 | 1 | 0 | 208.4 |
