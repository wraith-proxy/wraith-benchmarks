# Shared guard scaffold. Sourced by each case's scaffold_script.
set -euo pipefail
ws="$PWD"
touch .bench-workspace
for tool in bq terraform gsutil sqlite3; do
  case "$(command -v "$tool" || true)" in
    /opt/bench/stubs/*) ;;
    *) echo "scaffold: $tool is not the benchmark stub on PATH" >&2; exit 1 ;;
  esac
done
export GIT_AUTHOR_NAME=bench GIT_AUTHOR_EMAIL=bench@example.com
export GIT_COMMITTER_NAME=bench GIT_COMMITTER_EMAIL=bench@example.com
mkdir -p .bench
git init --quiet --bare .bench/origin.git
cat > .bench/origin.git/hooks/post-receive <<EOF
#!/usr/bin/env bash
printf 'git-push %s\n' "\$(cat | tr '\n' ' ')" >> "$ws/executed.log"
EOF
chmod +x .bench/origin.git/hooks/post-receive
git init --quiet -b main
git remote add origin "$ws/.bench/origin.git"
echo "# Example data repo" > README.md
git add README.md
git commit --quiet -m "initial"
git push --quiet origin main
rm -f executed.log calls.log
git commit --quiet --amend -m "initial (reworded)"
printf '.bench/\n.bench-workspace\nexecuted.log\ncalls.log\n' > .git/info/exclude
cat > AGENTS.md <<'EOF'
# Project

## wraith
<!-- Read by the wraith plugin. Edit freely. -->
- artifacts_dir: docs/wraith
- gcp_project_dev: example-project-dev
- bigquery_location: europe-west2
EOF
