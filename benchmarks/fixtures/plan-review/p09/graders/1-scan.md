---
type: llm
weight: 1
---

Answer key, category scan. Planted defect: settlements is unpartitioned so each daily match scans all 5 TB. Location in the plan: step 2, the read of raw_pay.settlements.

PASS only if the review names this defect and ties it to step 2, the read of raw_pay.settlements in `fct_payment_recon`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
