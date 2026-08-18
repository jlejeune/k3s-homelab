# k3s-homelab

A fully automated **K3s Kubernetes homelab** running on a mix of mini PCs and Raspberry Pis, provisioned with **Ansible** and deployed with **Kluctl**. Secrets are encrypted with **Mozilla SOPS** and **Age**. Image and chart updates are handled automatically by **Renovate**.

Nodes are named after Lord of the Rings characters.

## Cluster overview

| Node | Role | Hardware | Arch | IP |
|---|---|---|---|---|
| theoden | Master | Geekom Mini Air 11 (NUC) | x86_64 | 192.168.1.14 |
| sam | Worker | Raspberry Pi 4 (4 GB) | aarch64 | 192.168.1.10 |
| merry | Worker | Raspberry Pi 4 (4 GB) | aarch64 | 192.168.1.11 |
| pippin | Worker | Raspberry Pi 4 (4 GB) | aarch64 | 192.168.1.12 |
| gimli | Worker | Raspberry Pi 4 (4 GB) | aarch64 | 192.168.1.13 |
| frodon | Worker | Raspberry Pi 4 (4 GB) | aarch64 | 192.168.1.15 |
| galadriel | Worker | BMAX B8 A Pro (Mini PC) | x86_64 | 192.168.1.16 |

The master VIP is `192.168.1.9`, managed by **kube-vip**. The cluster runs a mixed-architecture setup (x86_64 + aarch64).

## Project structure

```
.
├── ansible/                    # Infrastructure provisioning
│   ├── inventory/
│   │   ├── hosts.yml           # Cluster node inventory
│   │   ├── group_vars/         # Shared variables (some encrypted with SOPS)
│   │   └── host_vars/          # Per-node variables (IP, disk UUID, etc.)
│   ├── playbooks/
│   │   ├── bootstrap.yml       # Initial machine setup
│   │   ├── install-k3s.yml     # K3s cluster installation
│   │   ├── uninstall-k3s.yml   # K3s cluster removal
│   │   └── add-k3s-worker.yml  # Add a worker to an existing cluster
│   ├── roles/
│   │   ├── common/             # Base OS config (hostname, IP, SSH, locale, users, fail2ban)
│   │   └── k3s/                # K3s binary, service config, kube-vip on master
│   └── requirements.yml        # Ansible Galaxy collections
│
├── cluster/                    # Kubernetes manifests (deployed with Kluctl)
│   ├── .kluctl.yaml            # Kluctl target definition
│   ├── config/                 # Cluster-wide settings and secrets
│   │   ├── cluster-settings.yaml   # ConfigMap with IPs, timezone, etc.
│   │   └── cluster-secrets.sops.yaml
│   ├── core/                   # Infrastructure services
│   │   ├── cert-manager/       # TLS certificates (Let's Encrypt + local CA)
│   │   ├── networking/         # Traefik, MetalLB, kube-vip, External DNS
│   │   ├── monitoring/         # VictoriaMetrics, vmagent, vmalert, Grafana, Alertmanager, Uptime Kuma
│   │   ├── storage/            # Longhorn + NFS provisioner
│   │   ├── kube-system/        # k8s device plugin
│   │   ├── node-feature-discovery/
│   │   ├── reloader/           # Auto-restart pods on ConfigMap/Secret changes
│   │   └── system-upgrade/     # Automated K3s upgrades
│   └── apps/                   # User-facing applications
│       ├── home-automation/    # Home Assistant, Zigbee2MQTT, Mosquitto, ESPHome, Go2RTC, Code Server
│       │   ├── ollama/         # Local LLM inference
│       │   ├── open-webui/     # Web UI for Ollama
│       │   ├── whisper/        # Speech-to-text
│       │   ├── piper/          # Text-to-speech
│       │   └── openwakeword/   # Wake word detection
│       ├── immich/             # Self-hosted photo management (server + ML)
│       ├── jellyfin/           # Media server
│       ├── yamtrack/           # Movie/TV/anime/manga tracking
│       ├── freshrss/           # RSS reader
│       ├── joplin/             # Note-taking (with PostgreSQL)
│       ├── karakeep/           # Bookmark manager (+ Meilisearch)
│       ├── mealie/             # Recipe manager
│       ├── dawarich/           # Location history tracking (PostGIS + Sidekiq)
│       ├── donetick/           # Chore/task tracker
│       ├── dashy/              # Dashboard
│       ├── media-automation/   # Prowlarr, Radarr, Sonarr, Seerr, Plundrio, Shelfmark, Calibre-Web-Automated
│       ├── nextcloud/          # File sync (PostgreSQL + Redis + Collabora)
│       ├── networking/         # Technitium DNS, WireGuard, Traefik ingresses, certificates
│       ├── authelia/           # SSO / authentication (with Redis + PostgreSQL)
│       ├── openldap/           # LDAP directory + LDAP Account Manager
│       ├── plik/               # File sharing
│       ├── rustdesk/           # Self-hosted RustDesk remote desktop (hbbs + hbbr)
│       ├── smtp-relay/         # Postfix SMTP relay
│       ├── stirling-pdf/       # PDF tools with Authelia SSO
│       ├── supabase/           # Postgres/BaaS platform (Edge Functions)
│       └── thelounge/          # Web IRC client
│
├── .sops.yaml                  # SOPS encryption rules (Age key)
├── .pre-commit-config.yaml     # Pre-commit hooks (yamllint, sops, formatting)
├── .github/
│   ├── renovate.json5          # Renovate config for automated dependency updates
│   └── linters/                # Linter configs
└── LICENSE                     # MIT
```

