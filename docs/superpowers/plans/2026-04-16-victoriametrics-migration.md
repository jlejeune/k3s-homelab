# VictoriaMetrics Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace kube-prometheus-stack with VictoriaMetrics single-node + VMAgent + VMAlert + Alertmanager standalone, keeping Grafana as a debug backend and routing node alerts to Discord.

**Architecture:** VictoriaMetrics single-node stores metrics scraped by VMAgent (node-exporter + Traefik). VMAlert evaluates alerting rules and forwards to Alertmanager, which routes to Discord. Grafana keeps working unchanged by pointing its datasource to VictoriaMetrics instead of Prometheus. Migration is done in phases to avoid a hard cutover: new stack deployed in parallel, Grafana switched, then old stack removed.

**Tech Stack:** Kluctl + Kustomize, Helm (victoriametrics/victoria-metrics-* charts, prometheus-community/alertmanager, prometheus-community/prometheus-node-exporter), SOPS/Age for secrets.

---

## File Map

**Create:**
- `core/monitoring/victoria-metrics/helm-chart.yaml` — chart source
- `core/monitoring/victoria-metrics/helm-values.yaml` — retention 7d, 10Gi Longhorn
- `core/monitoring/victoria-metrics/kustomization.yaml`
- `core/monitoring/vmagent/helm-chart.yaml`
- `core/monitoring/vmagent/helm-values.yaml` — scrape node-exporter (k8s SD) + Traefik (static)
- `core/monitoring/vmagent/kustomization.yaml`
- `core/monitoring/vmalert/helm-chart.yaml`
- `core/monitoring/vmalert/helm-values.yaml` — 5 node alerting rules → Alertmanager
- `core/monitoring/vmalert/kustomization.yaml`
- `core/monitoring/alertmanager/helm-chart.yaml`
- `core/monitoring/alertmanager/helm-values.yaml` — Discord receiver, env var substitution
- `core/monitoring/alertmanager/secret.sops.yaml` — DISCORD_WEBHOOK_URL (SOPS-encrypted)
- `core/monitoring/alertmanager/kustomization.yaml`
- `core/monitoring/node-exporter/helm-chart.yaml`
- `core/monitoring/node-exporter/helm-values.yaml` — tolerations control-plane, fullnameOverride
- `core/monitoring/node-exporter/kustomization.yaml`

**Modify:**
- `core/monitoring/deployment.yaml` — replace kube-prometheus-stack with new components
- `core/monitoring/kustomization.yaml` — same
- `core/monitoring/grafana/helm-values.yaml` — datasource URL → VictoriaMetrics
- `apps/networking/traefik/ingresses.yaml` — replace prometheus IngressRoute with victoria-metrics

**Delete:**
- `core/monitoring/kube-prometheus-stack/` — entire directory

---

## Task 1: Deploy VictoriaMetrics single-node

**Files:**
- Create: `core/monitoring/victoria-metrics/helm-chart.yaml`
- Create: `core/monitoring/victoria-metrics/helm-values.yaml`
- Create: `core/monitoring/victoria-metrics/kustomization.yaml`
- Modify: `core/monitoring/deployment.yaml`
- Modify: `core/monitoring/kustomization.yaml`

- [ ] **Step 1: Check latest chart version**

```bash
helm repo add victoriametrics https://victoriametrics.github.io/helm-charts/
helm repo update
helm search repo victoriametrics/victoria-metrics-single
```

Note the latest chart version (e.g., `0.11.0`) for the next step.

- [ ] **Step 2: Create `core/monitoring/victoria-metrics/helm-chart.yaml`**

```yaml
---
helmChart:
  repo: https://victoriametrics.github.io/helm-charts/
  chartName: victoria-metrics-single
  chartVersion: "0.11.0"  # replace with version found in step 1
  releaseName: victoria-metrics-single
  namespace: monitoring
```

- [ ] **Step 3: Create `core/monitoring/victoria-metrics/helm-values.yaml`**

```yaml
---
server:
  retentionPeriod: 7d
  persistentVolume:
    enabled: true
    storageClass: longhorn
    size: 10Gi
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 1000m
      memory: 1Gi
  extraArgs:
    envflag.enable: "true"
    envflag.prefix: VM_
    loggerFormat: json
```

