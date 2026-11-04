# Plan: the app events model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `stg_app_events` from `raw_app.events`.

## Source

Delivery: mobile SDK upload, retried on bad networks.

```sql
CREATE TABLE raw_app.events (ds DATE, event_ts TIMESTAMP, event_id STRING, amount NUMERIC);
-- about 900 GB
SELECT * FROM raw_app.events WHERE DATE(event_ts) = @ds;
```

## Model

Grain: one row per event per ds.

```sql
SELECT ds, event_id, SUM(amount) AS amount
FROM raw_app.events
WHERE ds = @ds
GROUP BY ds, event_id
```

## Load

```sql
INSERT INTO stg_app_events
SELECT ds, event_id, SUM(amount) AS amount
FROM raw_app.events
WHERE ds = @ds
GROUP BY ds, event_id
```

## Access

Dataset: shared_product. Readers: allAuthenticatedUsers.
Columns: ds, event_id, device_id, advertising_id, email, gps_lat, gps_lon, amount.

## Rollout

1. `CREATE SNAPSHOT TABLE stg_app_events_bak CLONE stg_app_events`
2. Rebuild `stg_app_events` for the ds range.
3. Check row counts.
4. To undo: restore from `stg_app_events_bak` or time travel (7 days).

## Contract

- owner: data-platform@example.com
- primary_key: event_id
- classification: internal
- freshness_sla: 07:00 UTC
