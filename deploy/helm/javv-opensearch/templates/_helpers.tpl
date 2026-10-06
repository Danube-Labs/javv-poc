{{/*
Helpers shared by this chart's templates and the official chart's templated values (named
templates are global across a chart and its subcharts). Each takes the `opensearch.javv` block,
so it works from either side: here `.Values.opensearch.javv`, there `.Values.javv`.
*/}}

{{/* "true" when the node uses certificates of your own instead of the demo ones */}}
{{- define "javv-opensearch.ownCertificates" -}}
{{- if or .tls.existingSecret .tls.certManager.enabled -}}true{{- end -}}
{{- end -}}

{{/* the Secret holding the admin password; takes (dict "javv" <block> "Release" .Release) */}}
{{- define "javv-opensearch.adminSecret" -}}
{{- .javv.auth.existingSecret | default (printf "%s-javv-opensearch-admin" .Release.Name) -}}
{{- end -}}

{{/* the Secret holding javv's password (issue 729); takes (dict "javv" <block> "Release" .Release) */}}
{{- define "javv-opensearch.backendSecret" -}}
{{- .javv.backend.existingSecret | default (printf "%s-javv-opensearch-backend" .Release.Name) -}}
{{- end -}}

{{/* the Secret holding your certificate; takes (dict "javv" <block> "Release" .Release) */}}
{{- define "javv-opensearch.tlsSecret" -}}
{{- .javv.tls.existingSecret | default (printf "%s-javv-opensearch-tls" .Release.Name) -}}
{{- end -}}

{{/* the official chart's Service name, from its own helper */}}
{{- define "javv-opensearch.service" -}}
{{- include "opensearch.serviceName" (dict "Values" .Values.opensearch) -}}
{{- end -}}

{{- define "javv-opensearch.labels" -}}
app.kubernetes.io/name: javv-opensearch
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}
