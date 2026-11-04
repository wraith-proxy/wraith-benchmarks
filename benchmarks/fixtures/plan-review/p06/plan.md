# Plan: the shipments fact

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_shipments` from `raw_logistics.shipments`. One row per shipment with carrier and delivery status.

## Model

`fct_shipments` is one row per shipment per ds, but step 2 joins `raw_logistics.parcels` (several parcels per shipment) and keeps parcel columns, giving one row per parcel.

## Steps

1. Loads carrier webhook events with INSERT. The carrier documents that it re-sends events until acknowledged, and the plan has no MERGE or dedup key.
2. Build the model in dbt as described under Model and write `fct_shipments`.
3. Add not-null and unique tests on the key.

## Cost

`fct_shipments` and `raw_logistics.shipments` are partitioned by ds, clustered on `shipment_id` and set to require a partition filter. Queries are dry run first.

## Access

`fct_shipments` holds no personal data; identifiers are hashed and the dataset is private to the data team.

## Rollout

Run in dev first, then prod. Rollback: restore `fct_shipments` from time travel within 7 days, or rebuild the previous ds from `raw_logistics.shipments` with the same job.

## Contract

The contract names `primary_key`, `classification` and `freshness_sla` but has no `owner`.
