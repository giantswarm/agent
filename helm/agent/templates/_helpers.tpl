{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Technical name of the agent: the Agent and its RemoteMCPServer. Defaults to
the release name.
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
Annotations of the Agent: ui.giantswarm.io/display-name,
ui.giantswarm.io/icon-url and ui.giantswarm.io/tags from agent.displayName /
agent.iconUrl / agent.tags (when set), next to .Values.annotations. Those three
keys are refused in .Values.annotations, where they would skip the schema of
the agent.* values. Empty when there is nothing to render.
*/}}
{{- define "agent.annotations" -}}
{{- $reserved := dict "ui.giantswarm.io/display-name" "agent.displayName" "ui.giantswarm.io/icon-url" "agent.iconUrl" "ui.giantswarm.io/tags" "agent.tags" -}}
{{- range $key, $value := $reserved -}}
{{- if hasKey $.Values.annotations $key -}}
{{- fail (printf "annotations[%q] is set by the chart: use %s" $key $value) -}}
{{- end -}}
{{- end -}}
{{- $annotations := deepCopy .Values.annotations -}}
{{- with .Values.agent.displayName -}}
{{- $_ := set $annotations "ui.giantswarm.io/display-name" . -}}
{{- end -}}
{{- with .Values.agent.iconUrl -}}
{{- $_ := set $annotations "ui.giantswarm.io/icon-url" . -}}
{{- end -}}
{{- with .Values.agent.tags -}}
{{- $_ := set $annotations "ui.giantswarm.io/tags" (join "," .) -}}
{{- end -}}
{{- toYaml $annotations -}}
{{- end -}}

