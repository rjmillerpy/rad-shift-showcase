"""Deploy published images to the local compose stack (item 17, CD in $0 mode).

Run by .github/workflows/deploy.yml on the self-hosted runner, or by hand
with the same AWS access (ECR pull) the workflow has:

    python3 scripts/deploy.py --registry <account>.dkr.ecr.us-east-2.amazonaws.com \\
        [--backend-tag <sha>] [--frontend-tag <sha>]

1. Resolve each tag (none given: the newest image in ECR) and check it exists.
2. Remember which images are running now.
3. Pull the new images, start them and wait for every health check
   (compose --wait), then check both services from the host.
4. If anything fails, start the previous images again and exit non-zero.

Database migrations run when the backend container starts
(docker-entrypoint.sh) and a rollback does not undo them. A schema change
must keep working with the previous image: add first, deploy, and remove
what the old code needed only in a later release (expand, then contract).

Standard library only, so the runner needs python3, docker and the AWS CLI,
not the app's virtualenv. At go-live the same steps become
`aws ecs update-service` (ECS does the health-gated rollout and the
rollback itself, with its deployment circuit breaker).
"""

import argparse
import json
import os
import re
import subprocess  # nosec B404 - fixed argument lists, never a shell
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "radshift"  # compose.yaml's `name:`: the stack you run locally
COMPOSE_FILES = ("compose.yaml", "compose.deploy.yaml")
COMPONENTS = ("backend", "frontend")
IMAGE_VARIABLES = {"backend": "BACKEND_IMAGE", "frontend": "FRONTEND_IMAGE"}
ENV_FILE_VARIABLE = "RADSHIFT_ENV_FILE"
# Published by compose.yaml on the host; checked after compose's own health checks.
HEALTH_URLS = ("http://127.0.0.1:5000/health", "http://127.0.0.1:3000/api/health")
# A commit SHA, short or full. Tags arrive from a workflow_dispatch form.
TAG_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
NO_IMAGE = "None"  # what `--output text` prints for an empty query result
WAIT_SECONDS = 240  # the backend's start_period is 60 s; migrations can add more
COMMAND_TIMEOUT_SECONDS = WAIT_SECONDS + 60
PROBE_TIMEOUT_SECONDS = 5
HTTP_OK = 200
ERROR_TAIL_CHARS = 2000

Images = dict[str, str]  # component -> image reference
Runner = Callable[[Sequence[str], Mapping[str, str]], str]
Probe = Callable[[str], bool]


class DeployError(Exception):
    """A deploy step failed; the message says which and why."""


def run_command(args: Sequence[str], env: Mapping[str, str]) -> str:
    """Run a command from the repository root and return its stdout."""
    try:
        result = subprocess.run(  # nosec B603 - fixed argument lists, never a shell
            list(args),
            cwd=ROOT,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        raise DeployError(
            f"{' '.join(args[:3])} failed:\n{exc.stderr[-ERROR_TAIL_CHARS:]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DeployError(
            f"{' '.join(args[:3])} timed out after {COMMAND_TIMEOUT_SECONDS} s"
        ) from exc
    return result.stdout


def http_ok(url: str) -> bool:
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected - only HEALTH_URLS (fixed 127.0.0.1 http URLs)
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_SECONDS) as response:  # nosec B310 - fixed local URLs
            return response.status == HTTP_OK
    except (urllib.error.URLError, OSError):
        return False


def repository(component: str) -> str:
    return f"{PROJECT}-{component}"  # created by infra/registry/


def resolve_tag(run: Runner, component: str, tag: str) -> str:
    """The tag to deploy: the one given (if it exists in ECR) or the newest."""
    describe = ["aws", "ecr", "describe-images", "--repository-name", repository(component)]
    if not tag:
        query = "sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]"
        newest = run([*describe, "--query", query, "--output", "text"], {}).strip()
        if newest in ("", NO_IMAGE):
            raise DeployError(
                f"{repository(component)} has no images yet; run its publish workflow first"
            )
        return newest
    if not TAG_PATTERN.fullmatch(tag):
        raise DeployError(f"{component} tag {tag!r} is not a commit SHA")
    try:
        run([*describe, "--image-ids", f"imageTag={tag}", "--output", "text"], {})
    except DeployError as exc:
        raise DeployError(
            f"{repository(component)}:{tag} is not in ECR (expired, or never published)"
        ) from exc
    return tag


