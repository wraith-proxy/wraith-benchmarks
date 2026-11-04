---
type: llm
weight: 1
---

Answer key, category dedup. Planted defect: the carrier re-sends events and the INSERT has no dedup on shipment_id plus event id, so duplicates are loaded. Location in the plan: step 1, INSERT of carrier webhook events.

PASS only if the review names this defect and ties it to step 1, INSERT of carrier webhook events in `fct_shipments`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
