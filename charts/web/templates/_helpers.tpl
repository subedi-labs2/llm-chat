{{- define "llm-chat-web.fullname" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "llm-chat-web.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "llm-chat-web.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "llm-chat-web.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | trunc 63 | quote }}
app.kubernetes.io/component: web
app.kubernetes.io/part-of: llm-chat
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "llm-chat-web.image" -}}
{{- with .Values.image }}
{{- if not (or .tag .digest) }}{{ fail "image.tag or image.digest is required" }}{{ end }}
{{- .repository }}{{ with .tag }}:{{ . }}{{ end }}{{ with .digest }}@{{ . }}{{ end }}
{{- end }}
{{- end }}
