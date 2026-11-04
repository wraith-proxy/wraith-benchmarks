---
type: llm
weight: 1
---

Answer key, category grain. Planted defect: the table is declared one row per subscription but the aggregation is per customer, so rows are merged. Location in the plan: step 2, the sum per customer.

PASS only if the review names this defect and ties it to step 2, the sum per customer in `fct_mrr`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
