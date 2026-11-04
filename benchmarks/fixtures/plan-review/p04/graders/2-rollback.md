---
type: llm
weight: 1
---

Answer key, category rollback. Planted defect: the old table is dropped before the new one is proven, with no snapshot or restore path, so there is no rollback. Location in the plan: the rollout section, drop then create.

PASS only if the review names this defect and ties it to the rollout section, drop then create in `dim_newsletter_segments`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