{{/*
Resolve and validate the agent's tool list. `tools` (selector strings or
one-key objects {selector: Allow|Ask|Block}) replaces the deprecated `toolset`
(selector strings); both set fails. Prints the effective selectors, settings
stripped, as a JSON array; prints nothing when neither is set (implicit full
access). Settings and `default` are read by agent-manager from the release
values and render nothing.

Selectors are preset:<name>, server:<name>, workflow:<name> or tool:<name>.
An empty list is refused so it can never silently mean full access; more than
128 selectors (`tools`: 32) is refused (define a preset instead);
toolset:<name> is reserved for shared toolsets; label: exists only inside
presets. `tools` also refuses a duplicated selector, preset:none next to other
entries or with a setting (or `default`), and muster.requireApproval together
with any setting. Fails the render with the offending value.
*/}}
{{- define "agent.tools.resolve" -}}
{{- $name := "toolset" -}}
{{- $items := .Values.toolset -}}
{{- if not (kindIs "invalid" .Values.tools) -}}
  {{- if not (kindIs "invalid" .Values.toolset) -}}
    {{- fail "tools and toolset are both set: use tools only (toolset is deprecated)" -}}
  {{- end -}}
  {{- $name = "tools" -}}
  {{- $items = .Values.tools -}}
{{- end -}}
{{- $settings := false -}}
{{- if not (kindIs "invalid" .Values.default) -}}
  {{- if not (has .Values.default (list "Allow" "Ask" "Block")) -}}
    {{- fail (printf "default %v is invalid: expected Allow, Ask or Block (case-sensitive)" .Values.default) -}}
  {{- end -}}
  {{- $settings = true -}}
{{- end -}}
{{- $selectors := list -}}
{{- if not (kindIs "invalid" $items) -}}
  {{- if not (kindIs "slice" $items) -}}
    {{- fail (printf "%s must be a list of selector strings, got %s" $name (kindOf $items)) -}}
  {{- end -}}
  {{- if eq (len $items) 0 -}}
    {{- fail (printf "%s is empty: an agent without tools declares %s: [\"preset:none\"]; leave %s unset for implicit full access to everything the gateway exposes" $name $name $name) -}}
  {{- end -}}
  {{- if and (eq $name "tools") (gt (len $items) 32) -}}
    {{- fail (printf "tools has %d items, above the limit of 32: define a preset (muster toolsetPresets) and select it with preset:<name>" (len $items)) -}}
  {{- end -}}
  {{- range $items -}}
    {{- $sel := . -}}
    {{- if and (eq $name "tools") (kindIs "map" .) -}}
      {{- if ne (len .) 1 -}}
        {{- fail (printf "tools item %v must have exactly one key (a selector), got %d" . (len .)) -}}
      {{- end -}}
      {{- range $k, $v := . -}}
        {{- $sel = $k -}}
        {{- if not (has $v (list "Allow" "Ask" "Block")) -}}
          {{- fail (printf "tools entry %q has the setting %v: expected Allow, Ask or Block (case-sensitive)" $k $v) -}}
        {{- end -}}
      {{- end -}}
      {{- $settings = true -}}
    {{- end -}}
    {{- if not (kindIs "string" $sel) -}}
      {{- fail (printf "%s selector %v must be a string" $name $sel) -}}
    {{- end -}}
    {{- if hasPrefix "toolset:" $sel -}}
      {{- fail (printf "%s selector %q: toolset:<name> is reserved for shared toolsets" $name $sel) -}}
    {{- end -}}
    {{- if hasPrefix "label:" $sel -}}
      {{- fail (printf "%s selector %q: label: selectors are allowed inside presets only" $name $sel) -}}
    {{- end -}}
    {{- if not (regexMatch `^(preset|server|workflow|tool):[^\s,]+$` $sel) -}}
      {{- fail (printf "%s selector %q is invalid: expected preset:<name>, server:<name>, workflow:<name> or tool:<name> (exact name, no whitespace or commas)" $name $sel) -}}
    {{- end -}}
    {{- if and (eq $name "tools") (has $sel $selectors) -}}
      {{- fail (printf "tools selector %q is listed more than once: a selector appears once, with or without a setting" $sel) -}}
    {{- end -}}
    {{- $selectors = append $selectors $sel -}}
  {{- end -}}
  {{- $bytes := len (join "," $selectors) -}}
  {{- if gt $bytes 8192 -}}
    {{- fail (printf "%s encodes to %d bytes, above the inline limit of 8192: define a preset (muster toolsetPresets) and select it with preset:<name>" $name $bytes) -}}
  {{- end -}}
  {{- if and (eq $name "tools") (has "preset:none" $selectors) -}}
    {{- if gt (len $selectors) 1 -}}
      {{- fail "tools: preset:none cannot be combined with other entries: a chat-only agent declares tools: [\"preset:none\"]" -}}
    {{- end -}}
    {{- if $settings -}}
      {{- fail "tools: preset:none cannot carry a setting (Allow, Ask or Block) and has no default: a chat-only agent has no tools to approve" -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- if and $settings .Values.muster.requireApproval -}}
  {{- fail "muster.requireApproval is deprecated and cannot be combined with tool approval settings (tools entries with Allow/Ask/Block, default): remove muster.requireApproval and set default: Ask" -}}
{{- end -}}
{{- if $selectors -}}{{ toJson $selectors }}{{- end -}}
{{- end -}}

{{/*
The agent's approval settings as the X-Muster-Tool-Approval header value:
"<selector>=<Setting>" per tools entry with a setting, then "default=<Setting>",
joined by commas; empty without settings. muster applies it to requests that
no Session binding with agent-manager's settings covers (Sessions not started
through agent-manager): it carries no grants, so it can only make tools
stricter than their connectors' settings.
*/}}
{{- define "agent.tools.approvalHeader" -}}
{{- $parts := list -}}
{{- if not (kindIs "invalid" .Values.tools) -}}
  {{- range .Values.tools -}}
    {{- if kindIs "map" . -}}
      {{- range $k, $v := . -}}
        {{- $parts = append $parts (printf "%s=%s" $k $v) -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- if not (kindIs "invalid" .Values.default) -}}
  {{- $parts = append $parts (printf "default=%s" .Values.default) -}}
{{- end -}}
{{- join "," $parts -}}
{{- end -}}

{{/*
Validate the tool list (see agent.tools.resolve); prints nothing.
*/}}
{{- define "agent.toolset.validate" -}}
{{- $_ := include "agent.tools.resolve" . -}}
{{- end -}}

{{/*
"true" when the tool list is exactly ["preset:none"]: the agent has no tools,
so neither the RemoteMCPServer nor the muster binding is rendered.
*/}}
{{- define "agent.toolset.isNone" -}}
{{- if eq (include "agent.tools.resolve" .) "[\"preset:none\"]" -}}true{{- end -}}
{{- end -}}

