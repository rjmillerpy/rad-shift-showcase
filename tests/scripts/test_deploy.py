"""scripts/deploy.py: the health-gated local deploy and its rollback.

The docker and AWS CLIs are the external boundary, so they are replaced by
FakeHost, a small model of ECR's contents and the running stack. Everything
else runs for real, through main(). run_command and http_ok, the two
adapters to that boundary, are tested against a real subprocess and a real
HTTP server.
"""

import http.server
import json
import socket
import threading
from collections.abc import Iterator, Mapping, Sequence

import pytest

from scripts import deploy

REGISTRY = "123456789012.dkr.ecr.us-east-2.amazonaws.com"
OLD = {"backend": "a" * 40, "frontend": "b" * 40}
NEW = {"backend": "c" * 40, "frontend": "d" * 40}


def image(component: str, tag: str) -> str:
    return f"{REGISTRY}/radshift-{component}:{tag}"


def images(tags: Mapping[str, str]) -> dict[str, str]:
    return {c: image(c, t) for c, t in tags.items()}


class FakeHost:
    """ECR (tags per repository, oldest first) and the compose stack."""

    def __init__(self) -> None:
        self.ecr = {
            "radshift-backend": [OLD["backend"], NEW["backend"]],
            "radshift-frontend": [OLD["frontend"], NEW["frontend"]],
        }
        self.running: dict[str, str] = images(OLD)
        self.unhealthy: set[str] = (
            set()
        )  # images whose health check never passes (compose --wait fails)
        self.not_serving: set[str] = set()  # images healthy inside, but not answering on the host
        self.pull_error = ""  # e.g. a registry rate limit
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    def run(self, args: Sequence[str], env: Mapping[str, str]) -> str:
        args = list(args)
        self.calls.append((args, dict(env)))
        if args[:3] == ["aws", "ecr", "describe-images"]:
            return self._describe(args)
        if "ps" in args:
            return "".join(
                json.dumps({"Service": s, "Image": i, "State": "running"}) + "\n"
                for s, i in self.running.items()
            )
        if "pull" in args:
            return self._pull(env)
        if "up" in args:
            return self._up(env)
        raise AssertionError(f"unexpected command {args}")

    def _describe(self, args: list[str]) -> str:
        tags = self.ecr[args[args.index("--repository-name") + 1]]
        if "--query" in args:
            return (tags[-1] if tags else "None") + "\n"
        tag = args[args.index("--image-ids") + 1].removeprefix("imageTag=")
        if tag not in tags:
            raise deploy.DeployError("ImageNotFoundException")
        return "IMAGEDETAILS\n"

    def _pull(self, env: Mapping[str, str]) -> str:
        if self.pull_error:
            raise deploy.DeployError(self.pull_error)
        for variable in ("BACKEND_IMAGE", "FRONTEND_IMAGE"):
            repo, tag = env[variable].rsplit("/", 1)[1].split(":")
            if tag not in self.ecr[repo]:
                raise deploy.DeployError("manifest unknown")
        return ""

    def _up(self, env: Mapping[str, str]) -> str:
        self.running = {"backend": env["BACKEND_IMAGE"], "frontend": env["FRONTEND_IMAGE"]}
        if self.unhealthy & set(self.running.values()):
            raise deploy.DeployError("dependency failed to start: container is unhealthy")
        return ""

    def probe(self, url: str) -> bool:
        return not (self.not_serving & set(self.running.values()))

    def commands(self, word: str) -> list[tuple[list[str], dict[str, str]]]:
        return [(args, env) for args, env in self.calls if word in args]


@pytest.fixture
def host() -> FakeHost:
    return FakeHost()


@pytest.fixture
def env_file(tmp_path) -> str:
    path = tmp_path / ".env"
    path.write_text("JWT_SECRET=test\n")
    return str(path)


@pytest.fixture(autouse=True)
def summary(tmp_path, monkeypatch):
    path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    return path


