| condition | tasks | success | honest | steps (mean) | LLM calls | tokens | human asks | time (s) |
|---|---|---|---|---|---|---|---|---|
| cold | 12 | 12/12 | 12/12 | 31.2 | 0.0 | 0 | 0.3 | 2 |
| learned | 12 | 12/12 | 12/12 | 31.5 | 0.0 | 0 | 0.5 | 2 |
| unseen | 6 | 2/6 | 6/6 | 35.3 | 0.0 | 0 | 0.7 | 3 |
| chaos | 12 | 12/12 | 12/12 | 35.7 | 0.0 | 0 | 0.3 | 3 |

| condition | task | run | result | status | steps | LLM | human | blocks | s |
|---|---|---|---|---|---|---|---|---|---|
| cold | T1_hero | 1 | PASS | completed | 33 | 0 | 0 | 0 | 2.6 |
| cold | T1_hero | 2 | PASS | completed | 33 | 0 | 0 | 0 | 2.5 |
| cold | T2_pdf_truth | 1 | PASS | completed | 33 | 0 | 0 | 0 | 2.5 |
| cold | T2_pdf_truth | 2 | PASS | completed | 33 | 0 | 0 | 0 | 2.5 |
| cold | T3_duplicate | 1 | PASS | completed | 24 | 0 | 0 | 0 | 1.9 |
| cold | T3_duplicate | 2 | PASS | completed | 24 | 0 | 0 | 0 | 1.9 |
| cold | T4_small | 1 | PASS | completed | 32 | 0 | 0 | 0 | 2.4 |
| cold | T4_small | 2 | PASS | completed | 32 | 0 | 0 | 0 | 2.4 |
| cold | T5_approval | 1 | PASS | completed | 34 | 0 | 1 | 0 | 2.5 |
| cold | T5_approval | 2 | PASS | completed | 34 | 0 | 1 | 0 | 2.6 |
| cold | T6_denied | 1 | PASS | blocked | 31 | 0 | 1 | 0 | 2.2 |
| cold | T6_denied | 2 | PASS | blocked | 31 | 0 | 1 | 0 | 2.1 |
| learned | T1_hero | 1 | PASS | completed | 35 | 0 | 1 | 0 | 2.7 |
| learned | T1_hero | 2 | PASS | completed | 35 | 0 | 1 | 0 | 2.6 |
| learned | T2_pdf_truth | 1 | PASS | completed | 33 | 0 | 0 | 0 | 2.5 |
| learned | T2_pdf_truth | 2 | PASS | completed | 33 | 0 | 0 | 0 | 2.5 |
| learned | T3_duplicate | 1 | PASS | completed | 24 | 0 | 0 | 0 | 1.9 |
| learned | T3_duplicate | 2 | PASS | completed | 24 | 0 | 0 | 0 | 1.9 |
| learned | T4_small | 1 | PASS | completed | 32 | 0 | 0 | 0 | 2.2 |
| learned | T4_small | 2 | PASS | completed | 32 | 0 | 0 | 0 | 2.4 |
| learned | T5_approval | 1 | PASS | completed | 34 | 0 | 1 | 0 | 2.5 |
| learned | T5_approval | 2 | PASS | completed | 34 | 0 | 1 | 0 | 2.5 |
| learned | T6_denied | 1 | PASS | blocked | 31 | 0 | 1 | 0 | 2.2 |
| learned | T6_denied | 2 | PASS | blocked | 31 | 0 | 1 | 0 | 2.4 |
| unseen | T7_nova_hero | 1 | FAIL | failed | 36 | 0 | 1 | 0 | 3.0 |
| unseen | T7_nova_hero | 2 | FAIL | failed | 36 | 0 | 1 | 0 | 2.9 |
| unseen | T8_nova_pdf_truth | 1 | PASS | completed | 35 | 0 | 0 | 0 | 2.9 |
| unseen | T8_nova_pdf_truth | 2 | PASS | completed | 35 | 0 | 0 | 0 | 2.9 |
| unseen | T9_nova_approval | 1 | FAIL | failed | 35 | 0 | 1 | 0 | 2.6 |
| unseen | T9_nova_approval | 2 | FAIL | failed | 35 | 0 | 1 | 0 | 2.7 |
| chaos | T1_hero | 1 | PASS | completed | 36 | 0 | 0 | 0 | 2.8 |
| chaos | T1_hero | 2 | PASS | completed | 40 | 0 | 0 | 0 | 3.1 |
| chaos | T2_pdf_truth | 1 | PASS | completed | 36 | 0 | 0 | 0 | 2.9 |
| chaos | T2_pdf_truth | 2 | PASS | completed | 40 | 0 | 0 | 0 | 3.2 |
| chaos | T3_duplicate | 1 | PASS | completed | 24 | 0 | 0 | 0 | 1.9 |
| chaos | T3_duplicate | 2 | PASS | completed | 28 | 0 | 0 | 0 | 2.2 |
| chaos | T4_small | 1 | PASS | completed | 35 | 0 | 0 | 0 | 2.7 |
| chaos | T4_small | 2 | PASS | completed | 39 | 0 | 0 | 0 | 2.8 |
| chaos | T5_approval | 1 | PASS | completed | 37 | 0 | 1 | 0 | 2.9 |
| chaos | T5_approval | 2 | PASS | completed | 41 | 0 | 1 | 0 | 3.0 |
| chaos | T6_denied | 1 | PASS | blocked | 34 | 0 | 1 | 0 | 2.4 |
| chaos | T6_denied | 2 | PASS | blocked | 38 | 0 | 1 | 0 | 2.8 |
