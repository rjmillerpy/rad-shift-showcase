"""Build the image variants Lambda's deployment zip (roadmap item 27).

    uv run python scripts/build_lambda.py            # -> dist/image_variants.zip

The zip holds the package at its repository path (lambdas/image_variants/,
so the handler is lambdas.image_variants.handler.handler) and Pillow built
for the Lambda runtime: Python 3.12 on arm64 (Graviton, about 20% cheaper
than x86). The Pillow version is the backend's own pin in pyproject.toml,
so the API and the Lambda decode images the same way. boto3 is left out:
the runtime provides it.

Reproducible: entries are sorted and dated 1980-01-01, so the same code
gives the same zip and the same hash, and Terraform only redeploys the
function when something in it changed.
"""

import argparse
import shutil
import subprocess  # nosec B404 - runs uv with fixed arguments, never a shell
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path("lambdas") / "image_variants"
DEFAULT_OUTPUT = ROOT / "dist" / "image_variants.zip"
# AWS's python3.12 runtime on arm64 (Amazon Linux 2023, glibc 2.34).
PYTHON_VERSION = "3.12"
PLATFORM = "aarch64-manylinux_2_28"
FIXED_DATE = (1980, 1, 1, 0, 0, 0)  # the earliest a zip can hold


def pinned(package: str) -> str:
    """The `package==version` requirement from pyproject.toml's dependencies."""
    dependencies = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    for requirement in dependencies:
        if requirement.lower().startswith(f"{package.lower()}=="):
            return str(requirement)
    raise LookupError(f"{package} is not pinned in pyproject.toml")


def install_dependencies(target: Path) -> None:
    uv = shutil.which("uv") or "uv"
    subprocess.run(  # noqa: S603 # nosec B603
        [
            uv,
            "pip",
            "install",
            "--quiet",
            "--target",
            str(target),
            "--python-version",
            PYTHON_VERSION,
            "--python-platform",
            PLATFORM,
            "--only-binary",
            ":all:",
            pinned("pillow"),
        ],
        check=True,
    )


def copy_package(target: Path) -> None:
    (target / "lambdas").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "lambdas" / "__init__.py", target / "lambdas" / "__init__.py")
    shutil.copytree(ROOT / PACKAGE, target / PACKAGE, ignore=shutil.ignore_patterns("__pycache__"))


def write_zip(source: Path, output: Path) -> None:
    """Zip `source` reproducibly: sorted entries, fixed dates and permissions."""
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(
        path for path in source.rglob("*") if path.is_file() and "__pycache__" not in path.parts
    )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            entry = zipfile.ZipInfo(path.relative_to(source).as_posix(), FIXED_DATE)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, path.read_bytes())


def build(output: Path) -> None:
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        install_dependencies(work)
        copy_package(work)
        write_zip(work, output)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    build(args.output)
    print(f"built {args.output} ({args.output.stat().st_size // 1024} KiB)", file=sys.stderr)  # noqa: T201


if __name__ == "__main__":
    main()
