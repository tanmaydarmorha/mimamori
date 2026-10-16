"""Entry point: `uvicorn conversation_svc.main:app`. Model, speech and URLs come from config."""

import logging

from .app import create_conversation_app

logging.basicConfig(level=logging.INFO)
app = create_conversation_app()
