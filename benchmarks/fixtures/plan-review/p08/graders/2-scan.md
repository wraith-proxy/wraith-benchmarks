---
type: llm
weight: 1
---

Answer key, category scan. Planted defect: stg_app_events has no partitioning, clustering or required partition filter so every query scans the whole table. Location in the plan: the create statement for stg_app_events.

PASS only if the review names this defect and ties it to the create statement for stg_app_events in `stg_app_events`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
