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
The curated Agent spec built from the values contract.
*/}}
{{- define "agent.curatedSpec" -}}
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
{{- end }}
declarative:
  runtime: {{ .Values.agent.runtime }}
  modelConfig: {{ .Values.modelConfig.name }}
  systemMessage: |-
    {{- .Values.agent.systemMessage | nindent 4 }}
  {{- if or .Values.muster.enabled .Values.extraTools }}
  tools:
    {{- if .Values.muster.enabled }}
    - type: McpServer
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
