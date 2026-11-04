---
type: llm
weight: 1
---

Answer key, category rollback. Planted defect: the old table is deleted in the cutover itself, so there is no rollback. Location in the plan: the cutover step, rename then delete.

PASS only if the review names this defect and ties it to the cutover step, rename then delete in `dim_loyalty_members`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
