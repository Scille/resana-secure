# Package Resana secure in a snap package

## Requirement

You need to be on linux with the following requirement

1. `snapd` installed <https://snapcraft.io/docs/installing-snapd>

2. Install `lxd` with:

   ```shell
   snap install lxd
   ```

   > Some distro provide other mean to install lxd than using `snap`, for more info:
   > <https://documentation.ubuntu.com/lxd/en/latest/installing/>

   You will also need to add the current user to the group `lxd`

   ```shell
   usermod -aG lxd $USER
   ```

3. If you don't have previously initialize `lxd` use the following command

   ```shell
   lxd init --preseed < lxd.preseed.yaml
   ```

   Here the `preseed` configuration

    ```yaml
    config:
      images.auto_update_interval: "0"

    networks:
    - config:
        ipv4.address: auto
        ipv6.address: auto
      description: ""
      name: lxdbr0
      type: ""
      project: default

    storage_pools:
    - config:
        source: /var/lib/lxd/storage-pools/scille
      description: ""
      name: scille
      driver: btrfs

    profiles:
    - config: {}
      description: ""
      devices:
        eth0:
          name: eth0
          network: lxdbr0
          type: nic
        root:
          path: /
          pool: scille
          type: disk
      name: default
    projects: []
    cluster: null
    ```

   You can find more information about it [here](https://documentation.ubuntu.com/lxd/en/latest/howto/initialize/).
