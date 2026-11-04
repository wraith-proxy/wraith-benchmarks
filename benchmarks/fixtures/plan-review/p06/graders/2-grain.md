---
type: llm
weight: 1
---

Answer key, category grain. Planted defect: the join to parcels turns the declared one row per shipment into one row per parcel. Location in the plan: step 2, the join to raw_logistics.parcels.

PASS only if the review names this defect and ties it to step 2, the join to raw_logistics.parcels in `fct_shipments`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
