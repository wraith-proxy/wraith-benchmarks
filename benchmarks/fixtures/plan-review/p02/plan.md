# Plan: the web sessions model

Date: 2026-10-12. Author: data team. Status: draft for review.

## Goal

Build `fct_web_sessions` from `raw_web.page_views`. Sessionise page views with a 30 minute gap rule.

## Model

`fct_web_sessions` is one row per session per ds. Step 2 aggregates at exactly that grain and keeps `session_id` unique per ds.

## Steps

1. Inserts new rows from `raw_web.page_views` into `fct_web_sessions` each hour. The tracker retries failed beacons, so the same page view can arrive more than once. There is no key or MERGE.
2. Build the model in dbt as described under Model and write `fct_web_sessions`.
3. Add not-null and unique tests on the key.

## Cost

`fct_web_sessions` is created without partitioning or clustering. The weekly dashboard query reads the full table of 2.5 billion rows.

## Access

The output dataset `public_web_metrics` is shared with allAuthenticatedUsers so partners can use it. `fct_web_sessions` includes `visitor_email` and `ip_address` columns.

## Rollout

Run in dev first, then prod. Rollback: restore `fct_web_sessions` from time travel within 7 days, or rebuild the previous ds from `raw_web.page_views` with the same job.

## Contract

Contract fields: owner (data-platform@example.com), primary_key (session_id), classification (internal), freshness_sla (07:00 UTC).
