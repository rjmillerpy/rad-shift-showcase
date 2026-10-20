"""scripts/sync_ssm_secrets.py against Moto's in-memory SSM (no AWS, no cost)."""

import boto3
import pytest
from moto import mock_aws

from scripts import sync_ssm_secrets as sync

NAMES = ["DB_PASSWORD", "JWT_SECRET", "RESEND_API_KEY", "ANTHROPIC_API_KEY", "ADMIN_SECRET"]
GOOD_VALUES = {
    "DB_PASSWORD": "db-pass-value",
    "JWT_SECRET": "j" * 64,
    "RESEND_API_KEY": "re_value",
    "ANTHROPIC_API_KEY": "sk-ant-value",
    "ADMIN_SECRET": "admin-secret-value",
}


@pytest.fixture
def ssm(monkeypatch):
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(var, "testing")  # moto: never touch real credentials
    with mock_aws():
        yield boto3.client("ssm", region_name="us-east-2")


@pytest.fixture
def env_file(tmp_path):
    def _write(values: dict[str, str]) -> str:
        path = tmp_path / ".env.production"
        path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
        return str(path)

    return _write


class TestSecretNames:
    def test_reads_the_secrets_section_of_env_example(self):
        assert sync.secret_names() == NAMES

    def test_example_without_the_section_is_an_error(self, tmp_path):
        bad = tmp_path / ".env.example"
        bad.write_text("FOO=\n")
        with pytest.raises(ValueError, match="Secrets"):
            sync.secret_names(bad)


class TestCheck:
    def test_reports_missing_then_present(self, ssm, env_file, capsys):
        assert sync.main(["--check"], ssm=ssm) == 1
        assert capsys.readouterr().out.count("MISSING") == len(NAMES)

        assert sync.main(["--apply", "--env-file", env_file(GOOD_VALUES)], ssm=ssm) == 0
        assert sync.main(["--check"], ssm=ssm) == 0
        assert "MISSING" not in capsys.readouterr().out


class TestApply:
    def test_writes_securestring_parameters_with_the_values(self, ssm, env_file):
        assert sync.main(["--apply", "--env-file", env_file(GOOD_VALUES)], ssm=ssm) == 0
        for name, value in GOOD_VALUES.items():
            param = ssm.get_parameter(Name=f"/radshift/{name}", WithDecryption=True)["Parameter"]
            assert param["Type"] == "SecureString"
            assert param["Value"] == value

    def test_never_prints_a_value(self, ssm, env_file, capsys):
        sync.main(["--apply", "--env-file", env_file(GOOD_VALUES)], ssm=ssm)
        sync.main(["--check"], ssm=ssm)
        output = capsys.readouterr()
        for value in GOOD_VALUES.values():
            assert value not in output.out + output.err

    def test_overwrites_on_rotation(self, ssm, env_file):
        sync.main(["--apply", "--env-file", env_file(GOOD_VALUES)], ssm=ssm)
        rotated = {**GOOD_VALUES, "ADMIN_SECRET": "rotated-admin-secret"}
        assert sync.main(["--apply", "--env-file", env_file(rotated)], ssm=ssm) == 0
        param = ssm.get_parameter(Name="/radshift/ADMIN_SECRET", WithDecryption=True)["Parameter"]
        assert param["Value"] == "rotated-admin-secret"
        assert param["Version"] == 2

    @pytest.mark.parametrize(
        ("change", "problem"),
        [
            ({"ADMIN_SECRET": ""}, "ADMIN_SECRET is missing"),
            ({"JWT_SECRET": "short"}, "JWT_SECRET is shorter than 32 bytes"),
        ],
        ids=["empty-value", "weak-jwt-secret"],
    )
    def test_refuses_bad_values_and_writes_nothing(self, ssm, env_file, capsys, change, problem):
        assert (
            sync.main(["--apply", "--env-file", env_file({**GOOD_VALUES, **change})], ssm=ssm) == 2
        )
        assert problem in capsys.readouterr().err
        assert sync.check(ssm, "/radshift", NAMES) == dict.fromkeys(NAMES, False)

    def test_apply_requires_an_env_file(self, ssm):
        with pytest.raises(SystemExit):
            sync.main(["--apply"], ssm=ssm)