- [ ] **Step 4: Create `core/monitoring/victoria-metrics/kustomization.yaml`**

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - helm-rendered.yaml
```

- [ ] **Step 5: Add victoria-metrics to `core/monitoring/deployment.yaml`**

Replace the full file:

```yaml
---
vars:
  - clusterSecret:
      name: cluster-secrets
      namespace: default
      key: SECRET_DOMAIN
      targetPath: SECRET_DOMAIN

deployments:
  - path: victoria-metrics
  - path: grafana
  - path: kube-prometheus-stack
  - path: uptime-kuma
  - path: maintenant
```

- [ ] **Step 6: Add victoria-metrics to `core/monitoring/kustomization.yaml`**

Replace the full file:

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - victoria-metrics
  - grafana
  - kube-prometheus-stack
  - uptime-kuma
  - maintenant
  - namespace.yaml
```

- [ ] **Step 7: Preview and deploy**

```bash
kluctl diff -t cluster --include-deployment-dir core/monitoring
kluctl deploy -t cluster --include-deployment-dir core/monitoring
```

- [ ] **Step 8: Verify VictoriaMetrics is running**

```bash
kubectl get pods -n monitoring -l app.kubernetes.io/name=victoria-metrics-single
# Expected: 1 pod Running

kubectl port-forward -n monitoring svc/victoria-metrics-single-server 8428:8428
# In another terminal:
curl http://localhost:8428/api/v1/query?query=up
# Expected: JSON with "status":"success"
```

- [ ] **Step 9: Commit**

```bash
git add core/monitoring/victoria-metrics/ core/monitoring/deployment.yaml core/monitoring/kustomization.yaml
git commit -m "feat(monitoring): add VictoriaMetrics single-node"
```

---

## Task 2: Deploy VMAgent (scrape node-exporter + Traefik)

At this stage, kube-prometheus-stack is still running. VMAgent will scrape its existing `node-exporter` service (same name, same namespace — no config change needed later).

**Files:**
- Create: `core/monitoring/vmagent/helm-chart.yaml`
- Create: `core/monitoring/vmagent/helm-values.yaml`
- Create: `core/monitoring/vmagent/kustomization.yaml`
- Modify: `core/monitoring/deployment.yaml`
- Modify: `core/monitoring/kustomization.yaml`

- [ ] **Step 1: Check latest chart version**

```bash
helm search repo victoriametrics/victoria-metrics-agent
```

- [ ] **Step 2: Create `core/monitoring/vmagent/helm-chart.yaml`**

```yaml
---
helmChart:
  repo: https://victoriametrics.github.io/helm-charts/
  chartName: victoria-metrics-agent
  chartVersion: "0.13.0"  # replace with version found in step 1
  releaseName: vmagent
  namespace: monitoring
```

- [ ] **Step 3: Create `core/monitoring/vmagent/helm-values.yaml`**

```yaml
---
remoteWrite:
  - url: http://victoria-metrics-single-server.monitoring.svc.cluster.local:8428/api/v1/write

rbac:
  create: true
  pspEnabled: false

resources:
  requests:
    cpu: 50m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi

extraScrapeConfigs: |
  - job_name: node-exporter
    kubernetes_sd_configs:
      - role: endpoints
        namespaces:
          names:
            - monitoring
    relabel_configs:
      - source_labels: [__meta_kubernetes_endpoints_name]
        regex: node-exporter
        action: keep
      - source_labels: [__meta_kubernetes_pod_node_name]
        target_label: nodename
      - source_labels: [nodename]
        target_label: instance
        regex: "([^:]+)(:[0-9]+)?"
        replacement: "${1}"
  - job_name: traefik
    static_configs:
      - targets:
          - traefik.networking.svc.cluster.local:9100
    metrics_path: /metrics
```

- [ ] **Step 4: Create `core/monitoring/vmagent/kustomization.yaml`**

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - helm-rendered.yaml
```

- [ ] **Step 5: Add vmagent to `core/monitoring/deployment.yaml`**

```yaml
---
vars:
  - clusterSecret:
      name: cluster-secrets
      namespace: default
      key: SECRET_DOMAIN
      targetPath: SECRET_DOMAIN

