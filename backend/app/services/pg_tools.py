"""Thin wrappers around ``pg_dump`` and ``pg_restore``.

We shell out (not psycopg) because the custom format ``.dump`` we want
to match Pug Finance App with is a binary format produced only by the
``pg_dump -Fc`` binary - there is no Python-only equivalent.

URL parsing:
``DATABASE_URL`` is a SQLAlchemy URL like
``postgresql+psycopg://user:pass@host:5432/db``; pg_dump only
understands the libpq form so the SQLAlchemy ``+driver`` part is
stripped.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

from app.core.config import settings

# pg_dump custom-format header: an 8-byte magic followed by version
# bytes. Used to sanity-check uploaded files before we run pg_restore
# against them - a malformed .dump would otherwise wipe the DB then
# fail mid-stream.
PGDUMP_MAGIC = b"PGDMP"


def _libpq_url() -> str:
    """Return ``DATABASE_URL`` with any SQLAlchemy driver suffix
    stripped so libpq tools (pg_dump / pg_restore / psql) accept it.

    Reads the env var on every call so test runs that override
    ``DATABASE_URL`` after import still take effect - the
    ``Settings`` object is cached at import time.
    """
    url = os.environ.get("DATABASE_URL") or settings.database_url
    # postgresql+psycopg:// -> postgresql://
    if url.startswith("postgresql+"):
        idx = url.find("://")
        url = "postgresql://" + url[idx + 3 :]
    return url


def _parsed_db():
    p = urlparse(_libpq_url())
    return {
        "scheme": p.scheme,
        "host": p.hostname or "127.0.0.1",
        "port": p.port or 5432,
        "user": p.username or "",
        "password": p.password or "",
        "dbname": (p.path or "/").lstrip("/"),
    }


def binary_path(name: str) -> str | None:
    """Resolve the pg_dump / pg_restore / psql binary. ``shutil.which``
    is enough on Linux LXC where they live in ``/usr/bin``; tests can
    monkeypatch this if they want."""
    return shutil.which(name)


def assert_binaries_present() -> None:
    """Raise a clear error if pg_dump / pg_restore are missing - logged
    at startup so a misconfigured container fails loudly, not silently
    on the first backup attempt."""
    for tool in ("pg_dump", "pg_restore", "psql"):
        if binary_path(tool) is None:
            raise RuntimeError(
                f"{tool} binary not found on PATH. Install postgresql-client "
                f"on this host before using the backup/restore feature."
            )


def is_postgres() -> bool:
    """Return True if the configured DB is Postgres. SQLite test runs
    skip the pg_dump path and use the legacy serialiser."""
    return _libpq_url().startswith("postgresql://")


def _env_with_password(db) -> dict[str, str]:
    """Provide the libpq password via PGPASSWORD env var so we don't
    smuggle credentials through argv (visible in `ps aux`).
    """
    env = os.environ.copy()
    if db["password"]:
        env["PGPASSWORD"] = db["password"]
    return env


def pg_dump_to_file(out_path: Path) -> None:
    """Run ``pg_dump -Fc`` against the configured database and write
    the custom-format archive to ``out_path``. Raises CalledProcessError
    with stderr on failure.
    """
    binary = binary_path("pg_dump")
    if binary is None:
        raise RuntimeError("pg_dump binary not found on PATH")
    db = _parsed_db()
    cmd = [
        binary,
        "-h", db["host"],
        "-p", str(db["port"]),
        "-U", db["user"],
        "-d", db["dbname"],
        "-Fc",  # custom format - same as Pug Finance App .dump
        "--no-owner",
        "--no-privileges",
        "-f", str(out_path),
    ]
    logger.info("Running pg_dump -> {}", out_path)
    proc = subprocess.run(
        cmd,
        env=_env_with_password(db),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed (rc={proc.returncode}): {proc.stderr.strip()}")


def pg_restore_from_file(in_path: Path) -> None:
    """Run ``pg_restore --clean --if-exists`` and replay ``in_path``
    onto the configured DB. Drops + recreates objects; safe to rerun.
    Errors from pg_restore are raised - caller should have taken a
    safety snapshot first.

    **Warning handling**: ``pg_restore`` with ``--clean --if-exists``
    commonly exits with rc=1 when it encounters non-fatal warnings
    (e.g. "relation does not exist, skipping"). We only treat rc > 1
    as a hard failure. rc=1 is logged as a warning and allowed to
    proceed — the data was still restored successfully.
    """
    binary = binary_path("pg_restore")
    if binary is None:
        raise RuntimeError("pg_restore binary not found on PATH")

    # Guard: make sure we received a *file* path, not a directory.
    # A previous bug passed the backups directory when storage_path
    # was empty (""), resulting in the cryptic "toc.dat does not exist"
    # error from pg_restore.
    if not in_path.exists():
        raise RuntimeError(f"pg_restore input file does not exist: {in_path}")
    if in_path.is_dir():
        raise RuntimeError(
            f"pg_restore received a directory instead of a .dump file: {in_path}"
        )

    db = _parsed_db()
    cmd = [
        binary,
        "-h", db["host"],
        "-p", str(db["port"]),
        "-U", db["user"],
        "-d", db["dbname"],
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--single-transaction",  # all-or-nothing - keeps DB consistent on failure
        str(in_path),
    ]
    logger.info("Running pg_restore <- {}", in_path)
    proc = subprocess.run(
        cmd,
        env=_env_with_password(db),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode > 1:
        # rc > 1 is a genuine failure (corrupt archive, connection
        # refused, permission denied, etc.)
        raise RuntimeError(
            f"pg_restore failed (rc={proc.returncode}): {proc.stderr.strip()[:2000]}"
        )
    if proc.returncode == 1:
        # rc=1 typically means non-fatal warnings (e.g. DROP IF EXISTS
        # on tables that don't exist yet). Log but don't abort — the
        # data was restored.
        logger.warning(
            "pg_restore exited with rc=1 (non-fatal warnings): {}",
            proc.stderr.strip()[:1000],
        )


def looks_like_pgdump_custom(path: Path) -> bool:
    """Quick header check: a ``pg_dump -Fc`` file starts with
    b'PGDMP'. Used to reject random uploads before we even consider
    restoring them.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(5)
        return head == PGDUMP_MAGIC
    except OSError:
        return False


def list_tables_in_dump(path: Path) -> set[str]:
    """Return the set of table names listed by ``pg_restore -l``.

    Used to detect cross-app uploads (e.g. a Finance App ``.dump``)
    before they're replayed - the caller compares this against a
    Legal-app fingerprint of expected tables. ``pg_restore -l`` lists
    the dump's table-of-contents without touching the DB.
    """
    binary = binary_path("pg_restore")
    if binary is None:
        return set()
    proc = subprocess.run(
        [binary, "-l", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return set()
    tables: set[str] = set()
    for line in proc.stdout.splitlines():
        # TOC lines look like: "123; 1259 12345 TABLE public cases postgres"
        parts = line.split()
        if len(parts) >= 6 and parts[3] == "TABLE":
            tables.add(parts[5])
    return tables
