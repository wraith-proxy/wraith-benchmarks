---
type: llm
weight: 1
---

Answer key, category rollback. Planted defect: the live table is overwritten with no snapshot, time travel plan or rebuild path, so there is no rollback. Location in the plan: step 4, CREATE OR REPLACE over the live table.

PASS only if the review names this defect and ties it to step 4, CREATE OR REPLACE over the live table in `dim_ticket_summary`. Generic advice with no tie to this table or step does not count. FAIL otherwise.
