# VictoriaMetrics — Remplacement de kube-prometheus-stack

**Date :** 2026-04-16
**Statut :** Approuvé

## Contexte

Le cluster k3s homelab utilise actuellement `kube-prometheus-stack` (Prometheus operator + Alertmanager + kube-state-metrics + node-exporter + Thanos sidecar) jugé trop lourd. La rétention Prometheus est de 6h, le cluster est mixte amd64/arm64.

L'objectif est de remplacer kube-prometheus-stack par une stack VictoriaMetrics plus légère, orientée "alert-first" avec Discord comme canal de notification, et Grafana conservé uniquement pour le debug.

## Objectifs

- Remplacer kube-prometheus-stack par des composants VictoriaMetrics séparés (Option B)
- Rétention métriques : 7 jours (contre 6h actuellement)
- Alertes nœuds vers Discord via VMAlert → Alertmanager
- Grafana conservé comme backend de debug uniquement
- Supprimer Beszel (remplacé par VMAlert pour les alertes nœuds)
- Conserver Uptime Kuma (checks HTTP → Discord, inévitable)
- Conserver Maintenant (dashboard K8s léger)

## Périmètre des métriques

- **Conservé :** métriques nœuds (node-exporter DaemonSet)
- **Supprimé :** kube-state-metrics (métriques K8s pods/deployments) — debug K8s via `kubectl` ou Maintenant
- **Conservé :** scrape Traefik (migré de ServiceMonitor Prometheus → scrape statique dans VMAgent)

## Architecture

```
node-exporter (DaemonSet)
        │ /metrics
        ▼
    VMAgent  ──────────────────────→  VictoriaMetrics single-node
    (scrape)                              (stockage 7j, :8428)
                                               │
                                    ┌──────────┴──────────┐
                                    ▼                     ▼
                                 VMAlert              Grafana
                                (règles)             (debug)
                                    │
                                    ▼
                              Alertmanager
                                    │
                                    ▼
                                 Discord
```

## Composants

| Composant | Helm Chart | Rôle |
|---|---|---|
| `victoria-metrics-single` | `victoriametrics/victoria-metrics-single` | Stockage TSDB, API PromQL compatible |
| `vmagent` | `victoriametrics/victoria-metrics-agent` | Scrape node-exporter + Traefik |
| `vmalert` | `victoriametrics/victoria-metrics-alert` | Évaluation des règles d'alerte |
| `alertmanager` | `prometheus-community/alertmanager` | Routage notifications → Discord |
| `node-exporter` | `prometheus-community/prometheus-node-exporter` | Métriques nœuds (DaemonSet) |
| `grafana` | Existant (modifié) | Datasource basculée sur VictoriaMetrics |

## Règles d'alerte VMAlert

| Alerte | Condition | Sévérité |
|---|---|---|
| `NodeCPUHigh` | CPU > 90% pendant 15min | warning |
| `NodeMemoryHigh` | RAM utilisée > 90% pendant 10min | warning |
| `NodeDiskLow` | Espace disque < 10% | critical |
| `NodeDown` | node-exporter injoignable depuis 5min | critical |
| `NodeFilesystemReadOnly` | Filesystem monté en read-only | critical |

Évaluation toutes les 60s. Grouping par `alertname` + `instance`. `group_wait: 30s`, `repeat_interval: 4h`.

## Configuration Alertmanager

- Receiver unique : Discord via webhook URL
- Webhook stocké dans `core/monitoring/alertmanager/secret.sops.yaml` (chiffré Age/SOPS)
- Pas d'Alertmanager intégré à kube-prometheus-stack — composant standalone `prometheus-community/alertmanager`

## Structure de fichiers

```
core/monitoring/
├── deployment.yaml                    # Mis à jour
├── kustomization.yaml                 # Mis à jour
├── namespace.yaml                     # Inchangé
├── victoria-metrics/                  # NOUVEAU
│   ├── kustomization.yaml
│   ├── helm-chart.yaml
│   └── helm-values.yaml               # retention=7d, 10Gi Longhorn
├── vmagent/                           # NOUVEAU
│   ├── kustomization.yaml
│   ├── helm-chart.yaml
│   └── helm-values.yaml               # extraScrapeConfigs: node-exporter + Traefik (scrape statique)
├── vmalert/                           # NOUVEAU
│   ├── kustomization.yaml
│   ├── helm-chart.yaml
│   └── helm-values.yaml               # règles alertes, pointe sur VM + Alertmanager
├── alertmanager/                      # NOUVEAU
│   ├── kustomization.yaml
│   ├── helm-chart.yaml
│   ├── helm-values.yaml               # config Discord receiver
│   └── secret.sops.yaml               # DISCORD_WEBHOOK_URL
├── node-exporter/                     # NOUVEAU (extrait de kube-prometheus-stack)
│   ├── kustomization.yaml
│   └── helm-chart.yaml
├── grafana/                           # MODIFIÉ
│   └── helm-values.yaml               # datasource url → http://victoria-metrics-single-server:8428
└── kube-prometheus-stack/             # SUPPRIMÉ
```

## IngressRoutes

Dans `apps/networking/traefik/ingresses.yaml` :
- **Supprimer** la route `prometheus` (port 9090)
- **Ajouter** la route `victoria-metrics` (port 8428)
- Grafana inchangée

## Stratégie de migration

1. Déployer VictoriaMetrics single-node, VMAgent, node-exporter
2. Vérifier que les métriques arrivent dans VictoriaMetrics
3. Déployer VMAlert + Alertmanager, tester les alertes Discord
4. Basculer Grafana datasource vers VictoriaMetrics
5. Supprimer kube-prometheus-stack
6. Mettre à jour l'IngressRoute (prometheus → victoria-metrics)

## Ce qui ne change pas

- Uptime Kuma (checks HTTP + alertes Discord)
- Maintenant (dashboard K8s)
- Namespace `monitoring`
- Grafana (UI + IngressRoute)
- Secrets SOPS/Age pattern
