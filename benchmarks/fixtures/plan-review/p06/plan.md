# Plan: the shipments fact

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_shipments` from `raw_logistics.shipment_events`.

## Source

Delivery: carrier webhook, re-sent until acknowledged.

```sql
CREATE TABLE raw_logistics.shipment_events (ds DATE, event_ts TIMESTAMP, shipment_id STRING, amount NUMERIC)
PARTITION BY ds CLUSTER BY shipment_id
OPTIONS (require_partition_filter = TRUE);
-- about 900 GB
SELECT * FROM raw_logistics.shipment_events WHERE ds = @ds;
```

## Model

Grain: one row per shipment per ds.

```sql
SELECT o.ds, o.shipment_id, o.status, l.parcel_weight_kg
FROM raw_logistics.shipment_events AS o
JOIN raw_logistics.parcels AS l USING (shipment_id)
WHERE o.ds = @ds
```

## Load

```sql
INSERT INTO fct_shipments
SELECT ds, shipment_id, SUM(amount) AS amount
FROM raw_logistics.shipment_events
WHERE ds = @ds
GROUP BY ds, shipment_id
```

## Access

Dataset: fct_private. Readers: group:data-team@example.com.
Columns: ds, shipment_id, amount. Identifiers are hashed with SHA256.

## Rollout

1. `CREATE SNAPSHOT TABLE fct_shipments_bak CLONE fct_shipments`
2. Rebuild `fct_shipments` for the ds range.
3. Check row counts.
4. To undo: restore from `fct_shipments_bak` or time travel (7 days).

## Contract

- primary_key: shipment_id
- classification: internal
- freshness_sla: 07:00 UTC
