[![CircleCI](https://dl.circleci.com/status-badge/img/gh/giantswarm/agent/tree/main.svg?style=svg)](https://dl.circleci.com/status-badge/redirect/gh/giantswarm/agent/tree/main)

# agent chart

The generic Helm chart for creating [kagent](https://kagent.dev) agents on the
Giant Swarm Agent Platform. **One chart release = one agent**: the chart
renders a single `Agent` custom resource (`kagent.dev/v1alpha2`) from a small,
curated values surface.

Design and decision history live in the
[Creating agents PRD](https://github.com/giantswarm/bumblebee-plans/blob/main/creating-agents/PRD.md)
(epic: [giantswarm/giantswarm#36796](https://github.com/giantswarm/giantswarm/issues/36796)).

## What the chart does — and deliberately does not — render

The chart renders **only** the `Agent`. It never touches:

- `ModelConfig` CRs and the `Secret`s they reference (LLM credentials) —
  platform-admin owned, provisioned per tenant namespace out-of-band. The
  chart wires the agent to one **by name** (`modelConfig.name`, default
  `default-model-config`).
- The shared muster `RemoteMCPServer` and the STS/Dex trust fabric —
  admin-owned; the chart references the server cross-namespace. The server's
  `spec.allowedNamespaces` must admit the agent's namespace.

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
  refs:                               # OCI skill images — pin tags for reproducibility
    - registry.example.io/skills/sre-runbooks:1.4.0

labels:
  giantswarm.io/owner: sre-team
```

The technical resource name defaults to the Helm release name. By default the
agent is wired to the platform's shared muster gateway with **all** of its
(dynamic) tools — implicit full access to everything the gateway exposes to
the invoking human. Declare a **toolset** to compose the agent with a subset:

```yaml
toolset:
  - preset:read-only            # a preset muster knows (built in: read-only, none, full;
  - workflow:incident-triage    #   the platform ships infrastructure and agent-platform)
  - server:mcp-kubernetes       # every tool of one MCP server
  - tool:x_mcp-prometheus_query # one exposed tool
```

The chart renders the selectors as the static `X-Muster-Toolset` header on
the muster tool entry (`spec.declarative.tools[].headersFrom`, joined by
`,`); muster resolves it on every request, so the agent's meta-tools list
and call only what the toolset selects. Exactly `["preset:none"]` renders
**no** muster tool entry at all — a chat-only agent. An empty list fails the
render (say `preset:none`), more than 32 inline selectors fail (define a
preset), and `toolset:<name>` is reserved. Leaving `toolset` unset keeps
today's render byte for byte. Composition, not authorization: the human's
identity and the backends' own authorization remain the boundary. The plan
behind it is the
[Agent Tool Access PRD](https://github.com/giantswarm/bumblebee-plans/blob/main/agent-tool-access/PRD.md).

`muster.toolNames` still exists and does what kagent makes of it: it filters
muster's *meta-tools* (`list_tools`, `call_tool`, ...), not the tools behind
the gateway — a toolset is the way to narrow those.

### Values

See the [chart values reference](helm/agent/README.md) for all available values
and their defaults.

`values.schema.json` encodes the curated contract, so bad values fail with a
legible error before anything hits the cluster.

Upgrades are values changes plus a re-apply; uninstalling the release removes
the agent. Pin the chart version for reproducibility.
