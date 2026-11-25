"""ci/jenkins/ and the Jenkinsfile: the local Jenkins's configuration (item 35).

The pipeline itself is exercised by running it (ci/jenkins/README.md,
drills); these pin the choices a careless edit would quietly undo.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
JENKINS = ROOT / "ci" / "jenkins"
PLUGIN = re.compile(r"^[a-z0-9-]+:[A-Za-z0-9._-]+$")


def plugin_lines() -> list[str]:
    lines = (JENKINS / "plugins.txt").read_text().splitlines()
    return [line for line in lines if line.strip() and not line.startswith("#")]


def test_every_plugin_is_pinned_once():
    lines = plugin_lines()
    unpinned = [line for line in lines if not PLUGIN.match(line)]
    assert unpinned == []
    names = [line.split(":")[0] for line in lines]
    assert len(names) == len(set(names))
    # The ones the pipeline uses directly. A lockfile once dropped them (the
    # resolver lists dependencies separately) and JCasC silently did nothing.
    assert {"configuration-as-code", "job-dsl", "workflow-aggregator", "git", "ssh-slaves",
            "junit", "coverage", "timestamper", "ws-cleanup"} <= set(names)  # fmt: skip


def test_the_controller_runs_no_builds():
    casc = yaml.safe_load((JENKINS / "casc.yaml").read_text())
    assert casc["jenkins"]["numExecutors"] == 0
    (node,) = casc["jenkins"]["nodes"]
    assert node["permanent"]["labelString"] == "python"


def test_no_secret_is_in_the_configuration():
    casc = (JENKINS / "casc.yaml").read_text()
    secrets = re.findall(r"\$\{(readFile|readFileBase64):(/run/secrets/[a-z-]+)\}", casc)
    assert {path for _, path in secrets} == {
        "/run/secrets/admin-password",
        "/run/secrets/agent-key",
        "/run/secrets/kind-kubeconfig",
    }
    assert "-----BEGIN" not in casc, "no key or certificate pasted in (PEM block)"


def test_jenkins_is_published_on_loopback_only():
    compose = yaml.safe_load((ROOT / "compose.jenkins.yaml").read_text())
    for service in compose["services"].values():
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:"), port


def test_the_secrets_folder_is_gitignored():
    assert "/ci/jenkins/.secrets/" in (ROOT / ".gitignore").read_text().splitlines()


def test_the_pipeline_waits_for_approval_without_holding_an_agent():
    jenkinsfile = (ROOT / "Jenkinsfile").read_text()
    assert re.search(r"pipeline \{\s*(//[^\n]*\n\s*)*agent none", jenkinsfile)
    deploy = jenkinsfile[jenkinsfile.index("stage('Deploy to staging')") :]
    assert deploy.index("input {") < deploy.index("agent { label 'python' }")
    assert "unstash 'chart'" in deploy, "deploys the packaged chart, not a fresh checkout"
