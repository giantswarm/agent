# agent

Create a kagent agent on the Giant Swarm agentic platform from a small, curated values surface. One chart release renders exactly one Agent custom resource; model configuration, credentials and the muster gateway are platform-admin owned and only referenced by name.

**Homepage:** <https://github.com/giantswarm/agent>

## Source Code

* <https://github.com/giantswarm/agent>

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| agent | object | `{"description":"","displayName":"","name":"","runtime":"go","systemMessage":"You are a helpful agent.\n"}` | Identity and prompt of the agent. |
| agent.name | string | `""` | Technical resource name (DNS-1123). Defaults to the Helm release name. |
| agent.displayName | string | `""` | Human-friendly name, Unicode allowed. Rendered as the ui.giantswarm.io/display-name annotation on the Agent. Size-limited so it cannot become a description. |
| agent.description | string | `""` | Rendered into the Agent's spec.description. |
| agent.systemMessage | string | `"You are a helpful agent.\n"` | The agent's system prompt. |
| agent.runtime | string | `"go"` | kagent runtime for the agent. Mirrors the Agent CRD's spec.declarative.runtime enum. |
| modelConfig | object | `{"name":"default-model-config"}` | Which platform-admin-provisioned ModelConfig the agent uses, referenced by name. kagent resolves it in the agent's own namespace. The chart never creates or mutates a ModelConfig, and tenants never handle LLM credentials. |
| modelConfig.name | string | `"default-model-config"` | Name of the admin-provisioned ModelConfig in the agent's namespace. |
| skills | object | `{"gitRefs":[],"refs":[]}` | kagent-native skills, pulled by the skills-init container and mounted under /skills. Prefer immutable refs (image tag/digest, git tag/SHA) in long-lived installs; git branches are a development convenience. |
| skills.refs | list | `[]` | OCI skill image references, e.g. ["registry.example.io/skills/runbooks:1.4.0"] |
| skills.gitRefs | list | `[]` | Git repository references for development iteration. |
| muster | object | `{"allowedHeaders":["authorization"],"enabled":true,"serverRef":{"apiGroup":"kagent.dev","kind":"RemoteMCPServer","name":"muster","namespace":"agentic-platform"},"stsWellKnownUri":"http://muster.agentic-platform.svc.cluster.local:8090/.well-known/oauth-authorization-server","toolNames":[]}` | The platform's shared muster gateway, referenced cross-namespace. The RemoteMCPServer is admin-owned; its spec.allowedNamespaces must admit this agent's namespace. |
| muster.enabled | bool | `true` | Wire the shared muster gateway into the agent's tools. |
| muster.serverRef | object | `{"apiGroup":"kagent.dev","kind":"RemoteMCPServer","name":"muster","namespace":"agentic-platform"}` | Reference to the admin-owned RemoteMCPServer. |
| muster.serverRef.kind | string | `"RemoteMCPServer"` | Kind of the referenced resource. |
| muster.serverRef.apiGroup | string | `"kagent.dev"` | API group of the referenced resource. |
| muster.serverRef.name | string | `"muster"` | Name of the referenced resource. |
| muster.serverRef.namespace | string | `"agentic-platform"` | Namespace of the referenced resource. |
| muster.allowedHeaders | list | `["authorization"]` | HTTP headers forwarded to the gateway. |
| muster.toolNames | list | `[]` | Set to narrow the tool surface; leave empty for all tools. muster's tools are dynamic and no toolNames means no tool filter — the agent gets every tool the gateway exposes. |
| muster.stsWellKnownUri | string | `"http://muster.agentic-platform.svc.cluster.local:8090/.well-known/oauth-authorization-server"` | OAuth authorization server discovery URI of muster's STS, used to exchange the propagated caller token for a muster access token before tool calls. The default targets muster's in-cluster Service: the discovery document is served unauthenticated and carries absolute endpoint URLs, so it is identical on every installation. Override only for a non-standard muster deployment; set to "" to disable the exchange (propagate-only). |
| extraTools | list | `[]` | Additional raw kagent tool entries appended after the muster gateway. |
| replicas | int | `1` | Number of agent pod replicas. |
| resources | object | `{"limits":{"cpu":"1","memory":"512Mi"},"requests":{"cpu":"100m","memory":"256Mi"}}` | Compute resources of the agent deployment. |
| resources.requests | object | `{"cpu":"100m","memory":"256Mi"}` | Resource requests. |
| resources.requests.cpu | string | `"100m"` | CPU request. |
| resources.requests.memory | string | `"256Mi"` | Memory request. |
| resources.limits | object | `{"cpu":"1","memory":"512Mi"}` | Resource limits. |
| resources.limits.cpu | string | `"1"` | CPU limit. |
| resources.limits.memory | string | `"512Mi"` | Memory limit. |
| nodeSelector | object | `{}` | Node selector for agent pod scheduling. |
| tolerations | list | `[]` | Tolerations for agent pod scheduling. |
| labels | object | `{}` | Extra labels merged over the standard set, e.g. tenant/owner dimensions. |
| annotations | object | `{}` | Extra annotations merged next to the display-name annotation. |
| extraAgentSpec | object | `{}` | Escape hatch: deep-merged over the curated Agent spec (this wins), so any kagent Agent field is reachable when the curated surface omits something. |
