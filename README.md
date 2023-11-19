# jlejeune.home-ansible

These ansible playbooks configure a fresh deployment of a k3s cluster on 4 rapsberry pi 4.

## Prerequisites
Hardware:
* a workstation to run ansible commands
* 4 x raspberry pi 4 (4GB ram)

Configure the workstation:
* Install ansible
* Install collections/roles from Ansible Galaxy by running `ansible-galaxy install -r requirements.yml`
* Install sshpass and python-apt by running `sudo apt-get install sshpass python-apt -y`
* Install age and age-keygen binaries from https://github.com/FiloSottile/age/releases
* Install Mozilla sops binary from https://github.com/mozilla/sops/releases

Configure the raspberry pi:
* Flash SD-card with last Raspbian lite release (64bit): enable ssh and configure password for pi user: raspberry

## Setting up Age
Here we will create a Age Private and Public key. Using [SOPS](https://github.com/mozilla/sops) with [Age](https://github.com/FiloSottile/age) allows us to encrypt secrets and use them in Ansible and Flux.

1. Create a Age Private / Public Key

    ```sh
    age-keygen -o age.agekey
    ```

2. Set up the directory for the Age key and move the Age file to it

    ```sh
    mkdir -p ~/.config/sops/age
    mv age.agekey ~/.config/sops/age/keys.txt
    ```

## Secrets
All secrets are encrypted by Mozilla sops tool and are defined in <filename>.sops.yaml files
in inventory folder.

## Bootstrap your raspberry pis
You need to find the dynamic IPs given to your raspberry pis, you can use
nmap command to do so and fill your inventory/hosts.yml file with the temporary IPs:

```yaml
---
all:
  children:
    k3s_master:
      hosts:
        <MASTER_NAME>:
          ansible_host: <TEMPORARY_MASTER_IP>
    k3s_workers:
      hosts:
        <WORKER1_NAME>:
          ansible_host: <TEMPORARY_WORKER1_IP>
        <WORKER2_NAME>:
          ansible_host: <TEMPORARY_WORKER2_IP>
        <WORKER3_NAME>:
          ansible_host: <TEMPORARY_WORKER3_IP>
    k3s_cluster:
      children:
        k3s_master:
          hosts:
        k3s_workers:
          hosts:
```

Run the bootstrap ansible playbook on this inventory.
```sh
ansible-playbook playbooks/bootstrap.yml -u pi --ask-pass
```

You can now edit your inventory file to put the correct IPs you wanted
(defined in inventory/host_vars/ folder) and run the install-k3s.yml playbook.
```sh
ansible-playbook playbooks/install-k3s.yml
```

## Ansible roles

### common

 * Configure hostname
 * Set static IP
 * Configure locale
 * Create users and delete default pi user
 * Set the default editor
 * Setup a secure SSH configuration
 * Configure /boot/config.txt
 * Run raspi-config

### k3s

 * Download k3s binary
 * Configure k3s service on both nodes
 * Install and configure flux v2 to deploy other kubernetes components from a repository

## Ansible playbooks

### Bootstrap raspberry pi
```sh
ansible-playbook playbooks/bootstrap.yml
```

### k3s
#### Install
```sh
ansible-playbook playbooks/install-k3s.yml
```
#### Uninstall
```sh
ansible-playbook playbooks/uninstall-k3s.yml
```

#### Add a new worker

Edit hosts.yaml inventory file to add the name and the temporary IP of your new worker.

Create a new file in inventory/host_vars folder matching the hostname of your new worker and fill it with the correct values.

Run these commands:
```sh
ansible-playbook playbooks/bootstrap.yml -e 'ansible_user=pi' --ask-pass -l <NEW_WORKER_NAME>
ansible <NEW_WORKER_NAME> -a "/sbin/shutdown -r now -b"
```

After reboot, update the inventory file with your final worker IP and run this command to finalize bootstrap:
```sh
ansible-playbook playbooks/bootstrap.yml -l <NEW_WORKER_NAME>
```

Get you k3s master token from your master node in that file:
/var/lib/rancher/k3s/server/token and run that command:
```sh
ansible-playbook playbooks/add-k3s-worker.yml -e "host=<NEW_WORKER_NAME>" -e "token=<YOUR_TOKEN>"
```

### Longhorn

In my case, I use three usb sticks of 64GB plugged on my three worker nodes.

#### Identify the disks
```sh
ansible k3s_workers -a "lsblk -f"  # to get usb_disk_name value
```
Fill your hosts_vars usb_disk_name value in inventory.

#### Wipe the disks and format them
```sh
ansible k3s_workers -b -m shell -a "wipefs -a /dev/{{ usb_disk_name }}"
ansible k3s_workers -b -m filesystem -a "fstype=ext4 dev=/dev/{{ usb_disk_name }}"
```

#### Identify the disks UUID
```sh
ansible k3s_workers -b -m shell -a "blkid -s UUID -o value /dev/{{ usb_disk_name }}"  # to get external_usb_uuid
```

Fill your hosts_vars usb_disk_uuid value in inventory.

#### Mount the disks
```sh
ansible k3s_workers -b -m ansible.posix.mount -a "path=/storage src=UUID={{ usb_disk_uuid }} fstype=ext4 state=mounted"
```

### flux
#### Sync on a dev branch
```sh
ansible-playbook playbooks/patch-flux-branch.yml --extra-vars "branch=dev"
```

#### Go back on master branch
```sh
ansible-playbook playbooks/revert-flux-branch.yml
```

#### Upgrade flux
```sh
ansible-playbook playbooks/upgrade-flux.yml
```
