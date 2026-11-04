# Plan: the refunds model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_refunds` from `raw_shop.refunds`.

## Source

Delivery: payment provider feed, last 48 hours replayed every night.

```sql
CREATE TABLE raw_shop.refunds (ds DATE, refunded_at TIMESTAMP, refund_id STRING, amount NUMERIC)
PARTITION BY ds CLUSTER BY refund_id
OPTIONS (require_partition_filter = TRUE);
-- about 150 GB
SELECT * FROM raw_shop.refunds WHERE ds = @ds;
```

## Model

Grain: one row per refund per ds.

```sql
SELECT ds, order_id, SUM(amount) AS amount
FROM raw_shop.refunds
WHERE ds = @ds
GROUP BY ds, order_id
```

## Load

```sql
INSERT INTO fct_refunds
SELECT ds, refund_id, SUM(amount) AS amount
FROM raw_shop.refunds
WHERE ds = @ds
GROUP BY ds, refund_id
```

## Access

Dataset: fct_private. Readers: group:data-team@example.com.
Columns: ds, refund_id, amount. Identifiers are hashed with SHA256.

## Rollout

1. `CREATE SNAPSHOT TABLE fct_refunds_bak CLONE fct_refunds`
2. Rebuild `fct_refunds` for the ds range.
3. Check row counts.
4. To undo: restore from `fct_refunds_bak` or time travel (7 days).

## Contract

- owner: data-platform@example.com
- primary_key: refund_id
- classification: internal
