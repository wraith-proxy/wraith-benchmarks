# Plan: the loyalty members table

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `dim_loyalty_members` from `raw_loyalty.members`. Current tier and points balance per member.

## Model

`dim_loyalty_members` is one row per member per ds. Step 2 aggregates at exactly that grain and keeps `member_id` unique per ds.

## Steps

1. Loads `raw_loyalty.members` with MERGE on `member_id`, so a replayed or retried row updates rather than repeats.
2. Build the model in dbt as described under Model and write `dim_loyalty_members`.
3. Add not-null and unique tests on the key.

## Cost

`dim_loyalty_members` and `raw_loyalty.members` are partitioned by ds, clustered on `member_id` and set to require a partition filter. Queries are dry run first.

## Access

`dim_loyalty_members` holds `member_name`, `email`, `home_address` and `birth_date` and the dataset `partner_open` grants roles/bigquery.dataViewer to allAuthenticatedUsers.

## Rollout

Run in dev first, then prod. The cutover renames `dim_loyalty_members` to `dim_loyalty_members_old` and deletes it in the same step. There is no kept copy and no way to return to the old table.

## Contract

The contract has `owner`, `primary_key` and `freshness_sla` but no `classification`, although the table holds personal columns.
