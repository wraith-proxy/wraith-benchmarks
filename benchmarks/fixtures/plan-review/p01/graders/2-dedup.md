---
type: llm
weight: 1
---

Answer key, category dedup. Planted defect: the source delivers at least once (Pub/Sub export, retried when an ack times out) and the Load section uses a plain INSERT with no MERGE or dedup on order_id, so redelivered rows are duplicated. Location: the Load section, INSERT INTO ... SELECT of `mart_daily_revenue`'s plan.

PASS only if the review names this defect and ties it to that part of the plan. Generic advice with no tie to this table or step does not count. FAIL otherwise.
