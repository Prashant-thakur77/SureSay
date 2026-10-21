"""Who is calling: the caller's address as AWS saw it, for rate limits and pairing budgets."""

from __future__ import annotations

import json
import os

from starlette.requests import Request


def client_ip(request: Request) -> str:
    """The caller's address as AWS saw it. On Lambda the function URL's request context (set by the web adapter)
    is authoritative, then the rightmost X-Forwarded-For entry (the one AWS appended). Off Lambda, the socket."""
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        try:
            ctx = json.loads(request.headers.get("x-amzn-request-context") or "{}")
            ip = (ctx.get("http") or {}).get("sourceIp") or (ctx.get("identity") or {}).get("sourceIp")
            if ip:
                return str(ip)
        except (ValueError, AttributeError):
            pass
        xff = [x.strip() for x in (request.headers.get("x-forwarded-for") or "").split(",") if x.strip()]
        if xff:
            return xff[-1]
    return request.client.host if request.client else "?"
