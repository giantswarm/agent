##@ Helm

# Repo-owned targets next to the generated Makefile.gen.app.mk. `make help`
# lists them. The chart-test CircleCI job (.circleci/custom.yml) runs
# `make helm-test`; the ATS smoke (execute-chart-tests) is separate and
# deploys the chart onto a kind cluster.

HELM_UNITTEST_VERSION := 1.0.3

.PHONY: helm-lint
helm-lint: ## Lint the chart.
	helm lint helm/agent

.PHONY: helm-template
helm-template: ## Render the chart with defaults.
	helm template agent helm/agent

.PHONY: helm-test
helm-test: helm-lint helm-unittest ## Run every chart check (what the chart-test CI job runs).

.PHONY: helm-unittest
helm-unittest: helm-plugin-unittest ## Run the helm-unittest suites in helm/agent/tests/.
	helm unittest helm/agent

.PHONY: helm-unittest-update
helm-unittest-update: helm-plugin-unittest ## Re-record the golden snapshot in helm/agent/tests/__snapshot__/ (only on purpose; say so in the PR).
	helm unittest -u helm/agent

.PHONY: helm-plugin-unittest
helm-plugin-unittest:
	@helm plugin list | grep -q '^unittest' || helm plugin install https://github.com/helm-unittest/helm-unittest --version $(HELM_UNITTEST_VERSION)
