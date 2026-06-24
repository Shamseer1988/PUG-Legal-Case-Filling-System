"""Storage / backup paths must resolve to the same absolute folder no
matter where uvicorn is launched from.

Regression: an earlier ``Path(p).resolve()`` anchored relative paths
(``../storage``) against the current working directory. Switching CWD
between runs sent uploads to different physical folders, so uploaded
branding logos and case attachments looked "wiped" after every restart.
"""

import os
from pathlib import Path

from app.core import config


def test_relative_storage_path_anchored_to_backend_root(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_LOCAL_PATH", "../storage")
    monkeypatch.setenv("BACKUP_LOCAL_PATH", "../backups")
    config.get_settings.cache_clear()
    cfg = config.get_settings()

    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent

    # Both should resolve relative to the backend root, not the test's CWD.
    cwd_before = os.getcwd()
    os.chdir(tmp_path)
    try:
        assert cfg.storage_path == (project_root / "storage").resolve()
        assert cfg.backup_path == (project_root / "backups").resolve()

        # And the same after switching CWD again
        nested = tmp_path / "nested"
        nested.mkdir()
        os.chdir(nested)
        assert cfg.storage_path == (project_root / "storage").resolve()
        assert cfg.backup_path == (project_root / "backups").resolve()
    finally:
        os.chdir(cwd_before)
        config.get_settings.cache_clear()


def test_absolute_storage_path_respected(monkeypatch, tmp_path):
    abs_storage = tmp_path / "abs-storage"
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(abs_storage))
    config.get_settings.cache_clear()
    cfg = config.get_settings()
    assert cfg.storage_path == abs_storage.resolve()
    config.get_settings.cache_clear()