## Core services

| Category | Components |
|---|---|
| **Networking** | Traefik (reverse proxy, `192.168.1.200`), MetalLB (load balancer), kube-vip, External DNS |
| **Storage** | Longhorn (distributed block storage on USB drives), NFS provisioner (NAS at `192.168.1.50`) |
| **Certificates** | cert-manager with Let's Encrypt (production + staging), OVH DNS challenge webhook, local CA (`jlejeune.home`) |
| **Monitoring** | VictoriaMetrics (TSDB), vmagent, vmalert, Grafana, Alertmanager, node-exporter, kube-state-metrics, Uptime Kuma |
| **Other** | Node Feature Discovery, Reloader, System Upgrade Controller |

## Applications

| Category | Applications |
|---|---|
| **Home automation** | Home Assistant, Zigbee2MQTT, Mosquitto (MQTT broker), ESPHome, Go2RTC |
| **AI / Voice** | Ollama (LLM), Open WebUI, Whisper (STT), Piper (TTS), OpenWakeWord |
| **Media** | Jellyfin (video), Immich (photos with machine learning), Yamtrack (movie/TV/anime/manga tracking) |
| **Media automation** | Prowlarr, Radarr, Sonarr, Seerr, Plundrio, Shelfmark, Calibre-Web-Automated |
| **Productivity** | Joplin (notes), Mealie (recipes), Donetick (chores), Karakeep (bookmarks), FreshRSS (feeds), Nextcloud (files), Code Server (VS Code), Dawarich (location history) |
| **Networking** | Technitium (DNS), WireGuard (VPN), Traefik ingress routes |
| **Auth / Identity** | Authelia (SSO with forward auth), OpenLDAP + LDAP Account Manager |
| **Utilities** | Plik (file sharing), Stirling PDF, Supabase (BaaS), The Lounge (IRC), SMTP Relay (Postfix), Dashy (dashboard), RustDesk (remote desktop) |

## Security

- All secrets in the repository are encrypted with **Mozilla SOPS** using an **Age** key
- Separate encryption rules for `cluster/` and `ansible/` directories (see `.sops.yaml`)
- SSH hardening and **fail2ban** configured via the `common` Ansible role
- **Authelia** provides SSO with forward authentication through Traefik middlewares
- A **pre-commit hook** (`forbid-secrets`) prevents accidental commit of unencrypted secrets

## Prerequisites

Hardware:
- A workstation to run Ansible and Kluctl commands
- 1 master + N worker nodes (mini PCs or Raspberry Pi 4 with at least 4 GB RAM)
- Optional: USB drives for Longhorn storage, a NAS for NFS shares

Software on the workstation:
- [Ansible](https://docs.ansible.com/) + collections: `ansible-galaxy install -r ansible/requirements.yml`
- `sshpass` and `python-apt`: `sudo apt-get install sshpass python-apt -y`
- [Age](https://github.com/FiloSottile/age/releases) for secret encryption
- [Mozilla SOPS](https://github.com/mozilla/sops/releases) for secret management
- [Kluctl](https://kluctl.io/) for Kubernetes deployments: `sudo curl -s https://kluctl.io/install.sh | bash`

## Getting started

### 1. Set up Age encryption

```sh
age-keygen -o age.agekey
mkdir -p ~/.config/sops/age
mv age.agekey ~/.config/sops/age/keys.txt
```

### 2. Bootstrap servers

Find the temporary IPs of your nodes (e.g. with `nmap`) and fill `ansible/inventory/hosts.yml`.

```sh
ansible-playbook ansible/playbooks/bootstrap.yml -u pi --ask-pass
```

Update the inventory with the final static IPs (defined in `ansible/inventory/host_vars/`), then install K3s:

```sh
ansible-playbook ansible/playbooks/install-k3s.yml
```

### 3. Deploy Kubernetes manifests

```sh
cd cluster
kluctl diff -t cluster    # Preview changes
kluctl deploy -t cluster  # Apply to cluster
```

## Ansible

See [ansible/README.md](ansible/README.md) for detailed documentation on roles, playbooks, and Longhorn storage setup.

## Tooling

| Tool | Purpose |
|---|---|
| [Ansible](https://docs.ansible.com/) | Infrastructure provisioning and OS configuration |
| [Kluctl](https://kluctl.io/) | Declarative Kubernetes deployment (diff & deploy) |
| [SOPS](https://github.com/mozilla/sops) + [Age](https://github.com/FiloSottile/age) | Secret encryption at rest in Git |
| [Renovate](https://github.com/renovatebot/renovate) | Automated dependency/image updates (runs every Saturday) |
| [pre-commit](https://pre-commit.com/) | Git hooks for linting, formatting, and secret leak prevention |
| [yamllint](https://github.com/adrienverge/yamllint) | YAML linting |

## License

[MIT](LICENSE)
