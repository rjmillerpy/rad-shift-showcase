# Ansible: provision a server and deploy rad-shift

Roadmap item 38. One playbook (`site.yml`) turns a fresh Debian server into one running
rad-shift's API and database. It runs for free against a local target: a systemd Debian
container reached over SSH (`target/`), which stands in for a VPS. A real VPS would cost about
$4–5 a month, so that's deferred. The playbook doesn't know the difference: point
`inventories/` at a real address and nothing else changes.

```sh
uv tool install --exclude-newer 2026-11-11 "ansible-core==2.22.0" --with "ansible-lint==26.11.0" --with-executables-from ansible-lint
ansible/test.sh          # fresh target, provision, provision again (must report changed=0), check
ansible/test.sh down     # remove the target and its Docker data
```

## What it does

| Role | Tasks |
|---|---|
| `base` | packages (incl. unattended-upgrades); a `deploy` user without sudo; SSH hardening (no root login, keys only), **validated with `sshd -t` before it's put in place**, since a broken sshd config locks you out |
| `docker` | Docker's apt signing key, **checked by fingerprint before it's trusted**; Docker's repository (deb822 format); Docker Engine and the Compose plugin; log rotation in `daemon.json`; the service; `deploy` in the docker group |
| `app` | `/opt/radshift`, a `.env` from the vault (mode 600), the Compose file; the API image; `docker compose up --wait`; a health check |

The API image is **shipped from the control machine** (`docker save`, copy, `docker load`) —
but only if the server doesn't already have that exact image ID. That's the air-gapped way, and
it needs no registry credentials on the server. The usual way is to pull from a registry;
item 39 covers that.

The API listens on the server's loopback only. A reverse proxy with TLS (like `caddy/` in this
repo) would face the internet.

## Secrets

`inventories/local/group_vars/app_servers/vault.yml` is encrypted with **ansible-vault** and
committed: the database password and the JWT secret. Its password is in `.secrets/vault-password`
(gitignored), which `test.sh` makes and passes in as `ANSIBLE_VAULT_PASSWORD_FILE`.

It's deliberately not set in `ansible.cfg`: there it would be required even to lint, and CI
lints with no password. On a team the password would live in a password manager or a secrets
store, read by a vault-password script.

## Drills (2026-11-25)

- **Fresh server:**
  - First run: 27 tasks, 21 changed.
  - Second run: **`changed=0`**. The test fails on anything else.
  - Total: 2 min 9 s.
  - The API answered `{"status":"ok"}` from the server, and both containers were healthy.
- **SSH hardening checked from outside:** root gets `Permission denied (publickey)`, and
  `sshd -T` shows `permitrootlogin no`, `passwordauthentication no`.
- **Configuration drift:**
  - I re-enabled root login by hand on the server.
  - The next run showed the diff (`-PermitRootLogin yes` / `+PermitRootLogin no`), changed only
    that file, and restarted SSH through the handler (`changed=2`).
  - Root login was off again.

### What broke along the way (failure stories)

1. **Docker Engine couldn't pull `postgres:16` inside the target:** "failed to extract layer to
   overlayfs".
   - overlayfs can't stack on the container's own overlay root.
   - I'd put `/var/lib/docker` on a volume, but Docker 29 keeps images in **containerd**
     (`/var/lib/containerd`), which was still on the overlay.
   - Both are volumes now.
2. **A check that couldn't fail:** under `set -o pipefail`, `ssh … | grep -q … && echo refused`
   never printed, because ssh's expected exit code failed the pipeline. Worse, the `&&` meant
   `set -e` didn't stop the script either, so a broken hardening check would have passed
   silently. The output is now captured first and the check exits 1 on a mismatch.
3. **The vault password file in `ansible.cfg` made linting need the secret.** It moved to an
   environment variable set by `test.sh`.

## Interview points

- **Ansible vs Terraform (the classic question):**
  - Terraform **provisions infrastructure** (creates the server, network, DNS) and keeps state.
  - Ansible **configures what exists** (packages, users, files, services). It's agentless over
    SSH, has no state, and checks the live system on every run.
  - They're often used together: Terraform creates the VPS, its output feeds Ansible's
    inventory, and Ansible configures it.
- **How a playbook is organised:**
  - inventory (hosts and groups, `group_vars` and `host_vars`);
  - playbooks, plays, roles and tasks;
  - modules vs `command`/`shell` (a module knows whether it changed anything; a command needs
    `changed_when`);
  - handlers, which run once at the end and only when notified;
  - facts.
- **Idempotency:**
  - It's the core idea: the playbook describes the end state, and re-running it is safe.
  - `changed=0` on a second run is how you test that.
  - `--check --diff` is a dry run.
- **Drift:** hand edits get reverted on the next run. Some teams schedule runs so drift can't
  linger.
- **Tooling around it:**
  - Vault for secrets.
  - `ansible-lint` profiles.
  - Molecule for testing roles (it automates what `test.sh` does, against containers or VMs).
  - Collections, pinned.
  - Pull mode (`ansible-pull`) vs push.
- **Where it fits now:** in a container world Ansible mostly configures the hosts that run the
  containers (or Kubernetes nodes), not the app inside them.
