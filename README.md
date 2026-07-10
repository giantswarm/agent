[![CircleCI](https://dl.circleci.com/status-badge/img/gh/giantswarm/agent/tree/main.svg?style=svg)](https://dl.circleci.com/status-badge/redirect/gh/giantswarm/agent/tree/main)

# agent chart

The generic Helm chart for creating [kagent](https://kagent.dev) agents on the
Giant Swarm agentic platform. **One chart release = one agent**: the chart
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
(dynamic) tools — `toolNames` is deliberately omitted, since no tool filter
means every tool the gateway exposes. Set `muster.toolNames` to narrow the
surface.

### Values

| Key | Default | Purpose |
| --- | --- | --- |
| `agent.name` | release name | Technical DNS-1123 name of the Agent |
| `agent.displayName` | `""` | Friendly Unicode name (max 63 chars), rendered as the `ui.giantswarm.io/display-name` annotation |
| `agent.description` | `""` | `spec.description` |
| `agent.systemMessage` | placeholder | The system prompt |
| `agent.runtime` | `go` | kagent runtime |
| `modelConfig.name` | `default-model-config` | Admin-provisioned ModelConfig, same namespace, referenced by name |
| `skills.refs` / `skills.gitRefs` | `[]` | kagent-native skills (OCI images / git repos for dev iteration) |
| `muster.*` | shared gateway | Server reference, `allowedHeaders`, optional `toolNames`, STS well-known URI |
| `extraTools` | `[]` | Additional raw kagent tool entries |
| `replicas`, `resources`, `nodeSelector`, `tolerations` | sane defaults | Runtime knobs |
| `labels` / `annotations` | `{}` | Merged over the standard metadata set |
| `extraAgentSpec` | `{}` | Escape hatch: deep-merged over the curated spec (wins on conflict), so any kagent `Agent` field stays reachable |

`values.schema.json` encodes the curated contract, so bad values fail with a
legible error before anything hits the cluster.

Upgrades are values changes plus a re-apply; uninstalling the release removes
the agent. Pin the chart version for reproducibility.
