"""
Tests for ConnectionManager — verifies session-based HTTP client behavior.
"""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from requests import Session

from src.connection_pool import ConnectionManager


class TestConnectionManagerInit(unittest.TestCase):
    """Test initialization and session creation."""

    def test_default_init(self):
        cm = ConnectionManager(firecrawl_api_key="test-key-123")
        self.assertIsNotNone(cm._session)
        self.assertEqual(cm._max_connections, 5)
        self.assertEqual(cm._max_retries, 3)
        self.assertEqual(cm._backoff_factor, 1.0)

    def test_custom_init(self):
        cm = ConnectionManager(
            firecrawl_api_key="key",
            max_connections=10,
            max_retries=5,
            backoff_factor=2.0,
        )
        self.assertEqual(cm._max_connections, 10)
        self.assertEqual(cm._max_retries, 5)
        self.assertEqual(cm._backoff_factor, 2.0)

    def test_session_has_auth_header(self):
        cm = ConnectionManager(firecrawl_api_key="my-api-key")
        self.assertIn("Authorization", cm._session.headers)
        self.assertEqual(cm._session.headers["Authorization"], "Bearer my-api-key")

    def test_session_has_content_type(self):
        cm = ConnectionManager(firecrawl_api_key="test-key")
        self.assertEqual(cm._session.headers["Content-Type"], "application/json")


class TestTimeoutConfig(unittest.TestCase):
    """Test per-request-type timeout configuration."""

    def test_search_timeout(self):
        cm = ConnectionManager(firecrawl_api_key="key")
        self.assertEqual(cm._get_timeout("search"), 15)

    def test_scrape_timeout(self):
        cm = ConnectionManager(firecrawl_api_key="key")
        self.assertEqual(cm._get_timeout("scrape"), 45)

    def test_default_timeout(self):
        cm = ConnectionManager(firecrawl_api_key="key")
        self.assertEqual(cm._get_timeout("default"), 30)

    def test_unknown_type_timeout(self):
        cm = ConnectionManager(firecrawl_api_key="key")
        self.assertEqual(cm._get_timeout("unknown"), 30)


class TestPost(unittest.TestCase):
    """Test POST request behavior."""

    @patch.object(Session, "post")
    def test_post_calls_session(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        cm = ConnectionManager(firecrawl_api_key="key")
        resp = cm.post("https://api.example.com/test", json={"key": "val"})

        mock_post.assert_called_once()
        self.assertEqual(resp.status_code, 200)

    @patch.object(Session, "post")
    def test_post_with_search_timeout(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        cm = ConnectionManager(firecrawl_api_key="key")
        cm.post("https://api.example.com/search", request_type="search")

        call_kwargs = mock_post.call_args
        self.assertEqual(call_kwargs.kwargs.get("timeout") or call_kwargs[1].get("timeout"), 15)

    @patch.object(Session, "post")
    def test_post_with_custom_timeout(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        cm = ConnectionManager(firecrawl_api_key="key")
        cm.post("https://api.example.com/test", timeout=99)

        call_kwargs = mock_post.call_args
        self.assertEqual(call_kwargs.kwargs.get("timeout") or call_kwargs[1].get("timeout"), 99)

    @patch.object(Session, "post")
    def test_post_increments_request_count(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)

        cm = ConnectionManager(firecrawl_api_key="key")
        cm.post("https://api.example.com/test")
        cm.post("https://api.example.com/test")

        self.assertEqual(cm._total_requests, 2)

    @patch.object(Session, "post")
    def test_post_increments_error_count_on_exception(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")

        cm = ConnectionManager(firecrawl_api_key="key")
        with self.assertRaises(Exception):
            cm.post("https://api.example.com/test")

        self.assertEqual(cm._total_errors, 1)


class TestGet(unittest.TestCase):
    """Test GET request behavior."""

    @patch.object(Session, "get")
    def test_get_calls_session(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        cm = ConnectionManager(firecrawl_api_key="key")
        resp = cm.get("https://api.example.com/test")

        mock_get.assert_called_once()
        self.assertEqual(resp.status_code, 200)


class TestClose(unittest.TestCase):
    """Test session cleanup."""

    @patch.object(Session, "close")
    def test_close_calls_session_close(self, mock_close):
        cm = ConnectionManager(firecrawl_api_key="key")
        cm.close()
        mock_close.assert_called_once()


class TestContextManager(unittest.TestCase):
    """Test context manager protocol."""

    @patch.object(Session, "close")
    @patch.object(Session, "post")
    def test_context_manager(self, mock_post, mock_close):
        mock_post.return_value = MagicMock(status_code=200)

        with ConnectionManager(firecrawl_api_key="key") as cm:
            cm.post("https://api.example.com/test")

        mock_close.assert_called_once()


class TestGetStats(unittest.TestCase):
    """Test statistics reporting."""

    def test_stats_structure(self):
        cm = ConnectionManager(firecrawl_api_key="key")
        stats = cm.get_stats()
        expected_keys = {
            "total_requests", "total_errors",
            "max_connections", "max_retries", "backoff_factor",
        }
        self.assertEqual(set(stats.keys()), expected_keys)

    @patch.object(Session, "post")
    def test_stats_after_requests(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)

        cm = ConnectionManager(firecrawl_api_key="key")
        cm.post("https://api.example.com/test")
        cm.post("https://api.example.com/test")

        stats = cm.get_stats()
        self.assertEqual(stats["total_requests"], 2)
        self.assertEqual(stats["total_errors"], 0)


class TestSessionReuse(unittest.TestCase):
    """Test that the session object is reused across requests."""

    @patch.object(Session, "post")
    def test_same_session_used(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)

        cm = ConnectionManager(firecrawl_api_key="key")
        session_id_1 = id(cm._session)
        cm.post("https://api.example.com/test")
        session_id_2 = id(cm._session)
        cm.post("https://api.example.com/test2")

        # Session object should be the same instance
        self.assertEqual(session_id_1, session_id_2)


if __name__ == "__main__":
    unittest.main()
