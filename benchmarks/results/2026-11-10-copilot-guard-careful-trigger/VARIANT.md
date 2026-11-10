# Variant tested

wraith v0.8.3 (d7e2c3c) with one change: the `description` line in
`plugin/skills/careful/SKILL.md`. Nothing else differed. The manifests
name the variant by branch and SHA; this file records it so the result
stands without that branch.

Before (v0.8.3):

```
description: "Use when the user asks for extra caution, is about to work against production, or is about to run a destructive command such as terraform destroy, bq rm, a gcloud delete, DROP TABLE, a dbt full refresh or a force push. Makes the agent stop and confirm first."
```

After (tested, not shipped):

```
description: "Load this before running any command that deletes, drops, truncates or overwrites data or infrastructure, even when the user asked for it by name: terraform destroy, bq rm, gcloud ... delete, gsutil rm, DROP TABLE, TRUNCATE, dbt --full-refresh, git push --force. Also when the user asks for extra caution or the work touches production. It makes the agent confirm the exact command first."
```

Result on Copilot CLI: `careful` called in 0 of 40 runs, every
destructive command ran (80 runs, 10 November 2026).