def compose(run: Runner, images: Images, env_file: str, *args: str) -> str:
    files = [arg for name in COMPOSE_FILES for arg in ("-f", name)]
    env = {IMAGE_VARIABLES[c]: images[c] for c in COMPONENTS} | {ENV_FILE_VARIABLE: env_file}
    return run(["docker", "compose", "-p", PROJECT, *files, *args], env)


def running_images(run: Runner) -> Images:
    """Image of each running app container; empty when the stack is down."""
    output = run(["docker", "compose", "-p", PROJECT, "ps", "--format", "json", *COMPONENTS], {})
    containers = [json.loads(line) for line in output.splitlines() if line.strip()]
    return {c["Service"]: c["Image"] for c in containers if c.get("State") == "running"}


def start(run: Runner, images: Images, env_file: str, *, pull: bool) -> None:
    if pull:
        compose(run, images, env_file, "pull", *COMPONENTS)
    compose(
        run, images, env_file,
        "up", "--detach", "--no-build", "--pull", "missing",
        "--wait", "--wait-timeout", str(WAIT_SECONDS),
        *COMPONENTS,
    )  # fmt: skip


def verify(run: Runner, probe: Probe, images: Images) -> list[str]:
    """Problems with the running stack; empty if it serves the expected images."""
    problems = [f"{url} is not answering 200" for url in HEALTH_URLS if not probe(url)]
    running = running_images(run)
    problems += [
        f"{c} runs {running.get(c, 'nothing')}, expected {images[c]}"
        for c in COMPONENTS
        if running.get(c) != images[c]
    ]
    return problems


def roll_back(run: Runner, probe: Probe, previous: Images, env_file: str) -> str:
    """Start the previous images again; a one-line outcome for the report."""
    if set(previous) != set(COMPONENTS):
        return "no rollback: the stack wasn't fully running before this deploy"
    try:
        start(run, previous, env_file, pull=False)
    except DeployError as exc:
        return f"rollback FAILED: {exc}"
    problems = verify(run, probe, previous)
    return (
        f"rollback FAILED: {'; '.join(problems)}"
        if problems
        else "rolled back to the previous images"
    )


def deploy(run: Runner, probe: Probe, images: Images, env_file: str) -> tuple[bool, str]:
    """Health-gated deploy with automatic rollback. Returns (succeeded, report)."""
    previous = running_images(run)
    if previous == images:
        return True, "already running these images; nothing to do"
    try:
        start(run, images, env_file, pull=True)
        problems = verify(run, probe, images)
    except DeployError as exc:
        problems = [str(exc)]
    if not problems:
        return True, "deployed; health checks pass"
    return (
        False,
        f"deploy failed: {'; '.join(problems)}\n{roll_back(run, probe, previous, env_file)}",
    )


def write_summary(images: Images, report: str) -> None:
    """The run's summary page on GitHub, when running in Actions."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    rows = "".join(f"| {c} | `{images[c]}` |\n" for c in COMPONENTS)
    with open(path, "a", encoding="utf-8") as summary:
        summary.write(f"### Local deploy\n\n| Service | Image |\n|---|---|\n{rows}\n{report}\n")


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deploy published images to the local compose stack."
    )
    parser.add_argument(
        "--registry", required=True, help="<account>.dkr.ecr.<region>.amazonaws.com"
    )
    for component in COMPONENTS:
        parser.add_argument(
            f"--{component}-tag", default="", help="commit SHA; default: the newest image"
        )
    parser.add_argument(
        "--env-file",
        default=os.environ.get(ENV_FILE_VARIABLE, ""),
        help=f"the backend's .env (default: ${ENV_FILE_VARIABLE})",
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None, run: Runner = run_command, probe: Probe = http_ok
) -> int:
    args = parse_args(argv)
    if not args.env_file or not Path(args.env_file).is_file():
        print(
            f"error: --env-file or ${ENV_FILE_VARIABLE} must name the backend's .env",
            file=sys.stderr,
        )
        return 1
    try:
        tags = {c: resolve_tag(run, c, getattr(args, f"{c}_tag")) for c in COMPONENTS}
    except DeployError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    images = {c: f"{args.registry}/{repository(c)}:{tags[c]}" for c in COMPONENTS}
    succeeded, report = deploy(run, probe, images, args.env_file)
    print(report)
    write_summary(images, report)
    return 0 if succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
