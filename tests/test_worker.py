from unittest.mock import MagicMock, patch

from app.config import settings as app_settings


class TestGetQueue:
    @patch.dict("os.environ", {"REDIS_URL": ""}, clear=False)
    def test_returns_none_when_redis_url_empty(self):
        # Re-import to pick up patched env
        from app.worker import get_queue

        assert get_queue() is None

    @patch.dict("os.environ", {"REDIS_URL": ""}, clear=False)
    def test_redis_available_false_when_redis_url_empty(self):
        from app.worker import redis_available

        assert redis_available() is False


class TestValidateRedisCredentialLeak:
    @patch("app.worker._get_connection")
    def test_unreachable_error_does_not_contain_url(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_conn.ping.side_effect = ConnectionError("refused")
        mock_get_conn.return_value = mock_conn

        secret_url = "redis://:s3cret@redis.example.com:6379/0"
        with patch.object(app_settings, "REDIS_URL", secret_url):
            from app.worker import validate_redis

            error = validate_redis()
        assert error is not None
        assert "s3cret" not in error
        assert "redis.example.com" not in error
        assert "Redis is not reachable" in error

    @patch("app.worker.Worker")
    @patch("app.worker._get_connection")
    def test_no_workers_error_does_not_contain_url(self, mock_get_conn, mock_worker_cls):
        mock_conn = MagicMock()
        mock_conn.ping.return_value = True
        mock_get_conn.return_value = mock_conn
        mock_worker_cls.all.return_value = []

        secret_url = "redis://:s3cret@redis.example.com:6379/0"
        with patch.object(app_settings, "REDIS_URL", secret_url):
            from app.worker import validate_redis

            error = validate_redis()
        assert error is not None
        assert "s3cret" not in error
        assert "redis.example.com" not in error
        assert "no workers" in error.lower()
