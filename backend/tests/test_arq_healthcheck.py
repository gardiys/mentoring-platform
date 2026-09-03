from __future__ import annotations

from unittest.mock import Mock, patch

from redis.exceptions import ConnectionError

from app.arq_healthcheck import arq_worker_is_healthy, main


def test_arq_worker_is_healthy_when_heartbeat_exists() -> None:
    client = Mock()
    client.get.return_value = b"worker health"

    with patch("app.arq_healthcheck.Redis.from_url", return_value=client) as from_url:
        assert arq_worker_is_healthy("redis://redis:6379/0", "worker:health") is True

    from_url.assert_called_once_with(
        "redis://redis:6379/0",
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    client.get.assert_called_once_with("worker:health")
    client.close.assert_called_once_with()


def test_arq_worker_is_unhealthy_when_heartbeat_is_missing() -> None:
    client = Mock()
    client.get.return_value = None

    with patch("app.arq_healthcheck.Redis.from_url", return_value=client):
        assert arq_worker_is_healthy("redis://redis:6379/0", "worker:health") is False

    client.close.assert_called_once_with()


def test_arq_worker_is_unhealthy_when_redis_is_unavailable() -> None:
    client = Mock()
    client.get.side_effect = ConnectionError("unavailable")

    with patch("app.arq_healthcheck.Redis.from_url", return_value=client):
        assert arq_worker_is_healthy("redis://redis:6379/0", "worker:health") is False

    client.close.assert_called_once_with()


def test_main_requires_redis_url(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("REDIS_URL", raising=False)

    assert main([]) == 1


def test_main_uses_requested_health_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")

    with patch("app.arq_healthcheck.arq_worker_is_healthy", return_value=True) as check:
        assert main(["notifications:health"]) == 0

    check.assert_called_once_with("redis://redis:6379/0", "notifications:health")
