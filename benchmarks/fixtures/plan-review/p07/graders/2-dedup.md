---
type: llm
weight: 1
---

Answer key, category dedup. Planted defect: CDC emits several rows per subscription and no latest-row dedup is applied, so history rows are counted as current. Location in the plan: step 1, the append of the CDC extract.

PASS only if the review names this defect and ties it to step 1, the append of the CDC extract in `fct_mrr`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