deployments:
  - path: victoria-metrics
  - path: vmagent
  - path: grafana
  - path: kube-prometheus-stack
  - path: uptime-kuma
  - path: maintenant
```

- [ ] **Step 6: Add vmagent to `core/monitoring/kustomization.yaml`**

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - victoria-metrics
  - vmagent
  - grafana
  - kube-prometheus-stack
  - uptime-kuma
  - maintenant
  - namespace.yaml
```

- [ ] **Step 7: Preview and deploy**

```bash
kluctl diff -t cluster --include-deployment-dir core/monitoring
kluctl deploy -t cluster --include-deployment-dir core/monitoring
```

- [ ] **Step 8: Verify metrics are flowing into VictoriaMetrics**

```bash
kubectl get pods -n monitoring -l app.kubernetes.io/name=victoria-metrics-agent
# Expected: 1 pod Running

kubectl port-forward -n monitoring svc/victoria-metrics-single-server 8428:8428
curl "http://localhost:8428/api/v1/query?query=node_cpu_seconds_total" | jq '.data.result | length'
# Expected: number > 0 (one series per CPU per node)
```

- [ ] **Step 9: Commit**

```bash
git add core/monitoring/vmagent/ core/monitoring/deployment.yaml core/monitoring/kustomization.yaml
git commit -m "feat(monitoring): add VMAgent scraping node-exporter and Traefik"
```

---

## Task 3: Create Alertmanager Discord secret

**Files:**
- Create: `core/monitoring/alertmanager/secret.sops.yaml`

- [ ] **Step 1: Create the unencrypted secret file**

```bash
cat > core/monitoring/alertmanager/secret.sops.yaml << 'EOF'
---
apiVersion: v1
kind: Secret
metadata:
  name: alertmanager-discord
  namespace: monitoring
stringData:
  discord_webhook_url: "https://discord.com/api/webhooks/REPLACE_WITH_YOUR_WEBHOOK_URL"
EOF
```

- [ ] **Step 2: Replace the placeholder with your actual Discord webhook URL**

In Discord: Server Settings → Integrations → Webhooks → New Webhook → Copy Webhook URL.

Edit `core/monitoring/alertmanager/secret.sops.yaml` and replace `REPLACE_WITH_YOUR_WEBHOOK_URL` with the actual URL.

- [ ] **Step 3: Encrypt with SOPS**

```bash
sops -e -i core/monitoring/alertmanager/secret.sops.yaml
```

Verify the `stringData.discord_webhook_url` field is now encrypted (starts with `ENC[AES256_GCM`).

---

## Task 4: Deploy Alertmanager

**Files:**
- Create: `core/monitoring/alertmanager/helm-chart.yaml`
- Create: `core/monitoring/alertmanager/helm-values.yaml`
- Create: `core/monitoring/alertmanager/kustomization.yaml`
- Modify: `core/monitoring/deployment.yaml`
- Modify: `core/monitoring/kustomization.yaml`

- [ ] **Step 1: Check latest chart version**

```bash
helm search repo prometheus-community/alertmanager
```

- [ ] **Step 2: Create `core/monitoring/alertmanager/helm-chart.yaml`**

```yaml
---
helmChart:
  repo: https://prometheus-community.github.io/helm-charts
  chartName: alertmanager
  chartVersion: "1.12.0"  # replace with version found in step 1
  releaseName: alertmanager
  namespace: monitoring
```

- [ ] **Step 3: Create `core/monitoring/alertmanager/helm-values.yaml`**

```yaml
---
extraArgs:
  - "--config.expand-env=true"

extraEnv:
  - name: DISCORD_WEBHOOK_URL
    valueFrom:
      secretKeyRef:
        name: alertmanager-discord
        key: discord_webhook_url

config:
  global:
    resolve_timeout: 5m
  receivers:
    - name: discord
      discord_configs:
        - webhook_url: "${DISCORD_WEBHOOK_URL}"
          title: |-
            [{{ .Status | toUpper }}{{ if eq .Status "firing" }}:{{ .Alerts.Firing | len }}{{ end }}] {{ .CommonLabels.alertname }}
          message: |-
            {{ range .Alerts -}}
            **{{ .Annotations.summary }}**
            {{ .Annotations.description }}
            Nœud: `{{ .Labels.instance }}`
            Sévérité: `{{ .Labels.severity }}`
            {{ end }}
  route:
    group_by: ['alertname', 'instance']
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 4h
    receiver: discord

resources:
  requests:
    cpu: 10m
    memory: 32Mi
  limits:
    cpu: 100m
    memory: 128Mi
```

