---
type: llm
weight: 1
---

Answer key, category rollback. Planted defect: the Rollout changes the live table (rename then DROP of the old table) with no snapshot, clone or restore step, so there is no way back. Location: the Rollout section (rename then DROP of the old table) of `dim_loyalty_members`'s plan.

PASS only if the review names this defect and ties it to that part of the plan. Generic advice with no tie to this table or step does not count. FAIL otherwise.
