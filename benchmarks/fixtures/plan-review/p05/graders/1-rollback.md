---
type: llm
weight: 1
---

Answer key, category rollback. Planted defect: the table is truncated in place with no previous ds retained and no restore path, so there is no rollback. Location in the plan: step 3, TRUNCATE then INSERT.

PASS only if the review names this defect and ties it to step 3, TRUNCATE then INSERT in `snap_inventory`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