{{/*
The X-Muster-Toolset header value: the selectors (settings stripped) joined by
"," (no spaces). Empty when neither tools nor toolset is set.
*/}}
{{- define "agent.toolset.header" -}}
{{- with include "agent.tools.resolve" . -}}{{ join "," (fromJsonArray .) }}{{- end -}}
{{- end -}}

{{/*
"true" when the agent is bound to muster: muster.enabled and the tool list is
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

{{- /*
agent.systemPrompt is systemMessage followed by the sections of
agent.platformPrompt. A network access note inside systemMessage (a line that
is the note's heading, and the paragraph after it up to the next blank line)
is replaced by the chart's: the prompt carries the note once, in the chart's
wording, whether or not agent.platformPrompt.egressNote is set.
*/ -}}
{{- define "agent.systemPrompt" -}}
{{- $prompt := .Values.agent.systemMessage -}}
{{- $egressNote := dig "platformPrompt" "egressNote" false .Values.agent -}}
{{- $own := regexReplaceAll `(?m)\s*^[ \t]*## Network access \(set by the platform\)[ \t]*\r?$(?:\n[ \t]*\r?$)*(?:\n[^\r\n]*\S[^\r\n]*\r?$)*` $prompt "" -}}
{{- if ne $own $prompt -}}
{{- $prompt = regexReplaceAll `\A(?:[ \t]*\r?\n)+` $own "" -}}
{{- $egressNote = true -}}
{{- end -}}
{{- if $egressNote -}}
{{- $prompt = regexReplaceAll `\s+\z` $prompt "" -}}
{{- $note := include "agent.egressNote" . -}}
{{- $prompt = ternary $note (printf "%s\n\n%s" $prompt $note) (eq $prompt "") -}}
{{- end -}}
{{- regexReplaceAll `\n+\z` $prompt "" -}}
{{- end -}}

{{- /*
agent.egressNote tells a coding agent what its sandbox reaches, so a refused
request reads as policy rather than as an outage. A Session's toolchains bring
origins of their own, which differ per Session, so the note names them by
place.
*/ -}}
{{- define "agent.egressNote" -}}
## Network access (set by the platform)

Besides your model and your tools, your sandbox reaches only {{ with .Values.agent.egress }}these origins: {{ join ", " . }}, and {{ end }}the registries of the toolchains mounted under /opt/kagent/tools. A request to any other host is refused by the egress policy and shows up as a failed command or tool call (connection refused, reset or 403). It is not transient: do not retry it or work around it; say which host the task needs.
{{- end -}}

{{- /*
agent.egress.validate mirrors the Agent CRD's rule for spec.egress (HTTP(S)
origins and tls:// origins with a port) so a bad origin fails the render naming
the entry, before the API server does.
*/ -}}
{{- define "agent.egress.validate" -}}
{{- range $i, $origin := .Values.agent.egress -}}
{{- if ne (kindOf $origin) "string" -}}
{{- fail (printf "agent.egress[%d] must be a string, got %s" $i (kindOf $origin)) -}}
{{- end -}}
{{- if not (regexMatch `^(https?://(\*\.([a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?\.)+|([a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?\.)*)[a-z]([-a-z0-9]{0,61}[a-z0-9])?(:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))?|tls://(\*\.([a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?\.)+|([a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?\.)*)[a-z]([-a-z0-9]{0,61}[a-z0-9])?:([1-9][0-9]{0,3}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5]))$` $origin) -}}
{{- fail (printf "agent.egress[%d] %q is not an egress origin: expected http(s)://<host>[:port] or tls://<host>:<port> with no path, the host optionally starting with a *. wildcard label over at least two labels" $i $origin) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Validate the skills beyond what the values schema can express: a skill name is
enabled once across skills[] and every plugin's selection, which the Harness
refuses otherwise. Everything else (exactly one of git/oci, full commit id,
digest-pinned image, relative path) is the schema's job. Fails the render
naming the entry.
*/}}
{{- define "agent.skills.validate" -}}
{{- $seen := dict -}}
{{- range $i, $skill := .Values.skills -}}
  {{- if hasKey $seen $skill.name -}}
    {{- fail (printf "skills[%d].name %q is already used by %s: skill names must be unique" $i $skill.name (get $seen $skill.name)) -}}
  {{- end -}}
  {{- $_ := set $seen $skill.name (printf "skills[%d]" $i) -}}
{{- end -}}
{{- range $i, $plugin := .Values.plugins -}}
  {{- range $j, $name := $plugin.skills -}}
    {{- if hasKey $seen $name -}}
      {{- fail (printf "plugins[%d].skills[%d] %q is already used by %s: skill names must be unique" $i $j $name (get $seen $name)) -}}
    {{- end -}}
    {{- $_ := set $seen $name (printf "plugins[%d].skills[%d]" $i $j) -}}
  {{- end -}}
{{- end -}}
{{- end -}}

