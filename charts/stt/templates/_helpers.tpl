{{- define "llm-chat-stt.fullname" -}}
{{- default .Release.Name .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "llm-chat-stt.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "llm-chat-stt.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "llm-chat-stt.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | trunc 63 | quote }}
app.kubernetes.io/component: stt
app.kubernetes.io/part-of: llm-chat
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "llm-chat-stt.image" -}}
{{- with .Values.image }}
{{- if not (or .tag .digest) }}{{ fail "image.tag or image.digest is required" }}{{ end }}
{{- .repository }}{{ with .tag }}:{{ . }}{{ end }}{{ with .digest }}@{{ . }}{{ end }}
{{- end }}
{{- end }}

{{- define "llm-chat-stt.claimName" -}}
{{- default (include "llm-chat-stt.fullname" .) .Values.persistence.existingClaim }}
{{- end }}
