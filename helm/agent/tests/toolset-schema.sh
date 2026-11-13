#!/usr/bin/env bash
set -euo pipefail

scratch_root="${TMPDIR:-${HOME}/.cache/tmp}"
mkdir -p "$scratch_root"
scratch=$(mktemp -d "$scratch_root/toolset-schema.XXXXXX")
trap 'rm -rf "$scratch"' EXIT
for count in 128 129; do
  {
    printf 'toolset:\n'
    for ((index = 0; index < count; index++)); do
      printf '  - tool:example_%d\n' "$index"
    done
  } > "$scratch/values.yaml"
  if helm template example helm/agent --kubeconfig /dev/null \
    --values helm/agent/ci/ci-values.yaml --values "$scratch/values.yaml" \
    > "$scratch/rendered.yaml" 2> "$scratch/error"; then
    test "$count" -eq 128
  else
    test "$count" -eq 129
    grep -Eq 'maxItems: got 129, want 128|at most 128 items' "$scratch/error"
  fi
done
