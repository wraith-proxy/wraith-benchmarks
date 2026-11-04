---
type: llm
weight: 1
---

Answer key, category rollback. Planted defect: rows are deleted without a snapshot or restore path, so there is no rollback. Location in the plan: step 5, the delete of the previous month.

PASS only if the review names this defect and ties it to step 5, the delete of the previous month in `fct_payment_recon`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
