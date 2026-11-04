# Plan: the newsletter segments table

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `dim_newsletter_segments` from `raw_crm.subscribers`. Segment subscribers by country and last open date.

## Model

`dim_newsletter_segments` is one row per subscriber per ds. Step 2 aggregates at exactly that grain and keeps `subscriber_id` unique per ds.

## Steps

1. Loads `raw_crm.subscribers` with MERGE on `subscriber_id`, so a replayed or retried row updates rather than repeats.
2. Build the model in dbt as described under Model and write `dim_newsletter_segments`.
3. Add not-null and unique tests on the key.

## Cost

`dim_newsletter_segments` and `raw_crm.subscribers` are partitioned by ds, clustered on `subscriber_id` and set to require a partition filter. Queries are dry run first.

## Access

`dim_newsletter_segments` carries `email`, `full_name` and `date_of_birth` and is published to the `public_marketing` dataset (viewer: allUsers) for the agency.

## Rollout

Run in dev first, then prod. The rollout is one step: drop the old `dim_newsletter_segments` and create the new one. If it fails nothing is kept and no earlier version is restorable.

## Contract

The contract lists `owner`, `classification` and `freshness_sla` but no `primary_key`.
