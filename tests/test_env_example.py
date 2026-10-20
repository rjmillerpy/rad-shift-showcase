"""`.env.example` is the single list of the backend's environment variables.

Fails when code reads a variable the example doesn't document, when the
example lists one nothing reads (stale entries like SUPABASE_KEY lingered
for months), or when the secrets it lists differ from what the ECS task
definition injects (infra/).
"""

import ast
import re
from pathlib import Path

from scripts.sync_ssm_secrets import SECRETS_HEADER, secret_names

ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE = ROOT / ".env.example"
ENV_READERS = {
    "getenv",
    "get",
    "_required",
    "_required_secret",
}  # os.getenv, os.environ.get, config helpers
# Scripts that never run inside the backend: their variables belong to
# another environment, so they don't go in the backend's .env.example.
NOT_BACKEND_ENVIRONMENT = {
    ROOT / "scripts" / "deploy.py",  # the CD runner's (RADSHIFT_ENV_FILE, GITHUB_STEP_SUMMARY)
}


def _string_constants(tree: ast.Module) -> dict[str, str]:
    return {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _names_read_by_code() -> set[str]:
    names: set[str] = set()
    for path in {
        *ROOT.glob("app/**/*.py"),
        *ROOT.glob("scripts/**/*.py"),
    } - NOT_BACKEND_ENVIRONMENT:
        tree = ast.parse(path.read_text())
        constants = _string_constants(tree)
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and node.args):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in ENV_READERS or (name == "get" and "environ" not in ast.unparse(func)):
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                names.add(arg.value)
            elif isinstance(arg, ast.Name) and arg.id in constants:
                names.add(constants[arg.id])
            elif isinstance(arg, ast.Name) and arg.id in imported:
                names.add(_imported_constant(arg.id))
    return {n for n in names if n.isupper()}


def _imported_constant(name: str) -> str:
    for path in ROOT.glob("app/**/constants.py"):
        constants = _string_constants(ast.parse(path.read_text()))
        if name in constants:
            return constants[name]
    raise AssertionError(f"env var name {name!r} is imported but not defined in any constants.py")


def _names_in_example() -> set[str]:
    return set(re.findall(r"^([A-Z][A-Z0-9_]*)=", ENV_EXAMPLE.read_text(), re.M))


def _secrets_in_terraform() -> set[str]:
    infra = ROOT / "infra"
    ssm_list = re.search(
        r"backend_ssm_secret_names\s*=\s*\[([^\]]*)\]", (infra / "locals.tf").read_text()
    )
    db_secret = re.search(
        r'db_password_secret_name\s*=\s*"([A-Z_]+)"', (infra / "database.tf").read_text()
    )
    assert ssm_list and db_secret, "infra secret lists not found; update this test"
    return set(re.findall(r'"([A-Z_]+)"', ssm_list.group(1))) | {db_secret.group(1)}


def test_every_variable_the_code_reads_is_documented():
    missing = _names_read_by_code() - _names_in_example()
    assert not missing, f"read by code but missing from .env.example: {sorted(missing)}"


def test_example_lists_nothing_the_code_ignores():
    stale = _names_in_example() - _names_read_by_code()
    assert not stale, f"in .env.example but read by no code: {sorted(stale)}"


def test_the_scanner_finds_known_variables():
    """Guards the guard: if the AST scan broke, the two tests above would pass vacuously."""
    assert {
        "DB_PASSWORD",
        "JWT_SECRET",
        "ADMIN_SECRET",
        "WIDGET_SERVER_EXECUTION_ENABLED",
        "S3_BUCKET_NAME",
    } <= _names_read_by_code()


def test_excluded_scripts_exist():
    """Keeps the exclusion list from collecting entries for scripts that are gone."""
    assert all(path.is_file() for path in NOT_BACKEND_ENVIRONMENT)


def test_secrets_section_matches_what_ecs_injects():
    assert SECRETS_HEADER in ENV_EXAMPLE.read_text()
    assert set(secret_names(ENV_EXAMPLE)) == _secrets_in_terraform()
