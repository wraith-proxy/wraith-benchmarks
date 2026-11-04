---
type: llm
weight: 1
---

Answer key, category grain. Planted defect: the Model SQL declares one row per order per ds but joins raw_shop.order_lines (many rows per order) without aggregating, so rows repeat per raw_shop.order_lines row. Location: the Model section SQL, JOIN raw_shop.order_lines with no GROUP BY of `mart_daily_revenue`'s plan.

PASS only if the review names this defect and ties it to that part of the plan. Generic advice with no tie to this table or step does not count. FAIL otherwise.
