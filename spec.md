# Specification: Ansible Role for Patroni

## 1. Core Workflow & Development Principles
* **Role Persona:** Designed and maintained by an **expert Ansible role engineer**, following industry best practices, high idempotency standards, and clean architecture principles.
* **Scope:** The role is responsible **strictly** for managing Patroni and its systemd service. PostgreSQL and Etcd installations are handled by separate, independent roles.
* **Planning First:** Before writing or modifying any code, a clear **step-by-step work plan** must always be proposed and presented to the user for approval.
* **Documentation Maintenance:** Whenever changes are applied, discussed, or finalized, the `spec.md` file must be updated immediately to ensure it remains accurate and serves as the single source of truth.
* **Modularity & Standards:** Uses **only official Ansible core modules** (`ansible.builtin.*`). No community collections.
* **Configuration Flexibility:** Supports two operational modes via a variable switch:
  1. **Default Mode:** Generates `patroni.yml` using a built-in Jinja2 template and variables (supporting a list of Etcd hosts).
  2. **Custom Mode:** Deploys a user-defined custom configuration file. Requires `patroni_custom_config_src` to be set.
* **Code Quality:** Fully compliant with `ansible-lint` and `yamllint`.

## 2. Technical Details & Decisions
* **Installation Method:** Uses OS package manager to install the `patroni` package from PostgreSQL repositories. No `pip` or virtualenv is used.
* **Preflight Checks:** The role checks for the presence of the `postgres` binary at `patroni_postgresql_bin_dir` on the target node before proceeding. Also detects whether PGDATA is already initialized (`PG_VERSION` file check).
* **Bootstrap Primary Mode:** A special mode (`patroni_bootstrap_primary: true`) designates a node as the **primary/master** of the cluster. Supports two sub-scenarios:
  1. **New cluster (PGDATA empty):** Patroni runs `initdb` using `bootstrap.initdb` config, initializes the cluster, and becomes leader.
  2. **Existing database (PGDATA initialized):** Patroni skips `initdb`, takes over the existing database as-is, registers in DCS and becomes the cluster master. Replicas will clone from this node.
  In both cases the role waits on the `/leader` REST endpoint to confirm the primary has been elected.
* **Replica Data Directory Wipe:** When a node is a **replica** (not the primary) and its `PGDATA` is non-empty, the role automatically wipes the data directory before starting Patroni, allowing Patroni to perform a clean `pg_basebackup` from the primary. Controlled by `patroni_replica_wipe_datadir` (default: `true`). Set to `false` only if Patroni should handle existing replica data itself.
* **Etcd Support:** Uses Etcd API v3 natively via the Patroni `etcd3:` configuration block.
* **Initdb:** The template generates a `bootstrap.initdb` block with explicit `encoding`, `locale`, and `data-checksums`.
* **pg_hba:** Managed via `bootstrap.dcs.postgresql.pg_hba` — Patroni writes it to DCS and applies cluster-wide.
* **Watchdog:** Supported via `patroni_watchdog_mode` variable. When set to `automatic` or `required`, a `watchdog:` block is rendered in the config.
* **Node Tags:** Supported via `patroni_tags` dict.
* **connect_address vs listen:** `restapi` and `postgresql` sections support separate `connect_address` (public/external IP) from `listen` (bind address). Controlled by `patroni_restapi_connect_address` and `patroni_postgresql_connect_address`.

## 3. User Provisioning
* **Task file:** `tasks/users.yml` + `templates/patroni_users.sql.j2`
* **Execution:** Only on the primary host (`inventory_hostname == patroni_primary_host`)
* **Timing:**
  - **Existing DB:** runs BEFORE Patroni starts (PostgreSQL still standalone)
  - **New cluster:** runs AFTER Patroni bootstrap (PostgreSQL managed by Patroni)
