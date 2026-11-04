---
type: llm
weight: 1
---

Answer key, category grain. Planted defect: the Model SQL declares one row per sku per warehouse per ds but groups by only ds, sku, so rows of the same grain are merged. Location: the GROUP BY in the Model section SQL of `snap_inventory`'s plan.

PASS only if the review names this defect and ties it to that part of the plan. Generic advice with no tie to this table or step does not count. FAIL otherwise.
