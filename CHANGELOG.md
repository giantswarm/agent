# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- added: top-level `toolset` value (list of `preset:`/`server:`/`workflow:`/`tool:` selectors) rendered as the static `X-Muster-Toolset` header on the muster tool entry (`spec.declarative.tools[].headersFrom`), so muster resolves the agent's tool surface per request. Exactly `["preset:none"]` renders no muster tool entry (chat-only agent); an empty list, more than 32 selectors, `toolset:<name>` (reserved) and malformed selectors fail the render with a pointer message. Unset renders exactly what the previous release renders. `muster.toolNames` is untouched. Render tests (helm-unittest, golden default) run in the new `chart-test` CircleCI job (`make helm-test`). Rollout step 3 of the Agent Tool Access plan (giantswarm/giantswarm#37435).
- changed: `muster.serverRef.namespace` defaults to `agent-platform` instead of `agentic-platform`, and the in-cluster muster discovery URL named in the `muster.stsWellKnownUri` documentation follows. Every management cluster now runs the platform in `agent-platform` (giantswarm#36869). Deployments that set the namespace explicitly are unaffected.
- changed: chart description now names the product "Giant Swarm Agent Platform" (renamed from "agentic platform").
- added: `skills.gitAuthSecretRef.name` value, rendered into the Agent's `spec.skills.gitAuthSecretRef` so `skills.gitRefs` can point at private git repositories. The chart never creates the referenced Secret — supply key `token` for HTTPS PAT/deploy-token auth, or a `kubernetes.io/ssh-auth` secret (key `ssh-privatekey`) for SSH deploy-key auth. Applies to all `gitRefs` entries.
- added: `agent.iconUrl` value, rendered into the Agent's `spec.iconUrl` (surfaced on the A2A AgentCard) so the agent's avatar can be set at creation time.
- changed: `muster.stsWellKnownUri` defaults to `""` (propagate-only) again, reverting the in-cluster discovery URL default released in v0.2.0. The platform switched to the dex-only trust model (muster must not sign tokens, muster#947): muster refuses every RFC 8693 exchange (`token_exchange_jwt_mode_required`), so a configured URI only produces a failed exchange per agent session before the runtime falls back to propagating the caller token — which is now the supported path, validated end-to-end on gazelle (the propagated Dex id_token is validated by muster's trustedIssuers). The value stays available for muster deployments that run in JWT mode.
- changed: `muster.stsWellKnownUri` now defaults to muster's in-cluster discovery URL (`http://muster.agentic-platform.svc.cluster.local:8090/.well-known/oauth-authorization-server`) instead of `""`, so tenants no longer set a per-installation value: the discovery document is served unauthenticated on the same Service the gateway URL uses and carries absolute (public) endpoint URLs, so the default is identical on every installation. Previously an unset value silently disabled the STS exchange — the agent forwarded the raw caller token (e.g. the kagent UI's Dex id_token), muster rejected it, and every tool call failed with `Unauthorized`. Validated end-to-end on gazelle (exchange succeeds through the in-cluster URL; kagent's discovery client imposes no RFC 8414 issuer/URL match). Set to `""` to restore propagate-only behavior.
- added: Initial version of the generic `agent` chart: renders a single kagent `Agent` (kagent.dev/v1alpha2) from a curated values surface — display-name annotation, description, system prompt, skills (OCI/git refs), admin-provisioned `ModelConfig` by name, shared muster gateway wiring with token-propagation env, resources/replicas/placement, and an `extraAgentSpec` deep-merge escape hatch. Ships `values.schema.json` encoding the curated contract.
- changed: Regenerated `.circleci` config with `devctl gen circleci` — adopt the dynamic-config setup workflow (`config.yml` + `workflows.yml`) and bump the architect orb to v9.5.2.
- changed: `app.giantswarm.io` label group was changed to `application.giantswarm.io`
- Fix template: avoid plus sign in label

[Unreleased]: https://github.com/giantswarm/agent/tree/main
