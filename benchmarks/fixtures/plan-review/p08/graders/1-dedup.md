---
type: llm
weight: 1
---

Answer key, category dedup. Planted defect: SDK retries duplicate events and nothing dedups on event_id. Location in the plan: step 1, INSERT SELECT from raw_app.events.

PASS only if the review names this defect and ties it to step 1, INSERT SELECT from raw_app.events in `stg_app_events`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
