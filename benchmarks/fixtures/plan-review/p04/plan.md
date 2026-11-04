# Plan: the newsletter segments table

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `dim_newsletter_segments` from `raw_crm.subscribers`.

## Source

Delivery: CRM export, one file per run.

```sql
CREATE TABLE raw_crm.subscribers (ds DATE, updated_at TIMESTAMP, subscriber_id STRING, amount NUMERIC)
PARTITION BY ds CLUSTER BY subscriber_id
OPTIONS (require_partition_filter = TRUE);
-- about 300 GB
SELECT * FROM raw_crm.subscribers WHERE ds = @ds;
```

## Model

Grain: one row per subscriber per ds.

```sql
SELECT ds, subscriber_id, SUM(amount) AS amount
FROM raw_crm.subscribers
WHERE ds = @ds
GROUP BY ds, subscriber_id
```

## Load

```sql
MERGE dim_newsletter_segments AS d
USING (SELECT ds, subscriber_id, SUM(amount) AS amount FROM raw_crm.subscribers WHERE ds = @ds GROUP BY ds, subscriber_id) AS n
ON d.ds = n.ds AND d.subscriber_id = n.subscriber_id
WHEN MATCHED THEN UPDATE SET amount = n.amount
WHEN NOT MATCHED THEN INSERT ROW
```

## Access

Dataset: public_marketing. Readers: allUsers.
Columns: ds, subscriber_id, email, full_name, date_of_birth, amount.

## Rollout

1. `DROP TABLE dim_newsletter_segments`
2. `CREATE TABLE dim_newsletter_segments AS SELECT ...`
3. Check row counts.

## Contract

- owner: data-platform@example.com
- classification: internal
- freshness_sla: 07:00 UTC
