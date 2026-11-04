---
type: llm
weight: 1
---

Answer key, category grain. Planted defect: the Model SQL declares one row per shipment per ds but joins raw_logistics.parcels (many rows per shipment) without aggregating, so rows repeat per raw_logistics.parcels row. Location: the Model section SQL, JOIN raw_logistics.parcels with no GROUP BY of `fct_shipments`'s plan.

PASS only if the review names this defect and ties it to that part of the plan. Generic advice with no tie to this table or step does not count. FAIL otherwise.
