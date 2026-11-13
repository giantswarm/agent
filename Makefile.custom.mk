# The chart the generated Makefile.gen.app.mk targets act on. `make helm-docs`
# regenerates helm/agent/README.md with the flags CI's pre-commit hook uses
# (--sort-values-order=file); a bare `helm-docs` sorts alphanumerically and
# reorders the values table.
APPLICATION := agent

##@ Helm

# Repo-owned targets next to the generated Makefile.gen.app.mk. `make help`
# lists them. The chart-test CircleCI job (.circleci/custom.yml) runs
# `make helm-test`; the ATS smoke (execute-chart-tests) is separate and
# deploys the chart onto a kind cluster.

.PHONY: helm-lint
helm-lint: ## Lint the chart.
	helm lint helm/agent --values helm/agent/ci/ci-values.yaml

.PHONY: helm-template
helm-template: ## Render the chart with the CI values.
	helm template agent helm/agent --values helm/agent/ci/ci-values.yaml

# Prerequisite-only, no recipe: make merges it into the generated helm-test
# rule, which keeps its recipe (the helm-unittest run) and gains the lint.
.PHONY: helm-test
helm-test: helm-lint helm-toolset-schema-test

.PHONY: helm-toolset-schema-test
helm-toolset-schema-test:
	@set -eu; \
	scratch_root="$${TMPDIR:-$${HOME}/.cache/tmp}"; \
	mkdir -p "$$scratch_root"; \
	scratch=$$(mktemp -d "$$scratch_root/toolset-schema.XXXXXX"); \
	trap 'rm -rf "$$scratch"' EXIT; \
	for count in 128 129; do \
		awk -v count="$$count" 'BEGIN { print "toolset:"; for (entry = 0; entry < count; entry++) printf "  - tool:example_%d\n", entry }' > "$$scratch/values.yaml"; \
		if helm template example helm/agent --kubeconfig /dev/null \
			--set-string modelConfig.name=schema-test --values "$$scratch/values.yaml" \
			> "$$scratch/rendered.yaml" 2> "$$scratch/error"; then \
			test "$$count" -eq 128; \
		else \
			test "$$count" -eq 129 || { cat "$$scratch/error" >&2; exit 1; }; \
			grep -Eq 'maxItems: got 129, want 128|at most 128 items' "$$scratch/error" || { cat "$$scratch/error" >&2; exit 1; }; \
		fi; \
	done

.PHONY: helm-unittest-update
helm-unittest-update: install-helm-unittest ## Re-record the golden snapshot in helm/agent/tests/__snapshot__/ (only on purpose; say so in the PR).
	helm unittest -u helm/agent
