# Ansible

Ansible playbooks and roles for provisioning and managing the K3s cluster nodes.

## Roles

### common

- Configure hostname and static IP
- Configure locale
- Create users and remove default `pi` user
- Set the default editor
- Set up secure SSH configuration
- Configure fail2ban
- Configure `/boot/config.txt`
- Run raspi-config
- Install plik client

### k3s

- Download K3s binary
- Configure K3s systemd service (master or worker)
- Deploy kube-vip on master nodes

## Playbooks

### Bootstrap

```sh
ansible-playbook playbooks/bootstrap.yml
```

### Install K3s

```sh
ansible-playbook playbooks/install-k3s.yml
```

### Uninstall K3s

```sh
ansible-playbook playbooks/uninstall-k3s.yml
```

### Promote a worker to master

Edit `inventory/hosts.yml` to move the worker into the `k3s_masters` group, then:

```sh
kubectl cordon <NODE>
kubectl drain --force --ignore-daemonsets --delete-emptydir-data --grace-period=10 <NODE>
kubectl delete nodes/<NODE>
ansible-playbook --limit <NODE> playbooks/uninstall-k3s.yml
ansible-playbook --limit <NODE> playbooks/install-k3s.yml
```

### Add a new worker

1. Add the new node to `inventory/hosts.yml` with its temporary IP
2. Create a host vars file in `inventory/host_vars/`
3. Run:

```sh
ansible-playbook playbooks/bootstrap.yml -e 'ansible_user=pi' --ask-pass -l <NEW_WORKER>
ansible <NEW_WORKER> -a "/sbin/shutdown -r now -b"
```

4. After reboot, update the inventory with the final IP and finalize:

```sh
ansible-playbook playbooks/bootstrap.yml -l <NEW_WORKER>
```

5. Get the K3s token from `/var/lib/rancher/k3s/server/token` on the master, then:

```sh
ansible-playbook playbooks/add-k3s-worker.yml -e "host=<NEW_WORKER>" -e "token=<TOKEN>"
```

## Longhorn storage setup

USB drives (64 GB) are used as Longhorn storage on worker nodes.

```sh
# Identify disks
ansible k3s_workers -a "lsblk -f"

# Wipe and format
ansible k3s_workers -b -m shell -a "wipefs -a /dev/{{ usb_disk_name }}"
ansible k3s_workers -b -m filesystem -a "fstype=ext4 dev=/dev/{{ usb_disk_name }}"

# Get UUID
ansible k3s_workers -b -m shell -a "blkid -s UUID -o value /dev/{{ usb_disk_name }}"

# Mount
ansible k3s_workers -b -m ansible.posix.mount -a "path=/storage src=UUID={{ usb_disk_uuid }} fstype=ext4 state=mounted"
```

Fill `usb_disk_name` and `usb_disk_uuid` in the corresponding `inventory/host_vars/` files.
