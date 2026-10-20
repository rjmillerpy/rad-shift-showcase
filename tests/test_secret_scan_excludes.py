"""The paths trufflehog skips are the same everywhere it runs.

CI's scans read .trufflehog-exclude.txt (--exclude-paths). The pre-commit
hook can't: trufflehog ignores --exclude-paths for files named on the
command line, so the hook carries the same paths as its own `exclude:`.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_FILE = ROOT / ".trufflehog-exclude.txt"
WORKFLOWS = [ROOT / ".github" / "workflows" / name for name in ("ci.yml", "secret-scan.yml")]


def _file_patterns() -> set[str]:
    lines = EXCLUDE_FILE.read_text().splitlines()
    return {line for line in lines if line.strip() and not line.startswith("#")}


def _hook_patterns() -> set[str]:
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hook = next(h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "trufflehog")
    return set(hook["exclude"].split("|"))


def test_hook_excludes_what_ci_excludes():
    assert _hook_patterns() == _file_patterns()


def test_every_ci_scan_reads_the_exclude_file():
    for workflow in WORKFLOWS:
        assert f"--exclude-paths={EXCLUDE_FILE.name}" in workflow.read_text(), workflow.name


def test_every_exclusion_is_explained():
    """A comment naming each path, so none is added without a reason."""
    comments = "\n".join(
        line for line in EXCLUDE_FILE.read_text().splitlines() if line.startswith("#")
    )
    for pattern in _file_patterns():
        plain = pattern.strip("^$").replace("\\.", ".")
        assert plain in comments, f"{pattern} has no reason in {EXCLUDE_FILE.name}"
