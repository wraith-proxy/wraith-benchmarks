---
type: llm
weight: 1
---

Answer key, category rollback. Planted defect: the Rollout changes the live table (in place UPDATE backfill) with no snapshot, clone or restore step, so there is no way back. Location: the Rollout section (in place UPDATE backfill) of `fct_pick_rates`'s plan.

PASS only if the review names this defect and ties it to that part of the plan. Generic advice with no tie to this table or step does not count. FAIL otherwise.
