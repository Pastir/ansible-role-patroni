# Changelog

## 2.1.0 — 2026-11

### Added
- `patroni_watchdog_udev` (default `true`, unchanged behaviour). `false`: the udev rule for the watchdog device
  is not created, changed or removed, and udev is not triggered. Independent of `patroni_watchdog_softdog`.
- Input check: `postgresql_start_conf` (pastir.postgresql), when defined, must be `manual` while
  `patroni_pg_start_conf_manual` is on.

### Changed
- `start.conf`: only the mode line is set to `manual` (`lineinfile`), the rest of the file is kept.

### Fixed
- The stock comments of `start.conf` were replaced with the role's own text (non-zero diff on existing servers).
- `start.conf` was rewritten on every run when pastir.postgresql ran on the same host (different file text).

## 2.0.0 — 2026-11

Rewrite: safe for clusters that are already running.

### BREAKING
- Removed `patroni_bootstrap_primary`, `patroni_primary_host`, `patroni_replica_wipe_datadir` and the
  replica wipe. Patroni bootstraps a new cluster by itself, and the role never deletes `PGDATA`.
- Removed user provisioning (`patroni_db_users`, SQL script). Patroni creates superuser, replication and
  rewind users at bootstrap. Application users belong to a separate role.
- Removed custom-file mode (`patroni_custom_config*`). Use `patroni_config_overrides`.
- Credentials: `patroni_postgresql_authentication` (dict with any libpq keys, including SSL) replaces
  `patroni_postgresql_{superuser,replication,rewind}_{username,password}`.
- DCS settings: one `patroni_dcs` dict replaces `patroni_dcs_*`, `patroni_postgresql_parameters` (now node-local)
  and `patroni_postgresql_pg_hba`.
- Etcd hosts are a list of `"host:port"` strings. Renamed `patroni_cluster_name` → `patroni_scope`,
  `patroni_node_name` → `patroni_name`, `patroni_bind_address` → `patroni_address` + `*_listen`.
- `patroni_watchdog_mode`/`_device`/`_safety_margin` → `patroni_watchdog` dict.

### Fixed
- **Data loss:** the old role wiped `PGDATA` on every member except `patroni_primary_host`. When no primary was
  set, that included the leader of a running cluster.
- A config change restarted Patroni and caused a failover. Now it is a rolling reload.
- `pg_hba` and parameters changed only `bootstrap.dcs`, which is ignored on a running cluster. Now they are
  applied with `PATCH /config`.
- Passwords with special characters broke YAML and SQL. The config is now generated with `to_nice_yaml`.
- SSL connection settings for superuser, replication and rewind are supported.

### Added
- Version pin and hold, upgrade guard, safe Patroni restart under `pause`.
- `start.conf` = `manual` for Debian clusters on the node.
- Config validation, watchdog setup (softdog + udev), pending-restart report and optional rolling restart.
- Molecule test of a 3-node cluster.
