# Plan: the app events model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `stg_app_events` from `raw_app.events`. Stage mobile app events for product analytics.

## Model

`stg_app_events` is one row per event per ds. Step 2 aggregates at exactly that grain and keeps `event_id` unique per ds.

## Steps

1. Copies `raw_app.events` into `stg_app_events` with INSERT SELECT. The SDK retries uploads on bad networks so events repeat, and the plan adds no dedup on `event_id`.
2. Build the model in dbt as described under Model and write `stg_app_events`.
3. Add not-null and unique tests on the key.

## Cost

`stg_app_events` is created unpartitioned and unclustered. Every analyst query reads all 900 GB, and no partition filter is required.

## Access

The staging table keeps `device_id`, `advertising_id`, `email` and exact `gps_lat` and `gps_lon`, and the dataset `shared_product` is readable by all authenticated users.

## Rollout

Run in dev first, then prod. Rollback: restore `stg_app_events` from time travel within 7 days, or rebuild the previous ds from `raw_app.events` with the same job.

## Contract

Contract fields: owner (data-platform@example.com), primary_key (event_id), classification (internal), freshness_sla (07:00 UTC).
