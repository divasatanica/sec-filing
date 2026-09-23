#!/usr/bin/env python3
"""Create an Alembic migration from ORM changes, then apply it locally.

Run from any directory with:
    uv run python scripts/migrate.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_alembic(*arguments: str) -> None:
    """Run Alembic through the same Python environment as this script."""

    subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
    )


def main() -> int:
    message = input("Migration message: ").strip()
    if not message:
        print("Migration cancelled: a message is required.", file=sys.stderr)
        return 1

    try:
        print("\nCreating migration from ORM changes...")
        run_alembic("revision", "--autogenerate", "-m", message)

        print("\nApplying all pending migrations...")
        run_alembic("upgrade", "head")
    except subprocess.CalledProcessError as error:
        print(f"\nMigration failed (exit code {error.returncode}).", file=sys.stderr)
        return error.returncode or 1

    print("\nMigration created and database upgraded to head.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
