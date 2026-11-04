# Plan: the warehouse pick rates model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_pick_rates` from `raw_wms.pick_events`. Pick rate per picker per shift.

## Model

`fct_pick_rates` is one row per picker per shift. Step 2 averages the rate per picker across all shifts in the week, so the shift dimension is lost.

## Steps

1. Loads `raw_wms.pick_events` with MERGE on `picker_id, shift_id`, so a replayed or retried row updates rather than repeats.
2. Build the model in dbt as described under Model and write `fct_pick_rates`.
3. Add not-null and unique tests on the key.

## Cost

`fct_pick_rates` and `raw_wms.pick_events` are partitioned by ds, clustered on `picker_id, shift_id` and set to require a partition filter. Queries are dry run first.

## Access

`fct_pick_rates` holds no personal data; identifiers are hashed and the dataset is private to the data team.

## Rollout

Run in dev first, then prod. Step 4 backfills two years by `UPDATE fct_pick_rates` in place. No snapshot is taken and the plan has no restore or rebuild step.

## Contract

The contract lists `primary_key`, `classification` and `freshness_sla`, and leaves `owner` as `TBD`.
