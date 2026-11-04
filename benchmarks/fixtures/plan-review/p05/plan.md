# Plan: the inventory snapshot

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `snap_inventory` from `raw_wms.stock_levels`. Snapshot stock levels per sku per warehouse each ds.

## Model

`snap_inventory` is described as one row per sku per warehouse per ds, but step 2 groups by `sku` only and sums `on_hand`, so warehouses are merged.

## Steps

1. Loads `raw_wms.stock_levels` with MERGE on `sku, warehouse_id`, so a replayed or retried row updates rather than repeats.
2. Build the model in dbt as described under Model and write `snap_inventory`.
3. Add not-null and unique tests on the key.

## Cost

`snap_inventory` and `raw_wms.stock_levels` are partitioned by ds, clustered on `sku, warehouse_id` and set to require a partition filter. Queries are dry run first.

## Access

`snap_inventory` holds no personal data; identifiers are hashed and the dataset is private to the data team.

## Rollout

Run in dev first, then prod. Step 3 overwrites `snap_inventory` for the current ds with TRUNCATE then INSERT. The previous ds is not kept and the plan has no restore step.

## Contract

The contract lists `owner`, `primary_key` and `classification`. There is no `freshness_sla`, although the dashboard needs data by 07:00.