{{/*
One immutable artifact source {git|oci, path} from a value entry {git|oci,
path}. Context: dict "entry", "field" (the value path, for the failure
message) and "credential" (skillsGitAuthSecretRef.name). With a credential,
every git source carries credentialRef {name, key: token}; the CRD admits a
credential on an https URL only, so a plain http source fails the render here,
naming the entry.
*/}}
{{- define "agent.artifactSource" -}}
{{- $entry := .entry -}}
{{- with $entry.git }}
git:
  url: {{ .url | quote }}
  commit: {{ .commit | quote }}
  {{- if $.credential }}
  {{- if not (hasPrefix "https://" .url) }}
    {{- fail (printf "%s: skillsGitAuthSecretRef.name is set, so every git source needs an https:// URL (the credential is offered to the source's https host only); got %q" $.field .url) }}
  {{- end }}
  credentialRef:
    name: {{ $.credential | quote }}
    key: token
  {{- end }}
{{- end }}
{{- with $entry.oci }}
oci: {{ . | quote }}
{{- end }}
{{- with $entry.path }}
path: {{ . | quote }}
{{- end }}
{{- end -}}

{{/*
The template's spec.skills: every value entry {name, git|oci, path} as a
{name, source: {git|oci, path}} item. With skillsGitAuthSecretRef.name set,
every git source carries credentialRef {name, key: token} (one credential fans
out to every git skill).
*/}}
{{- define "agent.skills" -}}
{{- $credential := (.Values.skillsGitAuthSecretRef | default dict).name -}}
{{- range $i, $skill := .Values.skills }}
- name: {{ $skill.name | quote }}
  source:
    {{- include "agent.artifactSource" (dict "entry" $skill "field" (printf "skills[%d] %q" $i $skill.name) "credential" $credential) | nindent 4 }}
{{- end }}
{{- end -}}

{{/*
The template's spec.plugins: every value entry {git|oci, path, skills} as a
{source: {git|oci, path}, skills} item, skills only when the entry selects
some. The same credential as the skills reaches every git plugin.
*/}}
{{- define "agent.plugins" -}}
{{- $credential := (.Values.skillsGitAuthSecretRef | default dict).name -}}
{{- range $i, $plugin := .Values.plugins }}
- source:
    {{- include "agent.artifactSource" (dict "entry" $plugin "field" (printf "plugins[%d]" $i) "credential" $credential) | nindent 4 }}
  {{- with $plugin.skills }}
  skills:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
{{- end -}}

{{/*
The curated template spec (the Agent's spec.template) built from the values
contract.
*/}}
{{- define "agent.curatedSpec" -}}
{{- include "agent.skills.validate" . -}}
{{- with .Values.agent.description }}
description: {{ . | quote }}
{{- end }}
{{- with .Values.modelConfig.name }}
modelConfig:
  name: {{ . | quote }}
{{- end }}
systemPrompt: {{ include "agent.systemPrompt" . | toJson }}
{{- with .Values.skills }}
skills:
  {{- include "agent.skills" $ | nindent 2 }}
{{- end }}
{{- with .Values.plugins }}
plugins:
  {{- include "agent.plugins" $ | nindent 2 }}
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
The final template spec: extraAgentSpec deep-merged over the curated spec,
with the escape hatch winning on conflicts.
*/}}
{{- define "agent.spec" -}}
{{- $curated := fromYaml (include "agent.curatedSpec" .) -}}
{{- toYaml (mustMergeOverwrite $curated (deepCopy .Values.extraAgentSpec)) -}}
{{- end -}}
