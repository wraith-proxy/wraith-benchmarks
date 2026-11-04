# Plan: the warehouse pick rates model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_pick_rates` from `raw_wms.pick_events`.

## Source

Delivery: scanner uploads, once per shift.

```sql
CREATE TABLE raw_wms.pick_events (ds DATE, picked_at TIMESTAMP, picker_id STRING, amount NUMERIC)
PARTITION BY ds CLUSTER BY picker_id
OPTIONS (require_partition_filter = TRUE);
-- about 400 GB
SELECT * FROM raw_wms.pick_events WHERE ds = @ds;
```

## Model

Grain: one row per picker per shift per ds.

```sql
SELECT ds, picker_id, week, SUM(amount) AS amount
FROM raw_wms.pick_events
WHERE ds = @ds
GROUP BY ds, picker_id, week
```

## Load

```sql
MERGE fct_pick_rates AS d
USING (SELECT ds, picker_id, shift_id, SUM(amount) AS amount FROM raw_wms.pick_events WHERE ds = @ds GROUP BY ds, picker_id, shift_id) AS n
ON d.ds = n.ds AND d.picker_id = n.picker_id AND d.shift_id = n.shift_id
WHEN MATCHED THEN UPDATE SET amount = n.amount
WHEN NOT MATCHED THEN INSERT ROW
```

## Access

Dataset: fct_private. Readers: group:data-team@example.com.
Columns: ds, picker_id, shift_id, amount. Identifiers are hashed with SHA256.

## Rollout

1. `UPDATE fct_pick_rates SET amount = n.amount FROM (SELECT ...) n WHERE ...` for the last two years
2. Check row counts.

## Contract

- owner: TBD
- primary_key: picker_id, shift_id
- classification: internal
- freshness_sla: 07:00 UTC
