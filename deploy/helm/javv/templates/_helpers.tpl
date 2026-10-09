{{/* the name every resource starts with: the release, plus "javv" unless the release has it */}}
{{- define "javv.fullname" -}}
{{- if contains "javv" .Release.Name -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-javv" .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "javv.labels" -}}
app.kubernetes.io/name: javv
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* selector labels; takes (dict "root" $ "component" "backend") */}}
{{- define "javv.selector" -}}
app.kubernetes.io/name: javv
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* the Secret with the secret key and the bootstrap admin password */}}
{{- define "javv.secretName" -}}
{{- .Values.secrets.existingSecret | default (printf "%s-secrets" (include "javv.fullname" .)) -}}
{{- end -}}

{{- define "javv.backendService" -}}
{{- printf "%s-backend" (include "javv.fullname" .) -}}
{{- end -}}

{{/* where the CA from opensearch.caSecret is mounted in the backend */}}
{{- define "javv.caDir" -}}/etc/javv/opensearch-ca{{- end -}}
