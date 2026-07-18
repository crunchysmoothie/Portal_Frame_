"""Start the PortalFrame FastAPI backend and Flet web UI together.

PyCharm setup:
    Script path:       run_designer.py
    Working directory: project root
    Python interpreter: .venv314
"""

from __future__ import annotations

import socket
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen

import flet as ft
import uvicorn

from ui.main import main as flet_main


HOST = "127.0.0.1"
API_PORT = 8000
UI_PORT = 8550
API_HEALTH_URL = f"http://{HOST}:{API_PORT}/api/health"
UI_URL = f"http://{HOST}:{UI_PORT}"


def _require_free_port(port: int) -> None:
    """Fail early with a useful message when another server owns a port."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        if probe.connect_ex((HOST, port)) == 0:
            raise RuntimeError(
                f"Port {port} is already in use. Stop the existing "
                "PortalFrame run in PyCharm and try again."
            )


def _wait_for_api(thread: threading.Thread, timeout_seconds: float = 10.0) -> None:
    """Wait until FastAPI is healthy or fail with its startup condition."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not thread.is_alive():
            raise RuntimeError(
                "FastAPI stopped during startup. Review the PyCharm Run output."
            )
        try:
            with urlopen(API_HEALTH_URL, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, URLError):
            time.sleep(0.1)
    raise RuntimeError(
        f"FastAPI did not become healthy at {API_HEALTH_URL} within "
        f"{timeout_seconds:g} seconds."
    )


def run() -> None:
    """Run both local services until the Flet application is stopped."""

    _require_free_port(API_PORT)
    _require_free_port(UI_PORT)

    api_config = uvicorn.Config(
        "backend.main:app",
        host=HOST,
        port=API_PORT,
        log_level="info",
    )
    api_server = uvicorn.Server(api_config)
    api_thread = threading.Thread(
        target=api_server.run,
        name="portalframe-api",
        daemon=True,
    )

    print("Starting PortalFrame API...")
    api_thread.start()
    try:
        _wait_for_api(api_thread)
        print(f"FastAPI ready: {API_HEALTH_URL}")
        print(f"Starting PortalFrame UI: {UI_URL}")
        ft.run(
            flet_main,
            host=HOST,
            port=UI_PORT,
            view=ft.AppView.WEB_BROWSER,
        )
    finally:
        print("Stopping PortalFrame API...")
        api_server.should_exit = True
        api_thread.join(timeout=5)


if __name__ == "__main__":
    run()
