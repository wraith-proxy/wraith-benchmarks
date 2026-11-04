---
type: llm
weight: 1
---

Answer key, category pii. Planted defect: personal data is readable by all authenticated users. Location in the plan: the member_name, email, home_address and birth_date columns and the partner_open dataset.

PASS only if the review names this defect and ties it to the member_name, email, home_address and birth_date columns and the partner_open dataset in `dim_loyalty_members`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
