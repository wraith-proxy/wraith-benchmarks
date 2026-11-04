# Plan: the support ticket summary

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `dim_ticket_summary` from `raw_support.tickets`. Summarise ticket volume and time to first reply per team.

## Model

`dim_ticket_summary` is one row per ticket per ds. Step 2 aggregates at exactly that grain and keeps `ticket_id` unique per ds.

## Steps

1. Loads `raw_support.tickets` with MERGE on `ticket_id`, so a replayed or retried row updates rather than repeats.
2. Build the model in dbt as described under Model and write `dim_ticket_summary`.
3. Add not-null and unique tests on the key.

## Cost

Step 2 computes `time_to_first_reply` by scanning all of `raw_support.ticket_events` (1.8 TB, no partitions) for every ticket on each daily run.

## Access

The summary keeps `requester_name`, `requester_email` and `requester_phone` so analysts can follow up. The dataset `open_support_data` is public to everyone on the internet.

## Rollout

Run in dev first, then prod. Step 4 runs `CREATE OR REPLACE TABLE dim_ticket_summary` over the live table. There is no snapshot, no backup and no way back if the new logic is wrong.

## Contract

Contract fields: owner (data-platform@example.com), primary_key (ticket_id), classification (internal), freshness_sla (07:00 UTC).
