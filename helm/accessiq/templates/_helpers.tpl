{{/*
Expand the name of the chart.
*/}}
{{- define "accessiq.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "accessiq.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "accessiq.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "accessiq.labels" -}}
helm.sh/chart: {{ include "accessiq.chart" . }}
{{ include "accessiq.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels.
*/}}
{{- define "accessiq.selectorLabels" -}}
app.kubernetes.io/name: {{ include "accessiq.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Namespace for rendered resources.
*/}}
{{- define "accessiq.namespace" -}}
{{- default .Release.Namespace .Values.namespace.name -}}
{{- end -}}

{{- define "accessiq.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "accessiq.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "accessiq.backendName" -}}
{{- printf "%s-backend" (include "accessiq.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "accessiq.frontendName" -}}
{{- printf "%s-frontend" (include "accessiq.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "accessiq.postgresqlName" -}}
{{- printf "%s-postgresql" (include "accessiq.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "accessiq.backendConfigMapName" -}}
{{- printf "%s-config" (include "accessiq.backendName" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "accessiq.frontendConfigMapName" -}}
{{- printf "%s-config" (include "accessiq.frontendName" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "accessiq.backendSecretName" -}}
{{- default (printf "%s-secret" (include "accessiq.backendName" .)) .Values.backend.secrets.existingSecret | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "accessiq.postgresqlSecretName" -}}
{{- default (printf "%s-secret" (include "accessiq.postgresqlName" .)) .Values.database.internal.auth.existingSecret | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "accessiq.databaseUrl" -}}
{{- if .Values.database.external.url -}}
{{- .Values.database.external.url -}}
{{- else if .Values.database.internal.enabled -}}
{{- printf "postgresql+psycopg://%s:%s@%s:%v/%s" .Values.database.internal.auth.username .Values.database.internal.auth.password (include "accessiq.postgresqlName" .) .Values.database.internal.service.port .Values.database.internal.auth.database -}}
{{- else -}}
{{- required "database.external.url is required when database.internal.enabled is false" .Values.database.external.url -}}
{{- end -}}
{{- end -}}

