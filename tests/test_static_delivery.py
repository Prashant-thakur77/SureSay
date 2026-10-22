"""The web client is served compressed, hashed assets are cached for good, and the page itself is always fresh."""

from __future__ import annotations

import re

import pytest

from .conftest import ROOT_DIR, Hub

DIST = ROOT_DIR / "web" / "dist"


@pytest.mark.skipif(not (DIST / "index.html").exists(), reason="web client not built")
def test_assets_are_compressed_and_cached_and_the_page_is_fresh(hub: Hub) -> None:
    page = hub.http.get("/", headers={"accept-encoding": "gzip"})
    assert page.status_code == 200 and "no-cache" in page.headers.get("cache-control", "")
    asset = re.search(r'/assets/[\w.-]+\.js', page.text)
    assert asset, "the page names its script"
    r = hub.http.get(asset.group(0), headers={"accept-encoding": "gzip"})
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"
    assert "immutable" in r.headers.get("cache-control", "") and "max-age=31536000" in r.headers["cache-control"]


def test_mcp_is_never_compressed(hub: Hub) -> None:
    r = hub.http.post("/mcp", headers={"accept-encoding": "gzip"}, json={})
    assert r.headers.get("content-encoding") != "gzip"
