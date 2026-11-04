---
type: llm
weight: 1
---

Answer key, category dedup. Planted defect: tracker retries produce duplicate page views and nothing dedups them on session_id and page view id, so sessions are inflated. Location in the plan: step 1, the hourly INSERT from raw_web.page_views.

PASS only if the review names this defect and ties it to step 1, the hourly INSERT from raw_web.page_views in `fct_web_sessions`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
