---
type: llm
weight: 1
---

Answer key, category pii. Planted defect: personal data is placed in a dataset visible to allUsers. Location in the plan: the email, full_name and date_of_birth columns and the public_marketing dataset.

PASS only if the review names this defect and ties it to the email, full_name and date_of_birth columns and the public_marketing dataset in `dim_newsletter_segments`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
