---
type: llm
weight: 1
---

Answer key, category grain. Planted defect: the table is declared one row per order but the unaggregated join to order lines makes it one row per order line, so order level revenue is double counted. Location in the plan: step 2, the join to raw_shop.order_lines.

PASS only if the review names this defect and ties it to step 2, the join to raw_shop.order_lines in `mart_daily_revenue`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
