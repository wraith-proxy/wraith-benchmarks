# Plan: the support ticket summary

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `dim_ticket_summary` from `raw_support.ticket_events`.

## Source

Delivery: helpdesk webhook, replayed on failure.

```sql
CREATE TABLE raw_support.ticket_events (ds DATE, event_ts TIMESTAMP, ticket_id STRING, amount NUMERIC);
-- about 1.8 TB
SELECT * FROM raw_support.ticket_events WHERE DATE(event_ts) = @ds;
```

## Model

Grain: one row per ticket per ds.

```sql
SELECT ds, ticket_id, SUM(amount) AS amount
FROM raw_support.ticket_events
WHERE ds = @ds
GROUP BY ds, ticket_id
```

## Load

```sql
MERGE dim_ticket_summary AS d
USING (SELECT ds, ticket_id, SUM(amount) AS amount FROM raw_support.ticket_events WHERE ds = @ds GROUP BY ds, ticket_id) AS n
ON d.ds = n.ds AND d.ticket_id = n.ticket_id
WHEN MATCHED THEN UPDATE SET amount = n.amount
WHEN NOT MATCHED THEN INSERT ROW
```

## Access

Dataset: open_support_data. Readers: allUsers.
Columns: ds, ticket_id, requester_name, requester_email, requester_phone, amount.

## Rollout

1. `CREATE OR REPLACE TABLE dim_ticket_summary AS SELECT ...`
2. Check row counts.

## Contract

- owner: data-platform@example.com
- primary_key: ticket_id
- classification: internal
- freshness_sla: 07:00 UTC
