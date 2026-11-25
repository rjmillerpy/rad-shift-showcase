"""ansible/: the playbook's configuration (roadmap item 38).

ansible/test.sh runs it for real (fresh target, two runs, changed=0 on the
second); these pin choices an edit would quietly undo.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "ansible"
VAULT = ANSIBLE / "inventories" / "local" / "group_vars" / "app_servers" / "vault.yml"


def tasks(role: str) -> list[dict]:
    return yaml.safe_load((ANSIBLE / "roles" / role / "tasks" / "main.yml").read_text())


def test_every_collection_is_pinned():
    collections = yaml.safe_load((ANSIBLE / "requirements.yml").read_text())["collections"]
    assert all(c.get("version", "").count(".") == 2 for c in collections), collections


def test_secrets_are_encrypted_in_git():
    assert VAULT.read_text().startswith("$ANSIBLE_VAULT;1.1;AES256")


def test_keys_vault_password_and_collections_stay_out_of_git():
    ignored = (ROOT / ".gitignore").read_text().splitlines()
    assert {"/ansible/.secrets/", "/ansible/collections/"} <= set(ignored)


def test_host_keys_are_checked():
    assert "host_key_checking = True" in (ANSIBLE / "ansible.cfg").read_text()


def test_sshd_config_is_validated_before_it_is_used():
    """A broken sshd config would lock the playbook out of the server."""
    (hardening,) = [t for t in tasks("base") if "Harden SSH" in t["name"]]
    assert hardening["ansible.builtin.copy"]["validate"].startswith("/usr/sbin/sshd -t")
    assert "PasswordAuthentication no" in hardening["ansible.builtin.copy"]["content"]


def test_dockers_key_is_checked_by_fingerprint_before_use():
    names = [t["name"] for t in tasks("docker")]
    assert names.index("Refuse a key that isn't Docker's") < names.index(
        "Add Docker's apt repository"
    )


def test_the_image_ships_only_when_the_server_lacks_it():
    (ship,) = [t for t in tasks("app") if t.get("name") == "Ship the image if the server's differs"]
    assert "app_local_image.stdout" in ship["when"]


def test_the_settings_file_is_private():
    (env,) = [t for t in tasks("app") if "settings" in t["name"]]
    assert env["ansible.builtin.template"]["mode"] == "0600"
