""".gitlab-ci.yml: the pipeline in GitLab's syntax (item 37).

gitlab-ci-local runs it (ci/gitlab/README.md); these pin the choices an
edit would quietly undo.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())
JOBS = {name: job for name, job in PIPELINE.items() if isinstance(job, dict) and "stage" in job}


def image(job: dict) -> str:
    return job.get("image") or PIPELINE[job["extends"]]["image"]


def test_every_job_has_a_known_stage():
    assert {job["stage"] for job in JOBS.values()} <= set(PIPELINE["stages"])


def test_every_image_is_pinned_by_digest():
    for name, job in JOBS.items():
        assert "@sha256:" in image(job), name


def test_deploy_is_manual_and_only_from_the_default_branch():
    deploy = JOBS["deploy-staging"]
    assert deploy["rules"] == [{"if": "$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH", "when": "manual"}]
    assert deploy["environment"]["name"] == "staging"
    assert deploy["needs"] == ["package"], "deploys the packaged chart"


def test_only_the_build_job_writes_the_cache():
    writers = [name for name, job in JOBS.items()
               if job.get("cache", PIPELINE[".python"]["cache"]).get("policy") == "pull-push"]  # fmt: skip
    assert writers == ["build"]


def test_test_results_and_coverage_reach_gitlab():
    reports = JOBS["test"]["artifacts"]["reports"]
    assert reports["junit"] == "reports/junit.xml"
    assert reports["coverage_report"]["coverage_format"] == "cobertura"
    assert JOBS["test"]["artifacts"]["when"] == "always", "failures are reported too"


def test_the_local_variables_file_is_gitignored():
    assert "/ci/gitlab/variables.yml" in (ROOT / ".gitignore").read_text().splitlines()
