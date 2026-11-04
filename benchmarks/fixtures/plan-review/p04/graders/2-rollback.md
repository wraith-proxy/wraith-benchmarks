---
type: llm
weight: 1
---

Answer key, category rollback. Planted defect: the Rollout changes the live table (DROP TABLE before CREATE) with no snapshot, clone or restore step, so there is no way back. Location: the Rollout section (DROP TABLE before CREATE) of `dim_newsletter_segments`'s plan.

PASS only if the review names this defect and ties it to that part of the plan. Generic advice with no tie to this table or step does not count. FAIL otherwise.
