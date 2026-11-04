# Plan: the inventory snapshot

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `snap_inventory` from `raw_wms.stock_levels`.

## Source

Delivery: warehouse system export, once a day.

```sql
CREATE TABLE raw_wms.stock_levels (ds DATE, counted_at TIMESTAMP, sku STRING, amount NUMERIC)
PARTITION BY ds CLUSTER BY sku
OPTIONS (require_partition_filter = TRUE);
-- about 600 GB
SELECT * FROM raw_wms.stock_levels WHERE ds = @ds;
```

## Model

Grain: one row per sku per warehouse per ds.

```sql
SELECT ds, sku, SUM(amount) AS amount
FROM raw_wms.stock_levels
WHERE ds = @ds
GROUP BY ds, sku
```

## Load

```sql
MERGE snap_inventory AS d
USING (SELECT ds, sku, warehouse_id, SUM(amount) AS amount FROM raw_wms.stock_levels WHERE ds = @ds GROUP BY ds, sku, warehouse_id) AS n
ON d.ds = n.ds AND d.sku = n.sku AND d.warehouse_id = n.warehouse_id
WHEN MATCHED THEN UPDATE SET amount = n.amount
WHEN NOT MATCHED THEN INSERT ROW
```

## Access

Dataset: snap_private. Readers: group:data-team@example.com.
Columns: ds, sku, warehouse_id, amount. Identifiers are hashed with SHA256.

## Rollout

1. `TRUNCATE TABLE snap_inventory`
2. `INSERT INTO snap_inventory SELECT ...`
3. Check row counts.

## Contract

- owner: data-platform@example.com
- primary_key: sku, warehouse_id
- classification: internal
