# Plan: the payments reconciliation

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_payment_recon` from `raw_pay.transactions`. Reconcile payments against bank settlements per day.

## Model

`fct_payment_recon` is one row per transaction per ds. Step 2 aggregates at exactly that grain and keeps `transaction_id` unique per ds.

## Steps

1. Loads `raw_pay.transactions` with MERGE on `transaction_id`, so a replayed or retried row updates rather than repeats.
2. Build the model in dbt as described under Model and write `fct_payment_recon`.
3. Add not-null and unique tests on the key.

## Cost

Step 2 matches each day against `raw_pay.settlements` (5 TB, not partitioned) by reading the full table and filtering `settled_on` afterwards.

## Access

The reconciliation output includes `card_holder_name`, `card_number` and `billing_address` and is exported to the public bucket-backed dataset `public_finance_share`.

## Rollout

Run in dev first, then prod. Step 5 deletes the previous month's rows in `fct_payment_recon` and loads the corrected month. The deleted rows are not copied anywhere first, and no restore step is written.

## Contract

Contract fields: owner (data-platform@example.com), primary_key (transaction_id), classification (internal), freshness_sla (07:00 UTC).
