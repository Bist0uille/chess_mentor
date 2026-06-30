"""Fixture : serveur uvicorn local pour les tests E2E."""
import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session", autouse=True)
def _require_browser():
    """Skip propre de tout l'E2E si Chromium n'est pas lançable."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            pw.chromium.launch().close()
    except Exception as e:  # navigateur absent / libs système manquantes
        pytest.skip(f"navigateur Playwright indisponible : {str(e)[:120]}")


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def server_url():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    ok = False
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/", timeout=1)
            ok = True
            break
        except Exception:
            time.sleep(0.25)
    if not ok:
        proc.terminate()
        pytest.skip("serveur local non démarré")
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