- [ ] **Step 4: Create `core/monitoring/alertmanager/kustomization.yaml`**

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - secret.sops.yaml
  - helm-rendered.yaml
```

- [ ] **Step 5: Add alertmanager to `core/monitoring/deployment.yaml`**

```yaml
---
vars:
  - clusterSecret:
      name: cluster-secrets
      namespace: default
      key: SECRET_DOMAIN
      targetPath: SECRET_DOMAIN

deployments:
  - path: victoria-metrics
  - path: vmagent
  - path: alertmanager
  - path: grafana
  - path: kube-prometheus-stack
  - path: uptime-kuma
  - path: maintenant
```

- [ ] **Step 6: Add alertmanager to `core/monitoring/kustomization.yaml`**

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - victoria-metrics
  - vmagent
  - alertmanager
  - grafana
  - kube-prometheus-stack
  - uptime-kuma
  - maintenant
  - namespace.yaml
```

- [ ] **Step 7: Preview and deploy**

```bash
kluctl diff -t cluster --include-deployment-dir core/monitoring
kluctl deploy -t cluster --include-deployment-dir core/monitoring
```

- [ ] **Step 8: Verify Alertmanager is running**

```bash
kubectl get pods -n monitoring -l app.kubernetes.io/name=alertmanager
# Expected: 1 pod Running

kubectl port-forward -n monitoring svc/alertmanager 9093:9093
curl http://localhost:9093/-/healthy
# Expected: "OK"
```

- [ ] **Step 9: Commit**

```bash
git add core/monitoring/alertmanager/ core/monitoring/deployment.yaml core/monitoring/kustomization.yaml
git commit -m "feat(monitoring): add Alertmanager with Discord receiver"
```

---

## Task 5: Deploy VMAlert (alerting rules)

**Files:**
- Create: `core/monitoring/vmalert/helm-chart.yaml`
- Create: `core/monitoring/vmalert/helm-values.yaml`
- Create: `core/monitoring/vmalert/kustomization.yaml`
- Modify: `core/monitoring/deployment.yaml`
- Modify: `core/monitoring/kustomization.yaml`

- [ ] **Step 1: Check latest chart version**

```bash
helm search repo victoriametrics/victoria-metrics-alert
```

- [ ] **Step 2: Create `core/monitoring/vmalert/helm-chart.yaml`**

```yaml
---
helmChart:
  repo: https://victoriametrics.github.io/helm-charts/
  chartName: victoria-metrics-alert
  chartVersion: "0.10.0"  # replace with version found in step 1
  releaseName: vmalert
  namespace: monitoring
```

- [ ] **Step 3: Create `core/monitoring/vmalert/helm-values.yaml`**

```yaml
---
server:
  datasource:
    url: "http://victoria-metrics-single-server.monitoring.svc.cluster.local:8428"
  notifiers:
    - url: "http://alertmanager.monitoring.svc.cluster.local:9093/api/v2/alerts"
  evaluationInterval: 60s

  resources:
    requests:
      cpu: 20m
      memory: 64Mi
    limits:
      cpu: 200m
      memory: 256Mi

  config:
    alerts:
      groups:
        - name: node.rules
          rules:
            - alert: NodeCPUHigh
              expr: >
                100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 90
              for: 15m
              labels:
                severity: warning
              annotations:
                summary: "CPU élevé sur {{ $labels.instance }}"
                description: "Utilisation CPU: {{ $value | humanize }}% depuis 15 minutes."

            - alert: NodeMemoryHigh
              expr: >
                (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 90
              for: 10m
              labels:
                severity: warning
              annotations:
                summary: "RAM élevée sur {{ $labels.instance }}"
                description: "Utilisation mémoire: {{ $value | humanize }}% depuis 10 minutes."

            - alert: NodeDiskLow
              expr: >
                (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}) * 100 < 10
              for: 5m
              labels:
                severity: critical
              annotations:
                summary: "Disque presque plein sur {{ $labels.instance }}"
                description: "Espace disque restant: {{ $value | humanize }}% sur {{ $labels.mountpoint }}."

            - alert: NodeDown
              expr: up{job="node-exporter"} == 0
              for: 5m
              labels:
                severity: critical
              annotations:
                summary: "Nœud {{ $labels.instance }} injoignable"
                description: "node-exporter sur {{ $labels.instance }} ne répond plus depuis 5 minutes."

            - alert: NodeFilesystemReadOnly
              expr: >
                node_filesystem_readonly{fstype!~"tmpfs|overlay|squashfs"} == 1
              for: 1m
              labels:
                severity: critical
              annotations:
                summary: "Filesystem en lecture seule sur {{ $labels.instance }}"
                description: "{{ $labels.mountpoint }} est monté en read-only sur {{ $labels.instance }}."
```

