# k3s Homelab — Cluster

## Overview

k3s Kubernetes homelab managed with **Kluctl** (orchestration) + **Kustomize** (manifest composition) + **Helm** (third-party charts) + **SOPS/Age** (encrypted secrets). GitOps with Renovate for automated updates.

## Project Structure

```
cluster/
├── .kluctl.yaml              # Target: "cluster", context: default, discriminator: my-homelab
├── deployment.yaml           # Kluctl entry point (config → core → apps, with barriers)
├── kustomization.yaml        # Root Kustomize
├── config/                   # Cluster-wide variables
│   ├── cluster-settings.yaml     # ConfigMap: MetalLB IPs, NAS, timezone
│   └── cluster-secrets.sops.yaml # Age-encrypted Secret: credentials, domains, OAuth tokens
├── core/                     # Base infrastructure (must deploy before apps)
│   ├── cert-manager/         # Let's Encrypt + OVH DNS webhook + local CA jlejeune.home
│   ├── kube-system/          # System components
│   ├── monitoring/           # kube-prometheus-stack, Grafana, Uptime Kuma
│   ├── networking/           # MetalLB, kube-vip (VIP: 192.168.1.9), Traefik, External DNS
│   ├── node-feature-discovery/
│   ├── reloader/             # Hot-reload ConfigMap/Secret changes
│   ├── storage/              # Longhorn (distributed block) + NFS provisioner
│   └── system-upgrade/       # System Upgrade Controller (FluxCD Kustomization)
└── apps/                     # User-facing applications
    ├── authelia/             # SSO / authentication
    ├── dashy/                # Dashboard
    ├── freshrss/             # RSS aggregator
    ├── home-automation/      # HA, Zigbee2MQTT, Mosquitto, ESPHome, Go2RTC, Ollama, Whisper, Piper, OpenWakeWord, Open WebUI, code-server
    ├── immich/               # Photo management (+ ML)
    ├── jellyfin/             # Video streaming
    ├── joplin/               # Notes
    ├── mealie/               # Recipes
    ├── openldap/             # LDAP directory (osixia/openldap:1.5.0, Longhorn PVCs) + LAM web UI
    ├── networking/           # IngressRoutes, wildcard certificates
    ├── nextcloud/            # File sharing + PostgreSQL + Redis + Collabora CODE
    ├── plik/                 # File sharing
    ├── pydio/                # File management + collaborative editing (Pydio Cells + ONLYOFFICE)
    ├── smtp-relay/           # Postfix relay
    └── supabase/             # PostgreSQL + API backend
```

## Essential Commands

```bash
# Preview changes before applying
kluctl diff -t cluster

# Deploy everything
kluctl deploy -t cluster

# Deploy a single app subset
kluctl deploy -t cluster --include-deployment-dir apps/immich
```

## Network — MetalLB IPs (range 192.168.1.200-250)

| Service | IP |
|---|---|
| Traefik (ingress) | 192.168.1.200 |
| Pi-hole | 192.168.1.202 |
| SMTP Relay | 192.168.1.203 |
| MQTT (Mosquitto) | 192.168.1.204 |
| Ollama | 192.168.1.205 |
| Go2RTC | 192.168.1.206 |
| Whisper (STT) | 192.168.1.207 |
| Piper (TTS) | 192.168.1.208 |
| OpenWakeWord | 192.168.1.209 |
| OpenLDAP | 192.168.1.210 |
| kube-vip (control plane) | 192.168.1.9 |
| NAS | 192.168.1.50 |
| Zigbee coordinator | 192.168.1.30 |

## Cluster Nodes

Named after Lord of the Rings characters: `theoden`, `sam`, `merry`, `pippin`, `gimli`, `frodon`, `galadriel`.
Mixed x86_64 + aarch64 (ARM) cluster. Some services have amd64 node affinity (e.g. Grafana).

## Configuration Patterns

### Kluctl Templating
Manifests use double-braces for variable substitution:
```yaml
# Reference to cluster-settings ConfigMap
address: "{{LB_TRAEFIK_ADDRESS}}"
# Reference to cluster-secrets Secret
domain: "{{SECRET_DOMAIN}}"
```
Note: use `{{VAR}}` without spaces — spaces cause Jinja2 rendering errors.

### Standard Helm Pattern
Each Helm chart = 2 files:
- `helm-chart.yaml` — chart source (repo + version)
- `helm-values.yaml` — custom values

### Typical App Layout
```
apps/my-app/
├── kustomization.yaml     # Resource list
├── namespace.yaml         # Dedicated namespace
├── deployment.yaml        # Kluctl deployment or direct manifests
├── helm-chart.yaml        # If Helm
├── helm-values.yaml       # If Helm
├── secret.sops.yaml       # Age-encrypted secret (if needed)
└── ingress.yaml           # Traefik IngressRoute
```

## Secrets — SOPS/Age

- All secrets encrypted with **Age** via **SOPS**
- Age public key: `age1v888svjrzkthezatjrvejzelr9r6zuv8sry280k4phuw8p7p4ycstn2ces`
- Concerned files: `*.sops.yaml`
- Only `data` and `stringData` fields are encrypted (structure remains readable)
- Central secret: `config/cluster-secrets.sops.yaml`
- Per-app secrets: `apps/<app>/secret.sops.yaml`

```bash
# Encrypt a new secret
sops -e -i apps/my-app/secret.sops.yaml

# Edit an encrypted secret
sops apps/my-app/secret.sops.yaml
```

## CI/CD & Automation

- **Renovate**: automatic updates for Docker images and Helm charts, scheduled every Saturday
- **Pre-commit hooks**: yamllint, unencrypted secret detection (`forbid-secrets`), formatting
- Renovate config: `.github/renovate.json5` (scans `cluster/.+\.ya?ml$`)

## Important Conventions

1. Always run `kluctl diff` before `kluctl deploy`
2. Never commit unencrypted secrets (pre-commit hook + SOPS)
3. Global variables go in `config/cluster-settings.yaml` (non-sensitive) or `config/cluster-secrets.sops.yaml` (sensitive)
4. New MetalLB IPs are allocated from range 192.168.1.200-250 and declared in `cluster-settings.yaml`
5. Each new app must have its own dedicated namespace
6. The root `deployment.yaml` controls deployment order: config → core (barrier) → apps (barrier)

## CLAUDE.md Maintenance

This file should be kept up to date as the project evolves. Update it when:
- A new application is added or removed from `apps/`
- A new MetalLB IP is assigned
- A new core infrastructure component is added
- Tooling or deployment patterns change
- New cluster nodes are added or renamed
