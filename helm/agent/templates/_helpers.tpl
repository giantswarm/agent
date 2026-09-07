{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Technical name of the agent. Defaults to the release name.
*/}}
{{- define "agent.name" -}}
{{- default .Release.Name .Values.agent.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "labels.common" -}}
app: {{ include "name" . | quote }}
{{ include "labels.selector" . }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
app.kubernetes.io/version: {{ .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" | quote }}
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
so the muster tool entry is omitted entirely.
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
The curated Agent spec built from the values contract.
*/}}
{{- define "agent.curatedSpec" -}}
{{- include "agent.toolset.validate" . -}}
{{- $musterTool := and .Values.muster.enabled (not (include "agent.toolset.isNone" .)) -}}
type: Declarative
{{- with .Values.agent.description }}
description: {{ . | quote }}
{{- end }}
{{- with .Values.agent.iconUrl }}
iconUrl: {{ . | quote }}
{{- end }}
{{- if or .Values.skills.refs .Values.skills.gitRefs }}
skills:
  {{- with .Values.skills.refs }}
  refs:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with .Values.skills.gitRefs }}
  gitRefs:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  {{- with .Values.skills.gitAuthSecretRef.name }}
  gitAuthSecretRef:
    name: {{ . | quote }}
  {{- end }}
{{- end }}
declarative:
  runtime: {{ .Values.agent.runtime }}
  modelConfig: {{ .Values.modelConfig.name }}
  systemMessage: |-
    {{- .Values.agent.systemMessage | nindent 4 }}
  {{- if or $musterTool .Values.extraTools }}
  tools:
    {{- if $musterTool }}
    - type: McpServer
      {{- with include "agent.toolset.header" . }}
      headersFrom:
        - name: X-Muster-Toolset
          value: {{ . | quote }}
      {{- end }}
      mcpServer:
        kind: {{ .Values.muster.serverRef.kind }}
        apiGroup: {{ .Values.muster.serverRef.apiGroup }}
        name: {{ .Values.muster.serverRef.name }}
        namespace: {{ .Values.muster.serverRef.namespace }}
        {{- with .Values.muster.allowedHeaders }}
        allowedHeaders:
          {{- toYaml . | nindent 10 }}
        {{- end }}
        {{- with .Values.muster.toolNames }}
        toolNames:
          {{- toYaml . | nindent 10 }}
        {{- end }}
    {{- end }}
    {{- with .Values.extraTools }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
  {{- end }}
  deployment:
    replicas: {{ .Values.replicas }}
    {{- if .Values.muster.enabled }}
    env:
      - name: KAGENT_PROPAGATE_TOKEN
        value: "true"
      {{- with .Values.muster.stsWellKnownUri }}
      - name: STS_WELL_KNOWN_URI
        value: {{ . | quote }}
      {{- end }}
    {{- end }}
    {{- with .Values.resources }}
    resources:
      {{- toYaml . | nindent 6 }}
    {{- end }}
    {{- with .Values.nodeSelector }}
    nodeSelector:
      {{- toYaml . | nindent 6 }}
    {{- end }}
    {{- with .Values.tolerations }}
    tolerations:
      {{- toYaml . | nindent 6 }}
    {{- end }}
{{- end -}}

{{/*
The final Agent spec: extraAgentSpec deep-merged over the curated spec,
with the escape hatch winning on conflicts.
*/}}
{{- define "agent.spec" -}}
{{- $curated := fromYaml (include "agent.curatedSpec" .) -}}
{{- toYaml (mustMergeOverwrite $curated (deepCopy .Values.extraAgentSpec)) -}}
{{- end -}}
