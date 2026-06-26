"""Unit tests for the R2 cloud-backup config resolver.

These cover the two common UX traps the field labels invite:
  1. Operator drops ``bucket/prefix`` (no s3:// scheme) into either field.
  2. Operator pastes the provider's HTTPS endpoint into ``offsite_s3_url``
     instead of into ``integrations.s3_endpoint``.

The resolver must recover from both without changing behaviour for an
existing correctly-configured deployment.
"""

from __future__ import annotations

import pytest

from app.services import r2_service


# _split_bucket_prefix --------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", ("", "")),
        ("   ", ("", "")),
        ("s3://bucket", ("bucket", "")),
        ("s3://bucket/", ("bucket", "")),
        ("s3://bucket/folder", ("bucket", "folder")),
        ("s3://bucket/folder/sub", ("bucket", "folder/sub")),
        ("bucket/folder", ("bucket", "folder")),
        ("bucket/folder/sub", ("bucket", "folder/sub")),
        ("bucket", ("bucket", "")),
        # Trailing / leading slashes stripped
        ("/bucket/folder/", ("bucket", "folder")),
        # The user's actual screenshot value
        ("pugfinapp/legal-backup", ("pugfinapp", "legal-backup")),
        ("s3://pugfinapp/legal-backup", ("pugfinapp", "legal-backup")),
    ],
)
def test_split_bucket_prefix(raw: str, expected: tuple[str, str]) -> None:
    assert r2_service._split_bucket_prefix(raw) == expected


# _resolve_config -------------------------------------------------------------

class _StubDB:
    """Minimal stand-in for the Session - r2_service only reads settings
    via settings_service.get_str, which we monkeypatch in the fixture."""


@pytest.fixture
def fake_settings(monkeypatch):
    store: dict[str, str] = {}

    def get_str(_db, key: str, default: str = "") -> str:
        return store.get(key, default)

    monkeypatch.setattr(r2_service.settings_service, "get_str", get_str)
    return store


def test_resolve_happy_path(fake_settings) -> None:
    """The intended config: cloud_folder + endpoint set on the right
    fields, access/secret on the Backup card."""
    fake_settings.update(
        {
            "backup.cloud_folder": "s3://pugfinapp/legal-backup",
            "integrations.s3_endpoint": "https://x.r2.cloudflarestorage.com",
            "backup.offsite_s3_access_key": "AK",
            "backup.offsite_s3_secret_key": "SK",
        }
    )
    bucket, prefix, endpoint, ak, sk = r2_service._resolve_config(_StubDB())
    assert bucket == "pugfinapp"
    assert prefix == "legal-backup"
    assert endpoint == "https://x.r2.cloudflarestorage.com"
    assert ak == "AK"
    assert sk == "SK"


def test_resolve_recovers_from_https_in_offsite_s3_url(fake_settings) -> None:
    """The exact mistake from the user's screenshot: HTTPS endpoint
    pasted into ``offsite_s3_url`` and bucket/prefix in cloud_folder."""
    fake_settings.update(
        {
            "backup.cloud_folder": "pugfinapp/legal-backup",
            "backup.offsite_s3_url": "https://x.r2.cloudflarestorage.com",
            # integrations.s3_endpoint deliberately left empty
            "backup.offsite_s3_access_key": "AK",
            "backup.offsite_s3_secret_key": "SK",
        }
    )
    bucket, prefix, endpoint, _, _ = r2_service._resolve_config(_StubDB())
    assert bucket == "pugfinapp"
    assert prefix == "legal-backup"
    assert endpoint == "https://x.r2.cloudflarestorage.com"


def test_resolve_legacy_backwards_compat(fake_settings) -> None:
    """A pre-fix deployment with only offsite_s3_url + integrations.s3_endpoint
    set must keep working exactly as before."""
    fake_settings.update(
        {
            "backup.offsite_s3_url": "s3://legacy-bucket/legacy-prefix",
            "integrations.s3_endpoint": "https://s3.amazonaws.com",
            "backup.offsite_s3_access_key": "AK",
            "backup.offsite_s3_secret_key": "SK",
        }
    )
    bucket, prefix, endpoint, _, _ = r2_service._resolve_config(_StubDB())
    assert bucket == "legacy-bucket"
    assert prefix == "legacy-prefix"
    assert endpoint == "https://s3.amazonaws.com"


def test_resolve_reports_missing_pieces(fake_settings) -> None:
    """Nothing set -> every piece comes back empty so the caller can
    name each missing field in the error message."""
    bucket, prefix, endpoint, ak, sk = r2_service._resolve_config(_StubDB())
    assert (bucket, prefix, endpoint, ak, sk) == ("", "", "", "", "")
