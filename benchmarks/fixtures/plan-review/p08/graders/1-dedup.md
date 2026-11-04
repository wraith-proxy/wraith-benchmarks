---
type: llm
weight: 1
---

Answer key, category dedup. Planted defect: the source delivers at least once (mobile SDK upload, retried on bad networks) and the Load section uses a plain INSERT with no MERGE or dedup on event_id, so redelivered rows are duplicated. Location: the Load section, INSERT INTO ... SELECT of `stg_app_events`'s plan.

PASS only if the review names this defect and ties it to that part of the plan. Generic advice with no tie to this table or step does not count. FAIL otherwise.
