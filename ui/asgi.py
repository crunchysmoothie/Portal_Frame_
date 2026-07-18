"""ASGI entry point used for browser testing without opening an OS browser."""

import flet as ft

from ui.main import main


app = ft.run(main, export_asgi_app=True)