def run_deploy(host: FakeHost, env_file: str, *extra: str) -> int:
    return deploy.main(
        ["--registry", REGISTRY, "--env-file", env_file, *extra], run=host.run, probe=host.probe
    )


def tag_args(tags: Mapping[str, str]) -> list[str]:
    return [f"--{c}-tag={t}" for c, t in tags.items()]


class TestDeploys:
    def test_no_tags_deploys_the_newest_image_of_each(self, host, env_file):
        host.ecr["radshift-frontend"] = [NEW["frontend"], OLD["frontend"]]  # pushed last = newest

        assert run_deploy(host, env_file) == 0

        assert host.running == {
            "backend": image("backend", NEW["backend"]),
            "frontend": image("frontend", OLD["frontend"]),
        }

    def test_given_tags_are_pulled_then_started_with_both_compose_files(self, host, env_file):
        assert run_deploy(host, env_file, *tag_args(OLD | {"backend": NEW["backend"]})) == 0

        ((up_args, up_env),) = host.commands("up")
        assert up_args[:9] == [
            "docker",
            "compose",
            "-p",
            "radshift",
            "-f",
            "compose.yaml",
            "-f",
            "compose.deploy.yaml",
            "up",
        ]
        assert {"--no-build", "--wait"} <= set(up_args)
        assert up_env == {
            "BACKEND_IMAGE": image("backend", NEW["backend"]),
            "FRONTEND_IMAGE": image("frontend", OLD["frontend"]),
            "RADSHIFT_ENV_FILE": env_file,
        }
        assert host.commands("pull"), "new images are pulled from ECR before starting"

    def test_a_short_sha_is_accepted(self, host, env_file):
        host.ecr["radshift-backend"].append("1234abc")

        assert run_deploy(host, env_file, "--backend-tag=1234abc") == 0

        assert host.running["backend"] == image("backend", "1234abc")

    def test_running_the_same_images_again_changes_nothing(self, host, env_file, capsys):
        assert run_deploy(host, env_file, *tag_args(OLD)) == 0

        assert not host.commands("up")
        assert "nothing to do" in capsys.readouterr().out

    def test_writes_the_run_summary(self, host, env_file, summary):
        run_deploy(host, env_file, *tag_args(NEW))

        text = summary.read_text()
        assert image("backend", NEW["backend"]) in text
        assert "deployed; health checks pass" in text

    def test_outside_actions_there_is_no_summary_file(self, host, env_file, summary, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY")

        assert run_deploy(host, env_file, *tag_args(NEW)) == 0

        assert not summary.exists()


class TestRefusesBeforeTouchingTheStack:
    @pytest.mark.parametrize(
        "tag",
        ["latest", "main", "abc", "C" * 40, "a" * 41, "abc1234; docker rm -f $(docker ps -q)"],
        ids=["latest", "branch-name", "too-short", "uppercase", "too-long", "shell-injection"],
    )
    def test_a_tag_that_is_not_a_commit_sha(self, host, env_file, capsys, tag):
        assert run_deploy(host, env_file, f"--backend-tag={tag}") == 1

        assert "not a commit SHA" in capsys.readouterr().err
        assert not host.commands("up") and not host.commands("pull")

    def test_a_tag_that_is_not_in_ecr(self, host, env_file, capsys):
        assert run_deploy(host, env_file, "--frontend-tag=" + "e" * 40) == 1

        assert "is not in ECR" in capsys.readouterr().err
        assert host.running == images(OLD)

    def test_an_empty_repository(self, host, env_file, capsys):
        host.ecr["radshift-backend"] = []

        assert run_deploy(host, env_file) == 1

        assert "no images yet" in capsys.readouterr().err

    @pytest.mark.parametrize("env_value", ["", "/nonexistent/.env"], ids=["unset", "missing-file"])
    def test_no_env_file(self, host, capsys, monkeypatch, env_value):
        monkeypatch.setenv("RADSHIFT_ENV_FILE", env_value)

        assert deploy.main(["--registry", REGISTRY], run=host.run, probe=host.probe) == 1

        assert "RADSHIFT_ENV_FILE" in capsys.readouterr().err
        assert not host.calls

    def test_env_file_defaults_to_the_runner_variable(self, host, env_file, monkeypatch):
        monkeypatch.setenv("RADSHIFT_ENV_FILE", env_file)

        assert (
            deploy.main(["--registry", REGISTRY, *tag_args(NEW)], run=host.run, probe=host.probe)
            == 0
        )


class TestRollsBack:
    def test_unhealthy_new_images_put_the_previous_ones_back(self, host, env_file, capsys):
        host.unhealthy.add(image("backend", NEW["backend"]))

        assert run_deploy(host, env_file, *tag_args(NEW)) == 1

        assert host.running == images(OLD)
        out = capsys.readouterr().out
        assert "container is unhealthy" in out and "rolled back to the previous images" in out
        assert len(host.commands("pull")) == 1, (
            "the previous images are already local; rollback doesn't pull"
        )

    def test_healthy_containers_that_dont_answer_on_the_host(self, host, env_file, capsys):
        host.not_serving.add(image("frontend", NEW["frontend"]))

        assert run_deploy(host, env_file, *tag_args(NEW)) == 1

        assert host.running == images(OLD)
        assert "not answering 200" in capsys.readouterr().out

    def test_a_failed_pull_leaves_the_stack_running(self, host, env_file):
        host.pull_error = "toomanyrequests"

        assert run_deploy(host, env_file, *tag_args(NEW)) == 1

        assert host.running == images(OLD)
        assert not [args for args, _ in host.commands("up") if NEW["backend"] in " ".join(args)]

    def test_no_rollback_when_the_stack_was_not_running(self, host, env_file, capsys):
        host.running = {}
        host.unhealthy.add(image("backend", NEW["backend"]))

        assert run_deploy(host, env_file, *tag_args(NEW)) == 1

        assert "no rollback" in capsys.readouterr().out
        assert len(host.commands("up")) == 1

    def test_reports_a_rollback_that_also_fails(self, host, env_file, capsys, summary):
        host.unhealthy |= {image("backend", NEW["backend"]), image("backend", OLD["backend"])}

        assert run_deploy(host, env_file, *tag_args(NEW)) == 1

        assert "rollback FAILED" in capsys.readouterr().out
        assert "rollback FAILED" in summary.read_text()

    def test_reports_a_rollback_whose_images_dont_answer(self, host, env_file, capsys):
        host.not_serving |= {image("backend", NEW["backend"]), image("backend", OLD["backend"])}

        assert run_deploy(host, env_file, *tag_args(NEW)) == 1

        assert "rollback FAILED: http://127.0.0.1" in capsys.readouterr().out


class TestRunCommand:
    def test_returns_stdout(self):
        assert deploy.run_command(["python3", "-c", "print('hi')"], {}) == "hi\n"

    def test_passes_extra_environment(self):
        script = "import os; print(os.environ['BACKEND_IMAGE'])"
        assert deploy.run_command(["python3", "-c", script], {"BACKEND_IMAGE": "x"}) == "x\n"

    def test_failure_carries_stderr(self):
        script = "import sys; sys.stderr.write('no such image'); sys.exit(3)"
        with pytest.raises(deploy.DeployError, match="no such image"):
            deploy.run_command(["python3", "-c", script], {})

    def test_timeout(self, monkeypatch):
        monkeypatch.setattr(deploy, "COMMAND_TIMEOUT_SECONDS", 0.2)
        with pytest.raises(deploy.DeployError, match="timed out"):
            deploy.run_command(["python3", "-c", "import time; time.sleep(5)"], {})


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200 if self.path == "/health" else 503)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


class TestHttpOk:
    def test_200(self, server):
        assert deploy.http_ok(f"{server}/health")

    def test_503(self, server):
        assert not deploy.http_ok(f"{server}/other")

    def test_nothing_listening(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            free_port = sock.getsockname()[1]
        assert not deploy.http_ok(f"http://127.0.0.1:{free_port}/health")
