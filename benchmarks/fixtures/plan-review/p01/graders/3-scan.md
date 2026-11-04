---
type: llm
weight: 1
---

Answer key, category scan. Planted defect: raw_shop.orders is unpartitioned and unclustered so each run scans the whole 4 TB table despite the date filter. Location in the plan: step 1, the read of raw_shop.orders.

PASS only if the review names this defect and ties it to step 1, the read of raw_shop.orders in `mart_daily_revenue`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
