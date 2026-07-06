"""
webserver.py — aiohttp web server for Koyeb.

Serves:
  GET /            -> status JSON (also doubles as Koyeb health check)
  GET /health      -> plain OK health check
  GET /{code}      -> countdown/landing page for a shortened URL
                       (does NOT reveal the destination URL)
  GET /r/{code}    -> server-side resolve endpoint: looks up the code and
                       issues an HTTP 302 redirect to the real destination

------------------------------------------------------------------------
ARCHITECTURE CHANGE (destination URL is no longer embedded in the page)
------------------------------------------------------------------------
Previously, GET /{code} looked the destination URL up immediately and
baked it directly into the HTML response (meta refresh, anchor href, and
an inline <script> variable). That means the destination URL was visible
in the page source the instant the countdown page loaded, before the
countdown even finished.

Now, GET /{code} only:
  1. validates the code exists (so we can show a proper "not found" page),
  2. returns the countdown page template as-is, with only the short CODE
     interpolated into it (the code is not sensitive -- it's already the
     path the visitor is on).

The destination URL itself is fetched from MongoDB for the *first* time
only when the browser makes a second, separate request to
GET /r/{code} -- which happens automatically when the countdown reaches
zero, or immediately if the visitor clicks "Open Link". That handler is
the only place `original_url` is ever read out of the database and put
into an HTTP response, and it does so via a redirect (Location header),
never via the page body. This keeps the backend as the single source of
truth for destination URLs and guarantees the destination never appears
in the initial page's HTML, JS, CSS, or any embedded JSON.

Click tracking also moves from "page was requested" to "redirect was
actually issued" (i.e. it now lives in the /r/{code} handler), which is
arguably a more accurate click count than before.
"""

import logging
import os
import re

from aiohttp import web

import db
import shortener
from config import API_KEY

logger = logging.getLogger(__name__)

# created_by value used for links created through the public HTTP API
# rather than through the Telegram bot itself.
_API_CREATED_BY = 0

_TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

with open(os.path.join(_TEMPLATE_DIR, "redirect.html"), "r", encoding="utf-8") as f:
    _REDIRECT_TEMPLATE = f.read()

with open(os.path.join(_TEMPLATE_DIR, "notfound.html"), "r", encoding="utf-8") as f:
    _NOTFOUND_TEMPLATE = f.read()

# Matches the same code shape accepted by the route patterns below.
# Used to defensively re-validate the code before using it, independent
# of aiohttp's own route matching.
_CODE_RE = re.compile(r"^[A-Za-z0-9]{3,16}$")


def _notfound_response():
    return web.Response(text=_NOTFOUND_TEMPLATE, content_type="text/html", status=404)


async def health(request):
    return web.Response(text="OK", status=200)


async def root(request):
    return web.json_response({
        "status": "running",
        "service": "URL Shortener Bot",
    })


async def redirect_handler(request):
    """
    GET /{code}

    Renders the countdown/landing page. Deliberately does NOT fetch or
    embed the destination URL -- it only confirms the code exists (so we
    can show the "not found" page for bad codes) and hands the browser a
    page whose only job is to navigate to /r/{code} once the countdown
    ends or the button is clicked.
    """
    code = request.match_info.get("code", "")

    if not _CODE_RE.match(code):
        return _notfound_response()

    link = await db.get_link(code)
    if not link:
        return _notfound_response()

    # Note: no `original_url` is read from `link` here, and nothing from
    # `link` is placed into the response -- only the already-public code.
    page = _REDIRECT_TEMPLATE.replace("__CODE__", code)
    return web.Response(text=page, content_type="text/html", status=200)


async def resolve_handler(request):
    """
    GET /r/{code}

    The ONLY place the destination URL is looked up and sent to the
    browser. Responds with an HTTP 302 redirect (Location header) rather
    than an HTML page, so the destination never appears in a document
    body -- it exists only in the redirect response's Location header,
    exactly like a classic URL shortener redirect.
    """
    code = request.match_info.get("code", "")

    if not _CODE_RE.match(code):
        return _notfound_response()

    link = await db.get_link(code)
    if not link:
        return _notfound_response()

    original_url = link["original_url"]

    # Click is now counted at the point the redirect actually happens,
    # rather than when the countdown page was merely requested.
    await db.increment_clicks(code)

    raise web.HTTPFound(location=original_url)


async def api_shorten(request):
    """
    GET /api?url={url}

    Public HTTP endpoint to create a shortened URL. Prints a JSON result
    directly in the browser, e.g.:

        GET https://domain.app/api?url=https://example.com/some/long/path

        {
          "status": "success",
          "original_url": "https://example.com/some/long/path",
          "short_url": "https://domain.app/A28UO"
        }

    If config.API_KEY is set, requests must include a matching key via
    either the "?api_key=" query parameter or the "X-API-Key" header.
    """
    if API_KEY:
        supplied = request.query.get("api_key") or request.headers.get("X-API-Key", "")
        if supplied != API_KEY:
            return web.json_response(
                {"status": "error", "message": "Invalid or missing API key."},
                status=401,
            )

    original_url = request.query.get("url", "").strip()
    if not original_url:
        return web.json_response(
            {"status": "error", "message": "Missing required 'url' query parameter."},
            status=400,
        )

    if not shortener.is_valid_url(original_url):
        return web.json_response(
            {"status": "error", "message": "Invalid URL. Must start with http:// or https://."},
            status=400,
        )

    try:
        short_url = await shortener.create_short_link(original_url, _API_CREATED_BY)
    except Exception as e:
        logger.error("API shorten failed for %s: %s", original_url, e)
        return web.json_response(
            {"status": "error", "message": "Failed to create short link."},
            status=500,
        )

    return web.json_response({
        "status": "success",
        "original_url": original_url,
        "short_url": short_url,
    })


def create_app():
    app = web.Application()
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    app.router.add_get("/api", api_shorten)
    # Restrict to alphanumeric codes so this doesn't swallow other routes.
    app.router.add_get(r"/r/{code:[A-Za-z0-9]{3,16}}", resolve_handler)
    app.router.add_get(r"/{code:[A-Za-z0-9]{3,16}}", redirect_handler)
    return app


async def run_webserver():
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Webserver running on http://0.0.0.0:8080")
    return runner
