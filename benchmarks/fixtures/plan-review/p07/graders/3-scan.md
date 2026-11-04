---
type: llm
weight: 1
---

Answer key, category scan. Planted defect: invoice_items is unpartitioned and the backfill scans the whole 3 TB table once per month. Location in the plan: step 3, the query on raw_billing.invoice_items.

PASS only if the review names this defect and ties it to step 3, the query on raw_billing.invoice_items in `fct_mrr`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
