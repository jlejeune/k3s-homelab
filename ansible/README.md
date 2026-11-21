# Ansible

Ansible playbooks and roles for provisioning and managing the K3s cluster nodes.

## Collections

ansible-galaxy collection install -r requirements.yml

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
- Install Claude Code and run Remote Control as a systemd service (`install_claude`, only on galadriel)
- Install localsend-cli and run it as a systemd service (`install_localsend`, only on galadriel)

#### Claude Code on galadriel

The `claude` tag installs Claude Code for `jlejeune` with the official installer. It then installs `claude-remote.service`, which runs `claude remote-control` in the repository clone. The `~/.claude` files come from chezmoi, in the `user` tag.

Before the service can start, log in once by hand on galadriel as `jlejeune`: run `claude` in the repository directory, log in with the claude.ai account and accept the trust prompt. Then apply the role:

```sh
ansible-playbook playbooks/bootstrap.yml -l galadriel --tags claude
```

Without the login, Ansible installs and enables the service but leaves it stopped. Claude Code updates itself, so Ansible does not install it again. Use `claude_remote_spawn` (`same-dir`, `worktree` or `session`) and `claude_remote_permission_mode` in `inventory/host_vars/galadriel.yml` to change the behavior.

#### LocalSend on galadriel

The `localsend` tag installs `localsend-cli` from a release of the `jlejeune/localsend` fork. The fork adds the `receive` command. The tag then installs `localsend-receive.service`, which runs `localsend-cli receive` as `jlejeune`. The service accepts files from paired devices and declines all other devices. It saves the files in `~/Downloads`. The tag also adds ufw rules that allow port 53317 (TCP and UDP) from the local network. It does not turn ufw on or off.

To install or update the service, run this command from the `ansible` directory:

```sh
ansible-playbook playbooks/bootstrap.yml -l galadriel --tags localsend
```

To install a new build, publish a new release in the fork. Then change `localsend_cli_release` and `localsend_cli_sha256` in `roles/common/defaults/main.yml`. The value of `localsend_cli_sha256` is the SHA-256 hash of the `LocalSend-CLI-<version>-linux-x86-64.tar.gz` file of that release. To get the hash, download the file and run `sha256sum` on it.

You must pair each device once by hand. The service reads the list of paired devices only at startup. Follow these steps on galadriel as `jlejeune`:

1. Stop the service with `sudo systemctl stop localsend-receive`.
2. Run `localsend-cli` in a terminal.
3. Send a file from the device that you want to pair.
4. When the request appears, press `P`.
5. Press Ctrl+C, then start the service with `sudo systemctl start localsend-receive`.

To read the log of the service, run `journalctl -u localsend-receive`.

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
