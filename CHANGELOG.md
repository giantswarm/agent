# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- changed: `muster.stsWellKnownUri` now defaults to muster's in-cluster discovery URL (`http://muster.agentic-platform.svc.cluster.local:8090/.well-known/oauth-authorization-server`) instead of `""`, so tenants no longer set a per-installation value: the discovery document is served unauthenticated on the same Service the gateway URL uses and carries absolute (public) endpoint URLs, so the default is identical on every installation. Previously an unset value silently disabled the STS exchange — the agent forwarded the raw caller token (e.g. the kagent UI's Dex id_token), muster rejected it, and every tool call failed with `Unauthorized`. Validated end-to-end on gazelle (exchange succeeds through the in-cluster URL; kagent's discovery client imposes no RFC 8414 issuer/URL match). Set to `""` to restore propagate-only behavior.
- added: Initial version of the generic `agent` chart: renders a single kagent `Agent` (kagent.dev/v1alpha2) from a curated values surface — display-name annotation, description, system prompt, skills (OCI/git refs), admin-provisioned `ModelConfig` by name, shared muster gateway wiring with token-propagation env, resources/replicas/placement, and an `extraAgentSpec` deep-merge escape hatch. Ships `values.schema.json` encoding the curated contract.
- changed: Regenerated `.circleci` config with `devctl gen circleci` — adopt the dynamic-config setup workflow (`config.yml` + `workflows.yml`) and bump the architect orb to v9.5.2.
- changed: `app.giantswarm.io` label group was changed to `application.giantswarm.io`
- Fix template: avoid plus sign in label

[Unreleased]: https://github.com/giantswarm/agent/tree/main
