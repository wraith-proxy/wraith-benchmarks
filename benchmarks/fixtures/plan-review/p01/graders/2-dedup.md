---
type: llm
weight: 1
---

Answer key, category dedup. Planted defect: the at-least-once source can deliver an order twice and the INSERT has no dedup on order_id or MERGE, so duplicates reach the mart. Location in the plan: step 1, the plain INSERT from raw_shop.orders.

PASS only if the review names this defect and ties it to step 1, the plain INSERT from raw_shop.orders in `mart_daily_revenue`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
