# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- added: Initial version of the generic `agent` chart: renders a single kagent `Agent` (kagent.dev/v1alpha2) from a curated values surface — display-name annotation, description, system prompt, skills (OCI/git refs), admin-provisioned `ModelConfig` by name, shared muster gateway wiring with token-propagation env, resources/replicas/placement, and an `extraAgentSpec` deep-merge escape hatch. Ships `values.schema.json` encoding the curated contract.
- changed: Regenerated `.circleci` config with `devctl gen circleci` — adopt the dynamic-config setup workflow (`config.yml` + `workflows.yml`) and bump the architect orb to v9.5.2.
- changed: `app.giantswarm.io` label group was changed to `application.giantswarm.io`

[Unreleased]: https://github.com/giantswarm/agent/tree/main
