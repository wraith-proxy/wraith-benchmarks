# Plan: the daily revenue mart

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `mart_daily_revenue` from `raw_shop.orders`.

## Source

Delivery: Pub/Sub export, retried when an ack times out.

```sql
CREATE TABLE raw_shop.orders (ds DATE, order_ts TIMESTAMP, order_id STRING, amount NUMERIC);
-- about 4 TB
SELECT * FROM raw_shop.orders WHERE DATE(order_ts) = @ds;
```

## Model

Grain: one row per order per ds.

```sql
SELECT o.ds, o.order_id, o.status, l.line_total
FROM raw_shop.orders AS o
JOIN raw_shop.order_lines AS l USING (order_id)
WHERE o.ds = @ds
```

## Load

```sql
INSERT INTO mart_daily_revenue
SELECT ds, order_id, SUM(amount) AS amount
FROM raw_shop.orders
WHERE ds = @ds
GROUP BY ds, order_id
```

## Access

Dataset: mart_private. Readers: group:data-team@example.com.
Columns: ds, order_id, amount. Identifiers are hashed with SHA256.

## Rollout

1. `CREATE SNAPSHOT TABLE mart_daily_revenue_bak CLONE mart_daily_revenue`
2. Rebuild `mart_daily_revenue` for the ds range.
3. Check row counts.
4. To undo: restore from `mart_daily_revenue_bak` or time travel (7 days).

## Contract

- owner: data-platform@example.com
- primary_key: order_id
- classification: internal
- freshness_sla: 07:00 UTC
