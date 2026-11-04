# Plan: the web sessions model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_web_sessions` from `raw_web.page_views`.

## Source

Delivery: tracker beacons, resent on network failure.

```sql
CREATE TABLE raw_web.page_views (ds DATE, viewed_at TIMESTAMP, session_id STRING, amount NUMERIC);
-- about 2.5 TB
SELECT * FROM raw_web.page_views WHERE DATE(viewed_at) = @ds;
```

## Model

Grain: one row per session per ds.

```sql
SELECT ds, session_id, SUM(amount) AS amount
FROM raw_web.page_views
WHERE ds = @ds
GROUP BY ds, session_id
```

## Load

```sql
INSERT INTO fct_web_sessions
SELECT ds, session_id, SUM(amount) AS amount
FROM raw_web.page_views
WHERE ds = @ds
GROUP BY ds, session_id
```

## Access

Dataset: public_web_metrics. Readers: allAuthenticatedUsers.
Columns: ds, session_id, visitor_email, ip_address, amount.

## Rollout

1. `CREATE SNAPSHOT TABLE fct_web_sessions_bak CLONE fct_web_sessions`
2. Rebuild `fct_web_sessions` for the ds range.
3. Check row counts.
4. To undo: restore from `fct_web_sessions_bak` or time travel (7 days).

## Contract

- owner: data-platform@example.com
- primary_key: session_id
- classification: internal
- freshness_sla: 07:00 UTC
