"""The hub as a module-level ASGI app, for uvicorn behind the Lambda Web Adapter."""

from suresay.hub import build_app

app = build_app()
