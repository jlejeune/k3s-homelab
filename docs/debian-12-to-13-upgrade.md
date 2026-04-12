# Upgrade Debian 12 (Bookworm) → Debian 13 (Trixie)

Node-by-node upgrade guide for the k3s homelab cluster. **Upgrade workers first, master last.**

## Prerequisites

- All nodes reachable via SSH
- `kubectl` working from `theoden` (or locally with the kubeconfig)
- Back up the kubeconfig: `cp /root/.kube/config /root/.kube/config.bak`

## Recommended upgrade order

```
sam → merry → pippin → gimli → frodon → galadriel → theoden (master last)
```

---

## Per-node procedure

### Step 1 — Drain the node (workers only, skip for theoden)

From `theoden` or locally:

```bash
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data
```

Confirm the node is in `SchedulingDisabled` state:

```bash
kubectl get nodes
```

### Step 2 — SSH into the node

```bash
ssh jlejeune@192.168.1.XX
sudo -i
```

### Step 3 — Fully update Debian 12 first

Make sure the system is fully up to date before migrating:

```bash
apt update && apt upgrade -y && apt full-upgrade -y
apt autoremove -y
```

### Step 4 — Replace APT sources

Debian 12 uses `/etc/apt/sources.list.d/debian.sources` (DEB822 format) on fresh installs,
but nodes configured by Ansible likely still use the legacy `/etc/apt/sources.list`.
Check which one is active:

```bash
ls /etc/apt/sources.list.d/
cat /etc/apt/sources.list
```

#### Legacy format (`/etc/apt/sources.list`)

```bash
# Back up the current config
cp /etc/apt/sources.list /etc/apt/sources.list.bak

# Replace bookworm with trixie
sed -i 's/bookworm/trixie/g' /etc/apt/sources.list

# Do the same for any files in sources.list.d/ if present
sed -i 's/bookworm/trixie/g' /etc/apt/sources.list.d/*.list 2>/dev/null || true
```

Verify the result:

```bash
cat /etc/apt/sources.list
```

Should look like:

```
deb http://deb.debian.org/debian trixie main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware
deb http://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware
```

#### DEB822 format (`/etc/apt/sources.list.d/debian.sources`)

```bash
cp /etc/apt/sources.list.d/debian.sources /etc/apt/sources.list.d/debian.sources.bak
sed -i 's/bookworm/trixie/g' /etc/apt/sources.list.d/debian.sources
```

### Step 5 — Release held network packages

The Ansible playbook puts some packages on hold. Temporarily unhold them:

```bash
apt-mark unhold ifupdown dhcpcd5 isc-dhcp-client isc-dhcp-common rsyslog raspberrypi-net-mods openresolv
```

### Step 6 — Run the migration

```bash
apt update
apt upgrade -y
apt full-upgrade -y
```

Answer interactive prompts:
- Modified config files: keep the local version (`N` / keep current)
- Services to restart: accept the defaults

### Step 7 — Clean up

```bash
apt autoremove -y
apt autoclean
```

### Step 8 — Pre-reboot checks

Verify the systemd-networkd config is intact:

```bash
cat /etc/systemd/network/01-eth0.link
cat /etc/systemd/network/10-wired.network
systemctl is-enabled systemd-networkd
```

On aarch64 nodes (Raspberry Pi), verify cgroup configuration survived:

```bash
cat /boot/cmdline.txt | grep cgroup
# Should contain: cgroup_enable=cpuset cgroup_memory=1 cgroup_enable=memory
```

> **Note:** Debian 13 ships with Linux 6.x — cgroup v2 is the default. If k3s behaves
> unexpectedly after reboot, check `cat /sys/fs/cgroup/cgroup.controllers` and ensure k3s
> systemd unit has `Delegate=yes` (already set by the Ansible role).

### Step 9 — Reboot

```bash
reboot
```

Wait ~60 seconds, then verify the node responds:

```bash
ping 192.168.1.XX
ssh jlejeune@192.168.1.XX
```

### Step 10 — Check k3s after reboot

On the node:

```bash
sudo systemctl status k3s-agent   # workers
sudo systemctl status k3s          # master
```

From `theoden`:

```bash
kubectl get nodes
```

The node should show `Ready` (with `SchedulingDisabled` for drained workers).

### Step 11 — Uncordon the node (workers only)

```bash
kubectl uncordon <node>
kubectl get nodes
```

### Step 12 — Re-run the bootstrap playbook

Ensure all Ansible configuration is correctly applied on Debian 13:

```bash
# From the ansible/ directory
ansible-playbook playbooks/bootstrap.yml --limit <node>
```

---

## Upgrading the master (theoden — 192.168.1.14)

The master hosts the kube-vip VIP (`192.168.1.9`). This upgrade is more sensitive.

> Do not drain theoden: it is not schedulable by default (taint `PreferNoSchedule`).

Before starting:

```bash
# Back up the kube-vip manifest
kubectl get pod -n kube-system kube-vip -o yaml > /tmp/kube-vip-backup.yaml

# Verify cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running
```

Follow the same steps 3 through 9.

After reboot, check the VIP first:

```bash
# VIP still alive
ping 192.168.1.9

# k3s master operational
sudo systemctl status k3s
kubectl get nodes
kubectl get pods -A
```

Then run the bootstrap playbook:

```bash
ansible-playbook playbooks/bootstrap.yml --limit theoden
```

---

## Post-upgrade verification (full cluster)

```bash
# All nodes Ready
kubectl get nodes -o wide

# All pods running
kubectl get pods -A | grep -v Running | grep -v Completed

# Check Debian version on all nodes
ansible all -m command -a "cat /etc/debian_version"

# k3s version unchanged
ansible all -m command -a "k3s --version" --limit k3s_masters
```

---

## Emergency rollback

If a node is unreachable after the upgrade:

1. Physical console access or IPMI
2. Boot from a Debian 12 live USB if needed
3. Restore `/etc/apt/sources.list.bak` (or `/etc/apt/sources.list.d/debian.sources.bak`) and downgrade: `apt full-upgrade -y` (rarely needed)
4. For k3s: the binary lives at `/usr/local/bin/k3s` and is independent of apt — it survives the OS upgrade

---

## References

- [Debian Trixie release notes — upgrading](https://www.debian.org/releases/trixie/amd64/release-notes/ch-upgrading.html)
- [k3s documentation](https://docs.k3s.io/)