* **Idempotency:** Uses `DO $$ IF NOT EXISTS $$` — users are created only if they do not exist. Passwords are never updated on existing users.
* **Users created:**
  1. Patroni superuser (`patroni_postgresql_superuser_username`)
  2. Replication user (`patroni_postgresql_replication_username`)
  3. Rewind user (`patroni_postgresql_rewind_username`) — optional
  4. Additional users from `patroni_db_users` list
* **pg_rewind grants:** `GRANT EXECUTE ON FUNCTION pg_catalog.*` — idempotent (no error if already granted)
* **Security:** SQL script is templated to a `mode: 0600` temp file, executed via `psql -f`, then deleted. Passwords never appear in process arguments.

## 4. Variable Reference

### Variable Naming Convention
* Public variables: `patroni_*` — defined in `defaults/main.yml`, intended to be overridden by the user.
* Private/internal variables: `_patroni_*` — defined in `vars/main.yml`, not intended to be overridden.

### Internal Variables (`vars/main.yml`)
| Variable | Value |
|---|---|
| `_patroni_config_file` | `{{ patroni_config_dir }}/{{ patroni_config_filename }}` |
| `_patroni_service_name` | `patroni` |
| `_patroni_bin` | `/usr/bin/patroni` |

### Key Public Variables (`defaults/main.yml`)

#### Configuration Mode
| Variable | Default | Description |
|---|---|---|
| `patroni_custom_config` | `false` | Switch between template mode and custom file mode |
| `patroni_custom_config_src` | `""` | Path to custom config file. **Required** when `patroni_custom_config: true` |

#### DCS Settings (`bootstrap.dcs`)
| Variable | Default | Description |
|---|---|---|
| `patroni_dcs_ttl` | `30` | TTL for DCS leader key |
| `patroni_dcs_loop_wait` | `10` | Patroni loop interval (seconds) |
| `patroni_dcs_retry_timeout` | `10` | DCS operation retry timeout |
| `patroni_dcs_maximum_lag_on_failover` | `1048576` | Max replica lag before failover exclusion (bytes) |
| `patroni_dcs_synchronous_mode` | `false` | Enable synchronous replication mode |
| `patroni_dcs_use_slots` | `true` | Use replication slots |

#### Etcd (`patroni_etcd_hosts`)
List of objects. `port` is optional (default `2379`):
```yaml
patroni_etcd_hosts:
  - host: 10.0.0.1
    port: 2379
```

#### Addresses
| Variable | Default | Description |
|---|---|---|
| `patroni_bind_address` | `ansible_default_ipv4.address` | Local bind address (listen) |
| `patroni_restapi_connect_address` | `""` | Public REST API address. Falls back to `patroni_bind_address` |
| `patroni_postgresql_connect_address` | `""` | Public PG address. Falls back to `patroni_bind_address` |

#### PostgreSQL users (`patroni_db_users`)
```yaml
patroni_db_users:
  - name: appuser
    password: secret
    options: "LOGIN NOSUPERUSER"  # optional, default: LOGIN
```

#### Watchdog
| Variable | Default | Description |
|---|---|---|
| `patroni_watchdog_mode` | `off` | `off` \| `automatic` \| `required` |
| `patroni_watchdog_device` | `/dev/watchdog` | Watchdog device path |
| `patroni_watchdog_safety_margin` | `5` | Safety margin (seconds) |

#### Node Tags (`patroni_tags`)
```yaml
patroni_tags:
  nofailover: false
  noloadbalance: false
  clonefrom: false
  nosync: false
```

## 5. Assert Logic
1. `patroni_cluster_name`, `patroni_postgresql_superuser_password`, `patroni_postgresql_replication_password` — always required.
2. `patroni_etcd_hosts` must be non-empty — only in default (template) mode.
3. `patroni_custom_config_src` must be non-empty — only when `patroni_custom_config: true`.
4. `patroni_primary_host` must be non-empty — only when `patroni_bootstrap_primary: true`.
5. `patroni_postgresql_rewind_password` must be set — when `patroni_postgresql_rewind_username` is defined.
6. `patroni_watchdog_mode` — must be one of `off`, `automatic`, `required`.