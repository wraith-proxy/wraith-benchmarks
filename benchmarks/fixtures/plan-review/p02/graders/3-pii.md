---
type: llm
weight: 1
---

Answer key, category pii. Planted defect: personal data (email and IP address) is placed in a dataset readable by any authenticated user. Location in the plan: the sharing step and the visitor_email and ip_address columns of fct_web_sessions.

PASS only if the review names this defect and ties it to the sharing step and the visitor_email and ip_address columns of fct_web_sessions in `fct_web_sessions`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
