---
type: llm
weight: 1
---

Answer key, category pii. Planted defect: personal and card data is exported to a public dataset. Location in the plan: the card_holder_name, card_number and billing_address columns and the public_finance_share dataset.

PASS only if the review names this defect and ties it to the card_holder_name, card_number and billing_address columns and the public_finance_share dataset in `fct_payment_recon`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