- [ ] **Step 4: Create `core/monitoring/vmalert/kustomization.yaml`**

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - helm-rendered.yaml
```

- [ ] **Step 5: Add vmalert to `core/monitoring/deployment.yaml`**

```yaml
---
vars:
  - clusterSecret:
      name: cluster-secrets
      namespace: default
      key: SECRET_DOMAIN
      targetPath: SECRET_DOMAIN

deployments:
  - path: victoria-metrics
  - path: vmagent
  - path: alertmanager
  - path: vmalert
  - path: grafana
  - path: kube-prometheus-stack
  - path: uptime-kuma
  - path: maintenant
```

- [ ] **Step 6: Add vmalert to `core/monitoring/kustomization.yaml`**

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - victoria-metrics
  - vmagent
  - alertmanager
  - vmalert
  - grafana
  - kube-prometheus-stack
  - uptime-kuma
  - maintenant
  - namespace.yaml
```

- [ ] **Step 7: Preview and deploy**

```bash
kluctl diff -t cluster --include-deployment-dir core/monitoring
kluctl deploy -t cluster --include-deployment-dir core/monitoring
```

- [ ] **Step 8: Verify VMAlert loaded the rules**

```bash
kubectl get pods -n monitoring -l app.kubernetes.io/name=victoria-metrics-alert
# Expected: 1 pod Running

kubectl logs -n monitoring -l app.kubernetes.io/name=victoria-metrics-alert --tail=20
# Expected: logs showing rules loaded, no errors about datasource connection
```

- [ ] **Step 9: Trigger a test alert to verify Discord delivery**

Temporarily lower NodeCPUHigh threshold to `> 0` to force firing:

```bash
kubectl edit configmap -n monitoring vmalert-config  # or patch via helm
```

Wait 2 minutes and verify a Discord message arrives. Then revert the threshold change.

Alternatively, use the Alertmanager API to send a test notification directly:

```bash
kubectl port-forward -n monitoring svc/alertmanager 9093:9093

curl -X POST http://localhost:9093/api/v2/alerts \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {"alertname": "TestAlert", "instance": "test-node", "severity": "warning"},
    "annotations": {"summary": "Test alerte", "description": "Test depuis le plan de migration."}
  }]'
```

Verify a message appears in Discord.

- [ ] **Step 10: Commit**

```bash
git add core/monitoring/vmalert/ core/monitoring/deployment.yaml core/monitoring/kustomization.yaml
git commit -m "feat(monitoring): add VMAlert with node alerting rules"
```

---

## Task 6: Migrate Grafana datasource to VictoriaMetrics

VictoriaMetrics expose une API PromQL-compatible sur le même path que Prometheus — seule l'URL change.

**Files:**
- Modify: `core/monitoring/grafana/helm-values.yaml`

- [ ] **Step 1: Update the datasource URL in `core/monitoring/grafana/helm-values.yaml`**

Find and replace:
```yaml
# Before
      - name: Prometheus
        type: prometheus
        access: proxy
        url: http://prometheus-prometheus:9090
        isDefault: true
        editable: true
```

```yaml
# After
      - name: Prometheus
        type: prometheus
        access: proxy
        url: http://victoria-metrics-single-server.monitoring.svc.cluster.local:8428
        isDefault: true
        editable: true
```

