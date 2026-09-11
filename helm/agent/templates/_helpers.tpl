{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Technical name of the agent: the AgentTemplate and its RemoteMCPServer.
Defaults to the release name.
*/}}
{{- define "agent.name" -}}
{{- default .Release.Name .Values.agent.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
The helm.sh/chart label: <name>-<version> as a valid label value. A label is at
most 63 characters and must end on an alphanumeric: Helm's `+` build metadata
(helm-controller appends the OCI digest to every chart version it installs,
`1.0.0+ed59d4befc7e`) becomes `_`, and after the cut every trailing `-`, `.`
and `_` goes — a branch build's long prerelease version
(`0.6.2-dev.<branch>.<date>.<time>.h<sha>+<digest>`) made the cut land on the
`_` once, and the apiserver rejected every object of the release.
*/}}
{{- define "chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimAll "-._" -}}
{{- end -}}

{{/*
The app.kubernetes.io/version label: the chart version made a valid label
value the same way (this chart has no image of its own; the chart version is
what identifies a release).
*/}}
{{- define "version" -}}
{{- .Chart.Version | replace "+" "_" | trunc 63 | trimAll "-._" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "labels.common" -}}
app: {{ include "name" . | quote }}
{{ include "labels.selector" . }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
app.kubernetes.io/version: {{ include "version" . | quote }}
application.giantswarm.io/team: {{ index .Chart.Annotations "io.giantswarm.application.team" | quote }}
helm.sh/chart: {{ include "chart" . | quote }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "labels.selector" -}}
app.kubernetes.io/name: {{ include "name" . | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end -}}

{{/*
Labels of every object the chart renders: the common set with .Values.labels
merged over it (the extra labels win).
*/}}
{{- define "agent.labels" -}}
{{- toYaml (mustMergeOverwrite (fromYaml (include "labels.common" .)) (deepCopy .Values.labels)) -}}
{{- end -}}

{{/*
Labels of the AgentTemplate: the shared set plus the Harness admission label
agent-platform.giantswarm.io/harness, valued by agent.harness. Extra labels
merge over it, so a deliberately different admission label is still one value
away.
*/}}
{{- define "agenttemplate.labels" -}}
{{- $labels := dict "agent-platform.giantswarm.io/harness" .Values.agent.harness -}}
{{- toYaml (mustMergeOverwrite $labels (fromYaml (include "agent.labels" .))) -}}
{{- end -}}

{{/*
Labels of the RemoteMCPServer: the shared set plus the discovery opt-out
kagent.dev/discovery=disabled unless muster.discovery.enabled is true. The
opt-out is the chart's decision, so it wins over an extra label of the same
name.
*/}}
{{- define "remotemcpserver.labels" -}}
{{- $labels := fromYaml (include "agent.labels" .) -}}
{{- if not .Values.muster.discovery.enabled -}}
{{- $_ := set $labels "kagent.dev/discovery" "disabled" -}}
{{- end -}}
{{- toYaml $labels -}}
{{- end -}}

{{/*
Annotations of the AgentTemplate: ui.giantswarm.io/display-name and
ui.giantswarm.io/icon-url from agent.displayName / agent.iconUrl (when set),
next to .Values.annotations. Empty when there is nothing to render.
*/}}
{{- define "agenttemplate.annotations" -}}
{{- $annotations := deepCopy .Values.annotations -}}
{{- with .Values.agent.displayName -}}
{{- $_ := set $annotations "ui.giantswarm.io/display-name" . -}}
{{- end -}}
{{- with .Values.agent.iconUrl -}}
{{- $_ := set $annotations "ui.giantswarm.io/icon-url" . -}}
{{- end -}}
{{- toYaml $annotations -}}
{{- end -}}

{{/*
Validate the toolset: a list of selector strings, each preset:<name>,
server:<name>, workflow:<name> or tool:<name>. Unset means implicit full
access (no header); an empty list is refused so it can never silently mean
full access; more than 32 selectors is refused (define a preset instead);
toolset:<name> is reserved for shared toolsets; label: exists only inside
presets. Fails the render with the offending selector.
*/}}
{{- define "agent.toolset.validate" -}}
{{- $ts := .Values.toolset -}}
{{- if not (kindIs "invalid" $ts) -}}
  {{- if not (kindIs "slice" $ts) -}}
    {{- fail (printf "toolset must be a list of selector strings, got %s" (kindOf $ts)) -}}
  {{- end -}}
  {{- if eq (len $ts) 0 -}}
    {{- fail "toolset is empty: an agent without tools declares toolset: [\"preset:none\"]; leave toolset unset for implicit full access to everything the gateway exposes" -}}
  {{- end -}}
  {{- if gt (len $ts) 32 -}}
    {{- fail (printf "toolset has %d selectors, above the inline cap of 32: define a preset (muster toolsetPresets) and select it with preset:<name>" (len $ts)) -}}
  {{- end -}}
  {{- range $ts -}}
    {{- if not (kindIs "string" .) -}}
      {{- fail (printf "toolset selector %v must be a string" .) -}}
    {{- end -}}
    {{- if hasPrefix "toolset:" . -}}
      {{- fail (printf "toolset selector %q: toolset:<name> is reserved for shared toolsets" .) -}}
    {{- end -}}
    {{- if hasPrefix "label:" . -}}
      {{- fail (printf "toolset selector %q: label: selectors are allowed inside presets only" .) -}}
    {{- end -}}
    {{- if not (regexMatch `^(preset|server|workflow|tool):[^\s,]+$` .) -}}
      {{- fail (printf "toolset selector %q is invalid: expected preset:<name>, server:<name>, workflow:<name> or tool:<name> (exact name, no whitespace or commas)" .) -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- end -}}

{{/*
"true" when the toolset is exactly ["preset:none"]: the agent has no tools,
so neither the RemoteMCPServer nor the muster binding is rendered.
*/}}
{{- define "agent.toolset.isNone" -}}
{{- $ts := .Values.toolset -}}
{{- if and (kindIs "slice" $ts) (eq (len $ts) 1) (eq (index $ts 0) "preset:none") -}}true{{- end -}}
{{- end -}}

{{/*
The X-Muster-Toolset header value: the selectors joined by "," (no spaces).
Empty when the toolset is unset.
*/}}
{{- define "agent.toolset.header" -}}
{{- if kindIs "slice" .Values.toolset -}}{{ join "," .Values.toolset }}{{- end -}}
{{- end -}}

{{/*
"true" when the agent is bound to muster: muster.enabled and the toolset is
not exactly ["preset:none"]. Gates the RemoteMCPServer and the binding alike.
*/}}
{{- define "agent.musterBinding" -}}
{{- include "agent.toolset.validate" . -}}
{{- if and .Values.muster.enabled (not (include "agent.toolset.isNone" .)) -}}true{{- end -}}
{{- end -}}

{{/*
Description of the agent's RemoteMCPServer: names the agent and its toolset.
*/}}
{{- define "remotemcpserver.description" -}}
{{- $toolset := include "agent.toolset.header" . -}}
{{- printf "muster MCP gateway of agent %s (%s)" (include "agent.name" .) (ternary (printf "toolset %s" $toolset) "implicit full access" (ne $toolset "")) -}}
{{- end -}}

{{/*
Validate the skills beyond what the values schema can express: names are
unique. Everything else (exactly one of git/oci, full commit id, digest-pinned
image, relative path) is the schema's job. Fails the render naming the entry.
*/}}
{{- define "agent.skills.validate" -}}
{{- $seen := dict -}}
{{- range $i, $skill := .Values.skills -}}
  {{- if hasKey $seen $skill.name -}}
    {{- fail (printf "skills[%d].name %q is already used by skills[%v]: skill names must be unique" $i $skill.name (get $seen $skill.name)) -}}
  {{- end -}}
  {{- $_ := set $seen $skill.name $i -}}
{{- end -}}
{{- end -}}

{{/*
The AgentTemplate's spec.skills: every value entry {name, git|oci, path} as a
{name, source: {git|oci, path}} item.
*/}}
{{- define "agent.skills" -}}
{{- include "agent.skills.validate" . -}}
{{- range .Values.skills }}
- name: {{ .name | quote }}
  source:
    {{- with .git }}
    git:
      url: {{ .url | quote }}
      commit: {{ .commit | quote }}
    {{- end }}
    {{- with .oci }}
    oci: {{ . | quote }}
    {{- end }}
    {{- with .path }}
    path: {{ . | quote }}
    {{- end }}
{{- end }}
{{- end -}}

{{/*
The curated AgentTemplate spec built from the values contract.
*/}}
{{- define "agent.curatedSpec" -}}
{{- with .Values.agent.description }}
description: {{ . | quote }}
{{- end }}
modelConfig:
  name: {{ .Values.modelConfig.name | quote }}
systemPrompt: |-
  {{- .Values.agent.systemMessage | nindent 2 }}
{{- with .Values.skills }}
skills:
  {{- include "agent.skills" $ | nindent 2 }}
{{- end }}
{{- $muster := include "agent.musterBinding" . -}}
{{- if or $muster .Values.extraTools }}
tools:
  {{- if $muster }}
  - mcp:
      server:
        kind: RemoteMCPServer
        name: {{ include "agent.name" . | quote }}
      {{- with .Values.muster.tools }}
      tools:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- if .Values.muster.requireApproval }}
      requireApproval: true
      {{- end }}
  {{- end }}
  {{- with .Values.extraTools }}
  {{- toYaml . | nindent 2 }}
  {{- end }}
{{- end }}
{{- end -}}

{{/*
The final AgentTemplate spec: extraAgentSpec deep-merged over the curated
spec, with the escape hatch winning on conflicts.
*/}}
{{- define "agent.spec" -}}
{{- $curated := fromYaml (include "agent.curatedSpec" .) -}}
{{- toYaml (mustMergeOverwrite $curated (deepCopy .Values.extraAgentSpec)) -}}
{{- end -}}
