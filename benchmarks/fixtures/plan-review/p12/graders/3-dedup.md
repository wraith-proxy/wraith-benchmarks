---
type: llm
weight: 1
---

Answer key, category dedup. Planted defect: the nightly 48 hour replay duplicates refunds and nothing dedups on refund_id. Location in the plan: step 1, the append of the refund feed.

PASS only if the review names this defect and ties it to step 1, the append of the refund feed in `fct_refunds`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
