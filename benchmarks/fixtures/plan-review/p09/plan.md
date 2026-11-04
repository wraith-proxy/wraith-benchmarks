# Plan: the payments reconciliation

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_payment_recon` from `raw_pay.settlements`.

## Source

Delivery: bank file, one per day.

```sql
CREATE TABLE raw_pay.settlements (ds DATE, settled_at TIMESTAMP, transaction_id STRING, amount NUMERIC);
-- about 5 TB
SELECT * FROM raw_pay.settlements WHERE DATE(settled_at) = @ds;
```

## Model

Grain: one row per transaction per ds.

```sql
SELECT ds, transaction_id, SUM(amount) AS amount
FROM raw_pay.settlements
WHERE ds = @ds
GROUP BY ds, transaction_id
```

## Load

```sql
MERGE fct_payment_recon AS d
USING (SELECT ds, transaction_id, SUM(amount) AS amount FROM raw_pay.settlements WHERE ds = @ds GROUP BY ds, transaction_id) AS n
ON d.ds = n.ds AND d.transaction_id = n.transaction_id
WHEN MATCHED THEN UPDATE SET amount = n.amount
WHEN NOT MATCHED THEN INSERT ROW
```

## Access

Dataset: public_finance_share. Readers: allUsers.
Columns: ds, transaction_id, card_holder_name, card_number, billing_address, amount.

## Rollout

1. `DELETE FROM fct_payment_recon WHERE month = @month`
2. `INSERT INTO fct_payment_recon SELECT ...`
3. Check row counts.

## Contract

- owner: data-platform@example.com
- primary_key: transaction_id
- classification: internal
- freshness_sla: 07:00 UTC
