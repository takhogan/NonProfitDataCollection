"""The worker's /health listener, which keeps Cloud Run's startup probe happy."""
import json
import socket
import urllib.error
import urllib.request

import pytest

from scripts.worker import start_health_server


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_health_server_answers_and_shuts_down():
    port = _free_port()
    server = start_health_server(port)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as resp:
            assert resp.status == 200
            assert json.loads(resp.read()) == {"status": "ok"}
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/other", timeout=3)
        assert exc.value.code == 404
    finally:
        server.shutdown()
        server.server_close()
