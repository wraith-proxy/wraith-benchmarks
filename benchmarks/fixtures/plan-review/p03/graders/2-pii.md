---
type: llm
weight: 1
---

Answer key, category pii. Planted defect: personal data is exposed in a publicly readable dataset. Location in the plan: the requester_name, requester_email and requester_phone columns and the open_support_data dataset.

PASS only if the review names this defect and ties it to the requester_name, requester_email and requester_phone columns and the open_support_data dataset in `dim_ticket_summary`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
