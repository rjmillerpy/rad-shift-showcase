"""Load the backend's secrets into SSM Parameter Store (item 12, go-live tool).

The secret names come from the "Secrets" section of .env.example, the single
list that tests/test_env_example.py also checks against what ECS injects.
Each becomes a SecureString parameter /radshift/<NAME> (Standard tier: free;
encrypted with the AWS-managed key: free). Values are never printed.

    # read-only: which parameters exist?
    python scripts/sync_ssm_secrets.py --check --profile radshift-admin
    # write them from a production env file (never commit it)
    python scripts/sync_ssm_secrets.py --apply --env-file .env.production --profile radshift-admin
"""

import argparse
import re
import sys
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
SECRETS_HEADER = "# --- Secrets"
DEFAULT_PREFIX = "/radshift"
DEFAULT_REGION = "us-east-2"  # matches infra/variables.tf
JWT_SECRET_NAME = "JWT_SECRET"  # nosec B105 - an env var name, not a secret
MIN_JWT_SECRET_BYTES = 32  # same rule as app/common/constants.py
SSM_CONNECT_TIMEOUT_SECONDS = 5
SSM_READ_TIMEOUT_SECONDS = 15
SSM_GET_BATCH = 10  # GetParameters accepts at most 10 names


def secret_names(example: Path = ENV_EXAMPLE) -> list[str]:
    """Variable names listed after the Secrets header, in file order."""
    text = example.read_text()
    if SECRETS_HEADER not in text:
        raise ValueError(f"{example} has no {SECRETS_HEADER!r} section")
    section = text.split(SECRETS_HEADER, 1)[1]
    return re.findall(r"^([A-Z][A-Z0-9_]*)=", section, re.M)


def parameter_name(prefix: str, name: str) -> str:
    return f"{prefix}/{name}"


def check(ssm, prefix: str, names: list[str]) -> dict[str, bool]:
    """Which parameters exist. Read-only, and doesn't decrypt anything."""
    found: set[str] = set()
    for start in range(0, len(names), SSM_GET_BATCH):
        batch = [parameter_name(prefix, n) for n in names[start : start + SSM_GET_BATCH]]
        response = ssm.get_parameters(Names=batch, WithDecryption=False)
        found |= {p["Name"] for p in response["Parameters"]}
    return {name: parameter_name(prefix, name) in found for name in names}


def validate(values: dict[str, str | None], names: list[str]) -> list[str]:
    """Problems with the values to upload; empty if none. Never includes a value."""
    problems = [f"{n} is missing or empty" for n in names if not values.get(n)]
    jwt = values.get(JWT_SECRET_NAME) or ""
    if jwt and len(jwt.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
        problems.append(f"{JWT_SECRET_NAME} is shorter than {MIN_JWT_SECRET_BYTES} bytes")
    return problems


def apply(ssm, prefix: str, values: dict[str, str], names: list[str]) -> list[str]:
    """Write every secret as a SecureString, replacing any existing value."""
    for name in names:
        ssm.put_parameter(
            Name=parameter_name(prefix, name),
            Value=values[name],
            Type="SecureString",
            Tier="Standard",
            Overwrite=True,
            Description="rad-shift backend secret (scripts/sync_ssm_secrets.py)",
        )
    return [parameter_name(prefix, n) for n in names]


def _client(profile: str | None, region: str):
    session = boto3.Session(profile_name=profile, region_name=region)
    config = BotoConfig(
        connect_timeout=SSM_CONNECT_TIMEOUT_SECONDS, read_timeout=SSM_READ_TIMEOUT_SECONDS
    )
    return session.client("ssm", config=config)


def main(argv: list[str] | None = None, ssm=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="report which parameters exist (read-only)"
    )
    mode.add_argument("--apply", action="store_true", help="write the parameters from --env-file")
    parser.add_argument(
        "--env-file", type=Path, help="env file holding the production values (--apply)"
    )
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--profile", default=None, help="AWS CLI profile, e.g. radshift-admin")
    args = parser.parse_args(argv)

    names = secret_names()
    ssm = ssm or _client(args.profile, args.region)

    if args.check:
        status = check(ssm, args.prefix, names)
        for name, exists in status.items():
            print(f"{'present' if exists else 'MISSING'}  {parameter_name(args.prefix, name)}")
        return 0 if all(status.values()) else 1

    if not args.env_file:
        parser.error("--apply needs --env-file")
    values = dotenv_values(args.env_file)
    problems = validate(values, names)
    if problems:
        for problem in problems:
            print(f"refusing: {problem}", file=sys.stderr)
        return 2
    for written in apply(ssm, args.prefix, {n: str(values[n]) for n in names}, names):
        print(f"written  {written}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
