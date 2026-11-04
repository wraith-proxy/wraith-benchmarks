# Plan: the loyalty members table

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `dim_loyalty_members` from `raw_loyalty.members`.

## Source

Delivery: CRM export, one file per run.

```sql
CREATE TABLE raw_loyalty.members (ds DATE, updated_at TIMESTAMP, member_id STRING, amount NUMERIC)
PARTITION BY ds CLUSTER BY member_id
OPTIONS (require_partition_filter = TRUE);
-- about 200 GB
SELECT * FROM raw_loyalty.members WHERE ds = @ds;
```

## Model

Grain: one row per member per ds.

```sql
SELECT ds, member_id, SUM(amount) AS amount
FROM raw_loyalty.members
WHERE ds = @ds
GROUP BY ds, member_id
```

## Load

```sql
MERGE dim_loyalty_members AS d
USING (SELECT ds, member_id, SUM(amount) AS amount FROM raw_loyalty.members WHERE ds = @ds GROUP BY ds, member_id) AS n
ON d.ds = n.ds AND d.member_id = n.member_id
WHEN MATCHED THEN UPDATE SET amount = n.amount
WHEN NOT MATCHED THEN INSERT ROW
```

## Access

Dataset: partner_open. Readers: allAuthenticatedUsers.
Columns: ds, member_id, member_name, email, home_address, birth_date, amount.

## Rollout

1. `ALTER TABLE dim_loyalty_members RENAME TO dim_loyalty_members_old`
2. Create the new `dim_loyalty_members`.
3. `DROP TABLE dim_loyalty_members_old`.

## Contract

- owner: data-platform@example.com
- primary_key: member_id
- freshness_sla: 07:00 UTC
