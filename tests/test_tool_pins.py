"""uv is pinned in three files and must be the same version in all of them.

Dependabot's Docker updater bumps only the Dockerfile's uv image (it opened
PRs for 0.13.0 and 0.13.1 that way), which would leave CI testing with one
uv while the image builds with another.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
WORKFLOWS = [ROOT / ".github" / "workflows" / name for name in ("ci.yml", "integration.yml")]

DOCKER_UV = re.compile(r"^FROM ghcr\.io/astral-sh/uv:(\S+) AS uv$", re.M)
# `version:` on the line(s) right after a setup-uv step's `with:`.
# The action may be pinned to a commit SHA with its version as a comment.
SETUP_UV = re.compile(r"astral-sh/setup-uv@\S+(?:[ \t]+#[^\n]*)?\s+with:\s+version:\s*\"([^\"]+)\"")


def docker_uv_version(text: str) -> str:
    versions = DOCKER_UV.findall(text)
    assert len(versions) == 1, f"expected one uv stage in the Dockerfile, found {versions}"
    return versions[0]


def workflow_uv_versions(text: str) -> list[str]:
    return SETUP_UV.findall(text)


def test_every_setup_uv_step_pins_the_dockerfile_version():
    expected = docker_uv_version(DOCKERFILE.read_text())
    for workflow in WORKFLOWS:
        versions = workflow_uv_versions(workflow.read_text())
        assert versions, f"no pinned setup-uv step found in {workflow.name}"
        assert set(versions) == {expected}, (
            f"{workflow.name} pins uv {versions}, the Dockerfile {expected}"
        )


def test_scanner_reads_a_setup_uv_step():
    step = 'uses: astral-sh/setup-uv@v10.3.0\n        with:\n          version: "0.13.1"\n'
    assert workflow_uv_versions(step) == ["0.13.1"]


def test_scanner_reads_a_sha_pinned_setup_uv_step():
    step = (
        "uses: astral-sh/setup-uv@1c37ad07a6a961277cf70c0d37d6f313000f5884 # v10.3.0\n"
        '        with:\n          version: "0.13.1"\n'
    )
    assert workflow_uv_versions(step) == ["0.13.1"]


def test_scanner_reads_the_dockerfile_stage():
    assert (
        docker_uv_version("FROM ghcr.io/astral-sh/uv:0.13.1 AS uv\nFROM python:3.12-slim\n")
        == "0.13.1"
    )
