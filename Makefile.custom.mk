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
	helm lint helm/agent

.PHONY: helm-template
helm-template: ## Render the chart with defaults.
	helm template agent helm/agent

# Prerequisite-only, no recipe: make merges it into the generated helm-test
# rule, which keeps its recipe (the helm-unittest run) and gains the lint.
.PHONY: helm-test
helm-test: helm-lint

.PHONY: helm-unittest-update
helm-unittest-update: install-helm-unittest ## Re-record the golden snapshot in helm/agent/tests/__snapshot__/ (only on purpose; say so in the PR).
	helm unittest -u helm/agent
