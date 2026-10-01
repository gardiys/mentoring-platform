import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def reset_database():
    yield


@pytest.mark.parametrize(
    "provider,key,success",
    [
        ("nexara", "NEXARA_API_KEY", True),
        ("soniox", "SONIOX_API_KEY", True),
        ("soniox", "NEXARA_API_KEY", False),
        ("nexara", "SONIOX_API_KEY", False),
        ("fake", "SONIOX_API_KEY", False),
    ],
)
def test_production_preflight_requires_only_selected_provider_key(tmp_path, provider, key, success):
    env = {
        "DOMAIN": "platform.test.org",
        "CADDY_EMAIL": "ops@test.org",
        "POSTGRES_PASSWORD": "p" * 32,
        "REDIS_PASSWORD": "r" * 32,
        "DATABASE_URL": "postgresql+asyncpg://app:secret@postgres:5432/mentoring",
        "BOT_INTEGRATION_TOKEN": "b" * 32,
        "WEB_SESSION_SECRET": "s" * 32,
        "TELEGRAM_BOT_TOKEN": "test-token",
        "TELEGRAM_BOT_URL": "https://t.me/test_bot",
        "TELEGRAM_WEB_CLIENT_ID": "123",
        "TELEGRAM_WEB_CLIENT_SECRET": "test-secret",
        "S3_BUCKET": "test",
        "S3_ACCESS_KEY_ID": "test",
        "S3_SECRET_ACCESS_KEY": "test-secret",
        "TRANSCRIPTION_PROVIDER": provider,
        key: "test-api-key",
        "INTERVIEW_AI_PROVIDER": "openai",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_ANALYSIS_MODEL": "model",
        "OPENAI_EXTRACTION_MODEL": "model",
    }
    path = tmp_path / "production.env"
    path.write_text("\n".join(f"{key}={value}" for key, value in env.items()) + "\n")
    script = Path(__file__).resolve().parents[2] / "infra/prod-preflight.sh"
    if not script.exists():
        pytest.skip("Infrastructure scripts are tested from the repository checkout")
    result = subprocess.run(
        ["sh", str(script), str(path)], capture_output=True, text=True, timeout=10
    )
    assert (result.returncode == 0) == success, result.stderr
