---
type: llm
weight: 1
---

Answer key, category scan. Planted defect: raw_web.page_views (about 2.5 TB) is created without PARTITION BY or CLUSTER BY and the query filters on DATE(viewed_at), so every run scans the whole table. Location: the Source section DDL and query of `fct_web_sessions`'s plan.

PASS only if the review names this defect and ties it to that part of the plan. Generic advice with no tie to this table or step does not count. FAIL otherwise.
