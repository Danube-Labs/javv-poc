{{/* the name every resource starts with: the release, plus "javv-scanner" unless the release has it */}}
{{- define "javv-scanner.fullname" -}}
{{- if contains "javv-scanner" .Release.Name -}}
{{- .Release.Name | trunc 36 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-javv-scanner" .Release.Name | trunc 36 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "javv-scanner.labels" -}}
app.kubernetes.io/name: javv-scanner
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* the scanners and their values, in a fixed order */}}
{{- define "javv-scanner.scanners" -}}
{{- list "trivy" "grype" | toJson -}}
{{- end -}}

{{/* takes (dict "root" $ "name" "trivy"): the image, by digest when one is given */}}
{{- define "javv-scanner.image" -}}
{{- $i := (index .root.Values .name).image -}}
{{- if $i.digest -}}
{{- printf "%s@%s" $i.repository $i.digest -}}
{{- else -}}
{{- printf "%s:%s" $i.repository $i.tag -}}
{{- end -}}
{{- end -}}

{{/* takes (dict "root" $ "name" "trivy"): the Secret holding that scanner's token */}}
{{- define "javv-scanner.tokenSecret" -}}
{{- (index .root.Values .name).token.existingSecret | default (printf "%s-%s-token" (include "javv-scanner.fullname" .root) .name) -}}
{{- end -}}

{{/* takes (dict "root" $ "name" "trivy"): that scanner's vuln-DB cache claim */}}
{{- define "javv-scanner.claim" -}}
{{- (index .root.Values .name).vulnDb.existingClaim | default (printf "%s-%s-vulndb" (include "javv-scanner.fullname" .root) .name) -}}
{{- end -}}

{{/* the ServiceAccount the scanners use; cluster-wide RBAC names add the namespace */}}
{{- define "javv-scanner.serviceAccount" -}}
{{- include "javv-scanner.fullname" . -}}
{{- end -}}
{{- define "javv-scanner.clusterName" -}}
{{- printf "%s-%s" .Release.Namespace (include "javv-scanner.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* takes the scanner's name: the vendor variables that keep the scan itself from updating its DB */}}
{{- define "javv-scanner.noUpdate" -}}
{{- if eq . "trivy" }}
- name: TRIVY_SKIP_DB_UPDATE
  value: "true"
- name: TRIVY_SKIP_JAVA_DB_UPDATE
  value: "true"
# misconfig scans then use the checks built into the Trivy binary, never a bundle fetched mid-scan
- name: TRIVY_SKIP_CHECK_UPDATE
  value: "true"
{{- else }}
- name: GRYPE_DB_AUTO_UPDATE
  value: "false"
{{- end }}
{{- end -}}

{{/* takes (dict "root" $ "name" "trivy"): where the refresh pulls the DB from, when set */}}
{{- define "javv-scanner.dbSource" -}}
{{- $db := (index .root.Values .name).vulnDb -}}
{{- if eq .name "trivy" }}
{{- with $db.repository }}
- name: TRIVY_DB_REPOSITORY
  value: {{ . | quote }}
{{- end }}
{{- with $db.javaRepository }}
- name: TRIVY_JAVA_DB_REPOSITORY
  value: {{ . | quote }}
{{- end }}
{{- else }}
{{- with $db.updateUrl }}
- name: GRYPE_DB_UPDATE_URL
  value: {{ . | quote }}
{{- end }}
{{- end }}
{{- end -}}

{{/* takes (dict "root" $ "name" "trivy"): the container that refreshes that scanner's vuln DB in
its cache volume, from the source in vulnDb, with the scanner's own image (so the DB schema it
fetches is the one that scanner reads, D41). The run's init container and the install's Job. */}}
{{- define "javv-scanner.refreshContainer" -}}
{{- $s := index .root.Values .name -}}
- name: refresh-vulndb
  image: {{ include "javv-scanner.image" . | quote }}
  imagePullPolicy: {{ $s.image.pullPolicy }}
  command: ["sh", "-c", {{ .root.Files.Get "files/refresh-vulndb.sh" | quote }}]
  {{- $source := include "javv-scanner.dbSource" . | trim }}
  {{- if or $source $s.extraEnv }}
  env:
    {{- with $source }}
    {{- . | nindent 4 }}
    {{- end }}
    {{- with $s.extraEnv }}
    {{- toYaml . | nindent 4 }}
    {{- end }}
  {{- end }}
  securityContext:
    {{- toYaml .root.Values.securityContext | nindent 4 }}
  {{- with $s.resources }}
  resources:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  volumeMounts:
    - name: vulndb
      mountPath: /var/cache/javv
    - name: tmp
      mountPath: /tmp
{{- end -}}
