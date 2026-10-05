"""Vercel Python entrypoint: a thin WSGI router in front of lab.service.

Vercel expects a WSGI application for a Python project. This module owns exactly
three things: routing, static file delivery, and security headers. All logic
lives in lab/service.py and lab/screening.py.

This file sits at the repository root, not in api/. A Python file inside api/
makes the build ambiguous: Vercel switches to the serverless-function builder
and the WSGI app is never mounted, which silently drops the entire backend.
"""

from __future__ import annotations

import json
import os
import sys

def _find_root() -> str:
    """Walk up from this file until we find the directory holding lab/.

    The entrypoint sits at the repository root, but Vercel may relocate or wrap
    it inside the function bundle, so a fixed number of dirname() hops is not
    safe. One extra hop is cheap; a wrong _ROOT silently 404s every asset.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (here, os.path.dirname(here), os.path.dirname(os.path.dirname(here))):
        if os.path.isdir(os.path.join(candidate, "lab")):
            return candidate
    return here


_ROOT = _find_root()
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from lab import service  # noqa: E402

# Single-page site. The dashboard and demo video pages are gone; everything a
# visitor needs is on the front page. The JSON endpoints stay so any figure on
# the page can be traced back to the record that produced it.
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/results": ("evidence/results.json", "application/json"),
    "/citations": ("evidence/citations.json", "application/json"),
    "/record": ("research_record.json", "application/json"),
}

SECURITY = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=(), interest-cohort=()"),
    ("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload"),
    ("Content-Security-Policy",
     "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
     # api.github.com is the single third-party origin, used only to read the
     # public star count. The page degrades to no badge if the call fails.
     "connect-src 'self' https://api.github.com; img-src 'self' data:; media-src 'self'; "
     "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
]


def _status(code):
    return f"{code} {service.STATUS_TEXT.get(code, 'Unknown')}"


def _static(start_response, relpath, ctype):
    path = os.path.join(_ROOT, relpath)
    if not os.path.isfile(path):
        start_response(_status(404), SECURITY + [("Content-Type", "text/plain")])
        return [b"not found"]
    with open(path, "rb") as fh:
        data = fh.read()
    # Documents and stylesheets must revalidate, otherwise an edit is invisible
    # for the whole TTL and you debug a stale page. Font binaries are content
    # addressed by nothing in particular, so they get a short TTL too; this is a
    # demo, not a CDN, and correctness beats a few hundred kilobytes.
    start_response(_status(200), SECURITY + [
        ("Content-Type", ctype),
        ("Cache-Control", "no-cache"),
    ])
    return [data]


def app(environ, start_response):
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/") or "/"

    # The Vercel build emits a path-preserving catch-all rewrite to this WSGI
    # app (src "/(.*)" -> dest "/python"), so any path reaches us intact.
    # Vercel reserves /api/* for serverless functions, so the endpoint is /lab.
    _wants_lab = (
        path in ("/lab", "/lab/", "/api/lab", "/api/lab/")
        or environ.get("HTTP_X_LAB", "") == "1"
        or "route=lab" in environ.get("QUERY_STRING", "")
    )
    if _wants_lab:
        path = "/lab"
        if method == "OPTIONS":
            start_response(_status(204), SECURITY + [
                ("Access-Control-Allow-Origin", "*"),
                ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
                ("Access-Control-Allow-Headers", "content-type")])
            return [b""]
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        raw = environ["wsgi.input"].read(length) if length else b""
        request = {"method": method, "body": raw.decode("utf-8", "replace")}
        response = service.handler(request)
        body = response["body"].encode("utf-8")
        headers = SECURITY + [
            ("Content-Type", "application/json"),
            ("Cache-Control", "no-store, max-age=0"),
            ("X-Robots-Tag", "noindex"),
            ("Access-Control-Allow-Origin", "*"),
        ]
        start_response(_status(response["statusCode"]), headers)
        return [body]

    if method in ("GET", "HEAD") and path in STATIC:
        relpath, ctype = STATIC[path]
        return _static(start_response, relpath, ctype)

    if method in ("GET", "HEAD"):
        # Generic fallback: serve any real file inside the project root. Keeps
        # the demo video, the JSON evidence and the agent specs reachable without
        # enumerating every path in vercel.json.
        target = path.lstrip("/")
        if target and ".." not in target:
            full = os.path.join(_ROOT, target)
            if os.path.isfile(full):
                ext = os.path.splitext(full)[1].lower()
                kinds = {".mp4": "video/mp4", ".html": "text/html; charset=utf-8",
                         ".json": "application/json", ".png": "image/png",
                         ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                         ".css": "text/css", ".js": "text/javascript",
                         ".svg": "image/svg+xml", ".md": "text/markdown; charset=utf-8",
                         ".woff2": "font/woff2", ".woff": "font/woff",
                         ".yaml": "text/yaml; charset=utf-8",
                         ".py": "text/x-python; charset=utf-8"}
                return _static(start_response, target,
                               kinds.get(ext, "application/octet-stream"))
        if path == "/favicon.ico":
            start_response(_status(204), SECURITY)
            return [b""]

    start_response(_status(404), SECURITY + [("Content-Type", "text/plain")])
    return [b"not found"]
