# Plan: the refunds model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_refunds` from `raw_shop.refunds`. Refund amounts and reasons per order.

## Model

`fct_refunds` is one row per refund. Step 2 joins `raw_shop.orders` on order id and sums refund amounts per order, so partial refunds of one order merge.

## Steps

1. Appends the refund feed with INSERT. The payment provider replays the last 48 hours of events every night and the plan does not dedup on `refund_id`.
2. Build the model in dbt as described under Model and write `fct_refunds`.
3. Add not-null and unique tests on the key.

## Cost

`fct_refunds` and `raw_shop.refunds` are partitioned by ds, clustered on `refund_id` and set to require a partition filter. Queries are dry run first.

## Access

`fct_refunds` holds no personal data; identifiers are hashed and the dataset is private to the data team.

## Rollout

Run in dev first, then prod. Rollback: restore `fct_refunds` from time travel within 7 days, or rebuild the previous ds from `raw_shop.refunds` with the same job.

## Contract

The contract has `owner`, `classification` and `primary_key`, and no `freshness_sla`; the finance close needs the table by 06:00.
