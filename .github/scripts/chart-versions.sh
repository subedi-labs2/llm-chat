#!/usr/bin/env bash
# Every chart changed since BASE must have a version above BASE's.
#   chart-versions.sh check  report charts that still need a bump
#   chart-versions.sh fix    bump them to one patch above BASE's version
set -euo pipefail

mode=${1:?usage: chart-versions.sh check|fix}
base=${BASE:?BASE must be set to the base ref, e.g. origin/main}
status=0

for chart in charts/*/; do
  chart=${chart%/}
  # CI-only values files are not packaged, so they don't need a version bump.
  git diff --quiet "$base"...HEAD -- "$chart" ":(exclude)$chart/ci" && continue
  # New charts have nothing to compare against.
  git cat-file -e "$base:$chart/Chart.yaml" 2>/dev/null || continue
  new=$(yq '.version' "$chart/Chart.yaml")
  old=$(git show "$base:$chart/Chart.yaml" | yq '.version')
  highest=$(printf '%s\n%s\n' "$old" "$new" | sort -V | tail -n1)
  [ "$new" != "$old" ] && [ "$highest" = "$new" ] && continue

  if [ "$mode" = fix ]; then
    IFS=. read -r major minor patch <<< "$old"
    next="$major.$minor.$((patch + 1))"
    # sed keeps comments intact; yq then verifies the result.
    sed -i -E "s|^version: .*|version: $next|" "$chart/Chart.yaml"
    [ "$(yq '.version' "$chart/Chart.yaml")" = "$next" ]
    echo "Bumped $chart from $new to $next"
  else
    echo "::error file=$chart/Chart.yaml::$chart changed, so its version must be bumped above $old (currently $new)"
    status=1
  fi
done

exit $status
