{{/* Names and labels shared by every template. */}}

{{- define "rad-shift.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* A component's resource name, e.g. rad-shift-backend. */}}
{{- define "rad-shift.name" -}}
{{- printf "%s-%s" (include "rad-shift.fullname" .root) .component | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* What a Service or Deployment selects on: never change these on a live
     release, a Deployment's selector is immutable. */}}
{{- define "rad-shift.selectorLabels" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "rad-shift.labels" -}}
{{ include "rad-shift.selectorLabels" . }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version }}
{{- end -}}

{{- define "rad-shift.image" -}}
{{- printf "%s:%s" .repository (required "an image tag is required" (toString .tag)) -}}
{{- end -}}

{{- define "rad-shift.dbHost" -}}
{{- if .Values.postgres.enabled -}}
{{- include "rad-shift.name" (dict "root" . "component" "postgres") -}}
{{- else -}}
{{- required "postgres.host is required when postgres.enabled is false" .Values.postgres.host -}}
{{- end -}}
{{- end -}}

{{/* Locked down: no root, no privilege escalation, no Linux capabilities,
     a read-only root filesystem (writes go to an emptyDir at /tmp). */}}
{{- define "rad-shift.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: [ALL]
{{- end -}}

{{- define "rad-shift.podSecurity" -}}
runAsNonRoot: true
runAsUser: {{ .uid }}
runAsGroup: {{ .uid }}
fsGroup: {{ .uid }}
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{/* The app image's settings: the ConfigMap, then the Secret. */}}
{{- define "rad-shift.appEnvFrom" -}}
envFrom:
  - configMapRef:
      name: {{ include "rad-shift.name" (dict "root" . "component" "config") }}
  - secretRef:
      name: {{ .Values.secretName }}
{{- end -}}

{{/* Pods restart when the settings they read change. */}}
{{- define "rad-shift.configChecksum" -}}
checksum/config: {{ include (print .Template.BasePath "/configmap.yaml") . | sha256sum }}
{{- end -}}

{{/* Waits for Postgres before the app starts, instead of crash-looping. */}}
{{- define "rad-shift.waitForPostgres" -}}
- name: wait-for-postgres
  image: {{ include "rad-shift.image" .Values.postgres.image }}
  # -U: without it pg_isready asks the OS for the current user's name, and
  # uid 1000 has none in this image, so it never even tries ("no attempt").
  command: ["sh", "-c", "until pg_isready -h \"$DB_HOST\" -p 5432 -U \"$DB_USER\" -t 2; do sleep 2; done"]
  env:
    - name: DB_HOST
      value: {{ include "rad-shift.dbHost" . }}
    - name: DB_USER
      value: {{ .Values.postgres.user | quote }}
  securityContext:
    {{- include "rad-shift.containerSecurity" . | nindent 4 }}
  resources:
    requests: {cpu: 10m, memory: 16Mi}
    limits: {memory: 64Mi}
{{- end -}}