- [ ] **Step 2: Preview and deploy**

```bash
kluctl diff -t cluster --include-deployment-dir core/monitoring
kluctl deploy -t cluster --include-deployment-dir core/monitoring
```

- [ ] **Step 3: Verify Grafana datasource**

```bash
# Open Grafana in browser: https://grafana.<your-domain>
# Go to: Connections → Data sources → Prometheus → Test
# Expected: "Data source is working"
```

Open the node-exporter dashboard and verify data is visible.

- [ ] **Step 4: Commit**

```bash
git add core/monitoring/grafana/helm-values.yaml
git commit -m "feat(monitoring): switch Grafana datasource to VictoriaMetrics"
```

---

## Task 7: Remove kube-prometheus-stack, deploy standalone node-exporter

kube-prometheus-stack includes its own node-exporter DaemonSet with service named `node-exporter`. The standalone chart will reuse that exact service name — VMAgent scrape config requires no changes.

**Files:**
- Create: `core/monitoring/node-exporter/helm-chart.yaml`
- Create: `core/monitoring/node-exporter/helm-values.yaml`
- Create: `core/monitoring/node-exporter/kustomization.yaml`
- Modify: `core/monitoring/deployment.yaml`
- Modify: `core/monitoring/kustomization.yaml`
- Delete: `core/monitoring/kube-prometheus-stack/` (entire directory)

- [ ] **Step 1: Check latest chart version**

```bash
helm search repo prometheus-community/prometheus-node-exporter
```

- [ ] **Step 2: Create `core/monitoring/node-exporter/helm-chart.yaml`**

```yaml
---
helmChart:
  repo: https://prometheus-community.github.io/helm-charts
  chartName: prometheus-node-exporter
  chartVersion: "4.46.0"  # replace with version found in step 1
  releaseName: node-exporter
  namespace: monitoring
```

- [ ] **Step 3: Create `core/monitoring/node-exporter/helm-values.yaml`**

```yaml
---
fullnameOverride: node-exporter

tolerations:
  - key: node-role.kubernetes.io/master
    operator: Exists
    effect: NoSchedule
  - key: node-role.kubernetes.io/control-plane
    operator: Exists
    effect: NoSchedule

hostNetwork: true
hostPID: true

resources:
  requests:
    cpu: 20m
    memory: 32Mi
  limits:
    cpu: 250m
    memory: 128Mi

service:
  port: 9100
  targetPort: 9100
```

- [ ] **Step 4: Create `core/monitoring/node-exporter/kustomization.yaml`**

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - helm-rendered.yaml
```

- [ ] **Step 5: Replace `core/monitoring/deployment.yaml` (remove kube-prometheus-stack, add node-exporter)**

```yaml
---
vars:
  - clusterSecret:
      name: cluster-secrets
      namespace: default
      key: SECRET_DOMAIN
      targetPath: SECRET_DOMAIN

deployments:
  - path: victoria-metrics
  - path: vmagent
  - path: alertmanager
  - path: vmalert
  - path: node-exporter
  - path: grafana
  - path: uptime-kuma
  - path: maintenant
```

- [ ] **Step 6: Replace `core/monitoring/kustomization.yaml`**

```yaml
---
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - victoria-metrics
  - vmagent
  - alertmanager
  - vmalert
  - node-exporter
  - grafana
  - uptime-kuma
  - maintenant
  - namespace.yaml
```

- [ ] **Step 7: Delete the kube-prometheus-stack directory**

```bash
rm -rf core/monitoring/kube-prometheus-stack
```

- [ ] **Step 8: Preview — verify kube-prometheus-stack resources show as deleted**

```bash
kluctl diff -t cluster --include-deployment-dir core/monitoring
# Expected: all kube-prometheus-stack resources shown as deleted
#           node-exporter DaemonSet shown as new
```

- [ ] **Step 9: Deploy**

```bash
kluctl deploy -t cluster --include-deployment-dir core/monitoring
```

- [ ] **Step 10: Verify node-exporter DaemonSet is running on all nodes**

```bash
kubectl get daemonset -n monitoring node-exporter
# Expected: DESIRED == READY == number of cluster nodes (7)

kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus-node-exporter
# Expected: 7 pods Running
```

- [ ] **Step 11: Verify metrics still flowing (node-exporter service name unchanged)**

```bash
kubectl port-forward -n monitoring svc/victoria-metrics-single-server 8428:8428
curl "http://localhost:8428/api/v1/query?query=node_cpu_seconds_total" | jq '.data.result | length'
# Expected: number > 0 (metrics from standalone node-exporter visible within ~60s)
```

- [ ] **Step 12: Commit**

```bash
git add core/monitoring/node-exporter/ core/monitoring/deployment.yaml core/monitoring/kustomization.yaml
git rm -r core/monitoring/kube-prometheus-stack/
git commit -m "feat(monitoring): replace kube-prometheus-stack with standalone node-exporter"
```

---

## Task 8: Update IngressRoutes

Replace the `prometheus` IngressRoute with `victoria-metrics`.

**Files:**
- Modify: `apps/networking/traefik/ingresses.yaml`

- [ ] **Step 1: In `apps/networking/traefik/ingresses.yaml`, replace the prometheus IngressRoute block**

Find:
```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: prometheus
  namespace: networking
  annotations:
    external-dns.alpha.kubernetes.io/target: {{LB_TRAEFIK_ADDRESS}}
    kubernetes.io/ingress.class: traefik
spec:
  entryPoints:
    - websecure
  routes:
    - kind: Rule
      match: "Host(`prometheus.{{SECRET_DOMAIN}}`) && PathPrefix(`/`)"
      middlewares:
        - name: security-header
          namespace: networking
      services:
        - name: prometheus-prometheus
          namespace: monitoring
          port: 9090
          scheme: http
  tls:
    secretName: "{{SECRET_DOMAIN}}-tls"
```

Replace with:
```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: victoria-metrics
  namespace: networking
  annotations:
    external-dns.alpha.kubernetes.io/target: {{LB_TRAEFIK_ADDRESS}}
    kubernetes.io/ingress.class: traefik
spec:
  entryPoints:
    - websecure
  routes:
    - kind: Rule
      match: "Host(`victoria-metrics.{{SECRET_DOMAIN}}`) && PathPrefix(`/`)"
      middlewares:
        - name: forwardauth-authelia
          namespace: networking
        - name: security-header
          namespace: networking
      services:
        - name: victoria-metrics-single-server
          namespace: monitoring
          port: 8428
          scheme: http
  tls:
    secretName: "{{SECRET_DOMAIN}}-tls"
```

- [ ] **Step 2: Preview and deploy**

```bash
kluctl diff -t cluster --include-deployment-dir apps/networking
kluctl deploy -t cluster --include-deployment-dir apps/networking
```

- [ ] **Step 3: Verify VictoriaMetrics is accessible via browser**

Open `https://victoria-metrics.<your-domain>` and verify the VictoriaMetrics UI loads.
Run a test query: `node_cpu_seconds_total` — verify results appear.

- [ ] **Step 4: Commit**

```bash
git add apps/networking/traefik/ingresses.yaml
git commit -m "feat(networking): replace prometheus IngressRoute with victoria-metrics"
```

---

## Verification Checklist

After all tasks, verify the complete stack:

```bash
# All monitoring pods running
kubectl get pods -n monitoring
# Expected: victoria-metrics, vmagent, alertmanager, vmalert, node-exporter (x7), grafana, uptime-kuma, maintenant

# No kube-prometheus-stack resources remaining
kubectl get pods -n monitoring | grep -E "prometheus|alertmanager-kube|kube-state"
# Expected: no output

# Metrics available in VictoriaMetrics (7 days retention)
kubectl port-forward -n monitoring svc/victoria-metrics-single-server 8428:8428
curl "http://localhost:8428/api/v1/query?query=node_memory_MemTotal_bytes" | jq '.data.result | map(.metric.instance) | unique'
# Expected: array with 7 node names

# VMAlert rules loaded
kubectl logs -n monitoring -l app.kubernetes.io/name=victoria-metrics-alert --tail=5
# Expected: no error about datasource, rules evaluated

# Grafana working
# Open https://grafana.<domain> → Connections → Data sources → Test: "working"

# Victoria-metrics accessible
# Open https://victoria-metrics.<domain> → UI loads
```
