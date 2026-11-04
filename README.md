# pastir.patroni

Deploys and operates a [Patroni](https://patroni.readthedocs.io/) PostgreSQL cluster with an etcd v3 DCS.
It is safe to run against a cluster that is already in production.

## Safety guarantees

- **No data is ever deleted.** The role does not touch `PGDATA`. A new cluster is created by Patroni itself:
  the first member to take the leader lock runs `initdb`, and the others clone from it.
- **No implicit failover or restart.**
  - A change to the local `config.yml` is applied with `systemctl reload patroni` (SIGHUP), one member at a time.
  - A cluster-wide change (`pg_hba`, parameters) is applied with `PATCH /config`.
  - Parameters that need a PostgreSQL restart are **reported**. They are restarted only with
    `patroni_restart_pending: true`: replicas first, the leader last.
- **A Patroni package upgrade** requires `patroni_allow_upgrade: true`. The cluster is put into maintenance mode
  (`pause`) first, so PostgreSQL keeps running while Patroni restarts.
- **`start.conf` = `manual`** for every Debian cluster on the node, so systemd never starts PostgreSQL behind
  Patroni's back.
- The config file is validated (`patroni --validate-config`) before it is written. It has mode `0600`,
  and diff output is disabled because the file contains passwords.

## Dynamic configuration

`patroni_dcs` is both `bootstrap.dcs` for a new cluster and the desired state of the running cluster.
On every run the role reads `GET /config`. If anything in `patroni_dcs` differs, it sends
`PATCH /config` with `patroni_dcs`.

- Keys not listed in `patroni_dcs` are left as they are.
- To **delete** a key (e.g. an obsolete parameter), set it to `null`.
- `pg_hba` is a list and is replaced as a whole.
- `on`/`true`/`1` style differences are ignored when comparing.

## Requirements

- PostgreSQL binaries from PGDG installed on every node. For example, `pastir.postgresql` with
  `postgresql_create_main_cluster: false`, `postgresql_start_conf: manual`, `postgresql_manage_service: false`.
- A reachable etcd v3 cluster (for example `pastir.etcd`).
- All members in one play (`patroni_cluster_group`).
- Collection `community.general` (only if the watchdog is enabled).

## Variables

| Variable | Default | Description |
|---|---|---|
| `patroni_version` | `4.1.5` | Pinned package version |
| `patroni_packages` | `patroni`, `python3-etcd` | |
| `patroni_allow_upgrade` | `false` | Allow changing the installed Patroni version |
| `patroni_hold` | `true` | `apt-mark hold patroni` |
| `patroni_config_file` | `/etc/patroni/config.yml` | Debian `patroni.service` reads this file |
| `patroni_cluster_group` | `patroni` | Inventory group of the cluster |
| `patroni_scope` | — | **Required.** Cluster name |
| `patroni_namespace` | `/service` | DCS namespace |
| `patroni_name` | hostname | Member name |
| `patroni_address` | default IPv4 | Base for connect addresses |
| `patroni_restapi_listen` / `_connect_address` / `_port` | `<address>:8008` | |
| `patroni_restapi_username` / `_password` | `""` | Basic auth for unsafe endpoints. The role uses it for `PATCH /config` |
| `patroni_restapi_extra` | `{}` | `certfile`, `keyfile`, `allowlist`, ... |
| `patroni_etcd_hosts` | `[]` | **Required.** `["10.0.0.1:2379", ...]` |
| `patroni_etcd_protocol` / `patroni_etcd_extra` | `http` / `{}` | TLS and auth for etcd |
| `patroni_postgresql_version` | `15` | Used for the default paths |
| `patroni_postgresql_listen` / `_connect_address` / `_port` | `<address>:5432` | |
| `patroni_postgresql_data_dir` / `_bin_dir` | Debian layout | |
| `patroni_postgresql_authentication` | superuser + replication | **Passwords required.** Any libpq keys (`sslmode`, `sslcert`...). `rewind` is optional |
| `patroni_postgresql_parameters` | `{}` | Node-local parameters (rarely needed) |
| `patroni_postgresql_extra` | `{}` | Other keys of the `postgresql` section |
| `patroni_dcs` | ttl/loop_wait/... | Dynamic configuration, see above |
| `patroni_dcs_manage` | `true` | Keep the running configuration in sync |
| `patroni_initdb` | UTF8, en_US.UTF-8, checksums | For a brand-new cluster |
| `patroni_watchdog` | `{mode: off}` | `automatic`/`required` also loads softdog (`patroni_watchdog_softdog`) and sets up a udev rule |
| `patroni_tags` | `{}` | `nofailover`, `noloadbalance`, `clonefrom`, `nosync`... |
| `patroni_config_overrides` | `{}` | Deep-merged into the generated config last |
| `patroni_pg_start_conf_manual` | `true` | Force `start.conf` = `manual` |
| `patroni_restart_pending` | `false` | Restart members with `pending_restart` (replicas first) |
| `patroni_wait_timeout` | `600` | Seconds to wait for a member / leader |

## Example

```yaml
- hosts: pg_cluster
  become: true
  roles:
    - role: pastir.postgresql
      vars:
        postgresql_minor_version: "15.19"
        postgresql_create_main_cluster: false
        postgresql_start_conf: manual
        postgresql_manage_service: false
    - role: pastir.patroni
      vars:
        patroni_cluster_group: pg_cluster
        patroni_scope: main-cluster
        patroni_etcd_hosts: ["10.0.0.1:2379", "10.0.0.2:2379", "10.0.0.3:2379"]
        patroni_restapi_username: patroni
        patroni_restapi_password: "{{ vault_patroni_api_password }}"
        patroni_postgresql_authentication:
          superuser: {username: postgres, password: "{{ vault_pg_super }}", sslmode: require}
          replication: {username: replicator, password: "{{ vault_pg_repl }}", sslmode: verify-full,
                        sslrootcert: /var/lib/postgresql/ssl/ca.crt}
          rewind: {username: rewind_user, password: "{{ vault_pg_rewind }}"}
        patroni_dcs:
          ttl: 30
          loop_wait: 10
          retry_timeout: 10
          maximum_lag_on_failover: 1048576
          postgresql:
            use_pg_rewind: true
            use_slots: true
            parameters:
              max_connections: 200
              shared_buffers: 4GB
              ssl: "on"
              wal_keep_segments: null   # remove an obsolete parameter
            pg_hba:
              - local all all peer
              - hostssl all all 0.0.0.0/0 scram-sha-256
```

### Taking over an existing cluster

1. Reproduce the current local `config.yml` with variables. Use `patroni_config_overrides` for anything unusual.
2. Copy `patronictl show-config` into `patroni_dcs`.
3. Run with `--check --diff`. The config diff is hidden (passwords), so compare the rendered file manually if needed.
4. Apply. Local changes are reloaded one member at a time, and DCS differences are applied with a single PATCH.

### Converting a standalone server

Start Patroni first on the server that holds the data (with `postgresql.data_dir` pointing to it).
Patroni takes over the existing data directory as the leader. Then add the other members with **empty** data
directories: they clone from the leader. Do not add members with old data directories. If a member reports a
system ID mismatch, run `patronictl reinit <scope> <member>` manually.

## Testing

`molecule test`: 3 nodes (Ubuntu 24.04 and 26.04), each running etcd + PostgreSQL 15 + Patroni. The test covers
bootstrap, idempotence, DCS patch (change, delete, pg_hba) without restart, the pending-restart report, a local
reload without restart or failover, and replication.

## Installation

```yaml
# requirements.yml
roles:
  - name: pastir.patroni
    src: git+git@github.com:Pastir/ansible-role-patroni.git
    version: main  # or a tag
```

```bash
ansible-galaxy install -r requirements.yml
```

## License

MIT-0
