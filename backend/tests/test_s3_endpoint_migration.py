"""Retired FirstVDS DNS must never appear in newly signed playback/upload URLs."""

from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.interviews.uploads import InterviewUploadStore, StoredUpload


@pytest.fixture(autouse=True)
def reset_database():
    """These tests only sign URLs locally; neither a database nor S3 is used."""
    yield


@pytest.mark.parametrize(
    "endpoint",
    ["https://s3.firstvds.ru", "https://s3.firstvds.ru:443", "https://s3.firstvds.ru:443/"],
)
def test_existing_firstvds_settings_use_current_endpoint_before_signing(endpoint):
    settings = Settings(
        _env_file=None,
        app_env="test",
        s3_endpoint_url=endpoint,
        s3_public_endpoint_url=endpoint,
        s3_access_key_id="synthetic-test-key",
        s3_secret_access_key="synthetic-test-secret",
        s3_bucket="test-bucket",
    )
    store = InterviewUploadStore(settings)
    assert urlsplit(store.client.meta.endpoint_url).netloc == "firsts3.ru"
    assert urlsplit(store.public_client.meta.endpoint_url).netloc == "firsts3.ru"
    assert urlsplit(store.legacy_client.meta.endpoint_url).netloc == "firsts3.ru"
    for key, expected_path in [
        ("recordings/new.mp4", "/test-bucket/recordings/new.mp4"),
        ("external:https://s3.firstvds.ru:443/interviews/old.mp4", "/interviews/old.mp4"),
        ("external:https://firsts3.ru/interviews/old.mp4", "/interviews/old.mp4"),
    ]:
        url = urlsplit(
            store.download_url(
                StoredUpload(
                    storage_key=key, filename="record.mp4", content_type="video/mp4", size=64
                ),
                inline=True,
            )
        )
        assert url.netloc == "firsts3.ru"
        assert url.path == expected_path
        query = parse_qs(url.query)
        assert query["X-Amz-Signature"]
        assert query["response-content-type"] == ["video/mp4"]
        assert query["response-content-disposition"][0].startswith("inline;")


@pytest.mark.parametrize(
    "endpoint",
    [None, "http://localhost:9000", "https://storage.example.test", "https://firsts3.ru"],
)
def test_other_storage_endpoints_are_unchanged(endpoint):
    settings = Settings(
        _env_file=None, app_env="test", s3_endpoint_url=endpoint, s3_public_endpoint_url=endpoint
    )
    assert settings.s3_endpoint_url == endpoint
    assert settings.s3_public_endpoint_url == endpoint


@pytest.mark.parametrize(
    "url",
    [
        "https://firsts3.ru.evil.test/interviews/file.mp4",
        "https://firsts3.ru@evil.test/interviews/file.mp4",
        "https://user@firsts3.ru/interviews/file.mp4",
        "https://firsts3.ru:444/interviews/file.mp4",
        "https://firsts3.ru/other-bucket/file.mp4",
        "http://firsts3.ru/interviews/file.mp4",
        "https://firsts3.ru/interviews/file.mp4?token=unexpected",
        "https://firsts3.ru/interviews/file.mp4#fragment",
    ],
)
def test_external_media_mapping_keeps_strict_provider_and_bucket_allowlist(url):
    assert InterviewUploadStore._external_media_location("external:" + url) is None


@pytest.mark.parametrize("suffix", ["?token=unexpected", "#fragment", "\n"])
def test_endpoint_migration_does_not_hide_invalid_configuration(suffix):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="test", s3_endpoint_url="https://s3.firstvds.ru" + suffix)
