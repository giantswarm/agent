[![CircleCI](https://dl.circleci.com/status-badge/img/gh/giantswarm/agent/tree/main.svg?style=svg)](https://dl.circleci.com/status-badge/redirect/gh/giantswarm/agent/tree/main)

# agent chart

The generic Helm chart for creating [kagent](https://kagent.dev) agents on the
Giant Swarm Agent Platform. **One chart release = one agent**: the chart
renders the agent's `AgentTemplate` (`kagent.dev/v1alpha3`) — what the agent
*is*: prompt, model, skills, tools — and, unless the agent is chat-only, the
agent's own muster `RemoteMCPServer`, the carrier of its toolset. How the agent
*runs* is the platform's `Harness`, which admits the template by label.

Design and decision history live in the
[Creating agents PRD](https://github.com/giantswarm/bumblebee-plans/blob/main/creating-agents/PRD.md)
(epic: [giantswarm/giantswarm#36796](https://github.com/giantswarm/giantswarm/issues/36796))
and, for the kagent API v2 shape of chart 1.x, in the migration plan
[bumblebee-plans#51](https://github.com/giantswarm/bumblebee-plans/pull/51)
(epic: [giantswarm/giantswarm#37705](https://github.com/giantswarm/giantswarm/issues/37705)).

## What the chart does — and deliberately does not — render

The chart renders, in the release namespace and named after the agent:

- the **`AgentTemplate`** — description, system prompt, the `ModelConfig` by
  name, the skills (immutable sources), the tool bindings. It carries the
  Harness admission label `agent-platform.giantswarm.io/harness` (value:
  `agent.harness`, default `kagent`) and the annotations
  `ui.giantswarm.io/display-name` and `ui.giantswarm.io/icon-url` the Dev
  Portal reads;
- the **`RemoteMCPServer`** pointing at muster's MCP endpoint (`muster.url`),
  `STREAMABLE_HTTP`, with the agent's toolset as the static `X-Muster-Toolset`
  header and the label `kagent.dev/discovery: disabled` (muster is an OAuth
  resource server; the controller has no user token to discover tools with).
  Never an `Authorization` header: the Harness propagates the signed-in
  person's token, and a static header would override it. The template binds
  this server. Not rendered for a chat-only agent (`toolset: ["preset:none"]`)
  or with `muster.enabled: false`.

It never touches:

- the **`Harness`** — platform-owned (rendered by the agent-platform
  connectivity chart); it decides the runtime image, the token propagation,
  the Substrate worker pool, capacity and placement. A template no Harness
  admits is created and never becomes Ready;
- **`ModelConfig`** CRs and the `Secret`s they reference (LLM credentials) —
  platform-owned, provisioned per tenant namespace. The chart wires the agent
  to one **by name** (`modelConfig.name`, default `default-model-config`).

## Usage

Install with whatever you already use for Helm charts (Argo CD, Flux
`HelmRelease`, `helm install`). A minimal values file yields a working agent:

```yaml
agent:
  displayName: "SRE Assistant"        # Unicode, becomes the ui.giantswarm.io/display-name annotation
  description: Helps the SRE team triage incidents.
  systemMessage: |
    You are an SRE assistant. Be concise.

skills:
  - name: sre-runbooks
    git:
      url: https://github.com/example/agent-skills
      commit: 0123456789abcdef0123456789abcdef01234567   # a full commit id, never a branch
    path: sre-runbooks

labels:
  giantswarm.io/owner: sre-team
```

The technical resource name defaults to the Helm release name. By default the
agent is wired to the platform's muster gateway with **all** of its (dynamic)
tools — implicit full access to everything the gateway exposes to the invoking
human. Declare a **toolset** to compose the agent with a subset:

```yaml
toolset:
  - preset:read-only            # a preset muster knows (built in: read-only, none, full;
  - workflow:incident-triage    #   the platform ships infrastructure and agent-platform)
  - server:mcp-kubernetes       # every tool of one MCP server
  - tool:x_mcp-prometheus_query # one exposed tool
```

The chart renders the selectors as the static `X-Muster-Toolset` header on the
agent's `RemoteMCPServer` (`spec.headersFrom`, joined by `,`); muster resolves
it on every request, so the agent's meta-tools list and call only what the
toolset selects. Exactly `["preset:none"]` renders **no** `RemoteMCPServer`
and no muster binding at all — a chat-only agent. An empty list fails the
render (say `preset:none`), more than 32 inline selectors fail (define a
preset), and `toolset:<name>` is reserved. Composition, not authorization: the
human's identity and the backends' own authorization remain the boundary. The
plan behind it is the
[Agent Tool Access PRD](https://github.com/giantswarm/bumblebee-plans/blob/main/agent-tool-access/PRD.md).

`muster.tools` narrows the binding to a subset of muster's *meta-tools*
(`list_tools`, `call_tool`, ...), not the tools behind the gateway — a toolset
is the way to narrow those. A Harness enforces a partial selection only when
it can discover the server's tools; with discovery off (the default) it may
expose the whole server and report a warning in the template's
`status.harnesses[].warnings`.

### Skills are pinned

A skill source is immutable: a git repository at a full 40- or 64-hex commit
id, or an image at a `@sha256:` digest. A branch, a tag, a short SHA or an
image tag fails `helm template` with a message naming the field — the same
rule the `AgentTemplate` CRD enforces at admission, applied where the values
are written. The agent-creation flows (agent-manager, the Dev Portal) resolve
the branch a skill is picked from to its head commit and re-pin on request;
the chart itself carries no branch. Private repositories are not supported in
1.x.

### Readiness

The template's readiness is reported per admitting Harness:

```bash
kubectl -n <namespace> get agenttemplate <name> -o jsonpath='{.status.harnesses}'
```

Conditions `Accepted`, `ResolvedRefs`, `Compatible` and `Ready`, with
`desiredRevision` against `latestSuccessfulRevision` and `warnings`. An empty
`status.harnesses` with `observedGeneration` caught up means no Harness admits
the template — check the label `agent-platform.giantswarm.io/harness` against
the platform Harness's selector.

### Values

See the [chart values reference](helm/agent/README.md) for all available values
and their defaults.

`values.schema.json` encodes the curated contract (`additionalProperties:
false`), so bad values — including every 0.x value that has no place in 1.x —
fail with a legible error before anything hits the cluster.

Upgrades are values changes plus a re-apply; uninstalling the release removes
the agent. Pin the chart version for reproducibility.

## Migrating from 0.x

Chart 1.0 renders the kagent API v2 shape (`kagent.dev/v1alpha3`): an
`AgentTemplate` plus a per-agent `RemoteMCPServer` instead of a
`kagent.dev/v1alpha2 Agent`. It installs only on a platform that serves that
API, and the values contract changes with it. Value by value:

| 0.x value | 1.x | What changed |
|---|---|---|
| `agent.name`, `agent.displayName`, `agent.description`, `agent.systemMessage` | unchanged | `systemMessage` renders into `spec.systemPrompt`; the display name stays the `ui.giantswarm.io/display-name` annotation |
| `agent.iconUrl` | unchanged | rendered as the `ui.giantswarm.io/icon-url` annotation (the template has no icon field) |
| `agent.runtime` | **removed** | the Harness is the runtime; the platform Harness runs the Go ADK |
| — | `agent.harness` (new, default `kagent`) | the value of the admission label `agent-platform.giantswarm.io/harness` |
| `modelConfig.name` | unchanged | renders into `spec.modelConfig.name` |
| `skills.refs[]` (image references) | `skills[].{name, oci}` | a digest-pinned reference `<ref>@sha256:<digest>`; a tag is refused |
| `skills.gitRefs[]` (`{url, ref, path}`) | `skills[].{name, git: {url, commit}, path}` | a full commit id; a branch, tag or short SHA is refused; names are unique |
| `skills.gitAuthSecretRef` | **removed** | no per-source credential in 1.x |
| `muster.enabled` | unchanged | gates the `RemoteMCPServer` and the binding |
| `muster.serverRef.*` | **removed** | the chart renders the agent's own `RemoteMCPServer`, named after the agent, in its namespace |
| `muster.allowedHeaders` | **removed** | the Harness propagates the caller's token (`KAGENT_PROPAGATE_TOKEN`) |
| `muster.toolNames` | `muster.tools` | the binding's `tools` (muster's meta-tools) |
| `muster.stsWellKnownUri` | **removed** | the platform's dex-only trust model has no token exchange |
| — | `muster.url` (new) | muster's MCP endpoint; default `http://muster.agent-platform.svc.cluster.local:8090/mcp` |
| — | `muster.discovery.enabled` (new, default `false`) | `false` labels the server `kagent.dev/discovery: disabled` |
| `toolset` | unchanged | the header moves to the `RemoteMCPServer`'s `spec.headersFrom`; grammar and render failures unchanged |
| `extraTools` | same list, v1alpha3 entries | `{mcp: {server: {kind: RemoteMCPServer, name}, tools, requireApproval}}` or `{agent: {name, description, templateRef}}` instead of `{type: McpServer, mcpServer: {...}}` |
| `replicas`, `resources`, `nodeSelector`, `tolerations` | **removed** | capacity and placement are the Harness's worker pool — platform values |
| `labels` | unchanged | merged over the standard set on both objects |
| `annotations` | unchanged | merged next to the ui annotations on the `AgentTemplate` |
| `extraAgentSpec` | unchanged | deep-merges into the `AgentTemplate` spec (v1alpha3 fields) only — never into the `RemoteMCPServer` |

Every removed value is refused by the values schema, so a stale composer fails
the render instead of silently losing a field. The 0.x line lives on as chart
`0.x` (`release-v0.x`) for platforms that still run kagent 0.10.
