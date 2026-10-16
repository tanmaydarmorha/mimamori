"""ASGI entry point: `uvicorn core_bank_mock.main:app`."""

from .app import create_core_bank_app

app = create_core_bank_app()
