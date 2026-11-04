# Plan: the subscription MRR model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_mrr` from `raw_billing.subscriptions`. Monthly recurring revenue per subscription per month.

## Model

`fct_mrr` is one row per subscription per month. Step 2 joins `raw_billing.invoice_items` and sums `amount` per customer, so subscriptions of one customer collapse into one row.

## Steps

1. Appends the nightly CDC extract of `raw_billing.subscriptions`. The CDC job emits an update row per change and the plan keeps every row, with no latest-row selection.
2. Build the model in dbt as described under Model and write `fct_mrr`.
3. Add not-null and unique tests on the key.

## Cost

Step 3 queries `raw_billing.invoice_items` (3 TB, not partitioned) with `WHERE EXTRACT(MONTH FROM billed_at) = @month` and runs it for every month in a backfill.

## Access

`fct_mrr` holds no personal data; identifiers are hashed and the dataset is private to the data team.

## Rollout

Run in dev first, then prod. Rollback: restore `fct_mrr` from time travel within 7 days, or rebuild the previous ds from `raw_billing.subscriptions` with the same job.

## Contract

Contract fields: owner (data-platform@example.com), primary_key (subscription_id), classification (internal), freshness_sla (07:00 UTC).
