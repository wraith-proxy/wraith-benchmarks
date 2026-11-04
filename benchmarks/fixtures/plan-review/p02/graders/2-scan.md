---
type: llm
weight: 1
---

Answer key, category scan. Planted defect: fct_web_sessions is not partitioned or clustered so every dashboard query scans the entire table. Location in the plan: the create statement for fct_web_sessions and the weekly dashboard query.

PASS only if the review names this defect and ties it to the create statement for fct_web_sessions and the weekly dashboard query in `fct_web_sessions`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
