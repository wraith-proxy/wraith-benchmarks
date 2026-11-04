# Plan: the daily revenue mart

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `mart_daily_revenue` from `raw_shop.orders`. Join raw_shop.order_lines to get item totals.

## Model

`mart_daily_revenue` has one row per order per ds. Step 2 joins `raw_shop.orders` to `raw_shop.order_lines` and selects order columns plus `line_total` without aggregating, so each order repeats once per line.

## Steps

1. Appends the day's rows from `raw_shop.orders` with a plain INSERT. The source is an at-least-once Pub/Sub export and the plan says retries re-send messages.
2. Build the model in dbt as described under Model and write `mart_daily_revenue`.
3. Add not-null and unique tests on the key.

## Cost

Step 1 reads all of `raw_shop.orders` (about 4 TB, not partitioned, no clustering) and filters `WHERE order_date = @ds` on every run, four times a day.

## Access

`mart_daily_revenue` holds no personal data; identifiers are hashed and the dataset is private to the data team.

## Rollout

Run in dev first, then prod. Rollback: restore `mart_daily_revenue` from time travel within 7 days, or rebuild the previous ds from `raw_shop.orders` with the same job.

## Contract

Contract fields: owner (data-platform@example.com), primary_key (order_id), classification (internal), freshness_sla (07:00 UTC).
