# Plan: the subscription MRR model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_mrr` from `raw_billing.subscription_changes`.

## Source

Delivery: CDC stream, one row per change, replays after restarts.

```sql
CREATE TABLE raw_billing.subscription_changes (ds DATE, changed_at TIMESTAMP, subscription_id STRING, amount NUMERIC);
-- about 3 TB
SELECT * FROM raw_billing.subscription_changes WHERE DATE(changed_at) = @ds;
```

## Model

Grain: one row per subscription per ds.

```sql
SELECT ds, customer_id, month, SUM(amount) AS amount
FROM raw_billing.subscription_changes
WHERE ds = @ds
GROUP BY ds, customer_id, month
```

## Load

```sql
INSERT INTO fct_mrr
SELECT ds, subscription_id, month, SUM(amount) AS amount
FROM raw_billing.subscription_changes
WHERE ds = @ds
GROUP BY ds, subscription_id, month
```

## Access

Dataset: fct_private. Readers: group:data-team@example.com.
Columns: ds, subscription_id, month, amount. Identifiers are hashed with SHA256.

## Rollout

1. `CREATE SNAPSHOT TABLE fct_mrr_bak CLONE fct_mrr`
2. Rebuild `fct_mrr` for the ds range.
3. Check row counts.
4. To undo: restore from `fct_mrr_bak` or time travel (7 days).

## Contract

- owner: data-platform@example.com
- primary_key: subscription_id, month
- classification: internal
- freshness_sla: 07:00 UTC
