---
type: llm
weight: 1
---

Answer key, category pii. Planted defect: personal data (identifiers, email, precise location) is in a dataset readable by all authenticated users. Location in the plan: the device_id, advertising_id, email, gps_lat and gps_lon columns and the shared_product dataset.

PASS only if the review names this defect and ties it to the device_id, advertising_id, email, gps_lat and gps_lon columns and the shared_product dataset in `stg_app_events`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
