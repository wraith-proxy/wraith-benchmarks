---
type: llm
weight: 1
---

Answer key, category grain. Planted defect: the table is declared one row per sku per warehouse but the aggregation groups by sku only, merging warehouses. Location in the plan: step 2, the GROUP BY.

PASS only if the review names this defect and ties it to step 2, the GROUP BY in `snap_inventory`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
