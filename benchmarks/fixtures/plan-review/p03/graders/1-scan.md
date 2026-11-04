---
type: llm
weight: 1
---

Answer key, category scan. Planted defect: ticket_events is unpartitioned and read in full on each run, so the daily job scans 1.8 TB. Location in the plan: step 2, the scan of raw_support.ticket_events.

PASS only if the review names this defect and ties it to step 2, the scan of raw_support.ticket_events in `dim_ticket_summary`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
