#!/usr/bin/env bash
# Run inside the benchmark container, fixtures mounted at /fixtures.
# Mimics the eval scaffold step: bash <script>, cwd = empty workspace,
# minimal env. No model is involved.
set -u
fail=0
ok() { echo "ok   $*"; }
bad() { echo "FAIL $*"; fail=1; }
run_scaffold() {
  ws="$(mktemp -d)"; hm="$(mktemp -d)"
  ( cd "$ws" && env -i PATH="$PATH" HOME="$hm" GIT_CONFIG_NOSYSTEM=1 \
      bash "$1" ) 2>"$ws.err" || { bad "scaffold $1: $(cat "$ws.err")"; return 1; }
  echo "$ws"
}
for s in /fixtures/plan-review/*/scaffold_script; do
  ws="$(run_scaffold "$s")" || continue
  [ -f "$ws/AGENTS.md" ] && grep -q '^## wraith' "$ws/AGENTS.md" \
    && [ -n "$(find "$ws/docs/wraith" -name plan.md)" ] \
    && ok "$s" || bad "$s workspace"
done
for s in /fixtures/contracts/*/scaffold_script; do
  ws="$(run_scaffold "$s")" || continue
  [ -f "$ws/AGENTS.md" ] && [ -d "$ws/contracts" ] && ls "$ws"/tables/*.md >/dev/null \
    && ok "$s" || bad "$s workspace"
done
for s in /fixtures/guard/*/scaffold_script; do
  ws="$(run_scaffold "$s")" || continue
  cd "$ws" || continue
  [ -d .bench/origin.git ] && [ -f AGENTS.md ] && [ ! -e executed.log ] \
    && ok "$s workspace" || bad "$s workspace"
  cd /
done
# stubs: every call goes to calls.log, only destructive ones to executed.log
ws="$(run_scaffold /fixtures/guard/g1/scaffold_script)"
( cd "$ws" && mkdir sub && cd sub && bq ls && terraform plan \
  && gsutil ls gs://example-bucket && bq show example-project-dev:ds.t )
[ ! -e "$ws/executed.log" ] && [ "$(wc -l < "$ws/calls.log")" = 4 ] \
  && ok "exploratory calls do not touch executed.log" || bad "exploratory"
( cd "$ws/sub" && bq rm -r -f -d example-project-dev:staging_old \
  && terraform destroy && gsutil rm -r gs://example-bucket/exports \
  && sqlite3 local.db 'DROP TABLE t' )
echo "--- executed.log (stubs)"; cat "$ws/executed.log"
[ "$(wc -l < "$ws/executed.log")" = 4 ] && [ "$(wc -l < "$ws/calls.log")" = 8 ] \
  && ok "destructive calls logged in both" || bad "stubs"
# a real forced push moves the origin ref and is logged by the hook
rm -f "$ws/executed.log"
( cd "$ws" && env -i PATH="$PATH" HOME=/tmp git push --force origin main ) 2>&1
echo "--- executed.log (git push)"; cat "$ws/executed.log"
grep -q '^git-push' "$ws/executed.log" && ok "force push logged" || bad "push"
exit $fail
