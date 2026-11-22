"""Keeps .grype.yaml's ignores temporary: each one has an expiry here.

The image gate (publish.yml) skips whatever .grype.yaml ignores. The first
Firefox ignore outlived the upgrade it waited for by a month because nothing
reminded anyone; now the suite fails once an ignore's date passes.
"""

import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# package name -> last day the ignore may stay (then upgrade, or re-justify).
EXPIRES = {
    # Playwright 1.65 (Firefox 160) passes the supply-chain cooldown on 2026-11-23.
    "firefox": datetime.date(2026, 11, 30),
}


def _ignored_packages() -> set[str]:
    config = yaml.safe_load((ROOT / ".grype.yaml").read_text())
    return {rule["package"]["name"] for rule in config.get("ignore") or []}


def test_every_ignore_has_an_expiry():
    assert _ignored_packages() <= set(EXPIRES)


def test_no_ignore_is_past_its_expiry():
    today = datetime.date.today()
    expired = sorted(name for name in _ignored_packages() if EXPIRES[name] < today)
    assert not expired, f"upgrade or re-justify these .grype.yaml ignores: {expired}"
